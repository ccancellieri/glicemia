"""Weather integration — OpenWeatherMap for location-based conditions."""

import logging
from typing import Optional

from app.config import settings

log = logging.getLogger(__name__)


async def get_current_weather(lat: float, lon: float) -> Optional[dict]:
    """Get current weather for a location from OpenWeatherMap.

    Returns:
        Dict with temp_c, feels_like_c, humidity, conditions, wind_kmh, icon.
    """
    if not settings.OPENWEATHER_API_KEY:
        log.debug("OPENWEATHER_API_KEY not set — skipping weather")
        return None

    try:
        import httpx

        url = "https://api.openweathermap.org/data/2.5/weather"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params={
                "lat": lat,
                "lon": lon,
                "appid": settings.OPENWEATHER_API_KEY,
                "units": "metric",
            })
            resp.raise_for_status()
            data = resp.json()

        main = data.get("main", {})
        weather = data.get("weather", [{}])[0]
        wind = data.get("wind", {})

        return {
            "temp_c": main.get("temp"),
            "feels_like_c": main.get("feels_like"),
            "humidity_pct": main.get("humidity"),
            "conditions": weather.get("description", ""),
            "icon": weather.get("icon", ""),
            "wind_kmh": round((wind.get("speed", 0)) * 3.6, 1),
            "location_name": data.get("name", ""),
        }

    except ImportError:
        log.warning("httpx not installed — skipping weather")
        return None
    except Exception as e:
        log.error("Weather fetch failed: %s", e)
        return None


async def get_forecast(lat: float, lon: float, hours_ahead: int = 12) -> Optional[list[dict]]:
    """Get hourly forecast for planned activities."""
    if not settings.OPENWEATHER_API_KEY:
        return None

    try:
        import httpx

        url = "https://api.openweathermap.org/data/2.5/forecast"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params={
                "lat": lat,
                "lon": lon,
                "appid": settings.OPENWEATHER_API_KEY,
                "units": "metric",
                "cnt": max(1, hours_ahead // 3),  # 3h intervals
            })
            resp.raise_for_status()
            data = resp.json()

        forecasts = []
        for item in data.get("list", []):
            main = item.get("main", {})
            weather = item.get("weather", [{}])[0]
            wind = item.get("wind", {})
            forecasts.append({
                "datetime": item.get("dt_txt", ""),
                "temp_c": main.get("temp"),
                "feels_like_c": main.get("feels_like"),
                "humidity_pct": main.get("humidity"),
                "conditions": weather.get("description", ""),
                "wind_kmh": round((wind.get("speed", 0)) * 3.6, 1),
                "rain_mm": item.get("rain", {}).get("3h", 0),
            })

        return forecasts

    except Exception as e:
        log.error("Forecast fetch failed: %s", e)
        return None
