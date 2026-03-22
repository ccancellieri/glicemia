"""Telegram bot handlers — platform-agnostic message processing."""

import base64
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from app.config import settings
from app.database import get_session
from app.models import (
    GlucoseReading, PumpStatus, LiabilityWaiver,
    ChatMessage, PatientProfile,
)
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


def _get_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("lang", settings.LANGUAGE)


def _get_name() -> str:
    return settings.PATIENT_NAME


def _is_authorized(user_id: int) -> bool:
    if not settings.TELEGRAM_ALLOWED_USERS:
        return True  # No restriction if list is empty
    return user_id in settings.TELEGRAM_ALLOWED_USERS


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start — show waiver if not accepted, else welcome."""
    if not _is_authorized(update.effective_user.id):
        return

    lang = _get_lang(context)
    session = get_session()

    try:
        waiver = session.query(LiabilityWaiver).filter_by(
            telegram_user_id=update.effective_user.id
        ).first()

        if waiver:
            await update.message.reply_text(
                msg("welcome", lang, name=_get_name()),
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
    if not _is_authorized(update.effective_user.id):
        return
    lang = _get_lang(context)
    await update.message.reply_text(
        msg("menu_title", lang),
        reply_markup=main_menu(lang),
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stato — show current CGM/pump status."""
    if not _is_authorized(update.effective_user.id):
        return

    lang = _get_lang(context)
    session = get_session()

    try:
        reading = (
            session.query(GlucoseReading)
            .order_by(GlucoseReading.timestamp.desc())
            .first()
        )
        pump = (
            session.query(PumpStatus)
            .order_by(PumpStatus.timestamp.desc())
            .first()
        )

        if not reading:
            await update.message.reply_text(
                msg("no_data", lang, name=_get_name())
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
            patient_name=_get_name(),
            lang=lang,
        )
        await update.message.reply_text(text, parse_mode="Markdown")
    finally:
        session.close()


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help."""
    if not _is_authorized(update.effective_user.id):
        return
    lang = _get_lang(context)
    await update.message.reply_text(
        msg("help_text", lang),
        parse_mode="Markdown",
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    if not _is_authorized(query.from_user.id):
        return

    lang = _get_lang(context)
    data = query.data

    if data == "main_menu":
        await query.edit_message_text(
            msg("menu_title", lang),
            reply_markup=main_menu(lang),
        )

    elif data == "status":
        session = get_session()
        try:
            reading = (
                session.query(GlucoseReading)
                .order_by(GlucoseReading.timestamp.desc())
                .first()
            )
            pump = (
                session.query(PumpStatus)
                .order_by(PumpStatus.timestamp.desc())
                .first()
            )
            if not reading:
                await query.edit_message_text(msg("no_data", lang, name=_get_name()))
                return

            text = format_status(
                sg=reading.sg,
                trend=reading.trend or "FLAT",
                iob=pump.active_insulin if pump else None,
                basal_rate=pump.basal_rate if pump else None,
                auto_mode=pump.auto_mode if pump else None,
                reservoir=pump.reservoir_units if pump else None,
                battery=pump.battery_pct if pump else None,
                patient_name=_get_name(),
                lang=lang,
            )
            await query.edit_message_text(text, parse_mode="Markdown")
        finally:
            session.close()

    elif data == "plan_activity":
        await query.edit_message_text(
            msg("btn_plan_activity", lang),
            reply_markup=activity_menu(lang),
        )

    elif data == "report":
        await query.edit_message_text(
            msg("btn_report", lang),
            reply_markup=report_menu(lang),
        )

    elif data == "settings":
        await query.edit_message_text(
            msg("btn_settings", lang),
            reply_markup=settings_menu(lang),
        )

    elif data == "set_language":
        await query.edit_message_text(
            msg("btn_language", lang),
            reply_markup=language_menu(),
        )

    elif data.startswith("lang_"):
        new_lang = data.replace("lang_", "")
        context.user_data["lang"] = new_lang
        await query.edit_message_text(
            msg("welcome", new_lang, name=_get_name()),
            reply_markup=main_menu(new_lang),
        )

    elif data == "import_csv":
        await query.edit_message_text(
            msg("csv_send_prompt", lang, name=_get_name()),
        )

    elif data == "help":
        await query.edit_message_text(
            msg("help_text", lang),
            parse_mode="Markdown",
        )

    elif data == "waiver_accept":
        session = get_session()
        try:
            session.add(LiabilityWaiver(
                telegram_user_id=query.from_user.id,
                language=lang,
            ))
            session.commit()
            await query.edit_message_text(
                msg("waiver_accepted", lang, name=_get_name()),
            )
        finally:
            session.close()

    elif data == "waiver_decline":
        await query.edit_message_text(
            msg("waiver_declined", lang, name=_get_name()),
        )

    elif data == "food_photo":
        food_prompt = {
            "it": f"{_get_name()}, inviami una foto del cibo e lo analizzo! 📸",
            "en": f"{_get_name()}, send me a photo of the food and I'll analyze it! 📸",
            "es": f"{_get_name()}, ¡envíame una foto de la comida y la analizo! 📸",
            "fr": f"{_get_name()}, envoie-moi une photo du repas et je l'analyse ! 📸",
        }
        await query.edit_message_text(food_prompt.get(lang, food_prompt["it"]))

    else:
        # For unhandled callbacks, acknowledge silently
        log.debug("Unhandled callback: %s", data)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle free-text messages — send to AI with full context."""
    if not _is_authorized(update.effective_user.id):
        return

    lang = _get_lang(context)
    user_text = update.message.text

    # Send "thinking" indicator
    thinking_msg = await update.message.reply_text(msg("thinking", lang))

    session = get_session()
    try:
        # Build context
        ctx = build_context(session)
        system_prompt = build_system_prompt(_get_name(), lang, ctx)

        # Get recent chat history (last 10 messages)
        recent = (
            session.query(ChatMessage)
            .filter_by(user_id=str(update.effective_user.id))
            .order_by(ChatMessage.timestamp.desc())
            .limit(10)
            .all()
        )
        recent.reverse()

        messages = [{"role": "system", "content": system_prompt}]
        for cm in recent:
            messages.append({"role": cm.role, "content": cm.content})
        messages.append({"role": "user", "content": user_text})

        # Call AI
        response = await ai_chat(messages)

        # Save conversation
        session.add(ChatMessage(
            user_id=str(update.effective_user.id),
            role="user", content=user_text,
        ))
        session.add(ChatMessage(
            user_id=str(update.effective_user.id),
            role="assistant", content=response,
        ))
        session.commit()

        # Edit thinking message with response
        await thinking_msg.edit_text(response, parse_mode="Markdown")

    except Exception as e:
        log.error("Error handling text message: %s", e)
        await thinking_msg.edit_text(f"[Error: {e}]")
    finally:
        session.close()


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages — food analysis with vision AI + own bolus estimation."""
    if not _is_authorized(update.effective_user.id):
        return

    lang = _get_lang(context)
    thinking_msg = await update.message.reply_text(msg("thinking", lang))

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        photo_bytes = await file.download_as_bytearray()
        photo_b64 = base64.b64encode(bytes(photo_bytes)).decode("utf-8")
        caption = update.message.caption or ""

        session = get_session()
        try:
            from app.bot.food import analyze_food_photo
            response, estimation = await analyze_food_photo(
                photo_b64, caption, session, _get_name(), lang
            )
            await thinking_msg.edit_text(response, parse_mode="Markdown")
        finally:
            session.close()

    except Exception as e:
        log.error("Error handling photo: %s", e)
        await thinking_msg.edit_text(f"[Error: {e}]")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages — transcribe + AI response with full context."""
    if not _is_authorized(update.effective_user.id):
        return

    lang = _get_lang(context)
    thinking_msg = await update.message.reply_text(msg("thinking", lang))

    try:
        voice = update.message.voice
        file = await voice.get_file()
        voice_bytes = await file.download_as_bytearray()

        session = get_session()
        try:
            from app.bot.voice import process_voice_message
            response = await process_voice_message(
                bytes(voice_bytes),
                session,
                user_id=str(update.effective_user.id),
                patient_name=_get_name(),
                lang=lang,
            )
            await thinking_msg.edit_text(response, parse_mode="Markdown")
        finally:
            session.close()

    except Exception as e:
        log.error("Error handling voice: %s", e)
        await thinking_msg.edit_text(f"[Error: {e}]")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document uploads — CSV import for CareLink data."""
    if not _is_authorized(update.effective_user.id):
        return

    lang = _get_lang(context)
    doc = update.message.document

    if not doc.file_name or not doc.file_name.lower().endswith(".csv"):
        await update.message.reply_text(
            msg("csv_import_error", lang, error="Only CSV files are supported")
        )
        return

    thinking_msg = await update.message.reply_text(msg("thinking", lang))

    try:
        file = await doc.get_file()
        file_bytes = await file.download_as_bytearray()

        session = get_session()
        try:
            stats = import_carelink_csv_bytes(
                bytes(file_bytes), doc.file_name, session
            )
            result_text = format_csv_import_result(stats, lang)
            await thinking_msg.edit_text(result_text)
        finally:
            session.close()

    except Exception as e:
        log.error("Error handling document: %s", e)
        await thinking_msg.edit_text(
            msg("csv_import_error", lang, error=str(e))
        )


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle shared GPS location — for activity planning."""
    if not _is_authorized(update.effective_user.id):
        return

    lang = _get_lang(context)
    loc = update.message.location

    # Store in user_data for activity planning flow
    context.user_data["last_location"] = {
        "lat": loc.latitude,
        "lon": loc.longitude,
    }

    session = get_session()
    try:
        ctx = build_context(session)
        system_prompt = build_system_prompt(_get_name(), lang, ctx)

        location_msg = {
            "it": (
                f"{_get_name()} ha condiviso la posizione: "
                f"lat={loc.latitude:.6f}, lon={loc.longitude:.6f}. "
                "Suggerisci attività in zona considerando glicemia attuale, "
                "storico e condizioni. Mostra previsione glicemia finale."
            ),
            "en": (
                f"{_get_name()} shared location: "
                f"lat={loc.latitude:.6f}, lon={loc.longitude:.6f}. "
                "Suggest activities in the area considering current glucose, "
                "history and conditions. Show final glucose prediction."
            ),
        }

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": location_msg.get(lang, location_msg["it"])},
        ]

        response = await ai_chat(messages)
        await update.message.reply_text(response, parse_mode="Markdown")
    finally:
        session.close()
