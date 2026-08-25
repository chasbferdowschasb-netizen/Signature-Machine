# -*- coding: utf-8 -*-

"""
Signature Machine — Workspace Manager

Workspace Architecture Foundation

IMPORTANT:
- Every Sample is a self-contained unit.
- Sample internal structure must not be split across Workspace folders.
- Existing Samples 001–025 must remain untouched.
- All future Samples, including 026 and 5000+, use the same Sample structure.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


WORKSPACE_TYPE = "SIGNATURE_MACHINE_WORKSPACE"
WORKSPACE_SCHEMA_VERSION = "1.0"
WORKSPACE_VERSION = "0.1"


@dataclass(frozen=True)
class WorkspaceLayout:
    root: Path

    @property
    def system(self) -> Path:
        return self.root / "SYSTEM"

    @property
    def database(self) -> Path:
        return self.root / "DATABASE"

    @property
    def knowledge(self) -> Path:
        return self.root / "KNOWLEDGE"

    @property
    def models(self) -> Path:
        return self.root / "MODELS"

    @property
    def samples(self) -> Path:
        return self.root / "SAMPLES"

    @property
    def archive(self) -> Path:
        return self.root / "ARCHIVE"

    @property
    def documentation(self) -> Path:
        return self.root / "DOCUMENTATION"

    @property
    def manifest(self) -> Path:
        return self.system / "workspace_manifest.json"

    def paths(self) -> dict[str, Path]:
        return {
            "root": self.root,
            "system": self.system,
            "database": self.database,
            "knowledge": self.knowledge,
            "models": self.models,
            "samples": self.samples,
            "archive": self.archive,
            "documentation": self.documentation,
        }


class WorkspaceManager:

    REQUIRED_DIRS = (
        "SYSTEM",
        "DATABASE",
        "KNOWLEDGE",
        "MODELS",
        "SAMPLES",
        "ARCHIVE",
        "DOCUMENTATION",
    )

    def __init__(self, root: str | Path):
        self.layout = WorkspaceLayout(
            Path(root).expanduser().resolve()
        )

    @property
    def root(self) -> Path:
        return self.layout.root

    def exists(self) -> bool:
        return self.root.is_dir()

    def is_initialized(self) -> bool:
        valid, _ = self.validate()
        return valid

    def validate(self) -> tuple[bool, list[str]]:
        errors: list[str] = []

        if not self.exists():
            return False, [
                f"Workspace root does not exist: {self.root}"
            ]

        for name in self.REQUIRED_DIRS:
            path = self.root / name

            if not path.is_dir():
                errors.append(
                    f"Missing workspace directory: {path}"
                )

        if not self.layout.manifest.is_file():
            errors.append(
                f"Missing workspace manifest: "
                f"{self.layout.manifest}"
            )

        return not errors, errors

    def initialize(self) -> dict:

        if self.exists():

            contents = list(self.root.iterdir())

            if contents:
                raise FileExistsError(
                    "Workspace already exists and contains data. "
                    "Initialization stopped for safety:\n"
                    f"{self.root}"
                )

        else:
            self.root.mkdir(
                parents=True,
                exist_ok=False
            )

        for name in self.REQUIRED_DIRS:
            (self.root / name).mkdir(
                exist_ok=True
            )

        manifest = {
            "workspace_type": WORKSPACE_TYPE,
            "workspace_id": str(uuid.uuid4()),
            "schema_version": WORKSPACE_SCHEMA_VERSION,
            "workspace_version": WORKSPACE_VERSION,
            "created_at_utc": (
                datetime.now(timezone.utc).isoformat()
            ),

            "sample_architecture": {
                "type": "SELF_CONTAINED",
                "structure_is_universal": True,
                "all_samples_share_same_structure": True,
                "existing_samples": "001-025",
                "future_samples": "026+",
                "reference_samples_are_immutable": True,
                "sample_artifacts_stay_inside_sample": True
            },

            "security": {
                "encrypted": False,
                "hardware_bound": False
            },

            "master_identity": None
        }

        self.layout.manifest.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        valid, errors = self.validate()

        if not valid:
            raise RuntimeError(
                "Workspace initialization failed validation:\n"
                + "\n".join(errors)
            )

        return manifest

    def read_manifest(self) -> dict:

        if not self.layout.manifest.is_file():
            raise FileNotFoundError(
                f"Manifest not found: "
                f"{self.layout.manifest}"
            )

        return json.loads(
            self.layout.manifest.read_text(
                encoding="utf-8"
            )
        )


def main() -> int:

    project_root = Path(__file__).resolve().parent
    workspace_root = project_root / "workspace"

    manager = WorkspaceManager(workspace_root)

    print()
    print("========================================")
    print("      SIGNATURE MACHINE WORKSPACE")
    print("========================================")
    print()

    print(f"Workspace Root:")
    print(f"  {manager.root}")
    print()

    if manager.is_initialized():

        print("Workspace Status: ALREADY INITIALIZED")
        print()

        manifest = manager.read_manifest()

        print(
            f"Workspace ID: "
            f"{manifest['workspace_id']}"
        )

        print(
            f"Schema Version: "
            f"{manifest['schema_version']}"
        )

        return 0

    if manager.exists():

        print(
            "Workspace exists but is not initialized."
        )

        print(
            "Initialization stopped for safety."
        )

        return 2

    print("Workspace Status: NOT INITIALIZED")
    print()

    answer = input(
        "Initialize Workspace? [y/N]: "
    ).strip().lower()

    if answer not in {"y", "yes"}:

        print(
            "Initialization cancelled."
        )

        return 0

    manifest = manager.initialize()

    print()
    print(
        "Workspace initialized successfully."
    )

    print()
    print(
        f"Workspace ID: "
        f"{manifest['workspace_id']}"
    )

    print(
        f"Schema Version: "
        f"{manifest['schema_version']}"
    )

    print()
    print(
        "Sample architecture:"
    )

    print(
        "  SELF-CONTAINED / UNIVERSAL"
    )

    print(
        "  Existing Samples: 001–025"
    )

    print(
        "  Future Samples: 026+"
    )

    print()
    print(
        "Existing Samples were not touched."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())