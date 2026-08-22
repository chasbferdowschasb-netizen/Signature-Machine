# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

try:
    from build_customer_packages import build_sample
except Exception:
    build_sample = None

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "online_training.html"

DATA_DIR = ROOT / "online_training_data"
REFERENCE_DIR = DATA_DIR / "reference_learning"
SAMPLES_DIR = REFERENCE_DIR / "samples"

# New samples are stored in one unified reference dataset.
# Legacy APPROVED/MASTER folders are NOT deleted or modified by this server.
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

HOST = "127.0.0.1"
PORT = 8765


def next_sample_id() -> str:
    """Return the next ID while avoiding collisions with legacy data."""
    numbers = []

    # New unified dataset
    for p in SAMPLES_DIR.iterdir():
        if p.is_dir():
            m = re.fullmatch(r"sample_(\d{6})", p.name)
            if m:
                numbers.append(int(m.group(1)))

    # Legacy folders are scanned only to keep IDs globally unique.
    for legacy_name in ("APPROVED", "MASTER"):
        legacy_dir = REFERENCE_DIR / legacy_name
        if not legacy_dir.exists():
            continue
        for p in legacy_dir.iterdir():
            if p.is_dir():
                m = re.fullmatch(r"sample_(\d{6})", p.name)
                if m:
                    numbers.append(int(m.group(1)))

    return f"sample_{max(numbers, default=0) + 1:06d}"


class Handler(BaseHTTPRequestHandler):
    server_version = "SignatureMachineOnlineTraining/0.3"

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
            render_png_data = payload.get("render_png_data", "")
            render_info = payload.get("render_info", {})
            label = str(payload.get("label", "unlabeled")).strip() or "unlabeled"

            if not strokes:
                raise ValueError("No strokes were supplied.")
            if not png_data.startswith("data:image/png;base64,"):
                raise ValueError("PNG payload missing or invalid.")
            if not render_png_data.startswith("data:image/png;base64,"):
                raise ValueError("High-resolution render payload missing or invalid.")

            sample_id = next_sample_id()
            sample_dir = SAMPLES_DIR / sample_id
            sample_dir.mkdir(parents=True, exist_ok=False)

            png_bytes = base64.b64decode(png_data.split(",", 1)[1])
            render_png_bytes = base64.b64decode(render_png_data.split(",", 1)[1])
            created = time.time()

            stats = payload.get("stats", {})
            record = {
                "schema_version": "online_pen_sample_v0.3",
                "sample_id": sample_id,
                "created_at_unix": created,
                "training_status": "REFERENCE",
                "label": label,
                "source": {
                    "device_input": "Pointer Events",
                    "expected_pointer_type": "pen",
                    "raw_points_preserved": True,
                    "touch_points_preserved": True,
                },
                "strokes": strokes,
                "stats": stats,
            }

            (sample_dir / "strokes.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (sample_dir / "raw.png").write_bytes(png_bytes)
            (sample_dir / "render.png").write_bytes(render_png_bytes)

            metadata = {
                "schema_version": "reference_metadata_v0.3",
                "sample_id": sample_id,
                "training_status": "REFERENCE",
                "label": label,
                "created_at_unix": created,
                "point_count": stats.get("point_count", 0),
                "stroke_count": stats.get("stroke_count", 0),
                "duration_ms": stats.get("duration_ms", 0),
                "pressure_available": stats.get("pressure_available", False),
                "pointer_types": stats.get("pointer_types", []),
                "render": {
                    "file": "render.png",
                    "scale": render_info.get("scale", 4),
                    "crop_x": render_info.get("crop_x"),
                    "crop_y": render_info.get("crop_y"),
                    "crop_width": render_info.get("crop_width"),
                    "crop_height": render_info.get("crop_height"),
                    "source_width": render_info.get("source_width"),
                    "source_height": render_info.get("source_height"),
                },
            }
            (sample_dir / "metadata.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            package_status = {"enabled": bool(build_sample), "ok": False}
            if build_sample is not None:
                try:
                    ok, msg = build_sample(sample_dir, overwrite=True)
                    package_status.update({"ok": bool(ok), "message": str(msg)})
                except Exception as package_exc:
                    # The reference sample is already safely saved. Do not roll it back
                    # merely because customer-package generation failed.
                    package_status.update({"ok": False, "error": str(package_exc)})

            response = json.dumps({
                "ok": True,
                "sample_id": sample_id,
                "training_status": "REFERENCE",
                "path": str(sample_dir.relative_to(ROOT)),
                "customer_package": package_status,
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
    print("SIGNATURE MACHINE - ONLINE PEN TRAINING v0.3")
    print("=" * 72)
    print(f"REFERENCE SAMPLES: {SAMPLES_DIR}")
    print("All newly saved signatures are REFERENCE samples.")
    print("Legacy APPROVED/MASTER folders are not read for learning or modified.")
    print("Touch points are preserved as raw pointer events.")
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
