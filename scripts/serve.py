#!/usr/bin/env python3
"""Local development only; production is static GitHub Pages."""
import http.server
import os
from pathlib import Path

os.chdir(Path(__file__).resolve().parents[1])
port = int(os.environ.get("PORT", "5173"))
print(f"OpenRS local preview: http://localhost:{port}", flush=True)
http.server.ThreadingHTTPServer(("0.0.0.0", port), http.server.SimpleHTTPRequestHandler).serve_forever()
