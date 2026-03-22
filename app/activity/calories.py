"""Energy expenditure estimation — MET-based + elevation adjustments."""

import logging
from typing import Optional

log = logging.getLogger(__name__)

# MET values by activity type and intensity
# Source: Compendium of Physical Activities (Ainsworth et al.)
MET_VALUES = {
    ("cycling", "low"): 4.0,         # <16 km/h, leisure
    ("cycling", "moderate"): 6.8,     # 16-19 km/h
    ("cycling", "vigorous"): 10.0,    # 20-25 km/h
    ("walking", "low"): 2.5,         # 3.2 km/h
    ("walking", "moderate"): 3.5,     # 4.8 km/h
    ("walking", "vigorous"): 5.0,     # 6.4 km/h, brisk
    ("running", "low"): 7.0,         # 8 km/h
    ("running", "moderate"): 9.8,     # 9.6 km/h
    ("running", "vigorous"): 12.8,    # 12 km/h
    ("gym", "low"): 3.5,
    ("gym", "moderate"): 5.0,
    ("gym", "vigorous"): 8.0,
}

# Elevation adjustment: additional kcal per kg per meter of ascent
ELEVATION_KCAL_PER_KG_PER_M = 0.0048  # ~4.8 kcal/kg per 1000m


def estimate_calories(
    activity_type: str,
    intensity: str = "moderate",
    duration_min: int = 30,
    weight_kg: float = 54.0,
    elevation_gain_m: float = 0,
    distance_km: float = 0,
) -> dict:
    """Estimate energy expenditure using MET formula.

    Calories = MET × weight_kg × duration_hours

    Returns:
        Dict with calories_total, calories_base, calories_elevation,
        met_value, details.
    """
    met = MET_VALUES.get((activity_type, intensity))
    if met is None:
        met = MET_VALUES.get((activity_type, "moderate"), 5.0)

    duration_hours = duration_min / 60
    calories_base = met * weight_kg * duration_hours

    # Elevation adjustment
    calories_elevation = weight_kg * elevation_gain_m * ELEVATION_KCAL_PER_KG_PER_M

    calories_total = calories_base + calories_elevation

    return {
        "calories_total": round(calories_total),
        "calories_base": round(calories_base),
        "calories_elevation": round(calories_elevation),
        "met_value": met,
        "activity_type": activity_type,
        "intensity": intensity,
        "duration_min": duration_min,
        "weight_kg": weight_kg,
        "elevation_gain_m": round(elevation_gain_m),
    }


def infer_intensity(
    activity_type: str,
    speed_kmh: Optional[float] = None,
    elevation_gain_m: float = 0,
    distance_km: float = 0,
) -> str:
    """Infer intensity from speed and/or elevation."""
    if speed_kmh is not None:
        thresholds = {
            "cycling": (14, 20),
            "walking": (4, 5.5),
            "running": (8, 11),
        }
        low, high = thresholds.get(activity_type, (5, 10))
        if speed_kmh < low:
            return "low"
        elif speed_kmh > high:
            return "vigorous"
        return "moderate"

    # Infer from elevation gradient
    if distance_km > 0 and elevation_gain_m > 0:
        gradient_pct = (elevation_gain_m / (distance_km * 1000)) * 100
        if gradient_pct > 5:
            return "vigorous"
        elif gradient_pct > 2:
            return "moderate"

    return "moderate"
