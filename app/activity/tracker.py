"""Activity tracker — records activities with glucose impact.

Manages the activity lifecycle: plan → start → track → complete.
Stores GPS tracks, glucose deltas, and enriches with weather data.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Activity, GlucoseReading, TripPlan
from app.activity.calories import estimate_calories, infer_intensity
from app.activity.weather import get_current_weather
from app.analytics.estimator import estimate_activity_impact, get_current_state

log = logging.getLogger(__name__)


async def plan_activity(
    session: Session,
    activity_type: str,
    route_data: Optional[dict] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    patient_name: str = "",
    weight_kg: float = 54.0,
) -> dict:
    """Create a full activity plan with route, calories, weather, glucose prediction.

    Returns a rich dict for display in Telegram.
    """
    distance_km = route_data.get("distance_km", 0) if route_data else 0
    duration_min = route_data.get("duration_min", 30) if route_data else 30
    elev_gain = route_data.get("elevation_gain_m", 0) if route_data else 0
    elev_loss = route_data.get("elevation_loss_m", 0) if route_data else 0

    # Infer intensity from route
    speed = distance_km / (duration_min / 60) if duration_min > 0 else 0
    intensity = infer_intensity(activity_type, speed, elev_gain, distance_km)

    # Calories
    cal = estimate_calories(
        activity_type, intensity, duration_min,
        weight_kg, elev_gain, distance_km,
    )

    # Weather
    weather = None
    if lat and lon:
        weather = await get_current_weather(lat, lon)

    # Glucose prediction
    glucose_impact = estimate_activity_impact(session, activity_type, duration_min, intensity)

    # Save trip plan
    plan = TripPlan(
        description=f"{activity_type} — {distance_km:.1f}km" if distance_km else activity_type,
        route_json=json.dumps(route_data) if route_data else None,
        distance_km=distance_km,
        elevation_profile_json=json.dumps({
            "gain_m": elev_gain, "loss_m": elev_loss,
        }),
        weather_json=json.dumps(weather) if weather else None,
        activity_type=activity_type,
        estimated_duration_min=duration_min,
        estimated_calories=cal["calories_total"],
        glucose_prediction_json=json.dumps(glucose_impact, default=str),
        suggestions_json=json.dumps(_build_suggestions(glucose_impact, weather)),
        status="planned",
    )
    session.add(plan)
    session.commit()

    return {
        "plan_id": plan.id,
        "activity_type": activity_type,
        "intensity": intensity,
        "distance_km": distance_km,
        "duration_min": duration_min,
        "elevation_gain_m": elev_gain,
        "elevation_loss_m": elev_loss,
        "calories": cal,
        "weather": weather,
        "glucose_impact": glucose_impact,
        "suggestions": _build_suggestions(glucose_impact, weather),
        "route_source": route_data.get("source", "none") if route_data else "none",
    }


async def start_activity(session: Session, plan_id: int) -> Optional[Activity]:
    """Start tracking an activity from a plan."""
    plan = session.query(TripPlan).get(plan_id)
    if not plan:
        return None

    plan.status = "active"

    state = get_current_state(session)
    start_sg = state["sg"] if state else None

    activity = Activity(
        timestamp_start=datetime.utcnow(),
        activity_type=plan.activity_type,
        distance_km=plan.distance_km,
        elevation_gain_m=plan.distance_km,  # Will be updated on completion
        start_sg=start_sg,
        source="telegram_gps",
    )
    session.add(activity)
    session.commit()

    return activity


async def complete_activity(
    session: Session,
    activity_id: int,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> Optional[dict]:
    """Complete an activity and record glucose delta."""
    activity = session.query(Activity).get(activity_id)
    if not activity:
        return None

    activity.timestamp_end = datetime.utcnow()
    if activity.timestamp_start:
        delta = (activity.timestamp_end - activity.timestamp_start).total_seconds()
        activity.duration_min = int(delta / 60)

    state = get_current_state(session)
    if state:
        activity.end_sg = state["sg"]
        if activity.start_sg:
            activity.sg_delta = state["sg"] - activity.start_sg

    # Weather at end
    if lat and lon:
        weather = await get_current_weather(lat, lon)
        if weather:
            activity.weather_temp_c = weather.get("temp_c")
            activity.weather_conditions = weather.get("conditions")

    session.commit()

    return {
        "activity_type": activity.activity_type,
        "duration_min": activity.duration_min,
        "start_sg": activity.start_sg,
        "end_sg": activity.end_sg,
        "sg_delta": activity.sg_delta,
        "distance_km": activity.distance_km,
    }


def _build_suggestions(glucose_impact: dict, weather: Optional[dict]) -> list[str]:
    """Build actionable suggestions based on predictions and weather."""
    suggestions = []

    if "error" not in glucose_impact:
        current = glucose_impact.get("current_sg", 0)
        predicted = glucose_impact.get("predicted_sg_end", 0)
        risk = glucose_impact.get("risk_level", "low")
        carbs = glucose_impact.get("carbs_recommended_g", 0)

        if current < 100:
            suggestions.append("Glicemia sotto 100 — mangia 15-20g CHO prima di partire")
        elif current < 130:
            suggestions.append(f"Parti a {current:.0f} — OK ma tieni CHO rapidi a portata")
        else:
            suggestions.append(f"Parti a {current:.0f} — buon livello per iniziare")

        if risk == "high":
            suggestions.append(f"Rischio ipo: stima arrivo a {predicted:.0f}. Porta almeno {carbs:.0f}g CHO")
        elif risk == "moderate":
            suggestions.append(f"Stima arrivo a {predicted:.0f}. Porta 15g CHO per sicurezza")

        if carbs > 0:
            suggestions.append(f"Suggerisco {carbs:.0f}g CHO durante l'attività")

    if weather:
        temp = weather.get("temp_c")
        if temp is not None:
            if temp > 30:
                suggestions.append("Caldo! Idratati bene, la glicemia può variare")
            elif temp < 5:
                suggestions.append("Freddo! L'insulina può agire diversamente")

    suggestions.append("Controlla la glicemia a metà attività e dopo 30 min dalla fine")

    return suggestions
