# -*- coding: utf-8 -*-
"""
Signature Machine - Online Pen Training v0.1

Safe first-stage training interface:
Surface Pen -> browser Pointer Events -> raw strokes -> JSON + PNG

This module intentionally does NOT:
- read the 4599-file Library
- modify existing knowledge files
- run visual_analyzer
- remove pixels
- call the generator

Run:
    python online_training.py

Then open:
    http://127.0.0.1:8765/
"""

from __future__ import annotations

import base64
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "online_training.html"
DATA_DIR = ROOT / "online_training_data"
SAMPLES_DIR = DATA_DIR / "samples"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

HOST = "127.0.0.1"
PORT = 8765


def next_sample_id() -> str:
    existing = []
    for p in SAMPLES_DIR.iterdir():
        m = re.fullmatch(r"sample_(\d{6})", p.name)
        if m:
            existing.append(int(m.group(1)))
    n = max(existing, default=0) + 1
    return f"sample_{n:06d}"


class Handler(BaseHTTPRequestHandler):
    server_version = "SignatureMachineOnlineTraining/0.1"

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ("/", "/online_training.html"):
            body = WEB.read_bytes()
            self._send(200, "text/html; charset=utf-8", body)
            return

        self._send(404, "text/plain; charset=utf-8", b"Not found")

    def do_POST(self):
        path = urlparse(self.path).path
        if path != "/api/save":
            self._send(404, "text/plain; charset=utf-8", b"Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))

            strokes = payload.get("strokes", [])
            png_data = payload.get("png_data", "")
            label = str(payload.get("label", "unlabeled"))

            if not strokes:
                raise ValueError("No strokes were supplied.")

            sample_id = next_sample_id()
            sample_dir = SAMPLES_DIR / sample_id
            sample_dir.mkdir(parents=True, exist_ok=False)

            # JSON is the authoritative raw record.
            record = {
                "schema_version": "online_pen_sample_v0.1",
                "sample_id": sample_id,
                "created_at_unix": time.time(),
                "label": label,
                "source": {
                    "device_input": "Pointer Events",
                    "expected_pointer_type": "pen",
                    "raw_points_preserved": True,
                },
                "strokes": strokes,
                "stats": payload.get("stats", {}),
            }

            (sample_dir / "strokes.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            if png_data.startswith("data:image/png;base64,"):
                encoded = png_data.split(",", 1)[1]
                (sample_dir / "raw.png").write_bytes(base64.b64decode(encoded))
            else:
                raise ValueError("PNG payload missing or invalid.")

            response = json.dumps(
                {"ok": True, "sample_id": sample_id},
                ensure_ascii=False,
            ).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", response)

        except Exception as exc:
            response = json.dumps(
                {"ok": False, "error": str(exc)},
                ensure_ascii=False,
            ).encode("utf-8")
            self._send(400, "application/json; charset=utf-8", response)

    def log_message(self, fmt, *args):
        print("[HTTP]", fmt % args)


def main() -> None:
    print("=" * 64)
    print("SIGNATURE MACHINE - ONLINE PEN TRAINING v0.1")
    print("=" * 64)
    print(f"Data directory: {DATA_DIR}")
    print(f"Open: http://{HOST}:{PORT}/")
    print("Stop with Ctrl+C")
    print("=" * 64)

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
