"""MCP server for Claude Desktop — exposes GliceMia data as tools.

Allows deep analysis via Claude Desktop with Pro subscription.
Provides tools: get_status, get_history, get_patterns, get_metrics,
get_conditions, search_glucose, estimate_bolus.

Each server instance is bound to exactly one patient (see
`_resolve_patient_id`) — in a multi-patient database an unscoped server
would mix patients' data into dose calculations, so it refuses to start
unless the bound patient is unambiguous.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

log = logging.getLogger(__name__)


def _resolve_patient_id(session) -> int:
    """Resolve the single patient this MCP server instance is scoped to.

    Priority: MCP_PATIENT_ID env var; else the sole active UserAccount if
    there's exactly one; otherwise refuse to start.
    """
    from app.config import settings

    if settings.MCP_PATIENT_ID:
        return settings.MCP_PATIENT_ID

    from app.users import get_all_active_users

    users = get_all_active_users(session)
    if len(users) == 1:
        return users[0].telegram_user_id

    raise RuntimeError("MCP server requires MCP_PATIENT_ID when multiple patients exist")


def create_mcp_server():
    """Create and configure the MCP server with all GliceMia tools."""
    try:
        from mcp.server import Server
        from mcp.types import Tool, TextContent
    except ImportError:
        log.warning("mcp package not installed — MCP server disabled")
        return None

    from app.database import get_session

    session = get_session()
    try:
        patient_id = _resolve_patient_id(session)
    finally:
        session.close()

    server = Server("glicemia")

    @server.list_tools()
    async def list_tools():
        return [
            Tool(
                name="get_status",
                description="Get current glucose, IOB, pump status, and trend",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="get_history",
                description="Get glucose readings for a date range",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "hours": {"type": "integer", "description": "Hours of history (default 24)", "default": 24},
                    },
                },
            ),
            Tool(
                name="get_patterns",
                description="Get pre-computed glucose patterns (hourly, daily, monthly)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "period_type": {
                            "type": "string",
                            "enum": ["hourly", "daily", "monthly", "yearly"],
                            "default": "hourly",
                        },
                    },
                },
            ),
            Tool(
                name="get_metrics",
                description="Get TIR, GMI, CV, and other metrics for a date range",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "description": "Days to analyze (default 14)", "default": 14},
                    },
                },
            ),
            Tool(
                name="get_conditions",
                description="Get active medical conditions with SNOMED/ICD codes",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="get_observations",
                description="Get lab results and clinical observations",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "default": 20},
                    },
                },
            ),
            Tool(
                name="get_activities",
                description="Get recent activities with glucose impact",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "default": 30},
                    },
                },
            ),
            Tool(
                name="estimate_bolus",
                description="Estimate bolus for a given carb amount using current state",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "carbs_g": {"type": "number", "description": "Carbohydrates in grams"},
                    },
                    "required": ["carbs_g"],
                },
            ),
            Tool(
                name="predict_glucose",
                description="Predict glucose at a future time point",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "minutes_ahead": {"type": "integer", "default": 60},
                        "carbs_g": {"type": "number", "default": 0},
                        "bolus_u": {"type": "number", "default": 0},
                    },
                },
            ),
            Tool(
                name="get_hypo_episodes",
                description="Analyze hypoglycemia episodes in a date range",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "default": 14},
                    },
                },
            ),
            Tool(
                name="get_insulin_settings",
                description="Get current I:C ratios and ISF by time of day",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        from app.database import get_session
        from app.models import (
            GlucoseReading, PumpStatus, GlucosePattern,
            Condition, Observation, Activity, InsulinSetting,
        )
        from app.analytics.metrics import compute_metrics, analyze_hypo_episodes
        from app.analytics.estimator import (
            estimate_bolus as est_bolus, predict_glucose as pred_glucose,
            get_current_state,
        )

        session = get_session()
        try:
            result = _handle_tool(
                name, arguments, session, patient_id,
                GlucoseReading, PumpStatus, GlucosePattern,
                Condition, Observation, Activity, InsulinSetting,
                compute_metrics, analyze_hypo_episodes,
                est_bolus, pred_glucose, get_current_state,
            )
            return [TextContent(type="text", text=json.dumps(result, default=str, indent=2))]
        finally:
            session.close()

    return server


def _handle_tool(
    name, arguments, session, patient_id,
    GlucoseReading, PumpStatus, GlucosePattern,
    Condition, Observation, Activity, InsulinSetting,
    compute_metrics, analyze_hypo_episodes,
    est_bolus, pred_glucose, get_current_state,
):
    """Dispatch tool calls to the appropriate handler, scoped to patient_id."""
    now = datetime.utcnow()

    if name == "get_status":
        state = get_current_state(session, patient_id=patient_id)
        return state or {"error": "No data available"}

    elif name == "get_history":
        hours = arguments.get("hours", 24)
        readings = (
            session.query(GlucoseReading)
            .filter(GlucoseReading.timestamp >= now - timedelta(hours=hours))
            .filter(GlucoseReading.patient_id == patient_id)
            .order_by(GlucoseReading.timestamp.asc())
            .all()
        )
        return [
            {"timestamp": r.timestamp.isoformat(), "sg": r.sg, "trend": r.trend}
            for r in readings
        ]

    elif name == "get_patterns":
        period_type = arguments.get("period_type", "hourly")
        patterns = (
            session.query(GlucosePattern)
            .filter_by(period_type=period_type, patient_id=patient_id)
            .all()
        )
        return [
            {
                "period_key": p.period_key,
                "avg_sg": p.avg_sg, "std_sg": p.std_sg,
                "tir_pct": p.tir_pct, "hypo_count": p.hypo_count,
                "sample_count": p.sample_count,
            }
            for p in patterns
        ]

    elif name == "get_metrics":
        days = arguments.get("days", 14)
        return compute_metrics(session, now - timedelta(days=days), now, patient_id=patient_id)

    elif name == "get_conditions":
        conditions = session.query(Condition).filter(
            Condition.patient_id == patient_id,
            Condition.clinical_status.in_(["active", "recurrence"]),
        ).all()
        return [
            {
                "display_name": c.display_name, "snomed": c.snomed_code,
                "icd": c.icd_code, "severity": c.severity,
                "status": c.clinical_status,
            }
            for c in conditions
        ]

    elif name == "get_observations":
        limit = arguments.get("limit", 20)
        obs = (
            session.query(Observation)
            .filter(Observation.patient_id == patient_id)
            .order_by(Observation.effective_date.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "test": o.display_name, "value": o.value, "unit": o.unit,
                "interpretation": o.interpretation,
                "date": o.effective_date.isoformat() if o.effective_date else None,
                "loinc": o.loinc_code,
            }
            for o in obs
        ]

    elif name == "get_activities":
        days = arguments.get("days", 30)
        activities = (
            session.query(Activity)
            .filter(Activity.timestamp_start >= now - timedelta(days=days))
            .filter(Activity.patient_id == patient_id)
            .order_by(Activity.timestamp_start.desc())
            .all()
        )
        return [
            {
                "type": a.activity_type, "start": a.timestamp_start.isoformat(),
                "duration_min": a.duration_min, "distance_km": a.distance_km,
                "start_sg": a.start_sg, "end_sg": a.end_sg,
                "sg_delta": a.sg_delta, "calories": a.calories_est,
            }
            for a in activities
        ]

    elif name == "estimate_bolus":
        return est_bolus(session, carbs_g=arguments["carbs_g"], patient_id=patient_id)

    elif name == "predict_glucose":
        return pred_glucose(
            session,
            minutes_ahead=arguments.get("minutes_ahead", 60),
            carbs_g=arguments.get("carbs_g", 0),
            bolus_u=arguments.get("bolus_u", 0),
            patient_id=patient_id,
        )

    elif name == "get_hypo_episodes":
        days = arguments.get("days", 14)
        return analyze_hypo_episodes(session, now - timedelta(days=days), now, patient_id=patient_id)

    elif name == "get_insulin_settings":
        settings = (
            session.query(InsulinSetting)
            .filter_by(patient_id=patient_id)
            .order_by(InsulinSetting.time_start)
            .all()
        )
        return [
            {
                "time_start": s.time_start, "ic_ratio": s.ic_ratio,
                "isf": s.isf, "target_sg": s.target_sg, "source": s.source,
            }
            for s in settings
        ]

    return {"error": f"Unknown tool: {name}"}


def main():
    """Run the MCP server over stdio — entry point for `python -m app.mcp.server`.

    This is what Claude Desktop launches as a subprocess for the MCP
    integration. Requires the optional `mcp` package (see requirements.txt).
    """
    server = create_mcp_server()
    if server is None:
        raise SystemExit(
            "mcp package not installed — install it to run the stdio server "
            "(see requirements.txt)"
        )

    import asyncio

    async def _run():
        from mcp.server.stdio import stdio_server

        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream, write_stream, server.create_initialization_options()
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()
