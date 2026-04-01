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
        [
            InlineKeyboardButton(msg("btn_sg_enter", lang), callback_data="sg_enter"),
            InlineKeyboardButton(msg("btn_food_photo", lang), callback_data="food_photo"),
        ],
        [
            InlineKeyboardButton(msg("btn_whatif", lang), callback_data="whatif_menu"),
            InlineKeyboardButton(msg("btn_plan_activity", lang), callback_data="plan_activity"),
        ],
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


def glucose_range_menu(lang: str = "it") -> InlineKeyboardMarkup:
    """Step 1: select a glucose range bucket."""
    ranges = [
        ("< 70", "sg_range:40:70"),
        ("70–120", "sg_range:70:120"),
        ("120–180", "sg_range:120:180"),
        ("180–250", "sg_range:180:250"),
        ("> 250", "sg_range:250:400"),
    ]
    rows = [[InlineKeyboardButton(label, callback_data=cb)] for label, cb in ranges]
    rows.append([InlineKeyboardButton(msg("btn_back", lang), callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)


def glucose_value_menu(low: int, high: int, lang: str = "it") -> InlineKeyboardMarkup:
    """Step 2: pick an exact value within the selected range."""
    step = 5 if (high - low) <= 60 else 10
    row, rows = [], []
    for v in range(low, high + 1, step):
        row.append(InlineKeyboardButton(str(v), callback_data=f"sg_val:{v}"))
        if len(row) >= 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(msg("btn_back", lang), callback_data="sg_enter")])
    return InlineKeyboardMarkup(rows)


def glucose_trend_menu(sg_value: int, lang: str = "it") -> InlineKeyboardMarkup:
    """Step 3: select the trend arrow direction."""
    trends = [
        ("⬆⬆ " + msg("btn_trend_up_fast", lang), f"sg_trend:{sg_value}:UP_FAST"),
        ("⬆ " + msg("btn_trend_up", lang), f"sg_trend:{sg_value}:UP"),
        ("➡ " + msg("btn_trend_flat", lang), f"sg_trend:{sg_value}:FLAT"),
        ("⬇ " + msg("btn_trend_down", lang), f"sg_trend:{sg_value}:DOWN"),
        ("⬇⬇ " + msg("btn_trend_down_fast", lang), f"sg_trend:{sg_value}:DOWN_FAST"),
    ]
    rows = [[InlineKeyboardButton(label, callback_data=cb)] for label, cb in trends]
    rows.append([InlineKeyboardButton(msg("btn_back", lang), callback_data="sg_enter")])
    return InlineKeyboardMarkup(rows)


def glucose_whatif_menu(lang: str = "it") -> InlineKeyboardMarkup:
    """What-if scenario quick buttons."""
    scenarios = [
        (msg("btn_whatif_meal", lang), "whatif_meal"),
        (msg("btn_whatif_activity", lang), "whatif_activity"),
        (msg("btn_whatif_bolus", lang), "whatif_bolus"),
    ]
    rows = [[InlineKeyboardButton(label, callback_data=cb)] for label, cb in scenarios]
    rows.append([InlineKeyboardButton(msg("btn_back", lang), callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)
