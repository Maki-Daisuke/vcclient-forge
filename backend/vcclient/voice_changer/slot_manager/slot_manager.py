import os
import shutil
import stat
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from vcclient.logger import logger

from ...exception import (
    ERROR_CODE_ESTIMATE_RVC_MODEL_FAILED,
    ERROR_CODE_SLOT_INDEX_NOT_FOUND,
    ERROR_CODE_SLOT_STATE_CONFLICT,
    VCClientError,
)
from ..data_types.slot_manager_data_types import (
    ModelImportParamMember,
    MoveModelParam,
    ReservedForSampleModelImportParam,
    ReservedForSampleSlotInfo,
    RVCSlotInfo,
    SetIconParam,
    SlotInfo,
    SlotInfoMember,
)
from ..voice_chanager_const import (
    MAX_SLOT_INDEX,
    SLOT_PARAM_FILE,
    ModelDir,
)
from .model_importer.model_importer import import_model
from .model_importer.rvc_model_estimator.rvc_model_estimator import estimate_rvc_model
from .onnx_exporter import export_pth_to_onnx


def load_slot_info(model_dir: Path, slot_index: int) -> SlotInfoMember:
    slot_dir = model_dir / str(slot_index)
    json_file = slot_dir / SLOT_PARAM_FILE
    if not os.path.exists(json_file):
        blank = SlotInfo()
        blank.voice_changer_type = None
        blank.slot_index = slot_index
        return blank
    try:
        content = open(json_file, "r", encoding="utf-8").read()
        tmp = SlotInfo.model_validate_json(content)
        slot_info: SlotInfoMember
        if tmp.voice_changer_type == "RESERVED_FOR_SAMPLE":
            slot_info = ReservedForSampleSlotInfo.model_validate_json(content)
        elif tmp.voice_changer_type == "RVC":
            slot_info = RVCSlotInfo.model_validate_json(content)
        else:
            slot_info = tmp
        slot_info.slot_index = slot_index
        return slot_info
    except Exception as e:
        logger.error("Error in loading slot info: %s", e)
        broken = SlotInfo()
        broken.voice_changer_type = "BROKEN"
        broken.slot_index = slot_index
        return broken


def reload_slot_infos(model_dir: Path) -> list[SlotInfoMember]:
    # 実際に存在する数字名ディレクトリを特定（ただし MAX_SLOT_INDEX 未満の正当なスロットのみ走査）
    existing_indices: set[int] = set()
    if model_dir.exists():
        for entry in model_dir.iterdir():
            if entry.is_dir() and entry.name.isdigit():
                idx = int(entry.name)
                if 0 <= idx < MAX_SLOT_INDEX:
                    existing_indices.add(idx)

    max_idx = max(existing_indices) if existing_indices else -1
    # 常に「現在の最大スロット番号 + 1（次の空き枠）」までを生成。
    # スロットが1つもない場合でも、スロット0を空き枠として生成する（要素数1）。
    # ただし MAX_SLOT_INDEX（199）を超えないように制限。
    slot_count = min(max_idx + 2, MAX_SLOT_INDEX) if max_idx >= 0 else 1

    slot_infos: list[SlotInfoMember] = []
    for i in range(slot_count):
        slot_info = load_slot_info(model_dir, i)
        slot_infos.append(slot_info)

    return slot_infos


def safe_rmtree(target_dir: Path | str, retries: int = 3, delay: float = 0.1) -> None:
    """Windows の ReadOnly 属性や一時的なファイルロック、POSIX 権限に対応した安全なディレクトリ削除関数。"""
    p = Path(target_dir)
    if not p.exists():
        return

    def _ensure_writable(path: Path | str) -> None:
        try:
            p_item = Path(path)
            if p_item.is_dir():
                os.chmod(p_item, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
            else:
                os.chmod(p_item, stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            pass

    def _make_writable_recursively(root: Path) -> None:
        _ensure_writable(root)
        try:
            for item in root.rglob("*"):
                _ensure_writable(item)
        except OSError:
            pass

    def _on_exc(func: Callable[..., Any], exc_path: str, _exc: BaseException) -> None:
        _ensure_writable(exc_path)

    for attempt in range(retries):
        try:
            _make_writable_recursively(p)
            shutil.rmtree(p, onexc=_on_exc)
            if not p.exists():
                return
        except OSError:
            pass
        if attempt < retries - 1:
            time.sleep(delay)

    if p.exists():
        shutil.rmtree(p)


def validate_slot_index(index: int, param_name: str = "slot_index") -> int:
    """Raise unless index is a valid slot ID; return the validated index."""
    if index < 0 or index >= MAX_SLOT_INDEX:
        raise VCClientError(
            ERROR_CODE_SLOT_INDEX_NOT_FOUND,
            f"{param_name} {index} is invalid (must be 0 <= index < {MAX_SLOT_INDEX})",
        )
    return index


class SlotManager:
    _instance: SlotManager | None = None
    slot_infos: list[SlotInfoMember]

    @classmethod
    def get_instance(cls) -> SlotManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self.reload()

    def reload(self) -> list[SlotInfoMember]:
        logger.debug("Reloading Slot info")
        self.slot_infos = reload_slot_infos(ModelDir)
        return self.slot_infos

    def get_slot_infos(self) -> list[SlotInfoMember]:
        return self.slot_infos

    def get_slot_info(self, index: int) -> SlotInfoMember:
        valid_index = validate_slot_index(index, "Slot index")
        for slot_info in self.slot_infos:
            if slot_info.slot_index == valid_index:
                return slot_info
        return load_slot_info(ModelDir, valid_index)

    def get_blank_slot_index(self) -> int:
        self.reload()
        for slot_info in self.slot_infos:
            if slot_info.voice_changer_type is None:
                return slot_info.slot_index
        raise VCClientError(
            ERROR_CODE_SLOT_INDEX_NOT_FOUND,
            f"No blank slot available (max {MAX_SLOT_INDEX} slots reached)",
        )

    def set_new_slot(self, model_import_param: ModelImportParamMember, remove_src: bool = False) -> None:
        if model_import_param.slot_index is None:
            model_import_param.slot_index = self.get_blank_slot_index()
        validate_slot_index(model_import_param.slot_index)
        if self.get_slot_info(model_import_param.slot_index).voice_changer_type is not None:
            raise VCClientError(
                ERROR_CODE_SLOT_STATE_CONFLICT,
                f"slot_index:{model_import_param.slot_index} is already occupied.",
            )
        logger.info("set new slot: %s", model_import_param)
        import_model(ModelDir, model_import_param, remove_src)
        self.reload()

    def reserve_slot_for_sample(self, slot_index: int, progress: float = 0) -> None:
        """
        サンプル用にスロットを確保する。
        サンプルのインポートは次の流れを想定している。
        (1)リザーブ -> (2)ダウンロード -> (3)解放 -> (4)インポートの流れで処理を行う
        厳密には(3)から(4)にかけてをアトミックにする必要があるが、厳密にはやらない。
        隙間に入り込まれたら処理が壊れるが、その場合はスロットをデリートすることで対応してもらう。

        ※別の観点で、同じファイル名のサンプルが同時にダウンロードされると、uploadフォルダ内で上書きされてしまうが、それもまずは見てみなふりをする。
        """
        validate_slot_index(slot_index)
        if self.get_slot_info(slot_index).voice_changer_type is not None:
            raise VCClientError(ERROR_CODE_SLOT_STATE_CONFLICT, f"slot_index:{slot_index} is already occupied.")
        import_param = ReservedForSampleModelImportParam(
            voice_changer_type="RESERVED_FOR_SAMPLE",
            name="RESERVED_FOR_SAMPLE",
            slot_index=slot_index,
            progress=progress,
        )
        import_model(ModelDir, import_param)
        self.reload()

    def update_slot_for_sample(self, slot_index: int, progress: float) -> None:
        slot_info = self.get_slot_info(slot_index)
        if not isinstance(slot_info, ReservedForSampleSlotInfo):
            raise VCClientError(
                ERROR_CODE_SLOT_STATE_CONFLICT,
                f"slot_index:{slot_index} is not reserved for sample.",
            )
        slot_info.progress = progress

    def release_slot_from_reseved_for_sample(self, slot_index: int) -> None:
        """
        サンプル用に確保していたスロットを解放する。
        reserve_new_slot_as_sampleを参照。
        """
        self.delete_slot(slot_index)

    def delete_slot(self, slot_index: int) -> None:
        validate_slot_index(slot_index)
        slot_dir = ModelDir / str(slot_index)
        if os.path.exists(slot_dir):
            safe_rmtree(slot_dir)
        self.reload()

    def save_slot_info(self, slot_info: SlotInfoMember) -> None:
        slot_dir = ModelDir / f"{slot_info.slot_index}"
        slot_dir.mkdir(parents=True, exist_ok=True)
        config_file = slot_dir / SLOT_PARAM_FILE
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(slot_info.model_dump_json(indent=4))
        self.reload()

    def update_slot_info(self, slot_info: SlotInfoMember) -> None:
        validate_slot_index(slot_info.slot_index)
        org_slot_info = self.get_slot_info(slot_info.slot_index)
        logger.debug("updating slot info: org => %s", org_slot_info)
        if org_slot_info.voice_changer_type is None:
            raise VCClientError(
                ERROR_CODE_SLOT_STATE_CONFLICT,
                f"slot_index:{slot_info.slot_index} does not exist.",
            )
        logger.debug("updating slot info: new => %s", slot_info)
        self.save_slot_info(slot_info)

    def find_legacy_pth_slots(self) -> list[tuple[int, Path]]:
        """スロットディレクトリを走査し、.pth が存在して .onnx が未生成のスロット一覧を返す。

        Returns:
            [(slot_index, pth_file_path), ...]
        """
        legacy_slots: list[tuple[int, Path]] = []
        if not ModelDir.exists():
            return legacy_slots

        # 実際に存在する数字名のスロットディレクトリのみを昇順で走査
        slot_dirs: list[tuple[int, Path]] = []
        for entry in ModelDir.iterdir():
            if entry.is_dir() and entry.name.isdigit():
                slot_dirs.append((int(entry.name), entry))

        slot_dirs.sort(key=lambda x: x[0])

        for slot_index, slot_dir in slot_dirs:
            if slot_index >= MAX_SLOT_INDEX:
                continue
            slot_info = self.get_slot_info(slot_index)
            pth_file = None
            if isinstance(slot_info, RVCSlotInfo) and slot_info.model_file:
                target = slot_dir / slot_info.model_file.name
                if target.suffix == ".pth" and target.exists():
                    pth_file = target

            if pth_file is None:
                pths = list(slot_dir.glob("*.pth"))
                if pths:
                    pth_file = pths[0]

            if pth_file and pth_file.exists():
                onnx_file = slot_dir / f"{pth_file.stem}.onnx"
                if not onnx_file.exists():
                    legacy_slots.append((slot_index, pth_file))

        return legacy_slots

    def convert_legacy_slot_to_onnx(self, slot_index: int, pth_path: Path) -> None:
        """指定スロットの .pth モデルを .onnx に変換し、スロット情報を更新する。"""
        slot_dir = ModelDir / str(slot_index)
        onnx_file = slot_dir / f"{pth_path.stem}.onnx"
        logger.info(
            "Converting legacy PyTorch model to ONNX for slot %s: %s -> %s",
            slot_index,
            pth_path,
            onnx_file,
        )
        export_pth_to_onnx(pth_path, onnx_file)

        existing_info = self.get_slot_info(slot_index)
        new_slot_info = estimate_rvc_model(onnx_file)
        if not isinstance(new_slot_info, RVCSlotInfo):
            raise VCClientError(
                ERROR_CODE_ESTIMATE_RVC_MODEL_FAILED,
                f"Converted model is not an RVC model: {onnx_file}",
            )
        new_slot_info.slot_index = slot_index

        if isinstance(existing_info, RVCSlotInfo):
            if existing_info.name:
                new_slot_info.name = existing_info.name
            if existing_info.description:
                new_slot_info.description = existing_info.description
            if existing_info.credit:
                new_slot_info.credit = existing_info.credit
            if existing_info.terms_of_use_url:
                new_slot_info.terms_of_use_url = existing_info.terms_of_use_url
            if existing_info.icon_file and (slot_dir / existing_info.icon_file.name).exists():
                new_slot_info.icon_file = existing_info.icon_file
            if existing_info.index_file and (slot_dir / existing_info.index_file.name).exists():
                new_slot_info.index_file = existing_info.index_file
            if existing_info.speakers:
                new_slot_info.speakers = existing_info.speakers
            new_slot_info.chunk_sec = existing_info.chunk_sec
            new_slot_info.pitch_shift = existing_info.pitch_shift
            new_slot_info.index_ratio = existing_info.index_ratio
            new_slot_info.protect_ratio = existing_info.protect_ratio
        else:
            indexes = list(slot_dir.glob("*.index"))
            if indexes:
                new_slot_info.index_file = Path(indexes[0].name)
            icons = [f for f in slot_dir.glob("*.*") if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif")]
            if icons:
                new_slot_info.icon_file = Path(icons[0].name)

        self.save_slot_info(new_slot_info)

    def move_model_slot(self, param: MoveModelParam) -> None:
        validate_slot_index(param.src, "src")
        validate_slot_index(param.dst, "dst")
        if self.get_slot_info(param.dst).voice_changer_type is not None:
            raise VCClientError(ERROR_CODE_SLOT_STATE_CONFLICT, f"dst:{param.dst} is already occupied.")
        if self.get_slot_info(param.src).voice_changer_type is None:
            raise VCClientError(ERROR_CODE_SLOT_STATE_CONFLICT, f"src:{param.src} does not exist.")
        slot_info = self.get_slot_info(param.src)
        slot_info.slot_index = param.dst
        src_path = ModelDir / str(param.src)
        dst_path = ModelDir / str(param.dst)
        if os.path.exists(src_path):
            shutil.move(src_path, dst_path)
        slot_dir = ModelDir / f"{param.dst}"
        config_file = slot_dir / SLOT_PARAM_FILE
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(slot_info.model_dump_json(indent=4))
        self.reload()

    def set_icon_file(self, param: SetIconParam) -> None:
        validate_slot_index(param.slot_index)
        slot_info = self.get_slot_info(param.slot_index)
        if slot_info.voice_changer_type is None:
            raise VCClientError(
                ERROR_CODE_SLOT_STATE_CONFLICT,
                f"slot_index:{param.slot_index} does not exist.",
            )
        icon_dst_path = ModelDir / f"{param.slot_index}" / param.icon_file.name
        shutil.move(param.icon_file, icon_dst_path)
        slot_info.icon_file = Path(icon_dst_path.name)
        self.update_slot_info(slot_info)
