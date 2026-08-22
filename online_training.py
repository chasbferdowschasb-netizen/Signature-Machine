# -*- coding: utf-8 -*-
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
REFERENCE_DIR = DATA_DIR / "reference_learning"
APPROVED_DIR = REFERENCE_DIR / "APPROVED"
MASTER_DIR = REFERENCE_DIR / "MASTER"

APPROVED_DIR.mkdir(parents=True, exist_ok=True)
MASTER_DIR.mkdir(parents=True, exist_ok=True)

HOST = "127.0.0.1"
PORT = 8765


def next_sample_id() -> str:
    numbers = []
    for base in (APPROVED_DIR, MASTER_DIR):
        for p in base.iterdir():
            if p.is_dir():
                m = re.fullmatch(r"sample_(\d{6})", p.name)
                if m:
                    numbers.append(int(m.group(1)))
    return f"sample_{max(numbers, default=0) + 1:06d}"


class Handler(BaseHTTPRequestHandler):
    server_version = "SignatureMachineOnlineTraining/0.2"

    def _send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/online_training.html"):
            self._send(200, "text/html; charset=utf-8", WEB.read_bytes())
        else:
            self._send(404, "text/plain; charset=utf-8", b"Not found")

    def do_POST(self):
        if urlparse(self.path).path != "/api/save":
            self._send(404, "text/plain; charset=utf-8", b"Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))

            strokes = payload.get("strokes", [])
            png_data = payload.get("png_data", "")
            label = str(payload.get("label", "unlabeled")).strip() or "unlabeled"
            tier = str(payload.get("tier", "APPROVED")).upper()

            if tier not in {"APPROVED", "MASTER"}:
                raise ValueError("Only APPROVED or MASTER is allowed.")
            if not strokes:
                raise ValueError("No strokes were supplied.")
            if not png_data.startswith("data:image/png;base64,"):
                raise ValueError("PNG payload missing or invalid.")

            target_root = MASTER_DIR if tier == "MASTER" else APPROVED_DIR
            sample_id = next_sample_id()
            sample_dir = target_root / sample_id
            sample_dir.mkdir(parents=True, exist_ok=False)

            png_bytes = base64.b64decode(png_data.split(",", 1)[1])
            created = time.time()

            stats = payload.get("stats", {})
            record = {
                "schema_version": "online_pen_sample_v0.2",
                "sample_id": sample_id,
                "created_at_unix": created,
                "training_status": tier,
                "label": label,
                "source": {
                    "device_input": "Pointer Events",
                    "expected_pointer_type": "pen",
                    "raw_points_preserved": True,
                },
                "strokes": strokes,
                "stats": stats,
            }

            (sample_dir / "strokes.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (sample_dir / "raw.png").write_bytes(png_bytes)

            metadata = {
                "schema_version": "reference_metadata_v0.2",
                "sample_id": sample_id,
                "training_status": tier,
                "label": label,
                "created_at_unix": created,
                "point_count": stats.get("point_count", 0),
                "stroke_count": stats.get("stroke_count", 0),
                "duration_ms": stats.get("duration_ms", 0),
                "pressure_available": stats.get("pressure_available", False),
                "pointer_types": stats.get("pointer_types", []),
            }
            (sample_dir / "metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            response = json.dumps({
                "ok": True,
                "sample_id": sample_id,
                "training_status": tier,
                "path": str(sample_dir.relative_to(ROOT)),
            }, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", response)

        except Exception as exc:
            response = json.dumps(
                {"ok": False, "error": str(exc)},
                ensure_ascii=False
            ).encode("utf-8")
            self._send(400, "application/json; charset=utf-8", response)

    def log_message(self, fmt, *args):
        print("[HTTP]", fmt % args)


def main():
    print("=" * 72)
    print("SIGNATURE MACHINE - ONLINE PEN TRAINING v0.2")
    print("=" * 72)
    print(f"APPROVED: {APPROVED_DIR}")
    print(f"MASTER:   {MASTER_DIR}")
    print("Existing Library is NOT read.")
    print(f"Open: http://{HOST}:{PORT}/")
    print("Stop with Ctrl+C")
    print("=" * 72)

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
