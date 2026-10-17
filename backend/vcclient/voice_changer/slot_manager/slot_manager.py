import logging
import os
import shutil
import stat
import time
from pathlib import Path

from ...const import LOGGER_NAME
from ...exception import (
    ERROR_CODE_IMPORT_MODEL_FAILED,
    ERROR_CODE_SLOT_INDEX_NOT_FOUND,
    VCClientError,
)
from ..data_types.slot_manager_data_types import (
    ModelImportParamMember,
    MoveExportedOnnxModelParam,
    MoveModelParam,
    OnnxExportParam,
    ReservedForSampleModelImportParam,
    ReservedForSampleSlotInfo,
    RVCSlotInfo,
    SetIconParam,
    SlotInfo,
    SlotInfoMember,
)
from ..voice_chanager_const import (
    SLOT_PARAM_FILE,
    ModelDir,
)
from .model_importer.model_importer import import_model
from .model_importer.rvc_model_estimator.rvc_model_estimator import estimate_rvc_model
from .onnx_exporter import export_pth_to_onnx


def load_slot_info(model_dir: Path, slot_index: int) -> SlotInfo:
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
        if tmp.voice_changer_type == "RESERVED_FOR_SAMPLE":
            slot_info = ReservedForSampleSlotInfo.model_validate_json(content)
        elif tmp.voice_changer_type == "RVC":
            slot_info = RVCSlotInfo.model_validate_json(content)
        else:
            slot_info = tmp
        slot_info.slot_index = slot_index
        return slot_info
    except Exception as e:
        logging.getLogger(LOGGER_NAME).error(f"Error in loading slot info: {e}")
        broken = SlotInfo()
        broken.voice_changer_type = "BROKEN"
        broken.slot_index = slot_index
        return broken


def reload_slot_infos(model_dir=None) -> list[SlotInfoMember]:
    if model_dir is None:
        target_dir = ModelDir
    else:
        target_dir = Path(model_dir)

    # 実際に存在する数字名ディレクトリを特定
    existing_indices = set()
    if target_dir.exists():
        for entry in target_dir.iterdir():
            if entry.is_dir() and entry.name.isdigit():
                existing_indices.add(int(entry.name))

    max_idx = max(existing_indices) if existing_indices else -1
    # 常に「現在の最大スロット番号 + 1（次の空き枠）」までを生成。
    # スロットが1つもない場合でも、スロット0を空き枠として生成する（要素数1）。
    slot_count = max_idx + 2 if max_idx >= 0 else 1

    slot_infos = []
    for i in range(slot_count):
        slot_info = load_slot_info(target_dir, i)
        slot_infos.append(slot_info)

    return slot_infos


def safe_rmtree(target_dir: Path | str, retries: int = 3, delay: float = 0.1) -> None:
    """Windows の ReadOnly 属性や一時的なファイルロックに対応した安全なディレクトリ削除関数。"""
    p = Path(target_dir)
    if not p.exists():
        return

    def _remove_readonly(func, exc_path, _exc_info):
        os.chmod(exc_path, stat.S_IWRITE)
        func(exc_path)

    for attempt in range(retries):
        try:
            shutil.rmtree(p, onexc=_remove_readonly)
            return
        except PermissionError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                raise


class SlotManager:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.reload()

    def reload(self, use_log=None):
        logging.getLogger(LOGGER_NAME).debug("Reloading Slot info")
        self.slot_infos = reload_slot_infos(ModelDir)
        return self.slot_infos

    def get_slot_infos(self):
        return self.slot_infos

    def get_slot_info(self, index: int | None = None) -> SlotInfoMember:
        if index is None:
            raise VCClientError(ERROR_CODE_SLOT_INDEX_NOT_FOUND, "Slot index is None")
        slot_info_array = [slot_info for slot_info in self.slot_infos if slot_info.slot_index == index]
        if len(slot_info_array) == 0:
            if index >= 0:
                return load_slot_info(ModelDir, index)
            raise VCClientError(ERROR_CODE_SLOT_INDEX_NOT_FOUND, f"Slot index {index} is not found")
        return slot_info_array[0]

    def get_blank_slot_index(self) -> int:
        self.reload(use_log=False)
        exist_slot_index = {
            slot_info.slot_index for slot_info in self.slot_infos if slot_info.voice_changer_type is not None
        }
        i = 0
        while i in exist_slot_index:
            i += 1
        return i

    def set_new_slot(self, model_import_param: ModelImportParamMember, remove_src: bool = False):
        if model_import_param.slot_index is None:
            model_import_param.slot_index = self.get_blank_slot_index()
        assert self.get_slot_info(model_import_param.slot_index).voice_changer_type is None, (
            f"slot_index:{model_import_param.slot_index} is already exists."
        )
        logging.getLogger(LOGGER_NAME).info(f"set new slot: {model_import_param}")
        import_model(ModelDir, model_import_param, remove_src)
        self.reload()

    def reserve_slot_for_sample(self, slot_index: int, progress: float = 0):
        """
        サンプル用にスロットを確保する。
        サンプルのインポートは次の流れを想定している。
        (1)リザーブ -> (2)ダウンロード -> (3)解放 -> (4)インポートの流れで処理を行う
        厳密には(3)から(4)にかけてをアトミックにする必要があるが、厳密にはやらない。
        隙間に入り込まれたら処理が壊れるが、その場合はスロットをデリートすることで対応してもらう。

        ※別の観点で、同じファイル名のサンプルが同時にダウンロードされると、uploadフォルダ内で上書きされてしまうが、それもまずは見てみなふりをする。
        """
        assert self.get_slot_info(slot_index).voice_changer_type is None, f"slot_index:{slot_index} is already exists."
        import_param = ReservedForSampleModelImportParam(
            voice_changer_type="RESERVED_FOR_SAMPLE",
            name="RESERVED_FOR_SAMPLE",
            slot_index=slot_index,
            progress=progress,
        )
        import_model(ModelDir, import_param)
        self.reload()

    def update_slot_for_sample(self, slot_index: int, progress: float):
        slot_info = self.get_slot_info(slot_index)
        assert slot_info.voice_changer_type == "RESERVED_FOR_SAMPLE", (
            f"slot_index:{slot_index} is not reserved for sample."
        )
        slot_info.progress = progress

    def release_slot_from_reseved_for_sample(self, slot_index: int):
        """
        サンプル用に確保していたスロットを解放する。
        reserve_new_slot_as_sampleを参照。
        """
        self.delete_slot(slot_index)

    def delete_slot(self, slot_index: int):
        slot_dir = ModelDir / str(slot_index)
        if os.path.exists(slot_dir):
            safe_rmtree(slot_dir)
        self.reload(use_log=False)

    def save_slot_info(self, slot_info: SlotInfoMember):
        slot_dir = ModelDir / f"{slot_info.slot_index}"
        slot_dir.mkdir(parents=True, exist_ok=True)
        config_file = slot_dir / SLOT_PARAM_FILE
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(slot_info.model_dump_json(indent=4))
        self.reload(use_log=False)

    def update_slot_info(self, slot_info: SlotInfoMember):
        org_slot_info = self.get_slot_info(slot_info.slot_index)
        logging.getLogger(LOGGER_NAME).debug(f"updating slot info: org => {org_slot_info}")
        assert org_slot_info.voice_changer_type is not None, f"src:{slot_info.slot_index} is not exist."
        logging.getLogger(LOGGER_NAME).debug(f"updating slot info: new => {slot_info}")
        self.save_slot_info(slot_info)

    def export_onnx(self, params: OnnxExportParam, store_dir: Path):
        slot_info = self.get_slot_info(params.slot_index)
        if slot_info.voice_changer_type != "RVC":
            raise VCClientError(
                ERROR_CODE_IMPORT_MODEL_FAILED,
                detail=f"Slot {params.slot_index} is not an RVC model ({slot_info.voice_changer_type}).",
            )
        slot_dir = ModelDir / str(params.slot_index)
        assert isinstance(slot_info, RVCSlotInfo)
        assert slot_info.model_file is not None, f"Slot {params.slot_index} has no model file."
        model_path = slot_dir / slot_info.model_file.name

        if model_path.suffix == ".onnx":
            logging.getLogger(LOGGER_NAME).info(f"Slot {params.slot_index} model is already ONNX: {model_path}")
            return

        onnx_file = slot_dir / f"{model_path.stem}.onnx"
        logging.getLogger(LOGGER_NAME).info(
            f"Exporting PyTorch model to ONNX for slot {params.slot_index}: {model_path} -> {onnx_file}"
        )
        export_pth_to_onnx(model_path, onnx_file)
        model_path.unlink()

        new_slot_info = estimate_rvc_model(onnx_file)
        assert isinstance(new_slot_info, RVCSlotInfo)
        new_slot_info.slot_index = slot_info.slot_index
        new_slot_info.name = slot_info.name
        new_slot_info.description = slot_info.description
        new_slot_info.credit = slot_info.credit
        new_slot_info.terms_of_use_url = slot_info.terms_of_use_url
        new_slot_info.icon_file = slot_info.icon_file
        new_slot_info.index_file = slot_info.index_file
        new_slot_info.speakers = slot_info.speakers
        new_slot_info.chunk_sec = slot_info.chunk_sec
        new_slot_info.pitch_shift = slot_info.pitch_shift
        new_slot_info.index_ratio = slot_info.index_ratio
        new_slot_info.protect_ratio = slot_info.protect_ratio

        self.update_slot_info(new_slot_info)
        self.reload(use_log=False)

    def find_legacy_pth_slots(self) -> list[tuple[int, Path]]:
        """スロットディレクトリを走査し、.pth が存在して .onnx が未生成のスロット一覧を返す。

        Returns:
            [(slot_index, pth_file_path), ...]
        """
        legacy_slots = []
        if not ModelDir.exists():
            return legacy_slots

        # 実際に存在する数字名のスロットディレクトリのみを昇順で走査
        slot_dirs: list[tuple[int, Path]] = []
        for entry in ModelDir.iterdir():
            if entry.is_dir() and entry.name.isdigit():
                slot_dirs.append((int(entry.name), entry))

        slot_dirs.sort(key=lambda x: x[0])

        for slot_index, slot_dir in slot_dirs:
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

    def convert_legacy_slot_to_onnx(self, slot_index: int, pth_path: Path):
        """指定スロットの .pth モデルを .onnx に変換し、スロット情報を更新する。"""
        slot_dir = ModelDir / str(slot_index)
        onnx_file = slot_dir / f"{pth_path.stem}.onnx"
        logging.getLogger(LOGGER_NAME).info(
            f"Converting legacy PyTorch model to ONNX for slot {slot_index}: {pth_path} -> {onnx_file}"
        )
        export_pth_to_onnx(pth_path, onnx_file)

        existing_info = self.get_slot_info(slot_index)
        new_slot_info = estimate_rvc_model(onnx_file)
        assert isinstance(new_slot_info, RVCSlotInfo)
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

    def move_model_slot(self, param: MoveModelParam):
        assert param.dst >= 0, f"dst:{param.dst} must be >= 0"
        assert self.get_slot_info(param.dst).voice_changer_type is None, f"dst:{param.dst} is already exists."
        assert self.get_slot_info(param.src).voice_changer_type is not None, f"src:{param.src} is not exist."
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
        self.reload(use_log=False)

    def move_model_slot_from_onnx_exported(self, param: MoveExportedOnnxModelParam):
        raise VCClientError(
            ERROR_CODE_IMPORT_MODEL_FAILED,
            "Moving exported ONNX model is not supported in VCClient Forge.",
        )

    def set_icon_file(self, param: SetIconParam):
        icon_dst_path = ModelDir / f"{param.slot_index}" / param.icon_file.name
        shutil.move(param.icon_file, icon_dst_path)
        slot_info = self.get_slot_info(param.slot_index)
        assert slot_info is not None, f"slot_index:{param.slot_index} is not exists."
        slot_info.icon_file = Path(icon_dst_path.name)
        self.update_slot_info(slot_info)
