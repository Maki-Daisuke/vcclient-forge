"""Recoverable directory moves for a model-list change.

Callers must serialize operations and keep audio stopped while this runs.
The journal protects against process interruption, not arbitrary external writes
or power-loss durability guarantees.
"""

import base64
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from vcclient.logger import logger

from ..voice_changer_const import MAX_SLOT_INDEX


class ModelTransactionError(RuntimeError):
    pass


class ModelTransaction:
    def __init__(self, model_dir: Path, config_file: Path) -> None:
        self.model_dir = model_dir
        self.config_file = config_file
        self.journal_dir = model_dir / ".model-order-transaction"
        self.manifest_path = self.journal_dir / "manifest.json"

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        temporary = self.journal_dir / "manifest.tmp"
        temporary.write_text(json.dumps(manifest), encoding="utf-8")
        os.replace(temporary, self.manifest_path)

    def _write_config(self, data: bytes) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".model-order-", dir=self.config_file.parent)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            os.replace(temporary, self.config_file)
        finally:
            temporary.unlink(missing_ok=True)

    def _stage(self, index: int) -> Path:
        return self.journal_dir / f"model-{index}"

    def recover(self) -> None:
        if not self.journal_dir.exists():
            return
        if not self.manifest_path.exists():
            entries = list(self.journal_dir.iterdir())
            if all(entry.name == "manifest.tmp" and entry.is_file() for entry in entries):
                shutil.rmtree(self.journal_dir)
                return
            raise ModelTransactionError("Model transaction has no recovery manifest")
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        originals: list[int] = manifest["originals"]
        order: list[int] = manifest["order"]
        if manifest["phase"] == "committed":
            shutil.rmtree(self.journal_dir)
            return
        if manifest["phase"] == "publishing":
            # Every source was staged before publishing began. Recover each
            # published directory to its unique staging name first.
            for destination, source in enumerate(order):
                staged = self._stage(source)
                target = self.model_dir / str(destination)
                if not staged.exists():
                    if not target.is_dir() or target.is_symlink():
                        raise ModelTransactionError(f"Missing model during recovery: {destination}")
                    target.rename(staged)
        elif manifest["phase"] not in ("staging", "restoring"):
            raise ModelTransactionError("Unknown model transaction phase")
        if manifest["phase"] != "restoring":
            manifest["phase"] = "restoring"
            self._write_manifest(manifest)
        for source in originals:
            staged = self._stage(source)
            target = self.model_dir / str(source)
            if staged.exists():
                if target.exists():
                    raise ModelTransactionError(f"Cannot restore model: slot {source} is occupied")
                staged.rename(target)
            elif not target.is_dir() or target.is_symlink():
                raise ModelTransactionError(f"Missing original model during recovery: {source}")
            original_params = base64.b64decode(manifest["params"][str(source)])
            params_file = target / "params.json"
            if params_file.read_bytes() != original_params:
                params_file.write_bytes(original_params)
        self._write_config(base64.b64decode(manifest["config"]))
        shutil.rmtree(self.journal_dir)

    def apply(self, originals: list[int], order: list[int], selected: int) -> int:
        if self.journal_dir.exists():
            raise ModelTransactionError("An unfinished model transaction requires recovery")
        if (
            any(type(index) is not int or not 0 <= index < MAX_SLOT_INDEX for index in originals + order)
            or len(set(originals)) != len(originals)
            or len(set(order)) != len(order)
            or not set(order) <= set(originals)
        ):
            raise ModelTransactionError("Invalid model order")
        for index in originals:
            path = self.model_dir / str(index)
            if not path.is_dir() or path.is_symlink() or not (path / "params.json").is_file():
                raise ModelTransactionError(f"Model slot {index} is unavailable")
        for index in range(len(order)):
            target = self.model_dir / str(index)
            if target.exists() and index not in originals:
                raise ModelTransactionError(f"Destination slot {index} is occupied")
        config = self.config_file.read_bytes()
        manifest: dict[str, Any] = {
            "phase": "staging",
            "originals": originals,
            "order": order,
            "params": {
                str(i): base64.b64encode((self.model_dir / str(i) / "params.json").read_bytes()).decode("ascii")
                for i in originals
            },
            "config": base64.b64encode(config).decode("ascii"),
        }
        self.journal_dir.mkdir()
        self._write_manifest(manifest)
        try:
            for index in originals:
                (self.model_dir / str(index)).rename(self._stage(index))
            manifest["phase"] = "publishing"
            self._write_manifest(manifest)
            for destination, source in enumerate(order):
                staged = self._stage(source)
                params_file = staged / "params.json"
                params = json.loads(params_file.read_text(encoding="utf-8"))
                params["slot_index"] = destination
                params_file.write_text(json.dumps(params, ensure_ascii=False, indent=4), encoding="utf-8")
                staged.rename(self.model_dir / str(destination))
            new_selected = order.index(selected) if selected in order else -1
            conf = json.loads(config)
            conf["current_slot_index"] = new_selected
            self._write_config(json.dumps(conf, ensure_ascii=False, indent=4).encode("utf-8"))
            manifest["phase"] = "committed"
            self._write_manifest(manifest)
        except Exception as error:
            try:
                self.recover()
            except Exception as recovery_error:
                raise ModelTransactionError(
                    f"Model operation failed; recovery is required: {recovery_error}"
                ) from error
            raise ModelTransactionError("Model operation failed and was rolled back") from error
        try:
            self.recover()
        except OSError:
            # The operation is already committed. Keep the journal so that
            # startup can retry removing the staged, deleted files.
            logger.warning("Committed model operation requires cleanup on startup", exc_info=True)
        return new_selected
