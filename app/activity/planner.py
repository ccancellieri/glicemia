"""Route planning with OpenRouteService — distance, elevation, duration."""

import json
import logging
from typing import Optional

from app.config import settings

log = logging.getLogger(__name__)

# Average speeds by activity (km/h)
AVG_SPEEDS = {
    "cycling": 15.0,
    "walking": 4.5,
    "running": 9.0,
}

# ORS profile mapping
ORS_PROFILES = {
    "cycling": "cycling-regular",
    "walking": "foot-walking",
    "running": "foot-walking",
}


async def plan_route(
    start: tuple[float, float],
    end: tuple[float, float],
    activity_type: str = "cycling",
) -> Optional[dict]:
    """Plan a route between two GPS points using OpenRouteService.

    Args:
        start: (longitude, latitude)
        end: (longitude, latitude)
        activity_type: cycling, walking, running

    Returns:
        Dict with distance_km, duration_min, elevation_gain_m, elevation_loss_m,
        geometry (GeoJSON), bbox, steps.
    """
    if not settings.ORS_API_KEY:
        log.warning("ORS_API_KEY not set — using straight-line estimate")
        return _straight_line_estimate(start, end, activity_type)

    try:
        import httpx

        profile = ORS_PROFILES.get(activity_type, "foot-walking")
        url = f"https://api.openrouteservice.org/v2/directions/{profile}"

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                url,
                json={
                    "coordinates": [list(start), list(end)],
                    "elevation": True,
                    "instructions": True,
                    "geometry": True,
                },
                headers={
                    "Authorization": settings.ORS_API_KEY,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        route = data["routes"][0]
        summary = route["summary"]
        segments = route.get("segments", [{}])

        # Extract elevation from segments
        elev_gain = 0
        elev_loss = 0
        steps = []
        for seg in segments:
            elev_gain += seg.get("ascent", 0)
            elev_loss += seg.get("descent", 0)
            for step in seg.get("steps", []):
                steps.append({
                    "instruction": step.get("instruction", ""),
                    "distance_m": step.get("distance", 0),
                    "duration_s": step.get("duration", 0),
                })

        distance_km = summary["distance"] / 1000
        duration_min = summary["duration"] / 60

        return {
            "distance_km": round(distance_km, 1),
            "duration_min": round(duration_min),
            "elevation_gain_m": round(elev_gain),
            "elevation_loss_m": round(elev_loss),
            "geometry": route.get("geometry"),
            "bbox": route.get("bbox"),
            "steps": steps[:10],  # First 10 navigation steps
            "source": "openrouteservice",
        }

    except ImportError:
        log.warning("httpx not installed — using straight-line estimate")
        return _straight_line_estimate(start, end, activity_type)
    except Exception as e:
        log.error("ORS route planning failed: %s", e)
        return _straight_line_estimate(start, end, activity_type)


async def get_elevation_profile(
    coordinates: list[tuple[float, float]],
) -> Optional[list[dict]]:
    """Get elevation profile for a list of coordinates."""
    if not settings.ORS_API_KEY:
        return None

    try:
        import httpx

        url = "https://api.openrouteservice.org/elevation/line"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                json={
                    "format_in": "point",
                    "format_out": "point",
                    "geometry": {
                        "coordinates": [list(c) for c in coordinates],
                        "type": "LineString",
                    },
                },
                headers={
                    "Authorization": settings.ORS_API_KEY,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        points = data.get("geometry", {}).get("coordinates", [])
        return [
            {"lon": p[0], "lat": p[1], "elevation_m": p[2] if len(p) > 2 else 0}
            for p in points
        ]
    except Exception as e:
        log.error("Elevation profile failed: %s", e)
        return None


def _straight_line_estimate(
    start: tuple[float, float],
    end: tuple[float, float],
    activity_type: str,
) -> dict:
    """Fallback: straight-line distance estimate when ORS is unavailable."""
    from math import radians, sin, cos, sqrt, atan2

    lon1, lat1 = radians(start[0]), radians(start[1])
    lon2, lat2 = radians(end[0]), radians(end[1])

    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    distance_km = 6371 * c

    # Road factor: actual roads are ~1.3x straight line
    distance_km *= 1.3
    speed = AVG_SPEEDS.get(activity_type, 5.0)
    duration_min = (distance_km / speed) * 60

    return {
        "distance_km": round(distance_km, 1),
        "duration_min": round(duration_min),
        "elevation_gain_m": 0,
        "elevation_loss_m": 0,
        "geometry": None,
        "bbox": None,
        "steps": [],
        "source": "straight_line_estimate",
    }
