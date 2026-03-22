#!/usr/bin/env python3
"""GliceMia — Open-Source T1D Intelligent Companion

Entry point for the GliceMia agent.
Copyright (C) 2025-2026 Carlo Cancellieri <ccancellieri@gmail.com>
SPDX-License-Identifier: AGPL-3.0-or-later
"""

import asyncio
import logging
import sys

from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("glicemia")


async def main():
    log.info("Starting GliceMia...")

    # TODO: Phase 1 — initialize database, CareLink poller, Telegram bot
    log.info("GliceMia is not yet implemented. See the plan for details.")


if __name__ == "__main__":
    asyncio.run(main())
