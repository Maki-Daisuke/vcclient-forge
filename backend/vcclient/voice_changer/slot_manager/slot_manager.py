import io
import logging
import os
import shutil
import zipfile
from pathlib import Path

import toml

from ...const import LOGGER_NAME
from ...exception import (
    ERROR_CODE_IMPORT_MODEL_FAILED,
    ERROR_CODE_NO_BLANK_SLOT,
    ERROR_CODE_SLOT_INDEX_NOT_FOUND,
    VCClientError,
)
from ..data_types.slot_manager_data_types import (
    BeatriceV2ModelInfo,
    BeatriceV2SlotInfo,
    ExportParam,
    ModelImportParamMember,
    MoveExportedOnnxModelParam,
    MoveModelParam,
    OnnxExportParam,
    ReservedForSampleModelImportParam,
    ReservedForSampleSlotInfo,
    RVCSlotInfo,
    SetBeatriceV2VoiceDescriptionParam,
    SetBeatriceV2VoiceIconFileParam,
    SetBeatriceV2VoiceNameParam,
    SetIconParam,
    SlotInfo,
    SlotInfoMember,
)
from ..voice_chanager_const import (
    BEATRICE_V2_ALPHA_SLOT_INDEX,
    BEATRICE_V2_BETA_SLOT_INDEX,
    MAX_SLOT_INDEX,
    MERGED_SLOT_INDEX,
    ONNX_EXPORTED_SLOT_INDEX,
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
        elif tmp.voice_changer_type == "Beatrice_v2":
            slot_info = BeatriceV2SlotInfo.model_validate_json(content)
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


def reload_slot_infos(model_dir=None):

    slot_infos = []

    for i in range(MAX_SLOT_INDEX):
        slot_info = load_slot_info(model_dir, i)

        slot_infos.append(slot_info)

    merged_model_slot = load_slot_info(model_dir, MERGED_SLOT_INDEX)

    slot_infos.append(merged_model_slot)

    exported_onnx_model_slot = load_slot_info(model_dir, ONNX_EXPORTED_SLOT_INDEX)

    slot_infos.append(exported_onnx_model_slot)

    beatrice_v2_alpha_slot = load_slot_info(model_dir, BEATRICE_V2_ALPHA_SLOT_INDEX)
    slot_infos.append(beatrice_v2_alpha_slot)
    beatrice_v2_beta_slot = load_slot_info(model_dir, BEATRICE_V2_BETA_SLOT_INDEX)
    slot_infos.append(beatrice_v2_beta_slot)

    return slot_infos


class SlotManager:
    _instance = None

    def get_instance(cls):

        if cls._instance is None:
            cls._instance = cls()

            return cls._instance

        return cls._instance

    get_instance = classmethod(get_instance)

    def __init__(self):

        self.reload()

    def reload(self=None, use_log=None):

        logging.getLogger(LOGGER_NAME).debug("Reloading Slot info")

        self.slot_infos = reload_slot_infos(ModelDir)

        return self.slot_infos

    def get_slot_infos(self=None):

        return self.slot_infos

    def get_slot_info(self=None, index=None):

        slot_info_array = [slot_info for slot_info in self.slot_infos if slot_info.slot_index == index]

        if len(slot_info_array) == 0:
            raise VCClientError(ERROR_CODE_SLOT_INDEX_NOT_FOUND, f"""Slot index {index} is not found""")

        return slot_info_array[0]

    def get_blank_slot_index(self) -> int:
        self.reload(use_log=False)
        exist_slot_index = {
            slot_info.slot_index for slot_info in self.slot_infos if slot_info.voice_changer_type is not None
        }
        next_index = next((i for i in range(MAX_SLOT_INDEX) if i not in exist_slot_index), -1)
        if next_index == -1:
            raise VCClientError(ERROR_CODE_NO_BLANK_SLOT)
        return next_index

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
            shutil.rmtree(slot_dir)
        self.reload(use_log=False)

    def update_slot_info(self, slot_info: SlotInfoMember):
        org_slot_info = self.get_slot_info(slot_info.slot_index)
        logging.getLogger(LOGGER_NAME).debug(f"updating slot info: org => {org_slot_info}")
        assert org_slot_info.voice_changer_type is not None, f"src:{slot_info.slot_index} is not exist."
        logging.getLogger(LOGGER_NAME).debug(f"updating slot info: new => {slot_info}")
        slot_dir = ModelDir / f"{slot_info.slot_index}"
        slot_dir.mkdir(parents=True, exist_ok=True)
        config_file = slot_dir / SLOT_PARAM_FILE
        with open(config_file, "w", encoding="utf-8") as f:
            f.write(slot_info.model_dump_json(indent=4))
        index_in_slot_info = [
            i for i, s in enumerate(self.get_slot_infos()) if s.slot_index == org_slot_info.slot_index
        ]
        assert len(index_in_slot_info) == 1
        self.slot_infos[index_in_slot_info[0]] = slot_info

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

    def export(self, params: ExportParam):
        logging.getLogger(LOGGER_NAME).info(f"export: {params}")
        voice_changer_type = self.get_slot_info(params.slot_index).voice_changer_type
        assert voice_changer_type == "Beatrice_v2", f"Export model failed. {voice_changer_type} is not supported."
        slot_path = ModelDir / str(params.slot_index)
        model_root_dir = slot_path / "model"
        assert os.path.exists(model_root_dir), f"model_dir:{model_root_dir} is not found."
        assert os.path.isdir(model_root_dir), f"model_dir:{model_root_dir} is not directory."
        model_dir = model_root_dir
        model_name = os.path.basename(model_dir)
        logging.getLogger(LOGGER_NAME).info(f"model_dir: {model_dir}, model_name: {model_name}")
        io_buffer = io.BytesIO()
        with zipfile.ZipFile(io_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for root, _, files in os.walk(model_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, model_dir)
                    zip_file.write(file_path, arcname)
        io_buffer.seek(0)
        return model_name, io_buffer

    def move_model_slot(self, param: MoveModelParam):
        assert param.dst <= MAX_SLOT_INDEX, f"dst:{param.dst} is over MAX_SLOT_INDEX:{MAX_SLOT_INDEX}"
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
        if param.dst is None:
            param.dst = self.get_blank_slot_index()
        move_modelparams = MoveModelParam(src=ONNX_EXPORTED_SLOT_INDEX, dst=param.dst)
        self.move_model_slot(move_modelparams)

    def set_icon_file(self, param: SetIconParam):
        icon_dst_path = ModelDir / f"{param.slot_index}" / param.icon_file.name
        shutil.move(param.icon_file, icon_dst_path)
        slot_info = self.get_slot_info(param.slot_index)
        assert slot_info is not None, f"slot_index:{param.slot_index} is not exists."
        slot_info.icon_file = Path(icon_dst_path.name)
        self.update_slot_info(slot_info)

    def _beatrice_update_toml_by_voice_param(self, slot_index: int, voice_index: int, key: str | list[str], val: str):
        slot_info = self.get_slot_info(slot_index)
        assert isinstance(slot_info, BeatriceV2SlotInfo), f"slot is not for BeatriceV2 model: {slot_info}"
        with open(slot_info.toml_file, "r", encoding="utf-8") as file:
            data = toml.load(file)
        target = data["voice"][f"{voice_index}"]
        if isinstance(key, list):
            for k in key[:-1]:
                target = target[k]
            target[key[-1]] = val
        else:
            target[key] = val
        with open(slot_info.toml_file, "w", encoding="utf-8") as file:
            toml.dump(data, file)
        model_info = BeatriceV2ModelInfo(**data)
        slot_info.model_info = model_info
        self.update_slot_info(slot_info)

    def beatrice_set_voice_icon_file(self, param: SetBeatriceV2VoiceIconFileParam):
        slot_info = self.get_slot_info(param.slot_index)
        assert isinstance(slot_info, BeatriceV2SlotInfo), f"slot is not for BeatriceV2 model: {slot_info}"
        icon_dst_path = slot_info.toml_file.parent / param.icon_file.name
        if icon_dst_path.parent.exists() is False:
            raise RuntimeError(f"slot index {icon_dst_path.parent} is not found")
        if param.icon_file.exists() is False:
            raise RuntimeError(f"icon file {param.icon_file} is not found")
        shutil.move(param.icon_file, icon_dst_path)
        self._beatrice_update_toml_by_voice_param(
            param.slot_index, param.voice_index, ["portrait", "path"], param.icon_file.name
        )

    def beatrice_set_voice_description(self, param: SetBeatriceV2VoiceDescriptionParam):
        self._beatrice_update_toml_by_voice_param(
            param.slot_index, param.voice_index, "description", param.voice_description
        )

    def beatrice_set_voice_name(self, param: SetBeatriceV2VoiceNameParam):
        self._beatrice_update_toml_by_voice_param(param.slot_index, param.voice_index, "name", param.voice_name)
