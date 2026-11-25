"""Recover model-order transactions left by older versions before migration."""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


def _write_manifest(journal_dir: Path, manifest: dict[str, Any]) -> None:
    temporary = journal_dir / "manifest.tmp"
    temporary.write_text(json.dumps(manifest), encoding="utf-8")
    os.replace(temporary, journal_dir / "manifest.json")


def _write_config(config_file: Path, data: bytes) -> None:
    config_file.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".model-order-", dir=config_file.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        os.replace(temporary, config_file)
    finally:
        temporary.unlink(missing_ok=True)


def recover_legacy_model_order(model_dir: Path, config_file: Path) -> None:
    """Restore an interrupted legacy transaction or clean up a committed one.

    A failed recovery is left in place and must stop startup before migration.
    """
    journal_dir = model_dir / ".model-order-transaction"
    if not journal_dir.exists():
        return
    manifest_path = journal_dir / "manifest.json"
    if not manifest_path.exists():
        entries = list(journal_dir.iterdir())
        if all(entry.name == "manifest.tmp" and entry.is_file() for entry in entries):
            shutil.rmtree(journal_dir)
            return
        raise RuntimeError("Legacy model transaction has no recovery manifest")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    originals: list[int] = manifest["originals"]
    order: list[int] = manifest["order"]
    phase = manifest["phase"]
    if phase == "committed":
        shutil.rmtree(journal_dir)
        return
    if phase == "publishing":
        for destination, source in enumerate(order):
            staged = journal_dir / f"model-{source}"
            target = model_dir / str(destination)
            if not staged.exists():
                if not target.is_dir() or target.is_symlink():
                    raise RuntimeError(f"Missing published model during recovery: {destination}")
                target.rename(staged)
    elif phase not in ("staging", "restoring"):
        raise RuntimeError(f"Unknown legacy model transaction phase: {phase}")

    if phase != "restoring":
        manifest["phase"] = "restoring"
        _write_manifest(journal_dir, manifest)
    for source in originals:
        staged = journal_dir / f"model-{source}"
        target = model_dir / str(source)
        if staged.exists():
            if target.exists():
                raise RuntimeError(f"Cannot restore model: slot {source} is occupied")
            staged.rename(target)
        elif not target.is_dir() or target.is_symlink():
            raise RuntimeError(f"Missing original model during recovery: {source}")
        original_params = base64.b64decode(manifest["params"][str(source)])
        params_file = target / "params.json"
        if params_file.read_bytes() != original_params:
            params_file.write_bytes(original_params)
    _write_config(config_file, base64.b64decode(manifest["config"]))
    shutil.rmtree(journal_dir)
