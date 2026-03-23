"""aiohttp web server — serves the Mini App and API.

The Mini App HTML can also be hosted on GitHub Pages or any static host.
Set WEBAPP_URL to the public URL (e.g., https://user.github.io/repo/webapp/).
The API server still needs to run locally and be accessible via WEBAPP_API_URL.
"""

import logging
import os

from aiohttp import web

from app.config import settings
from app.webapp.api import setup_routes

log = logging.getLogger(__name__)


async def serve_webapp(request):
    """Serve the Mini App HTML."""
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    return web.FileResponse(html_path)


async def create_webapp_server():
    """Create and start the aiohttp web server.

    Returns the AppRunner for later cleanup.
    """
    app = web.Application()

    # CORS middleware for Telegram WebApp
    @web.middleware
    async def cors_middleware(request, handler):
        if request.method == "OPTIONS":
            resp = web.Response()
        else:
            resp = await handler(request)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return resp

    app.middlewares.append(cors_middleware)

    # Routes
    app.router.add_get("/webapp", serve_webapp)
    app.router.add_get("/webapp/", serve_webapp)
    app.router.add_route("OPTIONS", "/api/{tail:.*}", lambda r: web.Response())
    setup_routes(app)

    # Start
    runner = web.AppRunner(app)
    await runner.setup()
    port = settings.WEBAPP_PORT
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info("WebApp server started on http://0.0.0.0:%d/webapp", port)

    return runner
