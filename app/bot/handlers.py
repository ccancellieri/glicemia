"""Telegram bot handlers — multi-patient, per-user auth from DB."""

import base64
import json
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from app.config import settings
from app.database import get_session
from app.models import (
    GlucoseReading, PumpStatus, LiabilityWaiver,
    ChatMessage, PatientProfile, UserAccount, GDPRConsent,
)
from app.users import get_user
from app.ai.llm import chat as ai_chat
from app.ai.system_prompt import build_system_prompt
from app.ai.context import build_context
from app.bot.menus import (
    main_menu, activity_menu, report_menu,
    settings_menu, language_menu, waiver_menu,
)
from app.bot.formatters import format_status, format_csv_import_result
from app.i18n.messages import msg
from app.carelink.csv_import import import_carelink_csv_bytes

log = logging.getLogger(__name__)


async def _extract_memories_safe(patient_id: int, user_text: str, response: str):
    """Background task: extract memories from a conversation turn.
    Runs in its own session so it doesn't block the handler."""
    try:
        from app.memory import extract_memories
        s = get_session()
        try:
            await extract_memories(s, patient_id, user_text, response)
        finally:
            s.close()
    except Exception as e:
        log.debug("Background memory extraction failed: %s", e)


# --- Per-user helpers ---

def _get_user_from_update(update: Update, session) -> UserAccount | None:
    """Look up the calling user in DB. Returns None if not registered/active."""
    return get_user(session, update.effective_user.id)


def _lang(user: UserAccount) -> str:
    return user.language or "it"


def _name(user: UserAccount) -> str:
    return user.patient_name


def _pid(user: UserAccount) -> int:
    return user.telegram_user_id


async def _require_user(update: Update, session) -> UserAccount | None:
    """Get user from DB; if not found, reply with a rejection and return None."""
    user = _get_user_from_update(update, session)
    if not user:
        await update.message.reply_text(
            "You are not registered. Ask an admin to add you, or use /setup if enabled."
        )
    return user


# --- Settings Commands ---

async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /settings — show user's current settings with edit options."""
    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        lang = _lang(user)
        from app.users import get_user_settings as _get_settings, check_token_limit

        extra = _get_settings(user)
        _allowed, _reason = check_token_limit(user)
        daily_lim = user.daily_token_limit or "unlimited"
        monthly_lim = user.monthly_token_limit or "unlimited"

        lines = []
        if lang == "it":
            lines.append(f"*Impostazioni di {_name(user)}*\n")
            lines.append(f"Lingua: `{user.language or 'it'}`")
            lines.append(f"Modello AI: `{user.ai_model or 'default server'}`")
            lines.append(f"CareLink: {'configurato' if user.carelink_username else 'non configurato'}")
            lines.append(f"Gemini API: {'configurata' if user.gemini_api_key else 'chiave server'}")
            lines.append(f"OpenWeather API: {'configurata' if user.openweather_api_key else 'chiave server'}")
            lines.append(f"\nToken oggi: {user.tokens_used_today or 0} / {daily_lim}")
            lines.append(f"Token mese: {user.tokens_used_month or 0} / {monthly_lim}")
            lines.append("\nUsa i pulsanti per modificare o apri la WebApp per tutte le impostazioni.")
        else:
            lines.append(f"*Settings for {_name(user)}*\n")
            lines.append(f"Language: `{user.language or 'it'}`")
            lines.append(f"AI Model: `{user.ai_model or 'default server'}`")
            lines.append(f"CareLink: {'configured' if user.carelink_username else 'not configured'}")
            lines.append(f"Gemini API: {'configured' if user.gemini_api_key else 'server key'}")
            lines.append(f"OpenWeather API: {'configured' if user.openweather_api_key else 'server key'}")
            lines.append(f"\nTokens today: {user.tokens_used_today or 0} / {daily_lim}")
            lines.append(f"Tokens month: {user.tokens_used_month or 0} / {monthly_lim}")
            lines.append("\nUse buttons to edit or open the WebApp for all settings.")

        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        buttons = [
            [InlineKeyboardButton(
                "Nome" if lang == "it" else "Name",
                callback_data="settings_name",
            ),
            InlineKeyboardButton(
                "Lingua" if lang == "it" else "Language",
                callback_data="set_language",
            )],
            [InlineKeyboardButton(
                "CareLink",
                callback_data="settings_carelink",
            ),
            InlineKeyboardButton(
                "Modello AI" if lang == "it" else "AI Model",
                callback_data="settings_ai_model",
            )],
            [InlineKeyboardButton(
                "API Keys",
                callback_data="settings_apikeys",
            )],
        ]
        # Add WebApp button if URL is configured
        if settings.WEBAPP_URL:
            buttons.append([InlineKeyboardButton(
                "Apri WebApp" if lang == "it" else "Open WebApp",
                web_app={"url": f"{settings.WEBAPP_URL.rstrip('/')}#settings"},
            )])
        buttons.append([InlineKeyboardButton(
            "Menu",
            callback_data="main_menu",
        )])

        await update.message.reply_text(
            "\n".join(lines),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    finally:
        session.close()


async def cmd_carelink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /carelink <username> <password> <country> — set CareLink credentials."""
    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        lang = _lang(user)
        args = context.args or []
        if len(args) < 3:
            if lang == "it":
                await update.message.reply_text(
                    "Uso: /carelink <username> <password> <paese>\n"
                    "Esempio: /carelink user@email.com MyPassword IT\n\n"
                    "Le credenziali vengono criptate e salvate in modo sicuro."
                )
            else:
                await update.message.reply_text(
                    "Usage: /carelink <username> <password> <country>\n"
                    "Example: /carelink user@email.com MyPassword IT\n\n"
                    "Credentials are encrypted and stored securely."
                )
            return

        user.carelink_username = args[0]
        user.carelink_password = args[1]
        user.carelink_country = args[2].upper()[:5]
        session.commit()

        # Delete the user's message containing credentials for security
        try:
            await update.message.delete()
        except Exception:
            pass

        if lang == "it":
            await update.effective_chat.send_message(
                "CareLink configurato! Le credenziali sono state criptate.\n"
                "Il messaggio con le credenziali e' stato eliminato per sicurezza."
            )
        else:
            await update.effective_chat.send_message(
                "CareLink configured! Credentials have been encrypted.\n"
                "The message with credentials was deleted for security."
            )
    finally:
        session.close()


async def cmd_apikey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /apikey <service> <key> — set per-user API keys."""
    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        lang = _lang(user)
        args = context.args or []
        if len(args) < 2:
            if lang == "it":
                await update.message.reply_text(
                    "Uso: /apikey <servizio> <chiave>\n"
                    "Servizi: gemini, groq, openrouter, openweather\n"
                    "Esempio: /apikey groq gsk_...\n\n"
                    "Usa /apikey <servizio> clear per rimuovere.\n\n"
                    "Le chiavi sono criptate nel database e il messaggio "
                    "viene eliminato automaticamente."
                )
            else:
                await update.message.reply_text(
                    "Usage: /apikey <service> <key>\n"
                    "Services: gemini, groq, openrouter, openweather\n"
                    "Example: /apikey groq gsk_...\n\n"
                    "Use /apikey <service> clear to remove.\n\n"
                    "Keys are encrypted in the database and your message "
                    "is automatically deleted."
                )
            return

        service = args[0].lower()
        key_value = args[1]

        if service == "gemini":
            user.gemini_api_key = None if key_value == "clear" else key_value
        elif service == "groq":
            user.groq_api_key = None if key_value == "clear" else key_value
        elif service == "openrouter":
            user.openrouter_api_key = None if key_value == "clear" else key_value
        elif service == "openweather":
            user.openweather_api_key = None if key_value == "clear" else key_value
        else:
            await update.message.reply_text(
                f"Unknown service: {service}. Use: gemini, groq, openrouter, openweather"
            )
            return

        session.commit()

        # Delete the message containing the key
        try:
            await update.message.delete()
        except Exception:
            pass

        action = "removed" if key_value == "clear" else "set"
        action_it = "rimossa" if key_value == "clear" else "configurata"
        if lang == "it":
            await update.effective_chat.send_message(
                f"API key {service} {action_it}! Il messaggio e' stato eliminato per sicurezza."
            )
        else:
            await update.effective_chat.send_message(
                f"API key {service} {action}! Message deleted for security."
            )
    finally:
        session.close()


async def cmd_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /model <model_name> — set preferred AI model."""
    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        lang = _lang(user)
        args = context.args or []
        if not args:
            current = user.ai_model or "server default"
            if lang == "it":
                await update.message.reply_text(
                    f"Modello attuale: `{current}`\n\n"
                    "Uso: /model <nome_modello>\n"
                    "Esempio: /model ollama/qwen2.5:14b-instruct-q4_K_M\n"
                    "Usa /model default per il modello del server.",
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text(
                    f"Current model: `{current}`\n\n"
                    "Usage: /model <model_name>\n"
                    "Example: /model ollama/qwen2.5:14b-instruct-q4_K_M\n"
                    "Use /model default for server default.",
                    parse_mode="Markdown",
                )
            return

        model = args[0]
        if model == "default":
            user.ai_model = None
        else:
            from app.users import is_model_allowed
            if not is_model_allowed(user, model):
                await update.message.reply_text(
                    "Model not in your allowed list." if lang != "it"
                    else "Modello non nella tua lista consentiti."
                )
                return
            user.ai_model = model

        session.commit()
        new_val = user.ai_model or "server default"
        await update.message.reply_text(
            f"AI model: `{new_val}`" if lang != "it"
            else f"Modello AI: `{new_val}`",
            parse_mode="Markdown",
        )
    finally:
        session.close()


# --- Admin & Setup Commands ---

async def cmd_setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setup — self-registration for new users (if allowed by admin).
    For now, only existing admins can add users via /adduser."""
    session = get_session()
    try:
        existing = get_user(session, update.effective_user.id)
        if existing:
            await update.message.reply_text(
                f"You are already registered as {existing.patient_name}."
            )
            return

        await update.message.reply_text(
            "Registration requires admin approval. "
            "Ask an admin to run: /adduser <your_telegram_id> <your_name>"
        )
    finally:
        session.close()


async def cmd_adduser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /adduser <telegram_id> <name> [lang] — admin-only command to add users."""
    session = get_session()
    try:
        admin = _get_user_from_update(update, session)
        if not admin or not admin.is_admin:
            await update.message.reply_text("Only admins can add users.")
            return

        args = context.args or []
        if len(args) < 2:
            await update.message.reply_text(
                "Usage: /adduser <telegram_id> <name> [language]\n"
                "Example: /adduser 123456789 Marco it"
            )
            return

        try:
            tg_id = int(args[0])
        except ValueError:
            await update.message.reply_text("telegram_id must be a number.")
            return

        name = args[1]
        lang = args[2] if len(args) > 2 else "it"

        if session.get(UserAccount, tg_id):
            await update.message.reply_text(f"User {tg_id} already exists.")
            return

        from app.users import create_user
        create_user(session, telegram_user_id=tg_id, patient_name=name, language=lang)
        await update.message.reply_text(
            f"User added: {name} (ID: {tg_id}, lang: {lang})"
        )
    finally:
        session.close()


async def cmd_setlimit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setlimit <telegram_id> <daily> <monthly> — admin-only token limit."""
    session = get_session()
    try:
        admin = _get_user_from_update(update, session)
        if not admin or not admin.is_admin:
            await update.message.reply_text("Only admins can set limits.")
            return

        args = context.args or []
        if len(args) < 3:
            await update.message.reply_text(
                "Usage: /setlimit <telegram_id> <daily_tokens> <monthly_tokens>\n"
                "Use 0 for unlimited. Example: /setlimit 123456789 50000 1000000"
            )
            return

        try:
            tg_id = int(args[0])
            daily = int(args[1])
            monthly = int(args[2])
        except ValueError:
            await update.message.reply_text("All arguments must be numbers.")
            return

        target = session.get(UserAccount, tg_id)
        if not target:
            await update.message.reply_text(f"User {tg_id} not found.")
            return

        target.daily_token_limit = daily
        target.monthly_token_limit = monthly
        session.commit()
        await update.message.reply_text(
            f"Limits set for {target.patient_name}: "
            f"daily={daily}, monthly={monthly} (0=unlimited)"
        )
    finally:
        session.close()


async def cmd_usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /usage — show token usage for the calling user."""
    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        from app.users import check_token_limit
        _allowed, _reason = check_token_limit(user)

        daily_lim = user.daily_token_limit or "unlimited"
        monthly_lim = user.monthly_token_limit or "unlimited"
        await update.message.reply_text(
            f"Token usage for {user.patient_name}:\n"
            f"Today: {user.tokens_used_today} / {daily_lim}\n"
            f"This month: {user.tokens_used_month} / {monthly_lim}"
        )
    finally:
        session.close()


# --- Memory Commands ---

async def cmd_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /memory — show what the bot has learned about this user."""
    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        lang = _lang(user)
        name = _name(user)
        pid = _pid(user)

        from app.memory import get_all_user_memories, MEMORY_TYPES

        # Optional filter: /memory decision, /memory preference, etc.
        type_filter = None
        if context.args:
            arg = context.args[0].lower()
            if arg in MEMORY_TYPES:
                type_filter = arg

        memories = get_all_user_memories(session, pid, memory_type=type_filter)

        if not memories:
            await update.message.reply_text(msg("memory_empty", lang, name=name))
            return

        text = msg("memory_title", lang, name=name)

        # Group by type
        type_labels = {
            "decision": msg("memory_type_decision", lang),
            "action": msg("memory_type_action", lang),
            "preference": msg("memory_type_preference", lang),
            "health_insight": msg("memory_type_health_insight", lang),
            "learned_fact": msg("memory_type_learned_fact", lang),
        }

        grouped: dict[str, list] = {}
        for mem in memories:
            grouped.setdefault(mem.memory_type, []).append(mem)

        for mem_type, label in type_labels.items():
            mems = grouped.get(mem_type, [])
            if not mems:
                continue
            text += f"*{label}*\n"
            for m in mems[:10]:
                stars = "★" * min(m.importance, 5) + "☆" * max(0, 5 - m.importance)
                text += f"  `#{m.id}` {stars} {m.content}\n"
            text += "\n"

        text += msg("memory_count", lang, count=len(memories))
        await update.message.reply_text(text, parse_mode="Markdown")

    finally:
        session.close()


async def cmd_forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /forget <id> or /forget all — remove memories."""
    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        lang = _lang(user)
        pid = _pid(user)

        if not context.args:
            await update.message.reply_text(msg("forget_usage", lang), parse_mode="Markdown")
            return

        arg = context.args[0].lower()

        if arg == "all":
            from app.memory import forget_all_memories
            count = forget_all_memories(session, pid)
            await update.message.reply_text(msg("forget_all_success", lang, count=count))
            return

        try:
            memory_id = int(arg)
        except ValueError:
            await update.message.reply_text(msg("forget_usage", lang), parse_mode="Markdown")
            return

        from app.memory import forget_memory
        if forget_memory(session, pid, memory_id):
            await update.message.reply_text(msg("forget_success", lang, id=memory_id))
        else:
            await update.message.reply_text(msg("forget_not_found", lang, id=memory_id))

    finally:
        session.close()


# --- Main Commands ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start — show waiver if not accepted, else welcome."""
    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        lang = _lang(user)
        waiver = session.query(LiabilityWaiver).filter_by(
            telegram_user_id=_pid(user)
        ).first()

        if waiver:
            await update.message.reply_text(
                msg("welcome", lang, name=_name(user)),
                reply_markup=main_menu(lang),
            )
        else:
            await update.message.reply_text(
                f"*{msg('waiver_title', lang)}*\n\n{msg('waiver_text', lang)}",
                reply_markup=waiver_menu(lang),
                parse_mode="Markdown",
            )
    finally:
        session.close()


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /menu — show main menu."""
    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return
        lang = _lang(user)
        await update.message.reply_text(
            msg("menu_title", lang),
            reply_markup=main_menu(lang),
        )
    finally:
        session.close()


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stato — show current CGM/pump status."""
    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        lang = _lang(user)
        pid = _pid(user)
        reading = (
            session.query(GlucoseReading)
            .filter_by(patient_id=pid)
            .order_by(GlucoseReading.timestamp.desc())
            .first()
        )
        pump = (
            session.query(PumpStatus)
            .filter_by(patient_id=pid)
            .order_by(PumpStatus.timestamp.desc())
            .first()
        )

        if not reading:
            await update.message.reply_text(
                msg("no_data", lang, name=_name(user))
            )
            return

        text = format_status(
            sg=reading.sg,
            trend=reading.trend or "FLAT",
            iob=pump.active_insulin if pump else None,
            basal_rate=pump.basal_rate if pump else None,
            auto_mode=pump.auto_mode if pump else None,
            reservoir=pump.reservoir_units if pump else None,
            battery=pump.battery_pct if pump else None,
            patient_name=_name(user),
            lang=lang,
        )
        await update.message.reply_text(text, parse_mode="Markdown")
    finally:
        session.close()


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help."""
    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return
        lang = _lang(user)
        await update.message.reply_text(
            msg("help_text", lang),
            parse_mode="Markdown",
        )
    finally:
        session.close()


async def cmd_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /privacy — GDPR data subject rights.

    Subcommands: info, consent, export, delete
    """
    from app.privacy import (
        PRIVACY_NOTICE, CONSENT_PURPOSES,
        get_consent_status, record_consent,
        export_user_data, delete_user_data,
    )
    import io

    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        lang = _lang(user)
        args = context.args
        subcmd = args[0].lower() if args else "info"

        if subcmd == "info":
            notice = PRIVACY_NOTICE.get(lang, PRIVACY_NOTICE["en"])
            await update.message.reply_text(notice)

        elif subcmd == "consent":
            # Show current consent status with inline buttons
            status = get_consent_status(session, _pid(user))
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            buttons = []
            for purpose, desc in CONSENT_PURPOSES.items():
                current = status.get(purpose, False)
                label = f"{'[ON]' if current else '[OFF]'} {purpose}"
                buttons.append([InlineKeyboardButton(
                    label, callback_data=f"gdpr_toggle_{purpose}"
                )])
            buttons.append([InlineKeyboardButton(
                "Grant all" if lang != "it" else "Accetta tutti",
                callback_data="gdpr_grant_all"
            )])
            buttons.append([InlineKeyboardButton(
                "Withdraw all" if lang != "it" else "Revoca tutti",
                callback_data="gdpr_withdraw_all"
            )])

            text = (
                "Your GDPR consents:\n\n" if lang != "it"
                else "I tuoi consensi GDPR:\n\n"
            )
            for purpose, desc in CONSENT_PURPOSES.items():
                on = status.get(purpose, False)
                text += f"{'[ON]' if on else '[OFF]'} {purpose}\n  {desc}\n\n"

            await update.message.reply_text(
                text, reply_markup=InlineKeyboardMarkup(buttons)
            )

        elif subcmd == "export":
            await update.message.reply_text(
                "Exporting your data..." if lang != "it"
                else "Esportazione dati in corso..."
            )
            data = export_user_data(session, _pid(user))
            json_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
            buf = io.BytesIO(json_bytes)
            buf.name = f"glicemia_data_{_pid(user)}.json"
            await update.message.reply_document(
                document=buf,
                caption=(
                    "Your complete data export (GDPR Art. 15/20)."
                    if lang != "it"
                    else "Export completo dei tuoi dati (GDPR Art. 15/20)."
                ),
            )

        elif subcmd == "delete":
            # Require confirmation
            if len(args) < 2 or args[1].upper() != "CONFIRM":
                await update.message.reply_text(
                    "This will permanently delete ALL your health data.\n"
                    "Type `/privacy delete CONFIRM` to proceed.\n\n"
                    "Consent audit trail will be retained (legal obligation)."
                    if lang != "it"
                    else "Questo cancellera TUTTI i tuoi dati sanitari.\n"
                    "Scrivi `/privacy delete CONFIRM` per procedere.\n\n"
                    "La cronologia dei consensi sara conservata (obbligo legale).",
                    parse_mode="Markdown",
                )
                return

            result = delete_user_data(session, _pid(user))
            summary = "\n".join(f"  {k}: {v}" for k, v in result.items())
            await update.message.reply_text(
                f"Data deleted (GDPR Art. 17):\n{summary}\n\n"
                "Your account has been deactivated."
                if lang != "it"
                else f"Dati cancellati (GDPR Art. 17):\n{summary}\n\n"
                "Il tuo account e stato disattivato."
            )

        else:
            await update.message.reply_text(
                "Usage: /privacy [info|consent|export|delete]"
            )
    finally:
        session.close()


async def cmd_sg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /sg — manual glucose entry.

    Usage:
        /sg 145         — enter SG 145 mg/dL (goes to trend selection)
        /sg 145 UP      — enter SG 145 with rising trend (confirm & save)
        /sg              — show range picker buttons
    """
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from app.bot.menus import glucose_range_menu, glucose_trend_menu

    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        lang = _lang(user)
        pid = _pid(user)
        args = context.args or []

        if not args:
            # Show step-by-step range picker
            await update.message.reply_text(
                msg("sg_pick_range", lang),
                reply_markup=glucose_range_menu(lang),
            )
            return

        # Parse value
        try:
            sg_value = int(float(args[0]))
        except ValueError:
            await update.message.reply_text(msg("sg_invalid", lang))
            return

        if len(args) > 1:
            # Trend provided — confirm & save directly
            trend = args[1].upper()
            valid_trends = ["UP", "UP_FAST", "UP_RAPID", "DOWN", "DOWN_FAST", "DOWN_RAPID", "FLAT"]
            if trend not in valid_trends:
                trend = "FLAT"

            keyboard = [
                [InlineKeyboardButton(
                    msg("sg_confirm", lang),
                    callback_data=f"sg_confirm:{sg_value}:{trend}:0:manual:{pid}"
                )],
                [InlineKeyboardButton(msg("sg_cancel", lang), callback_data="sg_cancel")],
            ]
            await update.message.reply_text(
                msg("sg_confirm_prompt", lang, value=sg_value, trend=trend),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="Markdown",
            )
        else:
            # No trend — show trend picker
            await update.message.reply_text(
                msg("sg_pick_trend", lang, value=sg_value),
                reply_markup=glucose_trend_menu(sg_value, lang),
            )

    finally:
        session.close()


async def cmd_whatif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /whatif — scenario simulation with trajectory prediction.

    Examples:
        /whatif 80g pasta
        /whatif cycling 60min
        /whatif 50g carbs + 3U bolus
        /whatif skip next bolus
    """
    import re
    from app.analytics.estimator import predict_trajectory, estimate_activity_impact

    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        lang = _lang(user)
        pid = _pid(user)
        raw = " ".join(context.args) if context.args else ""
        if not raw.strip():
            await update.message.reply_text(
                msg("whatif_usage", lang)
            )
            return

        # Parse structured patterns
        carbs_g = 0.0
        bolus_u = 0.0
        activity_type = None
        activity_min = 0

        # Match carbs: "80g", "80g carbs", "80g pasta"
        carb_match = re.search(r'(\d+(?:\.\d+)?)\s*g(?:\s|$)', raw, re.IGNORECASE)
        if carb_match:
            carbs_g = float(carb_match.group(1))

        # Match bolus: "3U", "3.5U bolus"
        bolus_match = re.search(r'(\d+(?:\.\d+)?)\s*[uU](?:\s|$)', raw)
        if bolus_match:
            bolus_u = float(bolus_match.group(1))

        # Match activity: "cycling 60min", "walking 30min"
        activity_match = re.search(
            r'(cycling|walking|running|gym|swimming|hiking)\s+(\d+)\s*min',
            raw, re.IGNORECASE
        )
        if activity_match:
            activity_type = activity_match.group(1).lower()
            activity_min = int(activity_match.group(2))

        if activity_type:
            # Activity scenario
            impact = estimate_activity_impact(
                session, activity_type, activity_min, intensity="moderate"
            )
            if "error" in impact:
                await update.message.reply_text(msg("no_data", lang, name=_name(user)))
                return

            lines = [
                f"*What if: {activity_type} {activity_min}min*",
                f"(current SG {impact['current_sg']}, IOB {impact['iob_current']}U)\n",
                f"Estimated drop: ~{impact['estimated_drop']} mg/dL",
                f"Predicted SG after: ~{impact['predicted_sg_end']} mg/dL",
                f"Range: {impact['predicted_range']}",
                f"Risk: {impact['risk_level']}",
            ]
            if impact['carbs_recommended_g'] > 0:
                lines.append(f"Suggested carbs before: {impact['carbs_recommended_g']}g")

            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        elif carbs_g > 0 or bolus_u > 0:
            # Meal/bolus scenario
            trajectory = predict_trajectory(
                session, carbs_g=carbs_g, bolus_u=bolus_u, horizons=(15, 30, 60, 90, 120)
            )
            if not trajectory or "error" in trajectory[0]:
                await update.message.reply_text(msg("no_data", lang, name=_name(user)))
                return

            current_sg = trajectory[0].get("current_sg", "?")
            iob = trajectory[0].get("iob_current", 0)

            scenario_parts = []
            if carbs_g > 0:
                scenario_parts.append(f"{carbs_g:.0f}g carbs")
            if bolus_u > 0:
                scenario_parts.append(f"{bolus_u:.1f}U bolus")
            scenario_desc = " + ".join(scenario_parts)

            lines = [
                f"*What if: {scenario_desc}*",
                f"(current SG {current_sg}, IOB {iob}U)\n",
            ]
            for p in trajectory:
                t = p["minutes_ahead"]
                sg = p["predicted_sg"]
                lo, hi = p["range_low"], p["range_high"]
                flag = ""
                if sg < 70:
                    flag = " ⚠️ HYPO"
                elif sg > 250:
                    flag = " ⚠️ HIGH"
                lines.append(f"  {t:>3} min: ~{sg} mg/dL ({lo}-{hi}){flag}")

            # Add bolus suggestion if only carbs given
            if carbs_g > 0 and bolus_u == 0:
                from app.analytics.estimator import estimate_bolus
                suggestion = estimate_bolus(session, carbs_g)
                if "total_suggested_bolus" in suggestion:
                    lines.append(
                        f"\nSuggested bolus: {suggestion['total_suggested_bolus']}U "
                        f"(I:C 1:{suggestion['ic_ratio']:.0f})"
                    )

            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        else:
            # Unstructured — send to AI for interpretation
            from app.analytics.estimator import get_current_state
            state = get_current_state(session)
            state_desc = (
                f"SG={state['sg']}, trend={state['trend']}, IOB={state['iob']}"
                if state else "No CGM data"
            )
            prompt = (
                f"The user asks: 'What if {raw}?'\n"
                f"Current state: {state_desc}\n"
                f"Analyze the scenario and predict glucose trajectory at 30 and 60 min."
            )
            ctx = build_context(session, patient_id=pid, now=datetime.utcnow(), query=raw)
            system = build_system_prompt(_name(user), lang, ctx)
            response = await ai_chat(
                user_message=prompt, system_prompt=system, patient_id=pid
            )
            await update.message.reply_text(response)
    finally:
        session.close()


async def cmd_accuracy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /accuracy — show prediction accuracy metrics (MARD, CEG zones)."""
    from app.analytics.metrics import reconcile_predictions, compute_prediction_accuracy

    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        pid = _pid(user)

        # Reconcile pending predictions first
        reconciled = reconcile_predictions(session, patient_id=pid)

        # Compute accuracy
        accuracy = compute_prediction_accuracy(session, patient_id=pid, days=7)
        if "error" in accuracy:
            await update.message.reply_text(
                msg("accuracy_no_data", _lang(user))
            )
            return

        lines = ["*Prediction Accuracy (7 days)*\n"]
        if reconciled > 0:
            lines.append(f"({reconciled} new predictions reconciled)\n")

        for horizon, metrics in sorted(accuracy.items()):
            zones = metrics["ceg_zones"]
            lines.append(
                f"*{horizon} min* — MARD: {metrics['mard_pct']}%, "
                f"RMSE: {metrics['rmse']} mg/dL\n"
                f"  Safe (A+B): {metrics['clinically_safe_pct']}% "
                f"| A: {zones.get('A', 0)}% B: {zones.get('B', 0)}% "
                f"C: {zones.get('C', 0)}% D: {zones.get('D', 0)}% E: {zones.get('E', 0)}%\n"
                f"  Predictions: {metrics['n']}"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    finally:
        session.close()


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    session = get_session()
    try:
        user = get_user(session, query.from_user.id)
        if not user:
            return

        lang = _lang(user)
        name = _name(user)
        pid = _pid(user)
        data = query.data

        # --- GDPR consent callbacks ---
        if data.startswith("gdpr_toggle_"):
            from app.privacy import has_consent, record_consent, CONSENT_PURPOSES
            purpose = data.replace("gdpr_toggle_", "")
            current = has_consent(session, pid, purpose)
            record_consent(session, pid, purpose, not current, language=lang)
            status_str = "withdrawn" if current else "granted"
            await query.edit_message_text(
                f"Consent for '{purpose}' {status_str}."
            )
            return

        elif data == "gdpr_grant_all":
            from app.privacy import record_consent, CONSENT_PURPOSES
            for purpose in CONSENT_PURPOSES:
                record_consent(session, pid, purpose, True, language=lang)
            await query.edit_message_text(
                "All consents granted." if lang != "it" else "Tutti i consensi accettati."
            )
            return

        elif data == "gdpr_withdraw_all":
            from app.privacy import record_consent, CONSENT_PURPOSES
            for purpose in CONSENT_PURPOSES:
                record_consent(session, pid, purpose, False, language=lang)
            await query.edit_message_text(
                "All consents withdrawn." if lang != "it" else "Tutti i consensi revocati."
            )
            return

        elif data == "main_menu":
            await query.edit_message_text(
                msg("menu_title", lang),
                reply_markup=main_menu(lang),
            )

        # --- Glucose entry flow: sg_enter → sg_range → sg_val → sg_trend → save ---
        elif data == "sg_enter":
            from app.bot.menus import glucose_range_menu
            await query.edit_message_text(
                msg("sg_pick_range", lang),
                reply_markup=glucose_range_menu(lang),
            )

        elif data.startswith("sg_range:"):
            from app.bot.menus import glucose_value_menu
            _, low, high = data.split(":")
            await query.edit_message_text(
                msg("sg_pick_value", lang),
                reply_markup=glucose_value_menu(int(low), int(high), lang),
            )

        elif data.startswith("sg_val:"):
            from app.bot.menus import glucose_trend_menu
            sg_value = int(data.split(":")[1])
            await query.edit_message_text(
                msg("sg_pick_trend", lang, value=sg_value),
                reply_markup=glucose_trend_menu(sg_value, lang),
            )

        elif data.startswith("sg_trend:"):
            # Final step: save the reading
            parts = data.split(":")
            sg_value = int(parts[1])
            trend = parts[2]
            _save_glucose_reading(session, pid, sg_value, trend, None, "manual")
            await query.edit_message_text(
                msg("sg_saved", lang, value=sg_value, trend=trend)
            )

        # --- What-if flow ---
        elif data == "whatif_menu":
            from app.bot.menus import glucose_whatif_menu
            await query.edit_message_text(
                msg("whatif_pick_scenario", lang),
                reply_markup=glucose_whatif_menu(lang),
            )

        elif data == "whatif_meal":
            context.user_data["editing"] = "whatif_carbs"
            await query.edit_message_text(msg("whatif_enter_carbs", lang))

        elif data == "whatif_activity":
            context.user_data["editing"] = "whatif_activity"
            await query.edit_message_text(msg("whatif_enter_activity", lang))

        elif data == "whatif_bolus":
            context.user_data["editing"] = "whatif_bolus"
            await query.edit_message_text(msg("whatif_enter_bolus", lang))

        elif data == "status":
            reading = (
                session.query(GlucoseReading)
                .filter_by(patient_id=pid)
                .order_by(GlucoseReading.timestamp.desc())
                .first()
            )
            pump = (
                session.query(PumpStatus)
                .filter_by(patient_id=pid)
                .order_by(PumpStatus.timestamp.desc())
                .first()
            )
            if not reading:
                await query.edit_message_text(msg("no_data", lang, name=name))
                return

            text = format_status(
                sg=reading.sg,
                trend=reading.trend or "FLAT",
                iob=pump.active_insulin if pump else None,
                basal_rate=pump.basal_rate if pump else None,
                auto_mode=pump.auto_mode if pump else None,
                reservoir=pump.reservoir_units if pump else None,
                battery=pump.battery_pct if pump else None,
                patient_name=name,
                lang=lang,
            )
            await query.edit_message_text(text, parse_mode="Markdown")

        elif data == "plan_activity":
            await query.edit_message_text(
                msg("btn_plan_activity", lang),
                reply_markup=activity_menu(lang),
            )

        elif data.startswith("activity_"):
            activity_type = data.replace("activity_", "")
            context.user_data["pending_activity"] = activity_type
            prompts = {
                "it": f"{name}, condividi la posizione di partenza per pianificare il percorso {activity_type}! \U0001f4cd",
                "en": f"{name}, share your starting location to plan the {activity_type} route! \U0001f4cd",
                "es": f"{name}, \u00a1comparte tu ubicaci\u00f3n de inicio para planificar la ruta de {activity_type}! \U0001f4cd",
                "fr": f"{name}, partage ta position de d\u00e9part pour planifier le parcours {activity_type} ! \U0001f4cd",
            }
            await query.edit_message_text(prompts.get(lang, prompts["it"]))

        elif data == "report":
            await query.edit_message_text(
                msg("btn_report", lang),
                reply_markup=report_menu(lang),
            )

        elif data == "settings":
            # Show full settings panel (same as settings_back)
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            from app.users import check_token_limit
            _allowed, _reason = check_token_limit(user)
            daily_lim = user.daily_token_limit or ("illimitato" if lang == "it" else "unlimited")
            monthly_lim = user.monthly_token_limit or ("illimitato" if lang == "it" else "unlimited")
            if lang == "it":
                slines = [
                    f"*Impostazioni di {name}*\n",
                    f"Nome: `{name}`",
                    f"Lingua: `{user.language or 'it'}`",
                    f"Modello AI: `{user.ai_model or 'default server'}`",
                    f"CareLink: {'configurato' if user.carelink_username else 'non configurato'}",
                    f"Gemini API: {'configurata' if user.gemini_api_key else 'chiave server'}",
                    f"OpenWeather: {'configurata' if user.openweather_api_key else 'chiave server'}",
                    f"\nToken oggi: {user.tokens_used_today or 0} / {daily_lim}",
                    f"Token mese: {user.tokens_used_month or 0} / {monthly_lim}",
                ]
            else:
                slines = [
                    f"*Settings for {name}*\n",
                    f"Name: `{name}`",
                    f"Language: `{user.language or 'it'}`",
                    f"AI Model: `{user.ai_model or 'default server'}`",
                    f"CareLink: {'configured' if user.carelink_username else 'not configured'}",
                    f"Gemini API: {'configured' if user.gemini_api_key else 'server key'}",
                    f"OpenWeather: {'configured' if user.openweather_api_key else 'server key'}",
                    f"\nTokens today: {user.tokens_used_today or 0} / {daily_lim}",
                    f"Tokens month: {user.tokens_used_month or 0} / {monthly_lim}",
                ]
            sbtns = [
                [InlineKeyboardButton("Nome" if lang == "it" else "Name", callback_data="settings_name"),
                 InlineKeyboardButton("Lingua" if lang == "it" else "Language", callback_data="set_language")],
                [InlineKeyboardButton("CareLink", callback_data="settings_carelink"),
                 InlineKeyboardButton("Modello AI" if lang == "it" else "AI Model", callback_data="settings_ai_model")],
                [InlineKeyboardButton("API Keys", callback_data="settings_apikeys")],
                [InlineKeyboardButton(
                    "Voice reply: " + ("ON" if context.user_data.get("voice_reply") else "OFF"),
                    callback_data="toggle_voice_reply")],
            ]
            if settings.WEBAPP_URL:
                sbtns.append([InlineKeyboardButton(
                    "Apri WebApp" if lang == "it" else "Open WebApp",
                    web_app={"url": f"{settings.WEBAPP_URL.rstrip('/')}#settings"})])
            sbtns.append([InlineKeyboardButton("Menu", callback_data="main_menu")])
            await query.edit_message_text("\n".join(slines), parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(sbtns))

        elif data == "toggle_voice_reply":
            current = context.user_data.get("voice_reply", False)
            context.user_data["voice_reply"] = not current
            if context.user_data["voice_reply"]:
                status_msg = msg("voice_reply_enabled", lang)
            else:
                status_msg = msg("voice_reply_disabled", lang)
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            await query.edit_message_text(
                status_msg,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Torna alle impostazioni" if lang == "it" else "Back to settings",
                        callback_data="settings")
                ]]),
            )

        elif data == "set_language":
            await query.edit_message_text(
                msg("btn_language", lang),
                reply_markup=language_menu(),
            )

        elif data.startswith("lang_"):
            new_lang = data.replace("lang_", "")
            # Persist language in DB
            user.language = new_lang
            session.commit()
            await query.edit_message_text(
                msg("welcome", new_lang, name=name),
                reply_markup=main_menu(new_lang),
            )

        elif data == "import_csv":
            await query.edit_message_text(
                msg("csv_send_prompt", lang, name=name),
            )

        elif data == "help":
            await query.edit_message_text(
                msg("help_text", lang),
                parse_mode="Markdown",
            )

        elif data == "waiver_accept":
            session.add(LiabilityWaiver(
                telegram_user_id=query.from_user.id,
                language=lang,
            ))
            session.commit()
            await query.edit_message_text(
                msg("waiver_accepted", lang, name=name),
            )

        elif data == "waiver_decline":
            await query.edit_message_text(
                msg("waiver_declined", lang, name=name),
            )

        elif data == "food_photo":
            food_prompt = {
                "it": f"{name}, inviami una foto del cibo e lo analizzo! \U0001f4f8",
                "en": f"{name}, send me a photo of the food and I'll analyze it! \U0001f4f8",
                "es": f"{name}, \u00a1env\u00edame una foto de la comida y la analizo! \U0001f4f8",
                "fr": f"{name}, envoie-moi une photo du repas et je l'analyse ! \U0001f4f8",
            }
            await query.edit_message_text(food_prompt.get(lang, food_prompt["it"]))

        elif data.startswith("report_"):
            period = data.replace("report_", "")
            await query.edit_message_text(msg("thinking", lang))
            from app.reports.generator import generate_report
            text, chart_bytes = generate_report(session, period, name, lang, patient_id=pid)
            if chart_bytes:
                await query.message.reply_photo(
                    photo=chart_bytes, caption=text[:1024], parse_mode="Markdown"
                )
            else:
                await query.edit_message_text(text, parse_mode="Markdown")

        elif data == "import_health":
            health_prompt = {
                "it": f"{name}, inviami il file ZIP esportato da Apple Health (Impostazioni \u2192 Salute \u2192 Esporta) \U0001f4f1",
                "en": f"{name}, send me the ZIP file exported from Apple Health (Settings \u2192 Health \u2192 Export) \U0001f4f1",
                "es": f"{name}, env\u00edame el archivo ZIP exportado de Apple Health (Ajustes \u2192 Salud \u2192 Exportar) \U0001f4f1",
                "fr": f"{name}, envoie-moi le fichier ZIP export\u00e9 d'Apple Sant\u00e9 (R\u00e9glages \u2192 Sant\u00e9 \u2192 Exporter) \U0001f4f1",
            }
            await query.edit_message_text(health_prompt.get(lang, health_prompt["it"]))

        # --- Settings callbacks ---
        elif data == "settings_carelink":
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            cl_user = user.carelink_username or ("non impostato" if lang == "it" else "not set")
            cl_country = user.carelink_country or ("non impostato" if lang == "it" else "not set")
            cl_poll = user.carelink_poll_interval or 300
            has_pw = "si" if user.carelink_password else "no"
            if lang != "it":
                has_pw = "yes" if user.carelink_password else "no"

            if lang == "it":
                text = (
                    f"*CareLink per {name}*\n\n"
                    f"Username: `{cl_user}`\n"
                    f"Password salvata: {has_pw}\n"
                    f"Paese: `{cl_country}`\n"
                    f"Polling: {cl_poll}s\n\n"
                    "Tocca un pulsante per modificare:"
                )
            else:
                text = (
                    f"*CareLink for {name}*\n\n"
                    f"Username: `{cl_user}`\n"
                    f"Password saved: {has_pw}\n"
                    f"Country: `{cl_country}`\n"
                    f"Polling: {cl_poll}s\n\n"
                    "Tap a button to edit:"
                )
            btns = [
                [InlineKeyboardButton("Username", callback_data="edit_cl_username"),
                 InlineKeyboardButton("Password", callback_data="edit_cl_password")],
                [InlineKeyboardButton("Paese" if lang == "it" else "Country", callback_data="edit_cl_country"),
                 InlineKeyboardButton("Polling", callback_data="edit_cl_poll")],
                [InlineKeyboardButton("Indietro" if lang == "it" else "Back", callback_data="settings_back")],
            ]
            await query.edit_message_text(text, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(btns))

        elif data == "settings_ai_model":
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            current = user.ai_model or ("default server" if lang != "it" else "default server")
            if lang == "it":
                text = f"*Modello AI per {name}*\n\nAttuale: `{current}`\n\nTocca per modificare:"
            else:
                text = f"*AI Model for {name}*\n\nCurrent: `{current}`\n\nTap to edit:"
            btns = [
                [InlineKeyboardButton("Cambia modello" if lang == "it" else "Change model",
                    callback_data="edit_ai_model")],
                [InlineKeyboardButton("Usa default" if lang == "it" else "Use default",
                    callback_data="set_ai_model_default")],
                [InlineKeyboardButton("Indietro" if lang == "it" else "Back", callback_data="settings_back")],
            ]
            await query.edit_message_text(text, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(btns))

        elif data == "settings_apikeys":
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            gem_status = ("configurata" if lang == "it" else "configured") if user.gemini_api_key else ("chiave server" if lang == "it" else "server key")
            ow_status = ("configurata" if lang == "it" else "configured") if user.openweather_api_key else ("chiave server" if lang == "it" else "server key")
            if lang == "it":
                text = f"*API Keys per {name}*\n\nGemini: {gem_status}\nOpenWeather: {ow_status}\n\nTocca per modificare:"
            else:
                text = f"*API Keys for {name}*\n\nGemini: {gem_status}\nOpenWeather: {ow_status}\n\nTap to edit:"
            btns = [
                [InlineKeyboardButton("Gemini API Key", callback_data="edit_gemini_key")],
                [InlineKeyboardButton("OpenWeather API Key", callback_data="edit_ow_key")],
            ]
            if user.gemini_api_key:
                btns.append([InlineKeyboardButton("Rimuovi Gemini" if lang == "it" else "Remove Gemini",
                    callback_data="clear_gemini_key")])
            if user.openweather_api_key:
                btns.append([InlineKeyboardButton("Rimuovi OpenWeather" if lang == "it" else "Remove OpenWeather",
                    callback_data="clear_ow_key")])
            btns.append([InlineKeyboardButton("Indietro" if lang == "it" else "Back", callback_data="settings_back")])
            await query.edit_message_text(text, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(btns))

        elif data == "settings_name":
            context.user_data["editing"] = "patient_name"
            prompt = "Scrivi il tuo nome:" if lang == "it" else "Type your name:"
            await query.edit_message_text(prompt)

        # --- Inline edit triggers: set editing state, prompt user for input ---
        elif data.startswith("edit_"):
            field = data[5:]  # e.g. "cl_username", "ai_model", "gemini_key"
            context.user_data["editing"] = field
            _edit_prompts = {
                "cl_username": ("Invia il tuo CareLink username:", "Send your CareLink username:"),
                "cl_password": ("Invia la tua CareLink password (il messaggio verra' eliminato):", "Send your CareLink password (message will be deleted):"),
                "cl_country": ("Invia il codice paese (es. IT, US, DE):", "Send the country code (e.g. IT, US, DE):"),
                "cl_poll": ("Invia l'intervallo polling in secondi (60-3600):", "Send the polling interval in seconds (60-3600):"),
                "ai_model": ("Invia il nome del modello AI (es. ollama/qwen2.5:14b-instruct-q4_K_M):", "Send the AI model name (e.g. ollama/qwen2.5:14b-instruct-q4_K_M):"),
                "gemini_key": ("Invia la tua Gemini API key (il messaggio verra' eliminato):", "Send your Gemini API key (message will be deleted):"),
                "ow_key": ("Invia la tua OpenWeather API key (il messaggio verra' eliminato):", "Send your OpenWeather API key (message will be deleted):"),
                "patient_name": ("Scrivi il tuo nome:", "Type your name:"),
            }
            prompts = _edit_prompts.get(field, ("Invia il valore:", "Send the value:"))
            prompt = prompts[0] if lang == "it" else prompts[1]
            await query.edit_message_text(prompt)

        elif data == "set_ai_model_default":
            user.ai_model = None
            session.commit()
            done = "Modello AI impostato a: default server" if lang == "it" else "AI model set to: server default"
            await query.edit_message_text(done)

        elif data == "clear_gemini_key":
            user.gemini_api_key = None
            session.commit()
            done = "Gemini API key rimossa." if lang == "it" else "Gemini API key removed."
            await query.edit_message_text(done)

        elif data == "clear_ow_key":
            user.openweather_api_key = None
            session.commit()
            done = "OpenWeather API key rimossa." if lang == "it" else "OpenWeather API key removed."
            await query.edit_message_text(done)

        elif data == "settings_back":
            # Re-show the settings overview as a new message (since we can't call cmd_settings from callback easily)
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            from app.users import check_token_limit
            _allowed, _reason = check_token_limit(user)
            daily_lim = user.daily_token_limit or ("illimitato" if lang == "it" else "unlimited")
            monthly_lim = user.monthly_token_limit or ("illimitato" if lang == "it" else "unlimited")
            if lang == "it":
                lines = [
                    f"*Impostazioni di {name}*\n",
                    f"Nome: `{name}`",
                    f"Lingua: `{user.language or 'it'}`",
                    f"Modello AI: `{user.ai_model or 'default server'}`",
                    f"CareLink: {'configurato' if user.carelink_username else 'non configurato'}",
                    f"Gemini API: {'configurata' if user.gemini_api_key else 'chiave server'}",
                    f"OpenWeather API: {'configurata' if user.openweather_api_key else 'chiave server'}",
                    f"\nToken oggi: {user.tokens_used_today or 0} / {daily_lim}",
                    f"Token mese: {user.tokens_used_month or 0} / {monthly_lim}",
                ]
            else:
                lines = [
                    f"*Settings for {name}*\n",
                    f"Name: `{name}`",
                    f"Language: `{user.language or 'it'}`",
                    f"AI Model: `{user.ai_model or 'default server'}`",
                    f"CareLink: {'configured' if user.carelink_username else 'not configured'}",
                    f"Gemini API: {'configured' if user.gemini_api_key else 'server key'}",
                    f"OpenWeather API: {'configured' if user.openweather_api_key else 'server key'}",
                    f"\nTokens today: {user.tokens_used_today or 0} / {daily_lim}",
                    f"Tokens month: {user.tokens_used_month or 0} / {monthly_lim}",
                ]
            btns = [
                [InlineKeyboardButton("Nome" if lang == "it" else "Name", callback_data="settings_name"),
                 InlineKeyboardButton("Lingua" if lang == "it" else "Language", callback_data="set_language")],
                [InlineKeyboardButton("CareLink", callback_data="settings_carelink"),
                 InlineKeyboardButton("Modello AI" if lang == "it" else "AI Model", callback_data="settings_ai_model")],
                [InlineKeyboardButton("API Keys", callback_data="settings_apikeys")],
            ]
            if settings.WEBAPP_URL:
                btns.append([InlineKeyboardButton(
                    "Apri WebApp" if lang == "it" else "Open WebApp",
                    web_app={"url": f"{settings.WEBAPP_URL.rstrip('/')}#settings"})])
            btns.append([InlineKeyboardButton("Menu" if lang == "it" else "Menu", callback_data="main_menu")])
            await query.edit_message_text("\n".join(lines), parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(btns))

        # --- Glucose reading callbacks ---
        elif data.startswith("sg_confirm:"):
            # sg_confirm:value:trend:iob:source:pid
            parts = data.split(":")
            sg_val = float(parts[1])
            trend_val = parts[2] if len(parts) > 2 else "FLAT"
            iob_val = float(parts[3]) if len(parts) > 3 else None
            source = parts[4] if len(parts) > 4 else "manual"
            sg_pid = int(parts[5]) if len(parts) > 5 else pid

            _save_glucose_reading(session, sg_pid, sg_val, trend_val, iob_val, source)
            await query.edit_message_text(
                msg("sg_saved", lang, value=int(sg_val), trend=trend_val)
            )

        elif data.startswith("sg_quick:"):
            # sg_quick:value:pid — quick keyboard tap, save directly with FLAT trend
            parts = data.split(":")
            sg_val = float(parts[1])
            sg_pid = int(parts[2]) if len(parts) > 2 else pid

            _save_glucose_reading(session, sg_pid, sg_val, "FLAT", None, "manual")
            await query.edit_message_text(
                msg("sg_saved", lang, value=int(sg_val), trend="FLAT")
            )

        elif data.startswith("sg_correct:"):
            # sg_correct:original_value:pid — user wants to manually correct
            context.user_data["editing"] = "sg_manual"
            prompt = msg("sg_enter_correct", lang)
            await query.edit_message_text(prompt)

        elif data == "sg_cancel":
            await query.edit_message_text(
                msg("sg_cancelled", lang)
            )

        else:
            log.debug("Unhandled callback: %s", data)

    finally:
        session.close()


def _save_glucose_reading(session, patient_id, sg, trend, iob, source):
    """Save a manually entered or photo-extracted glucose reading."""
    reading = GlucoseReading(
        patient_id=patient_id,
        timestamp=datetime.utcnow(),
        sg=sg,
        trend=trend,
        source=source or "manual",
    )
    session.add(reading)

    if iob is not None and iob > 0:
        pump = PumpStatus(
            patient_id=patient_id,
            timestamp=datetime.utcnow(),
            active_insulin=iob,
            source=source or "manual",
        )
        session.add(pump)

    session.commit()
    log.info("Saved manual glucose reading: %s mg/dL (trend=%s, source=%s)", sg, trend, source)


async def _handle_settings_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """If user is in settings-edit mode, apply the value and return True. Otherwise False."""
    editing = context.user_data.get("editing")
    if not editing:
        return False

    # Clear editing state immediately
    context.user_data.pop("editing", None)
    value = update.message.text.strip()
    is_sensitive = editing in ("cl_password", "gemini_key", "ow_key")

    session = get_session()
    try:
        user = get_user(session, update.effective_user.id)
        if not user:
            return True
        lang = _lang(user)

        # Apply the edit
        confirm = None
        if editing == "patient_name":
            user.patient_name = value[:100]
            confirm = f"Nome: `{user.patient_name}`"
        elif editing == "cl_username":
            user.carelink_username = value[:200]
            confirm = f"CareLink username: `{user.carelink_username}`"
        elif editing == "cl_password":
            user.carelink_password = value
            confirm = "CareLink password salvata." if lang == "it" else "CareLink password saved."
        elif editing == "cl_country":
            user.carelink_country = value.upper()[:5]
            confirm = f"CareLink paese: `{user.carelink_country}`"
        elif editing == "cl_poll":
            try:
                interval = max(60, min(3600, int(value)))
            except ValueError:
                interval = 300
            user.carelink_poll_interval = interval
            confirm = f"Polling: {interval}s"
        elif editing == "ai_model":
            if value.lower() == "default":
                user.ai_model = None
                confirm = "Modello AI: default server" if lang == "it" else "AI model: server default"
            else:
                from app.users import is_model_allowed
                if not is_model_allowed(user, value):
                    await update.message.reply_text(
                        "Modello non consentito." if lang == "it" else "Model not allowed."
                    )
                    return True
                user.ai_model = value[:200]
                confirm = f"Modello AI: `{user.ai_model}`"
        elif editing == "gemini_key":
            user.gemini_api_key = value
            confirm = "Gemini API key salvata." if lang == "it" else "Gemini API key saved."
        elif editing == "ow_key":
            user.openweather_api_key = value
            confirm = "OpenWeather API key salvata." if lang == "it" else "OpenWeather API key saved."
        elif editing == "sg_manual":
            # Manual glucose correction entry
            try:
                sg_val = float(value.split()[0])
                pid = _pid(user)
                _save_glucose_reading(session, pid, sg_val, "FLAT", None, "manual")
                confirm = msg("sg_saved", lang, value=int(sg_val), trend="FLAT")
            except (ValueError, IndexError):
                await update.message.reply_text(msg("sg_invalid", lang))
                return True
        elif editing == "whatif_carbs":
            # What-if meal scenario from button flow
            try:
                carbs = float(value.split()[0])
            except (ValueError, IndexError):
                await update.message.reply_text(msg("sg_invalid", lang))
                return True
            from app.analytics.estimator import predict_trajectory, estimate_bolus as est_bolus
            pid = _pid(user)
            trajectory = predict_trajectory(session, carbs_g=carbs)
            if not trajectory or "error" in trajectory[0]:
                await update.message.reply_text(msg("no_data", lang, name=_name(user)))
                return True
            lines = [f"*What if: {carbs:.0f}g carbs*\n"]
            for p in trajectory:
                flag = " ⚠️" if p["predicted_sg"] < 70 or p["predicted_sg"] > 250 else ""
                lines.append(f"  {p['minutes_ahead']:>3} min: ~{p['predicted_sg']} mg/dL ({p['range_low']}-{p['range_high']}){flag}")
            suggestion = est_bolus(session, carbs)
            if "total_suggested_bolus" in suggestion:
                lines.append(f"\nSuggested bolus: {suggestion['total_suggested_bolus']}U (I:C 1:{suggestion['ic_ratio']:.0f})")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
            return True
        elif editing == "whatif_activity":
            # What-if activity scenario from button flow
            import re as _re
            match = _re.search(r'(cycling|walking|running|gym|swimming|hiking)\s+(\d+)\s*min', value, _re.IGNORECASE)
            if not match:
                await update.message.reply_text(msg("whatif_enter_activity", lang))
                return True
            from app.analytics.estimator import estimate_activity_impact
            impact = estimate_activity_impact(session, match.group(1).lower(), int(match.group(2)))
            if "error" in impact:
                await update.message.reply_text(msg("no_data", lang, name=_name(user)))
                return True
            lines = [
                f"*What if: {match.group(1)} {match.group(2)}min*\n",
                f"Estimated drop: ~{impact['estimated_drop']} mg/dL",
                f"Predicted SG: ~{impact['predicted_sg_end']} mg/dL ({impact['predicted_range']})",
                f"Risk: {impact['risk_level']}",
            ]
            if impact['carbs_recommended_g'] > 0:
                lines.append(f"Suggested carbs: {impact['carbs_recommended_g']}g")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
            return True
        elif editing == "whatif_bolus":
            # What-if bolus scenario from button flow
            try:
                bolus = float(value.split()[0])
            except (ValueError, IndexError):
                await update.message.reply_text(msg("sg_invalid", lang))
                return True
            from app.analytics.estimator import predict_trajectory
            trajectory = predict_trajectory(session, bolus_u=bolus)
            if not trajectory or "error" in trajectory[0]:
                await update.message.reply_text(msg("no_data", lang, name=_name(user)))
                return True
            lines = [f"*What if: {bolus:.1f}U bolus*\n"]
            for p in trajectory:
                flag = " ⚠️" if p["predicted_sg"] < 70 or p["predicted_sg"] > 250 else ""
                lines.append(f"  {p['minutes_ahead']:>3} min: ~{p['predicted_sg']} mg/dL ({p['range_low']}-{p['range_high']}){flag}")
            await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
            return True

        session.commit()

        # Delete the message if it contained sensitive data
        if is_sensitive:
            try:
                await update.message.delete()
            except Exception:
                pass

        if confirm:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            back_btn = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "Torna alle impostazioni" if lang == "it" else "Back to settings",
                    callback_data="settings_back",
                )
            ]])
            if is_sensitive:
                # Send to chat (not reply, since original was deleted)
                await update.effective_chat.send_message(
                    confirm, parse_mode="Markdown", reply_markup=back_btn,
                )
            else:
                await update.message.reply_text(
                    confirm, parse_mode="Markdown", reply_markup=back_btn,
                )
    finally:
        session.close()
    return True


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle free-text messages — settings edit or AI with full context."""
    # Check if user is editing a setting field
    if await _handle_settings_edit(update, context):
        return

    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        lang = _lang(user)
        name = _name(user)
        pid = _pid(user)
        user_text = update.message.text

        thinking_msg = await update.message.reply_text(msg("thinking", lang))

        try:
            ctx = build_context(session, patient_id=pid, query=user_text)
            system_prompt = build_system_prompt(name, lang, ctx)

            # Get recent chat history (last 10 messages) — private per user
            recent = (
                session.query(ChatMessage)
                .filter_by(patient_id=pid)
                .order_by(ChatMessage.timestamp.desc())
                .limit(10)
                .all()
            )
            recent.reverse()

            messages = [{"role": "system", "content": system_prompt}]
            for cm in recent:
                messages.append({"role": cm.role, "content": cm.content})
            messages.append({"role": "user", "content": user_text})

            response = await ai_chat(messages, user=user)

            # Save conversation — private per user
            session.add(ChatMessage(
                patient_id=pid,
                role="user", content=user_text,
            ))
            session.add(ChatMessage(
                patient_id=pid,
                role="assistant", content=response,
            ))
            session.commit()

            await thinking_msg.edit_text(response, parse_mode="Markdown")

            # Extract memories in background (non-blocking)
            import asyncio
            from app.memory import extract_memories as _extract_memories
            asyncio.create_task(
                _extract_memories_safe(pid, user_text, response)
            )

        except Exception as e:
            log.error("Error handling text message: %s", e, exc_info=True)
            err = {"it": "Si è verificato un errore. Riprova.", "en": "An error occurred. Please try again."}
            await thinking_msg.edit_text(err.get(lang, err["it"]))

    finally:
        session.close()


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages — food analysis OR device glucose reading extraction."""
    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        lang = _lang(user)
        thinking_msg = await update.message.reply_text(msg("thinking", lang))

        try:
            photo = update.message.photo[-1]
            file = await photo.get_file()
            photo_bytes = await file.download_as_bytearray()
            photo_b64 = base64.b64encode(bytes(photo_bytes)).decode("utf-8")
            caption = update.message.caption or ""

            from app.bot.glucose_reader import is_likely_device_photo, extract_glucose_from_photo

            if is_likely_device_photo(caption):
                # Device photo — extract glucose reading
                data = await extract_glucose_from_photo(photo_b64, lang, user=user)
                if data and data.get("glucose_value"):
                    await _show_glucose_confirmation(
                        update, thinking_msg, data, user, lang, session
                    )
                else:
                    # Fallback: try as food photo
                    await _handle_food_photo(
                        update, thinking_msg, photo_b64, caption, user, lang, session
                    )
            else:
                await _handle_food_photo(
                    update, thinking_msg, photo_b64, caption, user, lang, session
                )

        except Exception as e:
            log.error("Error handling photo: %s", e, exc_info=True)
            err = {"it": "Errore nell'analisi della foto. Riprova.", "en": "Error analyzing photo. Please try again."}
            await thinking_msg.edit_text(err.get(lang, err["it"]))

    finally:
        session.close()


async def _handle_food_photo(update, thinking_msg, photo_b64, caption, user, lang, session):
    """Process a food photo with vision AI."""
    from app.bot.food import analyze_food_photo
    response, estimation = await analyze_food_photo(
        photo_b64, caption, session, _name(user), lang,
        patient_id=_pid(user), user=user,
    )
    await thinking_msg.edit_text(response, parse_mode="Markdown")


async def _show_glucose_confirmation(update, thinking_msg, data, user, lang, session):
    """Show extracted glucose value and ask for confirmation."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    sg = data["glucose_value"]
    device = data.get("device_type", "unknown")
    confidence = data.get("confidence", "low")
    trend = data.get("trend")
    iob = data.get("iob")
    notes = data.get("notes", "")

    device_names = {
        "pump_780g": "Medtronic 780G",
        "glucometer": "Glucometer",
        "cgm_receiver": "CGM Receiver",
    }
    device_label = device_names.get(device, device)

    lines = [
        msg("sg_photo_detected", lang),
        f"*{device_label}*",
        f"Glucose: *{sg} mg/dL*",
    ]
    if trend:
        lines.append(f"Trend: {trend}")
    if iob is not None:
        lines.append(f"IOB: {iob:.1f}U")
    if confidence != "high":
        lines.append(f"Confidence: {confidence}")
    if notes:
        lines.append(f"_{notes}_")

    # Store data in user context for callback
    update.message.from_user  # trigger user_data init
    context_data = update.message.chat_id
    pid = _pid(user)

    keyboard = [
        [
            InlineKeyboardButton(
                msg("sg_confirm", lang),
                callback_data=f"sg_confirm:{sg}:{trend or 'FLAT'}:{iob or 0}:{device}:{pid}"
            ),
        ],
        [
            InlineKeyboardButton(
                msg("sg_correct", lang),
                callback_data=f"sg_correct:{sg}:{pid}"
            ),
        ],
    ]

    await thinking_msg.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages — transcribe + AI response + optional voice reply."""
    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        lang = _lang(user)
        thinking_msg = await update.message.reply_text(msg("thinking", lang))

        try:
            voice = update.message.voice
            file = await voice.get_file()
            voice_bytes = await file.download_as_bytearray()

            from app.bot.voice import process_voice_message
            response = await process_voice_message(
                bytes(voice_bytes),
                session,
                patient_id=_pid(user),
                patient_name=_name(user),
                lang=lang,
                user=user,
            )
            await thinking_msg.edit_text(response, parse_mode="Markdown")

            if context.user_data.get("voice_reply", False):
                await _send_voice_reply(update, response, lang)

        except Exception as e:
            log.error("Error handling voice: %s", e, exc_info=True)
            err = {"it": "Errore nel messaggio vocale. Riprova.", "en": "Error processing voice message. Please try again."}
            await thinking_msg.edit_text(err.get(lang, err["it"]))

    finally:
        session.close()


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document uploads — CSV, ZIP (Apple Health), PDF (lab results)."""
    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        lang = _lang(user)
        pid = _pid(user)
        doc = update.message.document
        filename = (doc.file_name or "").lower()

        thinking_msg = await update.message.reply_text(msg("thinking", lang))

        try:
            file = await doc.get_file()
            file_bytes = bytes(await file.download_as_bytearray())

            if filename.endswith(".zip"):
                from app.health.apple import import_apple_health_zip
                stats = import_apple_health_zip(file_bytes, session, patient_id=pid)
                if "error" in stats:
                    await thinking_msg.edit_text(f"\u274c {stats['error']}")
                else:
                    text = (
                        f"\u2705 Apple Health importato!\n"
                        f"\u2022 {stats.get('records', 0)} record salute\n"
                        f"\u2022 {stats.get('workouts', 0)} allenamenti\n"
                        f"\u2022 {stats.get('skipped', 0)} duplicati saltati"
                    )
                    await thinking_msg.edit_text(text)

            elif filename.endswith(".csv"):
                stats = import_carelink_csv_bytes(file_bytes, doc.file_name, session, patient_id=pid)
                result_text = format_csv_import_result(stats, lang)
                await thinking_msg.edit_text(result_text)

            elif filename.endswith(".pdf"):
                from app.health.lab_analyzer import analyze_lab_results
                photo_b64 = base64.b64encode(file_bytes).decode("utf-8")
                results, summary = await analyze_lab_results(
                    image_b64=photo_b64, session=session,
                    patient_name=_name(user), lang=lang,
                    patient_id=pid,
                )
                if summary:
                    from app.health.conditions import update_conditions_from_labs
                    update_conditions_from_labs(session, patient_id=pid)
                    await thinking_msg.edit_text(summary, parse_mode="Markdown")
                else:
                    await thinking_msg.edit_text("\u274c Could not parse lab results")

            else:
                await thinking_msg.edit_text(
                    msg("csv_import_error", lang, error="Supported formats: CSV, ZIP, PDF")
                )

        except Exception as e:
            log.error("Error handling document: %s", e, exc_info=True)
            err = {"it": "Errore nell'importazione del file. Riprova.", "en": "Error importing file. Please try again."}
            await thinking_msg.edit_text(err.get(lang, err["it"]))
    finally:
        session.close()


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle shared GPS location — for activity planning."""
    session = get_session()
    try:
        user = await _require_user(update, session)
        if not user:
            return

        lang = _lang(user)
        name = _name(user)
        pid = _pid(user)
        loc = update.message.location

        context.user_data["last_location"] = {
            "lat": loc.latitude,
            "lon": loc.longitude,
        }

        pending_activity = context.user_data.get("pending_activity")
        if pending_activity:
            context.user_data.pop("pending_activity", None)
            thinking_msg = await update.message.reply_text(msg("thinking", lang))

            from app.activity.tracker import plan_activity
            plan = await plan_activity(
                session,
                activity_type=pending_activity,
                lat=loc.latitude,
                lon=loc.longitude,
                patient_name=name,
                patient_id=pid,
            )
            text = _format_activity_plan(plan, lang)

            ctx = build_context(session, patient_id=pid)
            system_prompt = build_system_prompt(name, lang, ctx)
            ai_prompt = (
                f"Activity plan for {name}: {pending_activity}, "
                f"duration {plan['duration_min']}min, "
                f"calories ~{plan['calories']['calories_total']}kcal, "
                f"glucose prediction: current {plan['glucose_impact'].get('current_sg', '?')} \u2192 "
                f"end {plan['glucose_impact'].get('predicted_sg_end', '?')} mg/dL. "
                f"Weather: {plan.get('weather', 'unknown')}. "
                "Give a brief, friendly commentary with practical tips. "
                "Always show final predicted glucose values."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": ai_prompt},
            ]
            ai_comment = await ai_chat(messages, user=user)

            await thinking_msg.edit_text(
                text + "\n\n" + ai_comment,
                parse_mode="Markdown",
            )
            return

        # General location share
        ctx = build_context(session, patient_id=pid)
        system_prompt = build_system_prompt(name, lang, ctx)

        location_msg = (
            f"{name} ha condiviso la posizione: "
            f"lat={loc.latitude:.6f}, lon={loc.longitude:.6f}. "
            "Suggerisci attivit\u00e0 in zona considerando glicemia attuale, "
            "storico e condizioni. Mostra previsione glicemia finale."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": location_msg},
        ]

        response = await ai_chat(messages, user=user)
        await update.message.reply_text(response, parse_mode="Markdown")
    finally:
        session.close()


# --- Utilities ---

async def _send_voice_reply(update: Update, text: str, lang: str):
    """Generate TTS audio and send as a Telegram voice message."""
    try:
        from app.bot.tts import text_to_speech
        import io

        audio_bytes = await text_to_speech(text, lang)
        if audio_bytes:
            await update.message.reply_voice(
                voice=io.BytesIO(audio_bytes),
            )
        else:
            log.warning("TTS returned no audio, skipping voice reply")
    except Exception as e:
        log.error("Failed to send voice reply: %s", e)


def _format_activity_plan(plan: dict, lang: str) -> str:
    """Format an activity plan into a Telegram message."""
    at = plan["activity_type"]
    icons = {"cycling": "\U0001f6b4", "walking": "\U0001f97e", "running": "\U0001f3c3", "gym": "\U0001f3cb\ufe0f"}
    icon = icons.get(at, "\U0001f3c3")

    lines = [f"{icon} *{at.title()}*\n"]

    if plan["distance_km"]:
        lines.append(f"\U0001f4cf {plan['distance_km']} km")
    if plan["elevation_gain_m"]:
        lines.append(f"\u26f0\ufe0f +{plan['elevation_gain_m']}m / -{plan['elevation_loss_m']}m")
    lines.append(f"\u23f1\ufe0f ~{plan['duration_min']} min")
    lines.append(f"\U0001f525 ~{plan['calories']['calories_total']} kcal")

    weather = plan.get("weather")
    if weather and weather.get("temp_c") is not None:
        lines.append(f"\U0001f321\ufe0f {weather['temp_c']:.0f}\u00b0C, {weather.get('conditions', '')}")

    gi = plan.get("glucose_impact", {})
    if "error" not in gi:
        lines.append(f"\n\U0001f4ca Glicemia: *{gi.get('current_sg', '?')}* \u2192 stima *{gi.get('predicted_sg_end', '?')}* mg/dL")
        lines.append(f"Calo stimato: ~{gi.get('estimated_drop', '?')} mg/dL")
        risk = gi.get("risk_level", "low")
        risk_icons = {"low": "\U0001f7e2", "moderate": "\U0001f7e1", "high": "\U0001f534"}
        lines.append(f"Rischio: {risk_icons.get(risk, '?')} {risk}")

    suggestions = plan.get("suggestions", [])
    if suggestions:
        lines.append("\n\U0001f4a1 *Suggerimenti:*")
        for i, s in enumerate(suggestions, 1):
            lines.append(f"{i}. {s}")

    return "\n".join(lines)
