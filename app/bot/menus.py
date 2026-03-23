"""Inline keyboard menus for the Telegram bot."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from app.config import settings
from app.i18n.messages import msg


def main_menu(lang: str = "it") -> InlineKeyboardMarkup:
    rows = []
    # WebApp dashboard button (if URL configured)
    if settings.WEBAPP_URL:
        webapp_labels = {"it": "📱 Dashboard", "en": "📱 Dashboard", "es": "📱 Panel", "fr": "📱 Tableau de bord"}
        rows.append([InlineKeyboardButton(
            webapp_labels.get(lang, "📱 Dashboard"),
            web_app=WebAppInfo(url=settings.WEBAPP_URL),
        )])
    rows.extend([
        [InlineKeyboardButton(msg("btn_status", lang), callback_data="status")],
        [InlineKeyboardButton(msg("btn_food_photo", lang), callback_data="food_photo")],
        [InlineKeyboardButton(msg("btn_plan_activity", lang), callback_data="plan_activity")],
        [
            InlineKeyboardButton(msg("btn_import_csv", lang), callback_data="import_csv"),
            InlineKeyboardButton(msg("btn_import_health", lang), callback_data="import_health"),
        ],
        [InlineKeyboardButton(msg("btn_report", lang), callback_data="report")],
        [
            InlineKeyboardButton(msg("btn_settings", lang), callback_data="settings"),
            InlineKeyboardButton(msg("btn_help", lang), callback_data="help"),
        ],
    ])
    return InlineKeyboardMarkup(rows)


def activity_menu(lang: str = "it") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(msg("btn_cycling", lang), callback_data="activity_cycling"),
            InlineKeyboardButton(msg("btn_walking", lang), callback_data="activity_walking"),
        ],
        [
            InlineKeyboardButton(msg("btn_running", lang), callback_data="activity_running"),
            InlineKeyboardButton(msg("btn_gym", lang), callback_data="activity_gym"),
        ],
        [InlineKeyboardButton(msg("btn_share_location", lang), callback_data="share_location")],
        [InlineKeyboardButton(msg("btn_back", lang), callback_data="main_menu")],
    ])


def report_menu(lang: str = "it") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(msg("btn_report_today", lang), callback_data="report_today"),
            InlineKeyboardButton(msg("btn_report_week", lang), callback_data="report_week"),
            InlineKeyboardButton(msg("btn_report_month", lang), callback_data="report_month"),
        ],
        [InlineKeyboardButton(msg("btn_back", lang), callback_data="main_menu")],
    ])


def settings_menu(lang: str = "it", voice_reply: bool = False) -> InlineKeyboardMarkup:
    voice_key = "btn_voice_reply_on" if voice_reply else "btn_voice_reply_off"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(msg("btn_language", lang), callback_data="set_language")],
        [InlineKeyboardButton(msg("btn_ai_model", lang), callback_data="set_ai_model")],
        [InlineKeyboardButton(msg(voice_key, lang), callback_data="toggle_voice_reply")],
        [InlineKeyboardButton(msg("btn_back", lang), callback_data="main_menu")],
    ])


def language_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇮🇹 Italiano", callback_data="lang_it"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
        ],
        [
            InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es"),
            InlineKeyboardButton("🇫🇷 Français", callback_data="lang_fr"),
        ],
        [InlineKeyboardButton("⬅️", callback_data="settings")],
    ])


def waiver_menu(lang: str = "it") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(msg("btn_accept_waiver", lang), callback_data="waiver_accept"),
            InlineKeyboardButton(msg("btn_decline_waiver", lang), callback_data="waiver_decline"),
        ],
    ])


def confirm_cancel_menu(lang: str = "it") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(msg("btn_confirm", lang), callback_data="confirm"),
            InlineKeyboardButton(msg("btn_cancel", lang), callback_data="cancel"),
        ],
    ])
