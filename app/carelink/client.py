"""CareLink Cloud API poller — reads real-time CGM/pump data from Medtronic 780G."""

import logging
from datetime import datetime
from typing import Optional

from app.config import settings

log = logging.getLogger(__name__)


class CareLinkClient:
    """Wraps carelink-python-client to poll CareLink Cloud every 5 minutes."""

    def __init__(self):
        self._client = None
        self._last_data = None

    def connect(self) -> bool:
        """Initialize the CareLink connection."""
        try:
            from carelink_client import CareLinkClient as CLC

            self._client = CLC(
                carelink_username=settings.CARELINK_USERNAME,
                carelink_password=settings.CARELINK_PASSWORD,
                carelink_country=settings.CARELINK_COUNTRY,
            )
            log.info("CareLink client initialized for country=%s", settings.CARELINK_COUNTRY)
            return True
        except ImportError:
            log.warning(
                "carelink-python-client not installed. "
                "Install with: pip install carelink-python-client"
            )
            return False
        except Exception as e:
            log.error("CareLink connection failed: %s", e)
            return False

    def fetch(self) -> Optional[dict]:
        """Fetch latest data from CareLink Cloud. Returns raw JSON dict or None."""
        if self._client is None:
            log.warning("CareLink client not connected")
            return None

        try:
            data = self._client.getRecentData()
            if data:
                self._last_data = data
                log.debug("CareLink data fetched successfully")
            else:
                log.warning("CareLink returned empty data (auth expired?)")
            return data
        except Exception as e:
            log.error("CareLink fetch failed: %s", e)
            return None

    @property
    def last_data(self) -> Optional[dict]:
        return self._last_data
