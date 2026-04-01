"""Per-user memory system — AI-powered learning from conversation history.

After each conversation, the AI extracts key memories (decisions, preferences,
health insights, learned facts). These are stored encrypted in SQLCipher and
injected into future AI context for personalized, adaptive responses.

Daily consolidation merges old/redundant memories and prunes low-value ones.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import UserMemory, ChatMessage

log = logging.getLogger(__name__)

# Memory types with their descriptions (used in extraction prompt)
MEMORY_TYPES = {
    "decision": "Therapeutic or management decisions (insulin adjustments, diet changes, pump settings)",
    "action": "Actions taken by the user or bot (data imports, setting changes, reports generated)",
    "preference": "User preferences and communication style (language, units, voice replies, response style)",
    "health_insight": "Learned health patterns (glucose responses to foods/activities, time-of-day patterns)",
    "learned_fact": "Facts about the user's life (work schedule, exercise habits, travel plans, family context)",
}

# Extraction prompt — asks the AI to identify memories from a conversation
_EXTRACTION_PROMPT = """You are a memory extraction system for a diabetes management bot.
Analyze the conversation below and extract important facts worth remembering for future conversations.

For each memory, return a JSON array of objects with these fields:
- "type": one of: decision, action, preference, health_insight, learned_fact
- "content": the memory itself (1-2 sentences, specific and factual)
- "importance": 1-10 score (10 = critical health decision, 1 = minor detail)

Types explained:
- decision: Therapeutic decisions (e.g. "Changed I:C ratio to 1:8 at lunch")
- action: Actions taken (e.g. "Imported 3 months of CareLink data")
- preference: User preferences (e.g. "Prefers responses in Italian, uses mg/dL")
- health_insight: Health patterns (e.g. "Tends to go low after cycling >1h")
- learned_fact: Life facts (e.g. "Works night shifts on Tuesdays")

Rules:
- Only extract NEW, non-obvious information worth remembering
- Skip greetings, small talk, and repeated information
- Be specific — include numbers, dates, times when available
- Maximum 5 memories per conversation
- If nothing worth remembering, return an empty array: []

Return ONLY valid JSON, no other text.

CONVERSATION:
{conversation}"""

# Consolidation prompt — merges related memories
_CONSOLIDATION_PROMPT = """You are a memory consolidation system. Review these memories for a diabetes patient
and produce a consolidated set that:
1. Merges redundant/overlapping memories into single, richer entries
2. Updates outdated information (keep the latest version)
3. Removes memories that are no longer relevant
4. Preserves all important health insights and decisions

Current memories:
{memories}

Return a JSON array of consolidated memories, each with:
- "id": original memory ID to keep (null for new merged memories)
- "type": memory type
- "content": consolidated content
- "importance": updated importance score (1-10)
- "remove_ids": list of original memory IDs that this entry replaces

Return ONLY valid JSON, no other text."""


async def extract_memories(
    session: Session,
    patient_id: int,
    user_message: str,
    assistant_response: str,
    user=None,
) -> list[UserMemory]:
    """Extract memories from a conversation turn using the AI.

    Called after each AI chat response. Uses a lightweight AI call to identify
    facts worth remembering. Stores them in the user_memories table.

    Returns the list of newly created UserMemory objects.
    """
    from app.ai.llm import chat as ai_chat

    conversation = f"User: {user_message}\nAssistant: {assistant_response}"
    prompt = _EXTRACTION_PROMPT.format(conversation=conversation)

    try:
        # Use a fast, cheap model for extraction (not the medical model)
        extraction_response = await ai_chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1024,
            user=None,  # Use server default, don't track tokens to user
        )

        memories_data = _parse_json_response(extraction_response)
        if not memories_data:
            return []

        created = []
        for mem in memories_data[:5]:  # Cap at 5 per conversation
            mem_type = mem.get("type", "")
            if mem_type not in MEMORY_TYPES:
                continue

            content = mem.get("content", "").strip()
            if not content or len(content) < 5:
                continue

            importance = min(max(int(mem.get("importance", 5)), 1), 10)

            # Check for near-duplicate before inserting
            if _is_duplicate(session, patient_id, content):
                continue

            memory = UserMemory(
                patient_id=patient_id,
                memory_type=mem_type,
                content=content,
                importance=importance,
                source_summary=user_message[:200],
            )
            session.add(memory)
            created.append(memory)

        if created:
            session.commit()
            log.info(
                "Extracted %d memories for user %d: %s",
                len(created), patient_id,
                ", ".join(f"{m.memory_type}({m.importance})" for m in created),
            )

        return created

    except Exception as e:
        log.warning("Memory extraction failed for user %d: %s", patient_id, e)
        return []


def get_relevant_memories(
    session: Session,
    patient_id: int,
    query: Optional[str] = None,
    limit: int = 15,
) -> list[UserMemory]:
    """Retrieve the most relevant active memories for a user.

    Scoring: importance * recency_weight * access_bonus.
    Returns up to `limit` memories, ordered by relevance.
    """
    q = (
        session.query(UserMemory)
        .filter_by(patient_id=patient_id, is_active=True)
        .order_by(
            UserMemory.importance.desc(),
            UserMemory.last_accessed.desc(),
        )
    )

    memories = q.limit(limit * 2).all()  # Fetch extra, then score

    if not memories:
        return []

    now = datetime.utcnow()
    scored = []
    for mem in memories:
        age_days = max((now - mem.created_at).days, 1)
        recency = 1.0 / (1.0 + age_days / 30.0)  # Decay over ~30 days
        access_bonus = min(mem.access_count * 0.1, 1.0)  # Cap at +1.0
        score = mem.importance * (0.6 + 0.3 * recency + 0.1 * access_bonus)

        # Keyword boost if query provided
        if query:
            query_lower = query.lower()
            content_lower = mem.content.lower()
            keyword_hits = sum(1 for word in query_lower.split() if word in content_lower)
            score += keyword_hits * 2

        scored.append((score, mem))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Update last_accessed for returned memories
    result = []
    for _, mem in scored[:limit]:
        mem.last_accessed = now
        mem.access_count += 1
        result.append(mem)

    session.commit()
    return result


def get_all_user_memories(
    session: Session,
    patient_id: int,
    memory_type: Optional[str] = None,
) -> list[UserMemory]:
    """Get all active memories for a user, optionally filtered by type."""
    q = session.query(UserMemory).filter_by(patient_id=patient_id, is_active=True)
    if memory_type and memory_type in MEMORY_TYPES:
        q = q.filter_by(memory_type=memory_type)
    return q.order_by(UserMemory.importance.desc(), UserMemory.created_at.desc()).all()


def forget_memory(session: Session, patient_id: int, memory_id: int) -> bool:
    """Deactivate a specific memory. Returns True if found and deactivated."""
    mem = (
        session.query(UserMemory)
        .filter_by(id=memory_id, patient_id=patient_id, is_active=True)
        .first()
    )
    if not mem:
        return False
    mem.is_active = False
    session.commit()
    log.info("Memory %d deactivated for user %d", memory_id, patient_id)
    return True


def forget_all_memories(session: Session, patient_id: int) -> int:
    """Deactivate all memories for a user. Returns count of deactivated memories."""
    count = (
        session.query(UserMemory)
        .filter_by(patient_id=patient_id, is_active=True)
        .update({"is_active": False})
    )
    session.commit()
    log.info("All %d memories deactivated for user %d", count, patient_id)
    return count


async def consolidate_memories(session: Session, patient_id: int) -> dict:
    """Daily consolidation — merge redundant memories, prune low-value ones.

    Strategy:
    1. Remove memories with importance <= 2 that are older than 7 days
    2. For each memory type, if >20 active memories, ask AI to consolidate
    3. Track statistics for logging

    Returns dict with stats: {"pruned": N, "consolidated": N, "remaining": N}
    """
    stats = {"pruned": 0, "consolidated": 0, "remaining": 0}

    # Step 1: Prune old, low-importance memories
    cutoff = datetime.utcnow() - timedelta(days=7)
    pruned = (
        session.query(UserMemory)
        .filter(
            UserMemory.patient_id == patient_id,
            UserMemory.is_active.is_(True),
            UserMemory.importance <= 2,
            UserMemory.created_at < cutoff,
            UserMemory.access_count == 0,  # Never used in context
        )
        .update({"is_active": False})
    )
    stats["pruned"] = pruned

    # Step 2: AI-powered consolidation for types with many memories
    for mem_type in MEMORY_TYPES:
        active = (
            session.query(UserMemory)
            .filter_by(patient_id=patient_id, memory_type=mem_type, is_active=True)
            .order_by(UserMemory.created_at.desc())
            .all()
        )

        if len(active) <= 20:
            continue

        # Ask AI to consolidate
        try:
            consolidated = await _ai_consolidate(session, active, mem_type)
            stats["consolidated"] += consolidated
        except Exception as e:
            log.warning("AI consolidation failed for user %d type %s: %s",
                        patient_id, mem_type, e)

    # Count remaining
    stats["remaining"] = (
        session.query(func.count(UserMemory.id))
        .filter_by(patient_id=patient_id, is_active=True)
        .scalar()
    )

    session.commit()

    if stats["pruned"] > 0 or stats["consolidated"] > 0:
        log.info(
            "Memory consolidation for user %d: pruned=%d, consolidated=%d, remaining=%d",
            patient_id, stats["pruned"], stats["consolidated"], stats["remaining"],
        )

    return stats


def build_memory_context(session: Session, patient_id: int, query: Optional[str] = None) -> str:
    """Build context string from user memories for AI prompt injection.

    Returns a formatted string suitable for the 13th context layer.
    """
    memories = get_relevant_memories(session, patient_id, query=query, limit=15)
    if not memories:
        return ""

    grouped: dict[str, list[str]] = {}
    for mem in memories:
        label = mem.memory_type.upper().replace("_", " ")
        grouped.setdefault(label, []).append(mem.content)

    lines = ["PATIENT MEMORY (learned from previous conversations):"]
    for label, items in grouped.items():
        lines.append(f"  [{label}]")
        for item in items:
            lines.append(f"    - {item}")

    return "\n".join(lines)


# --- Internal helpers ---

def _is_duplicate(session: Session, patient_id: int, content: str) -> bool:
    """Check if a very similar memory already exists (simple substring match)."""
    content_lower = content.lower().strip()
    # Check exact or near-exact matches
    existing = (
        session.query(UserMemory)
        .filter_by(patient_id=patient_id, is_active=True)
        .all()
    )
    for mem in existing:
        existing_lower = mem.content.lower().strip()
        # If >80% of words overlap, consider it a duplicate
        new_words = set(content_lower.split())
        existing_words = set(existing_lower.split())
        if not new_words:
            return True
        overlap = len(new_words & existing_words) / len(new_words)
        if overlap > 0.8:
            return True
    return False


def _parse_json_response(text: str) -> list[dict]:
    """Parse JSON from an AI response, handling markdown code blocks."""
    text = text.strip()
    # Strip markdown code fence if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first and last lines (```json and ```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        return []
    except (json.JSONDecodeError, TypeError):
        # Try to find JSON array in the text
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except (json.JSONDecodeError, TypeError):
                pass
        return []


async def _ai_consolidate(session: Session, memories: list[UserMemory], mem_type: str) -> int:
    """Use AI to consolidate a list of memories. Returns count of consolidated."""
    from app.ai.llm import chat as ai_chat

    mem_text = "\n".join(
        f"[ID={m.id}] ({m.created_at.strftime('%Y-%m-%d')}, importance={m.importance}) {m.content}"
        for m in memories
    )

    prompt = _CONSOLIDATION_PROMPT.format(memories=mem_text)

    response = await ai_chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=2048,
        user=None,
    )

    consolidated_data = _parse_json_response(response)
    if not consolidated_data:
        return 0

    consolidated_count = 0
    for entry in consolidated_data:
        remove_ids = entry.get("remove_ids", [])
        if not remove_ids:
            continue

        # Deactivate old memories
        for old_id in remove_ids:
            old_mem = session.query(UserMemory).filter_by(
                id=old_id, patient_id=memories[0].patient_id, is_active=True
            ).first()
            if old_mem:
                old_mem.is_active = False
                consolidated_count += 1

        # Create new consolidated memory if content provided
        content = entry.get("content", "").strip()
        if content:
            keep_id = entry.get("id")
            if keep_id:
                # Update existing memory
                existing = session.query(UserMemory).filter_by(id=keep_id).first()
                if existing:
                    existing.content = content
                    existing.importance = min(max(int(entry.get("importance", existing.importance)), 1), 10)
            else:
                # Create new merged memory
                new_mem = UserMemory(
                    patient_id=memories[0].patient_id,
                    memory_type=entry.get("type", mem_type),
                    content=content,
                    importance=min(max(int(entry.get("importance", 5)), 1), 10),
                    source_summary="Consolidated from multiple memories",
                )
                session.add(new_mem)

    session.commit()
    return consolidated_count
