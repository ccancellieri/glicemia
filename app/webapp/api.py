"""REST API endpoints for the GliceMia Mini App — per-patient data isolation."""

import json
import logging
from datetime import datetime, timedelta

from aiohttp import web

from app.config import settings
from app.database import get_session
from app.models import (
    GlucoseReading, PumpStatus, BolusEvent, Meal,
    PatientProfile, Condition, Activity, GlucosePattern,
    InsulinSetting, UserAccount,
)
from app.analytics.metrics import compute_metrics, time_slot_analysis
from app.webapp.auth import validate_init_data
from app.users import get_user

log = logging.getLogger(__name__)


def _auth_user(request, session) -> UserAccount | None:
    """Validate request auth and return the UserAccount. Returns None if unauthorized."""
    init_data = request.headers.get("Authorization", "")
    if init_data.startswith("tma "):
        init_data = init_data[4:]
    user_data = validate_init_data(init_data)
    if not user_data:
        return None
    tg_id = user_data.get("id")
    if not tg_id:
        return None
    return get_user(session, int(tg_id))


def _json(data, ok=True):
    return web.json_response({
        "ok": ok,
        "data": data,
        "ts": datetime.utcnow().isoformat() + "Z",
    }, dumps=lambda x: json.dumps(x, default=str))


def _err(msg, status=400):
    return web.json_response({"ok": False, "error": msg}, status=status)


async def get_status(request):
    """Current glucose, pump status, trend, predictions."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)
        pid = user.telegram_user_id

        now = datetime.utcnow()

        latest_sg = (
            session.query(GlucoseReading)
            .filter(GlucoseReading.patient_id == pid, GlucoseReading.sg.isnot(None))
            .order_by(GlucoseReading.timestamp.desc())
            .first()
        )

        latest_pump = (
            session.query(PumpStatus)
            .filter_by(patient_id=pid)
            .order_by(PumpStatus.timestamp.desc())
            .first()
        )

        recent = (
            session.query(GlucoseReading)
            .filter(
                GlucoseReading.patient_id == pid,
                GlucoseReading.timestamp >= now - timedelta(minutes=30),
                GlucoseReading.sg.isnot(None),
            )
            .order_by(GlucoseReading.timestamp.asc())
            .all()
        )

        trend = "FLAT"
        trend_rate = 0.0
        if len(recent) >= 2:
            delta = recent[-1].sg - recent[0].sg
            minutes = (recent[-1].timestamp - recent[0].timestamp).total_seconds() / 60
            if minutes > 0:
                trend_rate = delta / minutes
                if trend_rate > 2:
                    trend = "RISING_FAST"
                elif trend_rate > 1:
                    trend = "RISING"
                elif trend_rate < -2:
                    trend = "FALLING_FAST"
                elif trend_rate < -1:
                    trend = "FALLING"

        pred_30 = None
        pred_60 = None
        if latest_sg:
            pred_30 = round(latest_sg.sg + trend_rate * 30)
            pred_60 = round(latest_sg.sg + trend_rate * 60)

        sparkline = (
            session.query(GlucoseReading)
            .filter(
                GlucoseReading.patient_id == pid,
                GlucoseReading.timestamp >= now - timedelta(hours=3),
                GlucoseReading.sg.isnot(None),
            )
            .order_by(GlucoseReading.timestamp.asc())
            .all()
        )

        data = {
            "glucose": {
                "value": latest_sg.sg if latest_sg else None,
                "timestamp": latest_sg.timestamp.isoformat() if latest_sg else None,
                "trend": latest_sg.trend or trend if latest_sg else None,
                "trend_rate": round(trend_rate, 2),
                "age_minutes": round((now - latest_sg.timestamp).total_seconds() / 60) if latest_sg else None,
            },
            "pump": {
                "iob": latest_pump.active_insulin if latest_pump else None,
                "basal": latest_pump.basal_rate if latest_pump else None,
                "reservoir": latest_pump.reservoir_units if latest_pump else None,
                "battery": latest_pump.battery_pct if latest_pump else None,
                "mode": latest_pump.auto_mode if latest_pump else None,
            } if latest_pump else None,
            "predictions": {"min30": pred_30, "min60": pred_60},
            "sparkline": [{"t": r.timestamp.isoformat(), "v": r.sg} for r in sparkline],
        }
        return _json(data)
    finally:
        session.close()


async def get_readings(request):
    """Glucose readings for chart."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)
        pid = user.telegram_user_id

        hours = min(int(request.query.get("hours", "24")), 720)
        since = datetime.utcnow() - timedelta(hours=hours)
        readings = (
            session.query(GlucoseReading)
            .filter(
                GlucoseReading.patient_id == pid,
                GlucoseReading.timestamp >= since,
                GlucoseReading.sg.isnot(None),
            )
            .order_by(GlucoseReading.timestamp.asc())
            .all()
        )

        step = max(1, len(readings) // 2000)
        data = [
            {"t": r.timestamp.isoformat(), "v": r.sg}
            for i, r in enumerate(readings) if i % step == 0
        ]
        return _json(data)
    finally:
        session.close()


async def get_metrics(request):
    """TIR, GMI, CV and other metrics."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)
        pid = user.telegram_user_id

        period = request.query.get("period", "week")
        period_map = {"today": 1, "week": 7, "month": 30, "3month": 90}
        days = period_map.get(period, 7)

        now = datetime.utcnow()
        start = now - timedelta(days=days)
        metrics = compute_metrics(session, start, now, patient_id=pid)
        slots = time_slot_analysis(session, start, now, patient_id=pid)
        return _json({"metrics": metrics, "slots": slots, "period": period, "days": days})
    finally:
        session.close()


async def get_patterns(request):
    """Pre-computed glucose patterns."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)
        pid = user.telegram_user_id

        period_type = request.query.get("type", "hourly")
        patterns = (
            session.query(GlucosePattern)
            .filter_by(patient_id=pid, period_type=period_type)
            .order_by(GlucosePattern.period_key)
            .all()
        )
        data = [
            {
                "key": p.period_key,
                "avg": p.avg_sg, "std": p.std_sg,
                "tir": p.tir_pct, "hypo": p.hypo_count,
                "n": p.sample_count,
            }
            for p in patterns
        ]
        return _json(data)
    finally:
        session.close()


async def get_boluses(request):
    """Recent bolus events."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)
        pid = user.telegram_user_id

        hours = int(request.query.get("hours", "24"))
        since = datetime.utcnow() - timedelta(hours=hours)
        boluses = (
            session.query(BolusEvent)
            .filter(BolusEvent.patient_id == pid, BolusEvent.timestamp >= since)
            .order_by(BolusEvent.timestamp.desc())
            .all()
        )
        data = [
            {
                "t": b.timestamp.isoformat(),
                "units": b.volume_units,
                "type": b.bolus_type,
                "source": b.bolus_source,
                "carbs": b.bwz_carb_input,
            }
            for b in boluses
        ]
        return _json(data)
    finally:
        session.close()


async def get_meals(request):
    """Recent meals."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)
        pid = user.telegram_user_id

        hours = int(request.query.get("hours", "48"))
        since = datetime.utcnow() - timedelta(hours=hours)
        meals = (
            session.query(Meal)
            .filter(Meal.patient_id == pid, Meal.timestamp >= since)
            .order_by(Meal.timestamp.desc())
            .all()
        )
        data = [
            {
                "t": m.timestamp.isoformat(),
                "carbs": m.carbs_g,
                "description": m.description,
                "source": m.source,
            }
            for m in meals
        ]
        return _json(data)
    finally:
        session.close()


async def get_activities(request):
    """Recent activities."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)
        pid = user.telegram_user_id

        days = int(request.query.get("days", "30"))
        since = datetime.utcnow() - timedelta(days=days)
        activities = (
            session.query(Activity)
            .filter(Activity.patient_id == pid, Activity.timestamp_start >= since)
            .order_by(Activity.timestamp_start.desc())
            .all()
        )
        data = [
            {
                "type": a.activity_type,
                "start": a.timestamp_start.isoformat(),
                "duration": a.duration_min,
                "distance": a.distance_km,
                "calories": a.calories_est,
                "start_sg": a.start_sg,
                "end_sg": a.end_sg,
                "delta": a.sg_delta,
            }
            for a in activities
        ]
        return _json(data)
    finally:
        session.close()


async def get_conditions(request):
    """Active medical conditions."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)
        pid = user.telegram_user_id

        conditions = (
            session.query(Condition)
            .filter(
                Condition.patient_id == pid,
                Condition.clinical_status.in_(["active", "recurrence"]),
            )
            .all()
        )
        data = [
            {
                "name": c.display_name,
                "snomed": c.snomed_code,
                "icd": c.icd_code,
                "severity": c.severity,
                "status": c.clinical_status,
            }
            for c in conditions
        ]
        return _json(data)
    finally:
        session.close()


async def get_profile(request):
    """Patient profile."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)
        pid = user.telegram_user_id

        p = session.query(PatientProfile).filter_by(patient_id=pid).first()
        if not p:
            return _json(None)
        return _json({
            "name": p.name,
            "diabetes_type": p.diabetes_type,
            "pump": p.pump_model,
            "sensor": p.sensor_model,
            "diet": p.diet,
            "language": p.language,
        })
    finally:
        session.close()


async def post_chat(request):
    """Send a message to the AI and get a response."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)
        pid = user.telegram_user_id

        body = await request.json()
        message = body.get("message", "").strip()
        if not message:
            return _err("empty message")

        from app.ai.llm import chat as ai_chat
        from app.ai.system_prompt import build_system_prompt
        from app.ai.context import build_context

        ctx = build_context(session, patient_id=pid)
        system_prompt = build_system_prompt(
            user.patient_name, user.language or "it", ctx
        )

        response = await ai_chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            user=user,
        )

        return _json({"response": response})
    except Exception:
        log.exception("Error in post_chat")
        return _err("Internal error", 500)
    finally:
        session.close()


async def get_insulin_settings(request):
    """Current insulin settings (I:C, ISF by time of day)."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)
        pid = user.telegram_user_id

        settings_list = (
            session.query(InsulinSetting)
            .filter_by(patient_id=pid)
            .order_by(InsulinSetting.time_start)
            .all()
        )
        data = [
            {
                "time_start": s.time_start,
                "ic_ratio": s.ic_ratio,
                "isf": s.isf,
                "target": s.target_sg,
                "source": s.source,
            }
            for s in settings_list
        ]
        return _json(data)
    finally:
        session.close()


async def post_analyze_food(request):
    """Analyze a food photo (base64) and return carb estimate + bolus suggestion."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)

        body = await request.json()
        photo_b64 = body.get("photo", "")
        caption = body.get("caption", "")
        if not photo_b64:
            return _err("no photo")

        from app.bot.food import analyze_food_photo

        result = await analyze_food_photo(
            photo_b64, caption, session,
            user.patient_name, user.language or "it",
            patient_id=user.telegram_user_id, user=user,
        )
        return _json({"analysis": result})
    except Exception:
        log.exception("Error in post_analyze_food")
        return _err("Internal error", 500)
    finally:
        session.close()


async def post_estimate_bolus(request):
    """Estimate bolus for given carbs."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)
        pid = user.telegram_user_id

        body = await request.json()
        carbs = body.get("carbs", 0)
        if carbs <= 0:
            return _err("carbs must be > 0")

        from app.analytics.estimator import estimate_bolus
        result = estimate_bolus(session, carbs_g=carbs, patient_id=pid)
        return _json(result)
    finally:
        session.close()


async def post_predict_glucose(request):
    """Predict glucose at a future time point."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)
        pid = user.telegram_user_id

        body = await request.json()
        minutes = body.get("minutes", 60)
        carbs = body.get("carbs", 0)
        bolus = body.get("bolus", 0)

        from app.analytics.estimator import predict_glucose
        result = predict_glucose(session, minutes, carbs, bolus, patient_id=pid)
        return _json(result)
    finally:
        session.close()


async def post_plan_activity(request):
    """Plan an activity with glucose prediction."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)
        pid = user.telegram_user_id

        body = await request.json()
        activity_type = body.get("type", "cycling")
        duration = body.get("duration", 60)
        intensity = body.get("intensity", "moderate")
        start_lat = body.get("start_lat")
        start_lon = body.get("start_lon")
        end_lat = body.get("end_lat")
        end_lon = body.get("end_lon")

        from app.activity.tracker import plan_activity
        from app.analytics.estimator import estimate_activity_impact

        impact = estimate_activity_impact(session, activity_type, duration, intensity, patient_id=pid)

        route_info = None
        if start_lat and start_lon and end_lat and end_lon:
            from app.activity.planner import plan_route
            route_info = plan_route(
                (start_lat, start_lon), (end_lat, end_lon), activity_type
            )

        weather = None
        lat = start_lat or end_lat
        lon = start_lon or end_lon
        if lat and lon:
            from app.activity.weather import get_current_weather
            weather = get_current_weather(lat, lon)

        from app.activity.calories import estimate_calories
        weight = 60
        profile = session.query(PatientProfile).filter_by(patient_id=pid).first()
        if profile and profile.weight_kg:
            weight = profile.weight_kg

        elevation = route_info.get("elevation_gain", 0) if route_info else 0
        calories = estimate_calories(activity_type, intensity, duration, weight, elevation)

        return _json({
            "impact": impact,
            "route": route_info,
            "weather": weather,
            "calories": calories,
            "activity_type": activity_type,
            "duration": duration,
            "intensity": intensity,
        })
    finally:
        session.close()


async def get_alerts(request):
    """Get active alerts."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)
        pid = user.telegram_user_id

        from app.alerts.engine import check_alerts
        alerts = check_alerts(session, patient_id=pid)
        data = [
            {
                "type": a.alert_type,
                "severity": a.severity,
                "sg": a.sg,
                "predicted_sg": a.predicted_sg,
                "details": a.details,
            }
            for a in alerts
        ]
        return _json(data)
    finally:
        session.close()


async def get_i18n(request):
    """Get UI translations for the authenticated user's language."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)

        lang = request.query.get("lang", user.language or "it")
        translations = _get_translations()
        return _json(translations.get(lang, translations["it"]))
    finally:
        session.close()


async def get_user_settings(request):
    """Get the authenticated user's settings for the settings page."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)

        from app.users import get_user_settings as _get_settings, get_allowed_models
        extra = _get_settings(user)
        models = get_allowed_models(user)

        return _json({
            "patient_name": user.patient_name,
            "language": user.language or "it",
            "ai_model": user.ai_model or "",
            "carelink_username": user.carelink_username or "",
            "carelink_country": user.carelink_country or "",
            "carelink_poll_interval": user.carelink_poll_interval or 300,
            "has_carelink_password": bool(user.carelink_password),
            "has_gemini_key": bool(user.gemini_api_key),
            "has_openweather_key": bool(user.openweather_api_key),
            "allowed_models": models,
            "daily_token_limit": user.daily_token_limit or 0,
            "monthly_token_limit": user.monthly_token_limit or 0,
            "tokens_used_today": user.tokens_used_today or 0,
            "tokens_used_month": user.tokens_used_month or 0,
            "is_admin": user.is_admin,
            "extra_settings": extra,
        })
    finally:
        session.close()


async def post_user_settings(request):
    """Update the authenticated user's settings."""
    session = get_session()
    try:
        user = _auth_user(request, session)
        if not user:
            return _err("unauthorized", 403)

        body = await request.json()

        # Basic profile fields (anyone can edit their own)
        if "patient_name" in body and body["patient_name"].strip():
            user.patient_name = body["patient_name"].strip()[:100]
        if "language" in body and body["language"] in ("it", "en", "es", "fr"):
            user.language = body["language"]
        if "ai_model" in body:
            user.ai_model = body["ai_model"].strip()[:200] or None

        # CareLink credentials
        if "carelink_username" in body:
            user.carelink_username = body["carelink_username"].strip()[:200] or None
        if "carelink_password" in body and body["carelink_password"]:
            user.carelink_password = body["carelink_password"]
        if "carelink_country" in body:
            user.carelink_country = body["carelink_country"].strip()[:5] or None
        if "carelink_poll_interval" in body:
            interval = int(body["carelink_poll_interval"])
            user.carelink_poll_interval = max(60, min(3600, interval))

        # API keys (only set if non-empty — never overwrite with blank)
        if "gemini_api_key" in body and body["gemini_api_key"]:
            user.gemini_api_key = body["gemini_api_key"]
        if "openweather_api_key" in body and body["openweather_api_key"]:
            user.openweather_api_key = body["openweather_api_key"]

        # Clear keys explicitly
        if body.get("clear_gemini_key"):
            user.gemini_api_key = None
        if body.get("clear_openweather_key"):
            user.openweather_api_key = None

        # Extra settings JSON
        if "extra_settings" in body and isinstance(body["extra_settings"], dict):
            from app.users import update_user_settings
            update_user_settings(session, user, **body["extra_settings"])
        else:
            session.commit()

        return _json({"updated": True})
    except (ValueError, TypeError) as e:
        return _err("Invalid settings value", 400)
    except Exception:
        log.exception("Error updating settings")
        return _err("Internal error", 500)
    finally:
        session.close()


def _get_translations() -> dict:
    """Return all UI translation dictionaries."""
    return {
        "it": {
            "home": "Home", "charts": "Grafici", "food": "Cibo", "activity": "Attivita",
            "reports": "Report", "chat": "Chat", "profile": "Profilo",
            "pump": "Pompa", "last_3h": "Ultime 3 ore", "today": "Oggi",
            "quick_actions": "Azioni rapide", "analyze_food": "Analizza cibo",
            "plan_activity": "Attivita", "report": "Report", "ask": "Chiedi",
            "estimate_bolus": "Stima bolo", "prediction": "Previsione",
            "glucose": "Glicemia", "error": "Errore", "no_data": "Nessun dato",
        },
        "en": {
            "home": "Home", "charts": "Charts", "food": "Food", "activity": "Activity",
            "reports": "Reports", "chat": "Chat", "profile": "Profile",
            "pump": "Pump", "last_3h": "Last 3 hours", "today": "Today",
            "quick_actions": "Quick actions", "analyze_food": "Analyze food",
            "plan_activity": "Activity", "report": "Report", "ask": "Ask",
            "estimate_bolus": "Bolus estimate", "prediction": "Prediction",
            "glucose": "Glucose", "error": "Error", "no_data": "No data",
        },
        "es": {
            "home": "Inicio", "charts": "Graficos", "food": "Comida", "activity": "Actividad",
            "reports": "Informes", "chat": "Chat", "profile": "Perfil",
            "pump": "Bomba", "last_3h": "Ultimas 3 horas", "today": "Hoy",
            "quick_actions": "Acciones rapidas", "analyze_food": "Analizar comida",
            "plan_activity": "Actividad", "report": "Informe", "ask": "Preguntar",
            "estimate_bolus": "Estimar bolo", "prediction": "Prediccion",
            "glucose": "Glucosa", "error": "Error", "no_data": "Sin datos",
        },
        "fr": {
            "home": "Accueil", "charts": "Graphiques", "food": "Repas", "activity": "Activite",
            "reports": "Rapports", "chat": "Chat", "profile": "Profil",
            "pump": "Pompe", "last_3h": "3 dernieres heures", "today": "Aujourd'hui",
            "quick_actions": "Actions rapides", "analyze_food": "Analyser repas",
            "plan_activity": "Activite", "report": "Rapport", "ask": "Demander",
            "estimate_bolus": "Estimer bolus", "prediction": "Prediction",
            "glucose": "Glycemie", "error": "Erreur", "no_data": "Pas de donnees",
        },
    }


def setup_routes(app: web.Application):
    """Register all API routes."""
    app.router.add_get("/api/status", get_status)
    app.router.add_get("/api/readings", get_readings)
    app.router.add_get("/api/metrics", get_metrics)
    app.router.add_get("/api/patterns", get_patterns)
    app.router.add_get("/api/boluses", get_boluses)
    app.router.add_get("/api/meals", get_meals)
    app.router.add_get("/api/activities", get_activities)
    app.router.add_get("/api/conditions", get_conditions)
    app.router.add_get("/api/profile", get_profile)
    app.router.add_get("/api/insulin", get_insulin_settings)
    app.router.add_get("/api/alerts", get_alerts)
    app.router.add_post("/api/chat", post_chat)
    app.router.add_post("/api/analyze-food", post_analyze_food)
    app.router.add_post("/api/estimate-bolus", post_estimate_bolus)
    app.router.add_post("/api/predict", post_predict_glucose)
    app.router.add_post("/api/plan-activity", post_plan_activity)
    app.router.add_get("/api/i18n", get_i18n)
    app.router.add_get("/api/settings", get_user_settings)
    app.router.add_post("/api/settings", post_user_settings)
