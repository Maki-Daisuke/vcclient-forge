from __future__ import annotations

import json
import math
import mimetypes
import os
import re
import secrets
import shutil
import string
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, cast

from vcclient.exception import VCClientError, VCClientErrorInfo
from vcclient.logger import logger
from vcclient.server.api_common import (
    DomainApiError,
    compute_etag,
    ensure_model_not_in_use,
    ensure_model_not_starting,
    verify_if_match,
)

from .. import voice_changer_const
from ..data_types.slot_manager_data_types import RVCSlotInfo
from ..settings_manager import clear_model_id_if_matches
from ..slot_manager.model_importer.rvc_model_estimator.rvc_model_estimator import estimate_rvc_model
from ..voice_changer_const import EmbedderType, InferencerType
from .data_types import Model, ModelUpdate, StoredModelParams

ICON_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".bmp"}
_NANOID_ALPHABET = string.ascii_letters + string.digits
_VALID_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
_INVALID_DIRNAME_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
_WHITESPACE_RE = re.compile(r"\s+")
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}
_VALID_EMBEDDERS: set[str] = {
    "hubert_base_l9fp",
    "hubert_base_l12",
    "hubert_base_japanese_l9fp",
    "hubert_base_japanese_l12",
}


def generate_nanoid(length: int = 12) -> str:
    """Generate a URL- and filename-safe alphanumeric NanoID."""
    return "".join(secrets.choice(_NANOID_ALPHABET) for _ in range(length))


def sanitize_model_dirname(name: str) -> str:
    """Sanitize a display name into a cross-platform directory prefix."""
    cleaned = _INVALID_DIRNAME_CHARS_RE.sub("_", name)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip(" .")
    if len(cleaned) > 64:
        cleaned = cleaned[:64].rstrip(" .")
    if not cleaned or cleaned.upper() in _WINDOWS_RESERVED_NAMES:
        return "Model"
    return cleaned


def format_model_dirname(name: str, model_id: str) -> str:
    """Return the canonical model directory name `{sanitized_name} - {id}`."""
    return f"{sanitize_model_dirname(name)} - {model_id}"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(text, encoding="utf-8")
        tmp_path.replace(path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _existing_file_name(entry_dir: Path, raw_value: object, fallback_glob: str | None = None) -> str | None:
    if isinstance(raw_value, str) and raw_value.strip():
        candidate = Path(raw_value).name
        if (entry_dir / candidate).is_file():
            return candidate
    if fallback_glob is not None:
        matches = sorted(p for p in entry_dir.glob(fallback_glob) if p.is_file())
        if matches:
            return matches[0].name
    return None


def _existing_icon_name(entry_dir: Path, raw_value: object) -> str | None:
    if isinstance(raw_value, str) and raw_value.strip():
        candidate = Path(raw_value).name
        if (entry_dir / candidate).is_file():
            return candidate
    icons = sorted(p for p in entry_dir.iterdir() if p.is_file() and p.suffix.lower() in ICON_SUFFIXES)
    return icons[0].name if icons else None


def _normalize_embedder(raw_embedder: object) -> EmbedderType | None:
    if isinstance(raw_embedder, str):
        if raw_embedder in _VALID_EMBEDDERS:
            return cast(EmbedderType, raw_embedder)
        if raw_embedder == "contentvec":
            return "hubert_base_l12"
    return None


_lock = threading.RLock()
_cached_model_dir: Path | None = None
_cached_slot_infos: dict[str, RVCSlotInfo] = {}


def _to_rvc_slot_info(stored: StoredModelParams, entry_dir: Path) -> RVCSlotInfo | None:
    if not stored.model_file:
        return None
    model_path = (entry_dir / Path(stored.model_file).name).resolve()
    if not model_path.is_file():
        return None
    index_path = (
        (entry_dir / Path(stored.index_file).name).resolve()
        if stored.index_file and (entry_dir / Path(stored.index_file).name).is_file()
        else None
    )
    return RVCSlotInfo(
        slot_index=-1,
        model_id=stored.id,
        voice_changer_type="RVC",
        name=stored.name,
        model_file=model_path,
        index_file=index_path,
        is_onnx=stored.is_onnx,
        inferencer_type=stored.inferencer_type,
        sample_rate=stored.sample_rate,
        is_f0=stored.is_f0,
        embedder=stored.embedder,
        pitch_estimator=stored.pitch_estimator,
        version=stored.version,
        chunk_sec=stored.chunk_sec,
        pitch_shift=stored.pitch_shift,
        index_ratio=stored.index_ratio,
    )


def _replace_slot_cache_locked(model_dir: Path, entries: dict[str, tuple[StoredModelParams, Path]]) -> None:
    global _cached_model_dir, _cached_slot_infos
    next_cache: dict[str, RVCSlotInfo] = {}
    for mid, (stored, entry_dir) in entries.items():
        slot_info = _to_rvc_slot_info(stored, entry_dir)
        if slot_info is not None:
            next_cache[mid] = slot_info
    _cached_model_dir = model_dir
    _cached_slot_infos = next_cache


def _upsert_slot_cache_locked(model_dir: Path, stored: StoredModelParams, entry_dir: Path) -> None:
    global _cached_model_dir, _cached_slot_infos
    next_cache = dict(_cached_slot_infos) if _cached_model_dir == model_dir else {}
    slot_info = _to_rvc_slot_info(stored, entry_dir)
    if slot_info is not None:
        next_cache[stored.id] = slot_info
    else:
        next_cache.pop(stored.id, None)
    _cached_model_dir = model_dir
    _cached_slot_infos = next_cache


def _remove_slot_cache_locked(model_dir: Path, model_id: str) -> None:
    global _cached_slot_infos
    if _cached_model_dir == model_dir:
        next_cache = dict(_cached_slot_infos)
        next_cache.pop(model_id, None)
        _cached_slot_infos = next_cache


def _model_dir() -> Path:
    return Path(voice_changer_const.ModelDir)


def _config_file() -> Path:
    return Path(voice_changer_const.ConfigFile)


def _catalog_file(model_dir: Path) -> Path:
    return model_dir / "catalog.json"


def _read_raw_catalog_order(catalog_file: Path) -> list[str]:
    if not catalog_file.is_file():
        return []
    try:
        data = json.loads(catalog_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read catalog.json (%s): %s", catalog_file, exc)
        return []
    raw_order = data.get("order") if isinstance(data, dict) else None
    if not isinstance(raw_order, list):
        return []
    return [item for item in raw_order if isinstance(item, str) and item]


def _write_catalog_order(catalog_file: Path, order: list[str]) -> None:
    _atomic_write_text(catalog_file, json.dumps({"order": order}, indent=4))


def _unique_id(existing_ids: set[str], preferred: object = None) -> str:
    if isinstance(preferred, str) and _VALID_ID_RE.fullmatch(preferred) and preferred not in existing_ids:
        existing_ids.add(preferred)
        return preferred
    while True:
        candidate = generate_nanoid()
        if candidate not in existing_ids:
            existing_ids.add(candidate)
            return candidate


def _collect_existing_ids(model_dir: Path) -> set[str]:
    ids: set[str] = set()
    if not model_dir.exists():
        return ids
    for entry in model_dir.iterdir():
        if not entry.is_dir() or entry.name.startswith(".") or entry.name.isdigit():
            continue
        params_path = entry / voice_changer_const.SLOT_PARAM_FILE
        if params_path.is_file():
            try:
                data = json.loads(params_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("id"), str) and data["id"]:
                    ids.add(data["id"])
            except Exception:
                pass
    return ids


_EXPORT_ONNX_TIMEOUT_SEC = 300.0


def _parse_vcclient_error(stderr: str) -> VCClientError | None:
    for line in reversed(stderr.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        try:
            info = VCClientErrorInfo.model_validate_json(candidate)
        except Exception:
            continue
        return VCClientError(info.code, detail=info.detail)
    return None


def export_pth_to_onnx(
    pth_path: Path | str,
    output_path: Path | str | None = None,
    *,
    timeout: float = _EXPORT_ONNX_TIMEOUT_SEC,
) -> Path:
    """Convert a legacy .pth checkpoint to ONNX in an isolated subprocess."""
    pth_file = Path(pth_path).resolve()
    out_file = (Path(pth_path).with_suffix(".onnx") if output_path is None else Path(output_path)).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0

    # Stage subprocess output inside a hidden directory so crashes/timeouts never leave a partial .onnx behind.
    with tempfile.TemporaryDirectory(dir=out_file.parent, prefix=".export-onnx-") as tmp_dir:
        staged_out = Path(tmp_dir) / out_file.name
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "export-onnx", str(pth_file), str(staged_out)]
        else:
            main_py = Path(__file__).resolve().parents[3] / "main.py"
            cmd = [sys.executable, str(main_py), "export-onnx", str(pth_file), str(staged_out)]

        logger.info("Converting .pth model to ONNX via subprocess: %s -> %s", pth_file, out_file)
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                creationflags=creationflags,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"export-onnx timed out after {timeout:g}s") from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            if result.returncode == 2:
                vc_error = _parse_vcclient_error(detail)
                if vc_error is not None:
                    raise vc_error
            raise RuntimeError(detail or f"export-onnx failed with exit code {result.returncode}")
        if not staged_out.is_file():
            raise RuntimeError(f"export-onnx completed without creating output file: {out_file}")
        os.replace(staged_out, out_file)
    return out_file


def _migrate_single_legacy_slot(
    model_dir: Path,
    slot_index: int,
    slot_dir: Path,
    existing_ids: set[str],
) -> str | None:
    params_path = slot_dir / voice_changer_const.SLOT_PARAM_FILE
    raw_params: dict[str, Any] = {}
    if params_path.is_file():
        try:
            loaded = json.loads(params_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                raw_params = loaded
        except Exception as exc:
            logger.warning("Ignoring unreadable legacy params.json in slot %s: %s", slot_index, exc)

    vc_type = raw_params.get("voice_changer_type")
    if params_path.is_file() and vc_type is not None and vc_type != "RVC":
        return None

    onnx_name = _existing_file_name(slot_dir, raw_params.get("model_file"), "*.onnx")
    onnx_path: Path | None = slot_dir / onnx_name if onnx_name and onnx_name.endswith(".onnx") else None

    if onnx_path is None:
        pth_name = _existing_file_name(slot_dir, raw_params.get("model_file"), "*.pth")
        if pth_name is None or not pth_name.endswith(".pth"):
            return None
        pth_path = slot_dir / pth_name
        onnx_path = slot_dir / f"{pth_path.stem}.onnx"
        if not onnx_path.exists():
            export_pth_to_onnx(pth_path, onnx_path)

    embedder = _normalize_embedder(raw_params.get("embedder"))
    sample_rate = raw_params.get("sample_rate")
    has_estimated_meta = (
        isinstance(sample_rate, int)
        and sample_rate > 0
        and isinstance(raw_params.get("is_f0"), bool)
        and embedder is not None
    )
    if not has_estimated_meta:
        estimated = estimate_rvc_model(onnx_path)
        is_f0 = estimated.is_f0
        sample_rate_val = estimated.sample_rate
        inferencer_type = estimated.inferencer_type
        embedder_val: EmbedderType = embedder or estimated.embedder
        version_val = str(raw_params.get("version") or estimated.version)
    else:
        assert isinstance(sample_rate, int)
        assert embedder is not None
        is_f0 = bool(raw_params["is_f0"])
        sample_rate_val = sample_rate
        raw_inf = raw_params.get("inferencer_type")
        if raw_inf in ("onnxRVC", "onnxRVCNono"):
            inferencer_type = cast(InferencerType, raw_inf)
        elif isinstance(raw_inf, str) and "Nono" in raw_inf:
            inferencer_type = "onnxRVCNono"
        else:
            inferencer_type = "onnxRVC" if is_f0 else "onnxRVCNono"
        embedder_val = embedder
        version_val = str(raw_params.get("version") or "")

    name = str(raw_params.get("name") or "").strip() or onnx_path.stem
    model_id = _unique_id(existing_ids, raw_params.get("id"))
    index_name = _existing_file_name(slot_dir, raw_params.get("index_file"), "*.index")
    icon_name = _existing_icon_name(slot_dir, raw_params.get("icon_file"))
    raw_rev = raw_params.get("icon_revision")
    icon_revision = int(raw_rev) if isinstance(raw_rev, int) and raw_rev >= 0 else (1 if icon_name else 0)
    if icon_name and icon_revision == 0:
        icon_revision = 1

    stored = StoredModelParams(
        id=model_id,
        voice_changer_type="RVC",
        name=name,
        model_file=onnx_path.name,
        index_file=index_name,
        icon_file=icon_name,
        icon_revision=icon_revision,
        is_onnx=True,
        inferencer_type=inferencer_type,
        sample_rate=sample_rate_val,
        is_f0=is_f0,
        embedder=embedder_val,
        pitch_estimator=raw_params.get("pitch_estimator", "rmvpe"),
        version=version_val,
        chunk_sec=float(raw_params.get("chunk_sec", 0.5)),
        pitch_shift=int(raw_params.get("pitch_shift", 0)),
        index_ratio=float(raw_params.get("index_ratio", 0.0)),
    )
    _atomic_write_text(params_path, stored.model_dump_json(indent=4))

    target_dir = model_dir / format_model_dirname(stored.name, stored.id)
    if target_dir.exists():
        target_dir = model_dir / format_model_dirname("Model", generate_nanoid())
    slot_dir.rename(target_dir)
    logger.info("Migrated legacy model slot %s to '%s' (id=%s)", slot_index, target_dir.name, stored.id)
    return stored.id


def _migrate_legacy_numeric_slots(model_dir: Path, config_file: Path) -> None:
    legacy_slots: list[tuple[int, Path]] = []
    for entry in model_dir.iterdir():
        if entry.is_dir() and entry.name.isdigit():
            idx = int(entry.name)
            if 0 <= idx < voice_changer_const.MAX_SLOT_INDEX:
                legacy_slots.append((idx, entry))
    if not legacy_slots:
        return

    legacy_slots.sort(key=lambda item: item[0])
    existing_ids = _collect_existing_ids(model_dir)
    migrated_slot_map: dict[int, str] = {}
    migrated_order: list[str] = []

    for slot_index, slot_dir in legacy_slots:
        try:
            model_id = _migrate_single_legacy_slot(model_dir, slot_index, slot_dir, existing_ids)
            if model_id is not None:
                migrated_slot_map[slot_index] = model_id
                migrated_order.append(model_id)
        except Exception as exc:
            logger.error("Failed to migrate legacy slot %s: %s", slot_index, exc, exc_info=True)

    if not migrated_slot_map:
        return

    catalog_file = _catalog_file(model_dir)
    order = _read_raw_catalog_order(catalog_file)
    for model_id in migrated_order:
        if model_id not in order:
            order.append(model_id)
    _write_catalog_order(catalog_file, order)

    if config_file.is_file():
        try:
            conf_data = json.loads(config_file.read_text(encoding="utf-8"))
            if isinstance(conf_data, dict) and not conf_data.get("model_id"):
                selected_slot = conf_data.get("current_slot_index")
                if isinstance(selected_slot, int) and selected_slot in migrated_slot_map:
                    conf_data["model_id"] = migrated_slot_map[selected_slot]
                    _atomic_write_text(config_file, json.dumps(conf_data, indent=4))
        except Exception as exc:
            logger.warning("Failed to migrate selected model_id in %s: %s", config_file, exc)

    from ..configuration_manager.configuration_manager import ConfigurationManager

    cm = ConfigurationManager._instance
    if cm is not None and cm.voice_changer_configuration.model_id is None:
        selected = cm.voice_changer_configuration.current_slot_index
        if selected in migrated_slot_map:
            cm.voice_changer_configuration.model_id = migrated_slot_map[selected]


def _scan_catalog_locked() -> tuple[dict[str, tuple[StoredModelParams, Path]], list[str]]:
    model_dir = _model_dir()
    if not model_dir.exists():
        _replace_slot_cache_locked(model_dir, {})
        return ({}, [])

    _migrate_legacy_numeric_slots(model_dir, _config_file())

    entries: dict[str, tuple[StoredModelParams, Path]] = {}
    for entry in sorted(model_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_dir() or entry.name.startswith(".") or entry.name.isdigit():
            continue
        params_path = entry / voice_changer_const.SLOT_PARAM_FILE
        if not params_path.is_file():
            continue
        try:
            raw = json.loads(params_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                continue
            if raw.get("voice_changer_type", "RVC") != "RVC":
                continue
            needs_save = False
            if not raw.get("id") or str(raw["id"]) in entries:
                raw["id"] = generate_nanoid()
                while raw["id"] in entries:
                    raw["id"] = generate_nanoid()
                needs_save = True
            if raw.get("embedder") == "contentvec":
                raw["embedder"] = "hubert_base_l12"
                needs_save = True
            if "icon_revision" not in raw:
                has_ico = _existing_icon_name(entry, raw.get("icon_file")) is not None
                raw["icon_revision"] = 1 if has_ico else 0
                needs_save = True
            stored = StoredModelParams.model_validate(raw)
            if needs_save:
                _atomic_write_text(params_path, stored.model_dump_json(indent=4))
            entries[stored.id] = (stored, entry)
        except Exception as exc:
            logger.warning("Skipping invalid model directory '%s': %s", entry, exc)

    catalog_file = _catalog_file(model_dir)
    saved_order = _read_raw_catalog_order(catalog_file)
    reconciled_order = [model_id for model_id in saved_order if model_id in entries]
    seen = set(reconciled_order)
    for model_id in entries:
        if model_id not in seen:
            reconciled_order.append(model_id)
            seen.add(model_id)

    if reconciled_order != saved_order or (entries and not catalog_file.is_file()):
        _write_catalog_order(catalog_file, reconciled_order)

    _replace_slot_cache_locked(model_dir, entries)
    return (entries, reconciled_order)


def _to_wire_model(stored: StoredModelParams, entry_dir: Path) -> Model:
    has_icon = stored.icon_file is not None and (entry_dir / Path(stored.icon_file).name).is_file()
    return stored.to_model(model_dir_has_icon=has_icon)


def _resolve_entry_locked(model_id: str) -> tuple[Model, StoredModelParams, Path]:
    entries, _ = _scan_catalog_locked()
    if model_id not in entries:
        raise DomainApiError(404, "model_not_found", f"Model '{model_id}' not found.", {"model_id": model_id})
    stored, entry_dir = entries[model_id]
    return (_to_wire_model(stored, entry_dir), stored, entry_dir)


def list_models() -> list[Model]:
    with _lock:
        entries, order = _scan_catalog_locked()
        return [_to_wire_model(*entries[model_id]) for model_id in order]


def get_model(model_id: str) -> tuple[Model, str]:
    with _lock:
        model, _, _ = _resolve_entry_locked(model_id)
        return (model, compute_etag(model.model_dump()))


def get_model_entry(model_id: str) -> tuple[Model, StoredModelParams, Path]:
    with _lock:
        return _resolve_entry_locked(model_id)


def get_slot_info_by_model_id(model_id: str, *, use_cache_only: bool = False) -> RVCSlotInfo | None:
    """Resolve an RVCSlotInfo with absolute paths by NanoID `model_id`."""
    if use_cache_only:
        if _cached_model_dir != _model_dir():
            return None
        return _cached_slot_infos.get(model_id)
    with _lock:
        entries, _ = _scan_catalog_locked()
        entry = entries.get(model_id)
        if entry is None:
            return None
        stored, entry_dir = entry
        return _to_rvc_slot_info(stored, entry_dir)


def get_probe_slot_info(preferred_model_id: str | None = None) -> RVCSlotInfo | None:
    """Build a temporary RVCSlotInfo pointing to absolute model paths for device probing."""
    with _lock:
        entries, order = _scan_catalog_locked()
        candidate_ids = list(order)
        if preferred_model_id and preferred_model_id in entries:
            candidate_ids = [preferred_model_id] + [mid for mid in order if mid != preferred_model_id]
        for model_id in candidate_ids:
            slot_info = _to_rvc_slot_info(*entries[model_id])
            if slot_info is not None:
                return slot_info
        return None


def create_model(
    *,
    name: str,
    model_path: Path,
    index_path: Path | None = None,
    icon_path: Path | None = None,
    embedder: EmbedderType | None = None,
) -> tuple[Model, str]:
    normalized_name = name.strip()
    if not normalized_name:
        raise DomainApiError(422, "validation_error", "Model name must not be empty.")

    with _lock:
        model_dir = _model_dir()
        model_dir.mkdir(parents=True, exist_ok=True)
        existing_ids = _collect_existing_ids(model_dir)
        model_id = _unique_id(existing_ids)
        target_dir = model_dir / format_model_dirname(normalized_name, model_id)
        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            copied_model = target_dir / model_path.name
            shutil.copy2(model_path, copied_model)

            copied_index_name: str | None = None
            if index_path is not None:
                copied_index = target_dir / index_path.name
                shutil.copy2(index_path, copied_index)
                copied_index_name = copied_index.name

            copied_icon_name: str | None = None
            if icon_path is not None:
                copied_icon = target_dir / icon_path.name
                shutil.copy2(icon_path, copied_icon)
                copied_icon_name = copied_icon.name

            onnx_path = copied_model
            if copied_model.suffix.lower() == ".pth":
                onnx_path = target_dir / f"{copied_model.stem}.onnx"
                logger.info("Auto-converting imported PyTorch model to ONNX: %s -> %s", copied_model, onnx_path)
                export_pth_to_onnx(copied_model, onnx_path)
                copied_model.unlink(missing_ok=True)

            estimated = estimate_rvc_model(onnx_path)
            stored = StoredModelParams(
                id=model_id,
                voice_changer_type="RVC",
                name=normalized_name,
                model_file=onnx_path.name,
                index_file=copied_index_name,
                icon_file=copied_icon_name,
                icon_revision=1 if copied_icon_name is not None else 0,
                is_onnx=True,
                inferencer_type=estimated.inferencer_type,
                sample_rate=estimated.sample_rate,
                is_f0=estimated.is_f0,
                embedder=embedder if embedder is not None else estimated.embedder,
                pitch_estimator=estimated.pitch_estimator,
                version=estimated.version,
                chunk_sec=estimated.chunk_sec,
                pitch_shift=estimated.pitch_shift,
                index_ratio=estimated.index_ratio,
            )
            _atomic_write_text(target_dir / voice_changer_const.SLOT_PARAM_FILE, stored.model_dump_json(indent=4))

            catalog_file = _catalog_file(model_dir)
            order = _read_raw_catalog_order(catalog_file)
            if model_id not in order:
                order.append(model_id)
            _write_catalog_order(catalog_file, order)
        except Exception as exc:
            shutil.rmtree(target_dir, ignore_errors=True)
            if isinstance(exc, DomainApiError):
                raise
            if isinstance(exc, VCClientError):
                detail_msg = exc.info.detail or exc.info.reason
                raise DomainApiError(
                    422,
                    "model_import_failed",
                    f"Failed to import model: {detail_msg}",
                    exc.info.model_dump(),
                ) from exc
            raise DomainApiError(422, "model_import_failed", f"Failed to import model: {exc}") from exc

        _upsert_slot_cache_locked(model_dir, stored, target_dir)
        model = _to_wire_model(stored, target_dir)
        return (model, compute_etag(model.model_dump()))


def update_model(
    model_id: str,
    update: ModelUpdate,
    *,
    if_match: str | None = None,
) -> tuple[Model, str]:
    with _lock:
        current_model, stored, entry_dir = _resolve_entry_locked(model_id)
        verify_if_match(if_match, compute_etag(current_model.model_dump()))

        next_name = stored.name
        if update.name is not None:
            next_name = update.name.strip()
            if not next_name:
                raise DomainApiError(422, "validation_error", "Model name must not be empty.")
        if update.pitch_shift is not None and not (-24 <= update.pitch_shift <= 24):
            raise DomainApiError(422, "validation_error", "pitch_shift must be between -24 and 24.")
        if update.index_ratio is not None and (
            not math.isfinite(update.index_ratio) or not (0.0 <= update.index_ratio <= 1.0)
        ):
            raise DomainApiError(422, "validation_error", "index_ratio must be between 0.0 and 1.0.")
        if update.chunk_sec is not None and (
            not math.isfinite(update.chunk_sec) or not (0.05 <= update.chunk_sec <= 5.0)
        ):
            raise DomainApiError(422, "validation_error", "chunk_sec must be between 0.05 and 5.0.")

        target_dir = entry_dir
        renamed = False
        if next_name != stored.name:
            ensure_model_not_starting(
                model_id,
                f"Cannot rename model '{model_id}' while session startup is loading it.",
            )
            candidate_dir = _model_dir() / format_model_dirname(next_name, model_id)
            if candidate_dir != entry_dir:
                if candidate_dir.exists():
                    raise DomainApiError(
                        409,
                        "model_directory_conflict",
                        f"Target directory already exists: {candidate_dir.name}",
                    )
                try:
                    entry_dir.rename(candidate_dir)
                except PermissionError as exc:
                    raise DomainApiError(
                        409,
                        "model_in_use",
                        f"Cannot rename model '{model_id}' while its files are in use.",
                        {"model_id": model_id},
                    ) from exc
                target_dir = candidate_dir
                renamed = True

        stored.name = next_name
        if update.pitch_shift is not None:
            stored.pitch_shift = update.pitch_shift
        if update.index_ratio is not None:
            stored.index_ratio = update.index_ratio
        if update.chunk_sec is not None:
            stored.chunk_sec = update.chunk_sec
        if update.pitch_estimator is not None:
            stored.pitch_estimator = update.pitch_estimator

        try:
            _atomic_write_text(target_dir / voice_changer_const.SLOT_PARAM_FILE, stored.model_dump_json(indent=4))
        except Exception:
            if renamed and target_dir != entry_dir and not entry_dir.exists():
                target_dir.rename(entry_dir)
            raise

        _upsert_slot_cache_locked(_model_dir(), stored, target_dir)
        updated = _to_wire_model(stored, target_dir)
        return (updated, compute_etag(updated.model_dump()))


def delete_model(model_id: str, *, if_match: str | None = None) -> None:
    with _lock:
        current_model, _, entry_dir = _resolve_entry_locked(model_id)
        verify_if_match(if_match, compute_etag(current_model.model_dump()))
        ensure_model_not_in_use(
            model_id,
            f"Cannot delete model '{model_id}' while it is in use by an active session.",
        )

        shutil.rmtree(entry_dir)
        model_dir = _model_dir()
        _remove_slot_cache_locked(model_dir, model_id)
        catalog_file = _catalog_file(model_dir)
        order = [item for item in _read_raw_catalog_order(catalog_file) if item != model_id]
        _write_catalog_order(catalog_file, order)
        clear_model_id_if_matches(model_id)

        from ..configuration_manager.configuration_manager import ConfigurationManager
        from ..voice_change_manager.voice_changer import VoiceChanger

        cm = ConfigurationManager._instance
        if cm is not None and cm.voice_changer_configuration.model_id == model_id:
            cm.voice_changer_configuration.model_id = None
            cm.voice_changer_configuration.current_slot_index = -1

        vc = VoiceChanger.peek_instance()
        if vc is not None and vc.vc_info.model_id == model_id:
            vc.vc_pipeline = None
            vc.vc_info.model_id = None
            vc.vc_info.slot_index = -1
            vc.vc_info.voice_changer_type = None
            vc.vc_info.pitch_estimator_type = None
            vc.vc_info.pipeline_info = None


def get_icon_path(model_id: str) -> tuple[Path, str, str]:
    with _lock:
        model, stored, entry_dir = _resolve_entry_locked(model_id)
        if stored.icon_file is None:
            raise DomainApiError(404, "icon_not_found", f"Model '{model_id}' has no icon.")
        icon_path = entry_dir / Path(stored.icon_file).name
        if not icon_path.is_file():
            raise DomainApiError(404, "icon_not_found", f"Icon file for model '{model_id}' is missing.")
        media_type = mimetypes.guess_type(icon_path.name)[0] or "application/octet-stream"
        return (icon_path, media_type, compute_etag(model.model_dump()))


def set_icon(model_id: str, icon_src: Path, *, if_match: str | None = None) -> tuple[Model, str]:
    with _lock:
        model, stored, entry_dir = _resolve_entry_locked(model_id)
        verify_if_match(if_match, compute_etag(model.model_dump()))

        old_icon_name = Path(stored.icon_file).name if stored.icon_file else None
        new_icon_name = icon_src.name
        new_icon_dst = entry_dir / new_icon_name

        shutil.copy2(icon_src, new_icon_dst)
        orig_icon = stored.icon_file
        orig_rev = stored.icon_revision
        try:
            stored.icon_file = new_icon_name
            stored.icon_revision = orig_rev + 1
            _atomic_write_text(entry_dir / voice_changer_const.SLOT_PARAM_FILE, stored.model_dump_json(indent=4))
        except Exception:
            stored.icon_file = orig_icon
            stored.icon_revision = orig_rev
            if new_icon_name != old_icon_name:
                new_icon_dst.unlink(missing_ok=True)
            raise

        if old_icon_name and old_icon_name != new_icon_name:
            protected = {name for name in (stored.model_file, stored.index_file) if name}
            if old_icon_name not in protected:
                (entry_dir / old_icon_name).unlink(missing_ok=True)

        _upsert_slot_cache_locked(_model_dir(), stored, entry_dir)
        updated = _to_wire_model(stored, entry_dir)
        return (updated, compute_etag(updated.model_dump()))


def delete_icon(model_id: str, *, if_match: str | None = None) -> tuple[Model, str]:
    with _lock:
        model, stored, entry_dir = _resolve_entry_locked(model_id)
        etag = compute_etag(model.model_dump())
        verify_if_match(if_match, etag)

        old_icon_name = Path(stored.icon_file).name if stored.icon_file else None
        if old_icon_name is None:
            return (model, etag)

        stored.icon_file = None
        stored.icon_revision += 1
        _atomic_write_text(entry_dir / voice_changer_const.SLOT_PARAM_FILE, stored.model_dump_json(indent=4))

        protected = {name for name in (stored.model_file, stored.index_file) if name}
        if old_icon_name not in protected:
            (entry_dir / old_icon_name).unlink(missing_ok=True)

        _upsert_slot_cache_locked(_model_dir(), stored, entry_dir)
        updated = _to_wire_model(stored, entry_dir)
        return (updated, compute_etag(updated.model_dump()))


def get_order() -> tuple[list[str], str]:
    with _lock:
        _, order = _scan_catalog_locked()
        return (order, compute_etag({"model_ids": order}))


def set_order(model_ids: list[str], *, if_match: str | None = None) -> tuple[list[str], str]:
    with _lock:
        _, current_order = _scan_catalog_locked()
        verify_if_match(if_match, compute_etag({"model_ids": current_order}))
        if len(model_ids) != len(current_order) or len(set(model_ids)) != len(model_ids):
            raise DomainApiError(
                409,
                "catalog_mismatch",
                "Model order does not match current catalog; reload and retry.",
                {"expected_model_ids": current_order},
            )
        if set(model_ids) != set(current_order):
            raise DomainApiError(
                409,
                "catalog_mismatch",
                "Model order does not match current catalog; reload and retry.",
                {"expected_model_ids": current_order},
            )
        _write_catalog_order(_catalog_file(_model_dir()), model_ids)
        return (list(model_ids), compute_etag({"model_ids": model_ids}))
