#!/usr/bin/env python3
"""GliceMia — Open-Source T1D Intelligent Companion

Entry point for the GliceMia agent (multi-patient).
Copyright (C) 2025-2026 Carlo Cancellieri <ccancellieri@gmail.com>
SPDX-License-Identifier: AGPL-3.0-or-later
"""

import asyncio
import logging
import signal
import sys

from app.config import settings
from app.database import init_db, get_session
from app.models import UserAccount

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("glicemia")


def _seed_bootstrap_admin():
    """Create admin UserAccount(s) from TELEGRAM_ALLOWED_USERS env if none exist."""
    if not settings.TELEGRAM_ALLOWED_USERS:
        return

    session = get_session()
    try:
        for uid in settings.TELEGRAM_ALLOWED_USERS:
            if session.get(UserAccount, uid):
                continue
            from app.users import create_user
            create_user(
                session, telegram_user_id=uid,
                patient_name="Admin", language="it", is_admin=True,
            )
            log.info("Bootstrap admin seeded: tg_id=%d", uid)
    finally:
        session.close()


_telegram_app = None


async def _check_and_send_alerts():
    """Check proactive alerts for ALL active patients and send to each."""
    from app.alerts.engine import check_alerts
    from app.alerts.notifier import format_alert
    from app.users import get_all_active_users

    if not _telegram_app:
        return

    session = get_session()
    try:
        users = get_all_active_users(session)
        for user in users:
            pid = user.telegram_user_id
            alerts = check_alerts(session, patient_id=pid)
            if not alerts:
                continue
            for alert in alerts:
                text = format_alert(alert, user.patient_name, user.language or "it")
                try:
                    await _telegram_app.bot.send_message(
                        chat_id=pid, text=text, parse_mode="Markdown"
                    )
                    log.info("Alert sent to %d: %s (severity=%s)",
                             pid, alert.alert_type, alert.severity)
                except Exception as e:
                    log.error("Failed to send alert to %d: %s", pid, e)
    finally:
        session.close()


async def _start_carelink_poller():
    """Start CareLink polling for ALL patients with credentials."""
    from app.carelink.client import CareLinkClient
    from app.carelink.parser import parse_realtime
    from app.users import get_all_active_users

    async def poll_loop():
        while True:
            session = get_session()
            try:
                users = get_all_active_users(session)
                for user in users:
                    if not user.carelink_username or not user.carelink_password:
                        continue
                    try:
                        client = CareLinkClient(
                            username=user.carelink_username,
                            password=user.carelink_password,
                            country=user.carelink_country or "it",
                        )
                        if not client.connect():
                            continue
                        data = client.fetch()
                        if data:
                            parse_realtime(data, session, patient_id=user.telegram_user_id)
                    except Exception as e:
                        log.error("CareLink poll error for user %d: %s",
                                  user.telegram_user_id, e)

                # Check alerts after polling all patients
                await _check_and_send_alerts()
            except Exception as e:
                log.error("CareLink poll loop error: %s", e)
            finally:
                session.close()

            # Use the shortest poll interval among active CareLink users, min 60s
            session2 = get_session()
            try:
                users = get_all_active_users(session2)
                intervals = [
                    u.carelink_poll_interval for u in users
                    if u.carelink_username and u.carelink_poll_interval
                ]
                interval = min(intervals) if intervals else 300
                interval = max(interval, 60)
            finally:
                session2.close()

            await asyncio.sleep(interval)

    asyncio.create_task(poll_loop())
    log.info("CareLink multi-patient poller started")


async def _start_pattern_scheduler():
    """Compute patterns on startup and schedule daily recomputation."""
    from app.analytics.patterns import compute_all_patterns
    from app.users import get_all_active_users

    def compute_for_all():
        session = get_session()
        try:
            users = get_all_active_users(session)
            for user in users:
                try:
                    compute_all_patterns(session, patient_id=user.telegram_user_id)
                except Exception as e:
                    log.error("Pattern computation failed for user %d: %s",
                              user.telegram_user_id, e)
        finally:
            session.close()

    compute_for_all()

    async def daily_patterns():
        while True:
            await asyncio.sleep(3600)
            from datetime import datetime
            now = datetime.utcnow()
            if now.hour == 4 and now.minute < 5:
                log.info("Running daily pattern computation...")
                compute_for_all()

    asyncio.create_task(daily_patterns())
    log.info("Pattern scheduler started (daily at 04:00 UTC)")


async def main():
    log.info("Starting GliceMia...")

    # 1. Initialize database
    init_db()
    _seed_bootstrap_admin()

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

    # 5. Start WebApp server (Mini App + API)
    webapp_runner = None
    try:
        from app.webapp.server import create_webapp_server
        webapp_runner = await create_webapp_server()
    except Exception as e:
        log.debug("WebApp server not started: %s", e)

    # 6. Start Telegram bot
    global _telegram_app
    from app.chat.telegram import TelegramPlatform
    telegram = TelegramPlatform()

    stop_event = asyncio.Event()

    def handle_signal():
        log.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    await telegram.start()
    _telegram_app = telegram._app
    log.info("GliceMia is running! Press Ctrl+C to stop.")

    await stop_event.wait()

    await telegram.stop()
    if webapp_runner:
        await webapp_runner.cleanup()
    log.info("GliceMia stopped.")


if __name__ == "__main__":
    asyncio.run(main())
