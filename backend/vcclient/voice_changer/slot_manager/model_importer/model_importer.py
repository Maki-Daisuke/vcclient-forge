import logging
import shutil
from pathlib import Path
from typing import cast

from ....const import LOGGER_NAME
from ....exception import (
    ERROR_CODE_FILENAME_TOO_LONG,
    ERROR_CODE_IMPORT_MODEL_FAILED,
    ERROR_CODE_UNKNOWN_VOICE_CHANGER_TYPE,
    VCClientError,
)
from ...data_types.slot_manager_data_types import (
    ModelImportParamMember,
    ReservedForSampleModelImportParam,
    ReservedForSampleSlotInfo,
    RVCModelImportParam,
    RVCSlotInfo,
)
from ...voice_chanager_const import SLOT_PARAM_FILE
from ..onnx_exporter import export_pth_to_onnx
from .rvc_model_estimator.rvc_model_estimator import estimate_rvc_model


def import_model(model_dir: Path, model_importer_param: ModelImportParamMember, remove_src: bool = False):
    if model_importer_param.slot_index is None:
        raise VCClientError(ERROR_CODE_IMPORT_MODEL_FAILED, "slot_index is required for model import.")
    if model_importer_param.voice_changer_type == "RESERVED_FOR_SAMPLE" and not isinstance(
        model_importer_param, ReservedForSampleModelImportParam
    ):
        raise VCClientError(ERROR_CODE_UNKNOWN_VOICE_CHANGER_TYPE, "Invalid reserved sample import parameters.")
    if model_importer_param.voice_changer_type == "RVC" and not isinstance(model_importer_param, RVCModelImportParam):
        raise VCClientError(ERROR_CODE_UNKNOWN_VOICE_CHANGER_TYPE, "Invalid RVC import parameters.")

    slot_dir = model_dir / f"{model_importer_param.slot_index}"
    slot_dir.mkdir(parents=True, exist_ok=True)
    try:
        if model_importer_param.voice_changer_type == "RESERVED_FOR_SAMPLE":
            if not isinstance(model_importer_param, ReservedForSampleModelImportParam):
                raise VCClientError(ERROR_CODE_UNKNOWN_VOICE_CHANGER_TYPE, "Invalid reserved sample import parameters.")
            slot_info = ReservedForSampleSlotInfo(
                slot_index=model_importer_param.slot_index,
                progress=model_importer_param.progress,
            )
        elif model_importer_param.voice_changer_type == "RVC":
            if not isinstance(model_importer_param, RVCModelImportParam):
                raise VCClientError(ERROR_CODE_UNKNOWN_VOICE_CHANGER_TYPE, "Invalid RVC import parameters.")
            for src in cast(
                list[Path | None],
                [model_importer_param.model_file, model_importer_param.index_file, model_importer_param.icon_file],
            ):
                if src is not None:
                    dst = slot_dir / src.name
                    if len(src.name) > 80 or len(dst.name) > 80:
                        raise VCClientError(
                            ERROR_CODE_FILENAME_TOO_LONG, detail=f"filename is too long: {src.name} -> {dst.name}"
                        )
                    logging.getLogger(LOGGER_NAME).debug(f"copy {src} to {dst}")
                    shutil.copy(src, dst)
                    if remove_src is True:
                        src.unlink()
            model_file = slot_dir / model_importer_param.model_file.name
            if model_file.suffix == ".pth":
                onnx_file = slot_dir / f"{model_file.stem}.onnx"
                logging.getLogger(LOGGER_NAME).info(
                    f"Auto-converting imported PyTorch model to ONNX: {model_file} -> {onnx_file}"
                )
                export_pth_to_onnx(model_file, onnx_file)
                model_file.unlink()
                model_file = onnx_file

            slot_info = estimate_rvc_model(model_file)
            if not isinstance(slot_info, RVCSlotInfo):
                raise VCClientError(
                    ERROR_CODE_IMPORT_MODEL_FAILED,
                    f"Estimated model is not a valid RVC model: {model_file}",
                )
            slot_info.slot_index = model_importer_param.slot_index
            slot_info.name = model_importer_param.name
            slot_info.model_file = Path(model_file.name)
            slot_info.index_file = (
                Path(model_importer_param.index_file.name) if model_importer_param.index_file is not None else None
            )
            slot_info.icon_file = (
                Path(model_importer_param.icon_file.name) if model_importer_param.icon_file is not None else None
            )
            slot_info.terms_of_use_url = model_importer_param.terms_of_use_url
            if model_importer_param.embedder is not None:
                slot_info.embedder = model_importer_param.embedder
        else:
            logging.getLogger(LOGGER_NAME).error(
                f"Unknown voice changer type: {model_importer_param.voice_changer_type}"
            )
            raise VCClientError(
                ERROR_CODE_UNKNOWN_VOICE_CHANGER_TYPE,
                detail=f"Unknown voice changer type: {model_importer_param.voice_changer_type}",
            )
    except VCClientError as e:
        shutil.rmtree(slot_dir)
        raise e
    except Exception as e:
        logging.getLogger(LOGGER_NAME).error(f"Failed to import model: {e}")
        shutil.rmtree(slot_dir)
        raise VCClientError(ERROR_CODE_IMPORT_MODEL_FAILED, detail=f"Failed to import model: {e}")

    config_file = slot_dir / SLOT_PARAM_FILE
    with open(config_file, "w", encoding="utf-8") as f:
        f.write(slot_info.model_dump_json(indent=4))
