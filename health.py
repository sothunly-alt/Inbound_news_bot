"""HTTP health check server for Render Web Services."""

import logging
from http.server import BaseHTTPRequestHandler, HTTPServer

from config import PORT

logger = logging.getLogger(__name__)


class HealthHandler(BaseHTTPRequestHandler):
    """Minimal HTTP server so Render detects an open port."""

    def do_GET(self) -> None:
        body = b"ok" if self.path in ("/", "/health") else b"not found"
        code = 200 if body == b"ok" else 404
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Silence access logs."""
        return


def start_health_server() -> None:
    """Start the HTTP health server in the current thread (blocking)."""
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info("Health server listening on 0.0.0.0:%d (/ and /health)", PORT)
    server.serve_forever()
