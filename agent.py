#!/usr/bin/env python3
"""GliceMia — Open-Source T1D Intelligent Companion

Entry point for the GliceMia agent.
Copyright (C) 2025-2026 Carlo Cancellieri <ccancellieri@gmail.com>
SPDX-License-Identifier: AGPL-3.0-or-later
"""

import asyncio
import logging
import signal
import sys

from app.config import settings
from app.database import init_db, get_session
from app.models import PatientProfile, Condition

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("glicemia")


def _seed_patient_profile():
    """Create default patient profile if none exists."""
    session = get_session()
    try:
        if session.query(PatientProfile).first():
            return

        session.add(PatientProfile(
            name=settings.PATIENT_NAME,
            diabetes_type="T1D",
            pump_model="MiniMed 780G (MMT-1886)",
            sensor_model="Guardian 4",
            diet="vegetarian",
            language=settings.LANGUAGE,
        ))

        # Seed known conditions
        conditions = [
            Condition(
                snomed_code="46635009",
                icd_code="E10",
                display_name="Diabete tipo 1",
                clinical_status="active",
                severity="moderate",
            ),
        ]
        for c in conditions:
            session.add(c)

        session.commit()
        log.info("Patient profile seeded for %s", settings.PATIENT_NAME)
    finally:
        session.close()


_telegram_app = None  # Set when Telegram starts, used by alert notifier


async def _check_and_send_alerts(session):
    """Check for proactive alerts and send them via Telegram."""
    from app.alerts.engine import check_alerts
    from app.alerts.notifier import format_alert

    alerts = check_alerts(session)
    if not alerts or not _telegram_app or not settings.TELEGRAM_ALLOWED_USERS:
        return

    for alert in alerts:
        text = format_alert(alert, settings.PATIENT_NAME, settings.LANGUAGE)
        for user_id in settings.TELEGRAM_ALLOWED_USERS:
            try:
                await _telegram_app.bot.send_message(
                    chat_id=user_id, text=text, parse_mode="Markdown"
                )
                log.info("Alert sent: %s (severity=%s)", alert.alert_type, alert.severity)
            except Exception as e:
                log.error("Failed to send alert to %s: %s", user_id, e)


async def _start_carelink_poller():
    """Start the CareLink polling loop."""
    from app.carelink.client import CareLinkClient
    from app.carelink.parser import parse_realtime

    client = CareLinkClient()
    if not client.connect():
        log.warning("CareLink not available — running without real-time data")
        return

    async def poll_loop():
        while True:
            try:
                data = client.fetch()
                if data:
                    session = get_session()
                    try:
                        parse_realtime(data, session)
                        # Check proactive alerts after every poll
                        await _check_and_send_alerts(session)
                    finally:
                        session.close()
            except Exception as e:
                log.error("CareLink poll error: %s", e)
            await asyncio.sleep(settings.CARELINK_POLL_INTERVAL)

    asyncio.create_task(poll_loop())
    log.info("CareLink poller started (interval=%ds)", settings.CARELINK_POLL_INTERVAL)


async def _start_pattern_scheduler():
    """Compute patterns on startup and schedule daily recomputation."""
    from app.analytics.patterns import compute_all_patterns

    # Compute once on startup
    session = get_session()
    try:
        compute_all_patterns(session)
    except Exception as e:
        log.error("Initial pattern computation failed: %s", e)
    finally:
        session.close()

    # Schedule daily recomputation at 04:00
    async def daily_patterns():
        while True:
            await asyncio.sleep(3600)  # Check every hour
            from datetime import datetime
            now = datetime.utcnow()
            if now.hour == 4 and now.minute < 5:
                log.info("Running daily pattern computation...")
                session = get_session()
                try:
                    compute_all_patterns(session)
                except Exception as e:
                    log.error("Daily pattern computation failed: %s", e)
                finally:
                    session.close()

    asyncio.create_task(daily_patterns())
    log.info("Pattern scheduler started (daily at 04:00 UTC)")


async def main():
    log.info("Starting GliceMia...")

    # 1. Initialize database
    init_db()
    _seed_patient_profile()

    # 2. Start CareLink poller (non-blocking)
    await _start_carelink_poller()

    # 3. Compute patterns on startup + schedule daily recomputation
    await _start_pattern_scheduler()

    # 4. Start MCP server (if mcp package installed)
    try:
        from app.mcp.server import create_mcp_server
        mcp_server = create_mcp_server()
        if mcp_server:
            log.info("MCP server available for Claude Desktop")
    except Exception as e:
        log.debug("MCP server not started: %s", e)

    # 5. Start Telegram bot
    global _telegram_app
    from app.chat.telegram import TelegramPlatform
    telegram = TelegramPlatform()

    # Handle graceful shutdown
    stop_event = asyncio.Event()

    def handle_signal():
        log.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    await telegram.start()
    _telegram_app = telegram._app  # Expose for alert notifier
    log.info("GliceMia is running! Press Ctrl+C to stop.")

    # Wait for shutdown signal
    await stop_event.wait()

    await telegram.stop()
    log.info("GliceMia stopped.")


if __name__ == "__main__":
    asyncio.run(main())
