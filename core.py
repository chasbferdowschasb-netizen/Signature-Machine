# -*- coding: utf-8 -*-

"""
Signature Machine
Core v0.1

مسئولیت:
- مدیریت مسیرهای اصلی پروژه
- شناسایی Dataset
- بررسی اولیه تصاویر
- استخراج Metadata
- تولید Dataset Audit Report

اصل معماری:
این فایل هسته مرکزی است.
برای هر قابلیت، موتور مستقل ایجاد نمی‌کنیم مگر اینکه
واقعاً از نظر معماری ضروری باشد.

Original Dataset هرگز تغییر داده نمی‌شود.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image


# ============================================================
# PROJECT CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent
LIBRARY_DIR = PROJECT_ROOT / "library"

REPORT_FILE = PROJECT_ROOT / "dataset_report.json"

SUPPORTED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}


# ============================================================
# CORE
# ============================================================

class SignatureCore:
    """
    هسته مرکزی Signature Machine.

    فعلاً مسئول:
    - دسترسی به Library
    - Dataset Audit
    - ساخت گزارش Metadata
    """

    def __init__(
        self,
        project_root: Path = PROJECT_ROOT,
    ) -> None:

        self.project_root = Path(project_root)
        self.library_dir = self.project_root / "library"
        self.report_file = self.project_root / "dataset_report.json"

    # --------------------------------------------------------
    # PROJECT
    # --------------------------------------------------------

    def validate_project(self) -> None:
        """
        بررسی حداقل ساختار مورد نیاز پروژه.
        """

        if not self.library_dir.exists():

            raise FileNotFoundError(
                f"Library پیدا نشد: {self.library_dir}"
            )

        if not self.library_dir.is_dir():

            raise NotADirectoryError(
                f"Library یک پوشه نیست: {self.library_dir}"
            )

    # --------------------------------------------------------
    # FILE DISCOVERY
    # --------------------------------------------------------

    def discover_images(self) -> list[Path]:
        """
        تمام فایل‌های تصویری Library را پیدا می‌کند.

        Original files فقط خوانده می‌شوند.
        """

        files: list[Path] = []

        for path in self.library_dir.rglob("*"):

            if not path.is_file():
                continue

            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(path)

        return sorted(files)

    # --------------------------------------------------------
    # HASH
    # --------------------------------------------------------

    @staticmethod
    def calculate_hash(
        path: Path,
    ) -> str:
        """
        SHA256 فایل برای شناسایی فایل‌های یکسان.
        """

        sha256 = hashlib.sha256()

        with path.open("rb") as file:

            while True:

                chunk = file.read(1024 * 1024)

                if not chunk:
                    break

                sha256.update(chunk)

        return sha256.hexdigest()

    # --------------------------------------------------------
    # IMAGE ANALYSIS
    # --------------------------------------------------------

    @staticmethod
    def analyze_image(
        path: Path,
    ) -> dict[str, Any]:

        result: dict[str, Any] = {
            "filename": path.name,
            "relative_path": str(path),
            "extension": path.suffix.lower(),
            "valid": False,
            "width": None,
            "height": None,
            "mode": None,
            "has_alpha": False,
            "error": None,
        }

        try:

            with Image.open(path) as image:

                result["valid"] = True
                result["width"] = image.width
                result["height"] = image.height
                result["mode"] = image.mode
                result["has_alpha"] = (
                    "A" in image.getbands()
                )

        except Exception as exc:

            result["error"] = str(exc)

        return result

    # --------------------------------------------------------
    # AUDIT
    # --------------------------------------------------------

    def audit_dataset(self) -> dict[str, Any]:

        self.validate_project()

        images = self.discover_images()

        print()
        print("=" * 60)
        print("SIGNATURE MACHINE")
        print("CORE v0.1 — DATASET AUDIT")
        print("=" * 60)

        print()
        print(f"Project: {self.project_root}")
        print(f"Library: {self.library_dir}")
        print()
        print(f"Image files found: {len(images)}")

        # ----------------------------------------------------
        # Counters
        # ----------------------------------------------------

        extensions = Counter()
        modes = Counter()

        valid_count = 0
        invalid_count = 0
        alpha_count = 0

        width_values = []
        height_values = []

        file_records = []

        # ----------------------------------------------------
        # Process
        # ----------------------------------------------------

        for index, path in enumerate(images, start=1):

            result = self.analyze_image(path)

            file_records.append(result)

            extensions[result["extension"]] += 1

            if result["valid"]:

                valid_count += 1

                modes[result["mode"]] += 1

                width_values.append(
                    result["width"]
                )

                height_values.append(
                    result["height"]
                )

                if result["has_alpha"]:
                    alpha_count += 1

            else:

                invalid_count += 1

            # Progress

            if (
                index == 1
                or index % 250 == 0
                or index == len(images)
            ):

                print(
                    f"Analyzed: "
                    f"{index}/{len(images)}"
                )

        # ----------------------------------------------------
        # Dimensions
        # ----------------------------------------------------

        dimensions = {
            "min_width": min(width_values)
            if width_values else None,

            "max_width": max(width_values)
            if width_values else None,

            "min_height": min(height_values)
            if height_values else None,

            "max_height": max(height_values)
            if height_values else None,
        }

        # ----------------------------------------------------
        # Duplicate candidates
        # ----------------------------------------------------

        print()
        print("Calculating file hashes...")

        hash_map: dict[str, list[str]] = {}

        for index, path in enumerate(
            images,
            start=1,
        ):

            try:

                file_hash = self.calculate_hash(path)

                hash_map.setdefault(
                    file_hash,
                    [],
                ).append(
                    str(
                        path.relative_to(
                            self.project_root
                        )
                    )
                )

            except Exception:
                continue

            if (
                index % 500 == 0
                or index == len(images)
            ):

                print(
                    f"Hashed: "
                    f"{index}/{len(images)}"
                )

        duplicate_groups = [
            paths
            for paths in hash_map.values()
            if len(paths) > 1
        ]

        duplicate_file_count = sum(
            len(group)
            for group in duplicate_groups
        )

        # ----------------------------------------------------
        # REPORT
        # ----------------------------------------------------

        report = {
            "report_version": "0.1",

            "project": {
                "root": str(
                    self.project_root
                ),
                "library": str(
                    self.library_dir
                ),
            },

            "dataset": {
                "total_files": len(images),
                "valid_images": valid_count,
                "invalid_images": invalid_count,
            },

            "formats": dict(
                extensions
            ),

            "image_modes": dict(
                modes
            ),

            "transparency": {
                "images_with_alpha": alpha_count,
                "images_without_alpha": (
                    valid_count - alpha_count
                ),
            },

            "dimensions": dimensions,

            "duplicates": {
                "duplicate_groups": len(
                    duplicate_groups
                ),
                "duplicate_files": (
                    duplicate_file_count
                ),
            },

            "files": file_records,
        }

        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        with self.report_file.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                report,
                file,
                ensure_ascii=False,
                indent=2,
            )

        # ----------------------------------------------------
        # SUMMARY
        # ----------------------------------------------------

        print()
        print("=" * 60)
        print("DATASET AUDIT COMPLETE")
        print("=" * 60)

        print()
        print(
            f"Total files:      {len(images)}"
        )

        print(
            f"Valid images:     {valid_count}"
        )

        print(
            f"Invalid images:   {invalid_count}"
        )

        print(
            f"With alpha:       {alpha_count}"
        )

        print(
            f"Duplicate groups: {len(duplicate_groups)}"
        )

        print()
        print(
            f"Report saved to:"
        )

        print(
            self.report_file
        )

        print()
        print("CORE v0.1: OK")

        return report


# ============================================================
# ENTRY POINT
# ============================================================

def main() -> None:

    core = SignatureCore()

    core.audit_dataset()


if __name__ == "__main__":

    main()