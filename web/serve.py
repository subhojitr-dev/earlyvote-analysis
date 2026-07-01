"""Minimal static server for the dashboard. Binds the port the preview harness
assigns via $PORT (falls back to 8123 for manual local use)."""
import functools
import http.server
import os
import socketserver

PORT = int(os.environ.get("PORT", "8123"))
HERE = os.path.dirname(os.path.abspath(__file__))
Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=HERE)

with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
    print(f"serving {HERE} on http://127.0.0.1:{PORT}")
    httpd.serve_forever()
