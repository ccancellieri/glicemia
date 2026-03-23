"""REST API endpoints for the GliceMia Mini App."""

import json
import logging
from datetime import datetime, timedelta

from aiohttp import web

from app.config import settings
from app.database import get_session
from app.models import (
    GlucoseReading, PumpStatus, BolusEvent, Meal,
    PatientProfile, Condition, Activity, GlucosePattern,
    InsulinSetting,
)
from app.analytics.metrics import compute_metrics, time_slot_analysis
from app.webapp.auth import validate_init_data

log = logging.getLogger(__name__)


def _auth(request) -> dict | None:
    """Validate request auth. Returns user dict or None."""
    init_data = request.headers.get("Authorization", "")
    if init_data.startswith("tma "):
        init_data = init_data[4:]
    return validate_init_data(init_data)


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
    if not _auth(request):
        return _err("unauthorized", 403)

    session = get_session()
    try:
        now = datetime.utcnow()

        # Latest glucose
        latest_sg = (
            session.query(GlucoseReading)
            .filter(GlucoseReading.sg.isnot(None))
            .order_by(GlucoseReading.timestamp.desc())
            .first()
        )

        # Latest pump status
        latest_pump = (
            session.query(PumpStatus)
            .order_by(PumpStatus.timestamp.desc())
            .first()
        )

        # Recent readings for trend (last 30 min)
        recent = (
            session.query(GlucoseReading)
            .filter(
                GlucoseReading.timestamp >= now - timedelta(minutes=30),
                GlucoseReading.sg.isnot(None),
            )
            .order_by(GlucoseReading.timestamp.asc())
            .all()
        )

        # Trend calculation
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

        # Predictions
        pred_30 = None
        pred_60 = None
        if latest_sg:
            pred_30 = round(latest_sg.sg + trend_rate * 30)
            pred_60 = round(latest_sg.sg + trend_rate * 60)

        # 3h sparkline
        sparkline = (
            session.query(GlucoseReading)
            .filter(
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
            "predictions": {
                "min30": pred_30,
                "min60": pred_60,
            },
            "sparkline": [
                {"t": r.timestamp.isoformat(), "v": r.sg}
                for r in sparkline
            ],
        }
        return _json(data)
    finally:
        session.close()


async def get_readings(request):
    """Glucose readings for chart."""
    if not _auth(request):
        return _err("unauthorized", 403)

    hours = int(request.query.get("hours", "24"))
    hours = min(hours, 720)  # max 30 days

    session = get_session()
    try:
        since = datetime.utcnow() - timedelta(hours=hours)
        readings = (
            session.query(GlucoseReading)
            .filter(
                GlucoseReading.timestamp >= since,
                GlucoseReading.sg.isnot(None),
            )
            .order_by(GlucoseReading.timestamp.asc())
            .all()
        )

        # Thin data for large ranges (max ~2000 points)
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
    if not _auth(request):
        return _err("unauthorized", 403)

    period = request.query.get("period", "week")
    period_map = {"today": 1, "week": 7, "month": 30, "3month": 90}
    days = period_map.get(period, 7)

    session = get_session()
    try:
        now = datetime.utcnow()
        start = now - timedelta(days=days)
        metrics = compute_metrics(session, start, now)
        slots = time_slot_analysis(session, start, now)
        return _json({"metrics": metrics, "slots": slots, "period": period, "days": days})
    finally:
        session.close()


async def get_patterns(request):
    """Pre-computed glucose patterns."""
    if not _auth(request):
        return _err("unauthorized", 403)

    period_type = request.query.get("type", "hourly")

    session = get_session()
    try:
        patterns = (
            session.query(GlucosePattern)
            .filter_by(period_type=period_type)
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
    if not _auth(request):
        return _err("unauthorized", 403)

    hours = int(request.query.get("hours", "24"))
    session = get_session()
    try:
        since = datetime.utcnow() - timedelta(hours=hours)
        boluses = (
            session.query(BolusEvent)
            .filter(BolusEvent.timestamp >= since)
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
    if not _auth(request):
        return _err("unauthorized", 403)

    hours = int(request.query.get("hours", "48"))
    session = get_session()
    try:
        since = datetime.utcnow() - timedelta(hours=hours)
        meals = (
            session.query(Meal)
            .filter(Meal.timestamp >= since)
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
    if not _auth(request):
        return _err("unauthorized", 403)

    days = int(request.query.get("days", "30"))
    session = get_session()
    try:
        since = datetime.utcnow() - timedelta(days=days)
        activities = (
            session.query(Activity)
            .filter(Activity.timestamp_start >= since)
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
    if not _auth(request):
        return _err("unauthorized", 403)

    session = get_session()
    try:
        conditions = (
            session.query(Condition)
            .filter(Condition.clinical_status.in_(["active", "recurrence"]))
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
    if not _auth(request):
        return _err("unauthorized", 403)

    session = get_session()
    try:
        p = session.query(PatientProfile).first()
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
    user = _auth(request)
    if not user:
        return _err("unauthorized", 403)

    body = await request.json()
    message = body.get("message", "").strip()
    if not message:
        return _err("empty message")

    from app.ai.llm import chat as ai_chat
    from app.ai.system_prompt import build_system_prompt
    from app.ai.context import build_context

    session = get_session()
    try:
        ctx = build_context(session)
        system_prompt = build_system_prompt(
            settings.PATIENT_NAME, settings.LANGUAGE, ctx
        )

        response = await ai_chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ])

        return _json({"response": response})
    finally:
        session.close()


async def get_insulin_settings(request):
    """Current insulin settings (I:C, ISF by time of day)."""
    if not _auth(request):
        return _err("unauthorized", 403)

    session = get_session()
    try:
        settings_list = (
            session.query(InsulinSetting)
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
    user = _auth(request)
    if not user:
        return _err("unauthorized", 403)

    body = await request.json()
    photo_b64 = body.get("photo", "")
    caption = body.get("caption", "")
    if not photo_b64:
        return _err("no photo")

    from app.bot.food import analyze_food_photo

    session = get_session()
    try:
        result = await analyze_food_photo(
            photo_b64, caption, session,
            settings.PATIENT_NAME, settings.LANGUAGE,
        )
        return _json({"analysis": result})
    finally:
        session.close()


async def post_estimate_bolus(request):
    """Estimate bolus for given carbs."""
    user = _auth(request)
    if not user:
        return _err("unauthorized", 403)

    body = await request.json()
    carbs = body.get("carbs", 0)
    if carbs <= 0:
        return _err("carbs must be > 0")

    from app.analytics.estimator import estimate_bolus

    session = get_session()
    try:
        result = estimate_bolus(session, carbs_g=carbs)
        return _json(result)
    finally:
        session.close()


async def post_predict_glucose(request):
    """Predict glucose at a future time point."""
    user = _auth(request)
    if not user:
        return _err("unauthorized", 403)

    body = await request.json()
    minutes = body.get("minutes", 60)
    carbs = body.get("carbs", 0)
    bolus = body.get("bolus", 0)

    from app.analytics.estimator import predict_glucose

    session = get_session()
    try:
        result = predict_glucose(session, minutes, carbs, bolus)
        return _json(result)
    finally:
        session.close()


async def post_plan_activity(request):
    """Plan an activity with glucose prediction."""
    user = _auth(request)
    if not user:
        return _err("unauthorized", 403)

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

    session = get_session()
    try:
        # Get activity impact estimate
        impact = estimate_activity_impact(session, activity_type, duration, intensity)

        # If coordinates provided, get route info
        route_info = None
        if start_lat and start_lon and end_lat and end_lon:
            from app.activity.planner import plan_route
            route_info = plan_route(
                (start_lat, start_lon), (end_lat, end_lon), activity_type
            )

        # Weather if location available
        weather = None
        lat = start_lat or end_lat
        lon = start_lon or end_lon
        if lat and lon:
            from app.activity.weather import get_current_weather
            weather = get_current_weather(lat, lon)

        # Calories estimate
        from app.activity.calories import estimate_calories
        weight = 60  # default
        profile = session.query(PatientProfile).first()
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
    if not _auth(request):
        return _err("unauthorized", 403)

    from app.alerts.engine import check_alerts

    session = get_session()
    try:
        alerts = check_alerts(session)
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
    """Get all UI translations for the configured language."""
    if not _auth(request):
        return _err("unauthorized", 403)

    lang = request.query.get("lang", settings.LANGUAGE)
    translations = {
        "it": {
            "home": "Home", "charts": "Grafici", "food": "Cibo", "activity": "Attivita",
            "reports": "Report", "chat": "Chat", "profile": "Profilo",
            "pump": "Pompa", "last_3h": "Ultime 3 ore", "today": "Oggi",
            "quick_actions": "Azioni rapide", "analyze_food": "Analizza cibo",
            "plan_activity": "Attivita", "report": "Report", "ask": "Chiedi",
            "estimate_bolus": "Stima bolo", "prediction": "Previsione",
            "glucose": "Glicemia", "hourly_patterns": "Pattern orari (14 giorni)",
            "no_pattern": "Nessun pattern", "camera_or": "oppure",
            "choose_gallery": "Scegli dalla galleria",
            "caption_hint": "Descrizione (opzionale): es. pasta al pesto",
            "analyze": "Analizza", "analyzing": "Analizzando...", "result": "Risultato",
            "no_result": "Nessun risultato",
            "activity_type": "Tipo di attivita", "duration_intensity": "Durata e intensita",
            "duration": "Durata", "intensity": "Intensita",
            "light": "Leggera", "moderate": "Moderata", "intense": "Intensa",
            "position": "Posizione", "tap_start": "Tocca per partenza (GPS)",
            "tap_end": "Tocca per destinazione (GPS)", "locating": "Localizzazione...",
            "calculate_plan": "Calcola piano", "activity_plan": "Piano attivita",
            "route": "Percorso", "estimated_calories": "Calorie stimate",
            "glucose_impact": "Impatto glicemico", "estimated_delta": "Delta stimato",
            "estimated_after": "Glicemia stimata dopo",
            "tir": "Time in Range", "metrics": "Metriche", "slot_analysis": "Analisi fasce orarie",
            "week": "Settimana", "month": "Mese", "three_months": "3 Mesi",
            "slot": "Fascia", "mean": "Media", "notes": "Note",
            "readings": "Letture", "bolus_day": "Boli/giorno", "below_70": "Sotto 70", "above_180": "Sopra 180",
            "write_message": "Scrivi un messaggio...",
            "chat_welcome": "Ciao! Sono GliceMia. Chiedimi qualsiasi cosa sulla gestione del diabete.",
            "patient_profile": "Profilo paziente", "active_conditions": "Condizioni attive",
            "insulin_settings": "Impostazioni insulina", "no_conditions": "Nessuna condizione attiva",
            "no_settings": "Nessuna impostazione",
            "name": "Nome", "type": "Tipo", "pump_label": "Pompa", "sensor": "Sensore",
            "diet": "Dieta", "language": "Lingua", "time": "Orario", "target": "Target",
            "min_ago": "min fa", "h_ago": "h fa",
            "cycling": "Bici", "walking": "Camminata", "running": "Corsa", "gym": "Palestra",
            "swimming": "Nuoto", "hiking": "Escursione", "yoga": "Yoga", "other": "Altro",
            "gps_unavailable": "GPS non disponibile", "gps_error": "Errore GPS",
            "mic_unavailable": "Microfono non disponibile", "voice_msg": "Messaggio vocale",
            "carbs_prompt": "Grammi di carboidrati:", "error": "Errore", "no_data": "Nessun dato",
            "bolus_food": "Bolo cibo", "correction": "Correzione", "total": "Totale",
            "glucose_2h": "Glicemia 2h", "current": "Attuale", "predicted": "Prevista",
            "range": "Range", "trend": "Trend",
        },
        "en": {
            "home": "Home", "charts": "Charts", "food": "Food", "activity": "Activity",
            "reports": "Reports", "chat": "Chat", "profile": "Profile",
            "pump": "Pump", "last_3h": "Last 3 hours", "today": "Today",
            "quick_actions": "Quick actions", "analyze_food": "Analyze food",
            "plan_activity": "Activity", "report": "Report", "ask": "Ask",
            "estimate_bolus": "Bolus estimate", "prediction": "Prediction",
            "glucose": "Glucose", "hourly_patterns": "Hourly patterns (14 days)",
            "no_pattern": "No patterns", "camera_or": "or",
            "choose_gallery": "Choose from gallery",
            "caption_hint": "Description (optional): e.g. pesto pasta",
            "analyze": "Analyze", "analyzing": "Analyzing...", "result": "Result",
            "no_result": "No result",
            "activity_type": "Activity type", "duration_intensity": "Duration & intensity",
            "duration": "Duration", "intensity": "Intensity",
            "light": "Light", "moderate": "Moderate", "intense": "Intense",
            "position": "Location", "tap_start": "Tap for start (GPS)",
            "tap_end": "Tap for destination (GPS)", "locating": "Locating...",
            "calculate_plan": "Calculate plan", "activity_plan": "Activity plan",
            "route": "Route", "estimated_calories": "Estimated calories",
            "glucose_impact": "Glucose impact", "estimated_delta": "Estimated delta",
            "estimated_after": "Estimated glucose after",
            "tir": "Time in Range", "metrics": "Metrics", "slot_analysis": "Time slot analysis",
            "week": "Week", "month": "Month", "three_months": "3 Months",
            "slot": "Slot", "mean": "Mean", "notes": "Notes",
            "readings": "Readings", "bolus_day": "Boluses/day", "below_70": "Below 70", "above_180": "Above 180",
            "write_message": "Write a message...",
            "chat_welcome": "Hi! I'm GliceMia. Ask me anything about diabetes management.",
            "patient_profile": "Patient profile", "active_conditions": "Active conditions",
            "insulin_settings": "Insulin settings", "no_conditions": "No active conditions",
            "no_settings": "No settings",
            "name": "Name", "type": "Type", "pump_label": "Pump", "sensor": "Sensor",
            "diet": "Diet", "language": "Language", "time": "Time", "target": "Target",
            "min_ago": "min ago", "h_ago": "h ago",
            "cycling": "Cycling", "walking": "Walking", "running": "Running", "gym": "Gym",
            "swimming": "Swimming", "hiking": "Hiking", "yoga": "Yoga", "other": "Other",
            "gps_unavailable": "GPS unavailable", "gps_error": "GPS error",
            "mic_unavailable": "Microphone unavailable", "voice_msg": "Voice message",
            "carbs_prompt": "Grams of carbohydrates:", "error": "Error", "no_data": "No data",
            "bolus_food": "Food bolus", "correction": "Correction", "total": "Total",
            "glucose_2h": "Glucose 2h", "current": "Current", "predicted": "Predicted",
            "range": "Range", "trend": "Trend",
        },
        "es": {
            "home": "Inicio", "charts": "Graficos", "food": "Comida", "activity": "Actividad",
            "reports": "Informes", "chat": "Chat", "profile": "Perfil",
            "pump": "Bomba", "last_3h": "Ultimas 3 horas", "today": "Hoy",
            "quick_actions": "Acciones rapidas", "analyze_food": "Analizar comida",
            "plan_activity": "Actividad", "report": "Informe", "ask": "Preguntar",
            "estimate_bolus": "Estimar bolo", "prediction": "Prediccion",
            "glucose": "Glucosa", "hourly_patterns": "Patrones horarios (14 dias)",
            "no_pattern": "Sin patrones", "camera_or": "o",
            "choose_gallery": "Elegir de galeria",
            "caption_hint": "Descripcion (opcional): ej. pasta al pesto",
            "analyze": "Analizar", "analyzing": "Analizando...", "result": "Resultado",
            "no_result": "Sin resultado",
            "activity_type": "Tipo de actividad", "duration_intensity": "Duracion e intensidad",
            "duration": "Duracion", "intensity": "Intensidad",
            "light": "Ligera", "moderate": "Moderada", "intense": "Intensa",
            "position": "Ubicacion", "tap_start": "Toca para inicio (GPS)",
            "tap_end": "Toca para destino (GPS)", "locating": "Localizando...",
            "calculate_plan": "Calcular plan", "activity_plan": "Plan de actividad",
            "route": "Ruta", "estimated_calories": "Calorias estimadas",
            "glucose_impact": "Impacto glucemico", "estimated_delta": "Delta estimado",
            "estimated_after": "Glucosa estimada despues",
            "tir": "Tiempo en Rango", "metrics": "Metricas", "slot_analysis": "Analisis por franja horaria",
            "week": "Semana", "month": "Mes", "three_months": "3 Meses",
            "slot": "Franja", "mean": "Media", "notes": "Notas",
            "readings": "Lecturas", "bolus_day": "Bolos/dia", "below_70": "Bajo 70", "above_180": "Sobre 180",
            "write_message": "Escribe un mensaje...",
            "chat_welcome": "Hola! Soy GliceMia. Preguntame lo que quieras sobre la gestion de la diabetes.",
            "patient_profile": "Perfil del paciente", "active_conditions": "Condiciones activas",
            "insulin_settings": "Ajustes de insulina", "no_conditions": "Sin condiciones activas",
            "no_settings": "Sin ajustes",
            "name": "Nombre", "type": "Tipo", "pump_label": "Bomba", "sensor": "Sensor",
            "diet": "Dieta", "language": "Idioma", "time": "Hora", "target": "Objetivo",
            "min_ago": "min", "h_ago": "h",
            "cycling": "Bici", "walking": "Caminar", "running": "Correr", "gym": "Gimnasio",
            "swimming": "Nadar", "hiking": "Senderismo", "yoga": "Yoga", "other": "Otro",
            "gps_unavailable": "GPS no disponible", "gps_error": "Error GPS",
            "mic_unavailable": "Microfono no disponible", "voice_msg": "Mensaje de voz",
            "carbs_prompt": "Gramos de carbohidratos:", "error": "Error", "no_data": "Sin datos",
            "bolus_food": "Bolo comida", "correction": "Correccion", "total": "Total",
            "glucose_2h": "Glucosa 2h", "current": "Actual", "predicted": "Prevista",
            "range": "Rango", "trend": "Tendencia",
        },
        "fr": {
            "home": "Accueil", "charts": "Graphiques", "food": "Repas", "activity": "Activite",
            "reports": "Rapports", "chat": "Chat", "profile": "Profil",
            "pump": "Pompe", "last_3h": "3 dernieres heures", "today": "Aujourd'hui",
            "quick_actions": "Actions rapides", "analyze_food": "Analyser repas",
            "plan_activity": "Activite", "report": "Rapport", "ask": "Demander",
            "estimate_bolus": "Estimer bolus", "prediction": "Prediction",
            "glucose": "Glycemie", "hourly_patterns": "Patterns horaires (14 jours)",
            "no_pattern": "Aucun pattern", "camera_or": "ou",
            "choose_gallery": "Choisir de la galerie",
            "caption_hint": "Description (optionnel): ex. pates au pesto",
            "analyze": "Analyser", "analyzing": "Analyse...", "result": "Resultat",
            "no_result": "Aucun resultat",
            "activity_type": "Type d'activite", "duration_intensity": "Duree et intensite",
            "duration": "Duree", "intensity": "Intensite",
            "light": "Legere", "moderate": "Moderee", "intense": "Intense",
            "position": "Position", "tap_start": "Appuyez pour depart (GPS)",
            "tap_end": "Appuyez pour destination (GPS)", "locating": "Localisation...",
            "calculate_plan": "Calculer le plan", "activity_plan": "Plan d'activite",
            "route": "Itineraire", "estimated_calories": "Calories estimees",
            "glucose_impact": "Impact glycemique", "estimated_delta": "Delta estime",
            "estimated_after": "Glycemie estimee apres",
            "tir": "Temps dans la cible", "metrics": "Metriques", "slot_analysis": "Analyse par tranche horaire",
            "week": "Semaine", "month": "Mois", "three_months": "3 Mois",
            "slot": "Tranche", "mean": "Moyenne", "notes": "Notes",
            "readings": "Lectures", "bolus_day": "Bolus/jour", "below_70": "Sous 70", "above_180": "Au-dessus 180",
            "write_message": "Ecrivez un message...",
            "chat_welcome": "Bonjour! Je suis GliceMia. Posez-moi toute question sur la gestion du diabete.",
            "patient_profile": "Profil patient", "active_conditions": "Conditions actives",
            "insulin_settings": "Parametres insuline", "no_conditions": "Aucune condition active",
            "no_settings": "Aucun parametre",
            "name": "Nom", "type": "Type", "pump_label": "Pompe", "sensor": "Capteur",
            "diet": "Regime", "language": "Langue", "time": "Heure", "target": "Cible",
            "min_ago": "min", "h_ago": "h",
            "cycling": "Velo", "walking": "Marche", "running": "Course", "gym": "Salle",
            "swimming": "Natation", "hiking": "Randonnee", "yoga": "Yoga", "other": "Autre",
            "gps_unavailable": "GPS indisponible", "gps_error": "Erreur GPS",
            "mic_unavailable": "Micro indisponible", "voice_msg": "Message vocal",
            "carbs_prompt": "Grammes de glucides:", "error": "Erreur", "no_data": "Pas de donnees",
            "bolus_food": "Bolus repas", "correction": "Correction", "total": "Total",
            "glucose_2h": "Glycemie 2h", "current": "Actuelle", "predicted": "Prevue",
            "range": "Plage", "trend": "Tendance",
        },
    }
    return _json(translations.get(lang, translations["it"]))


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
