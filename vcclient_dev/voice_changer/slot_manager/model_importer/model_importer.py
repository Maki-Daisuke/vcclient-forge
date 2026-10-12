import glob
import logging
import os
import shutil
import zipfile
from pathlib import Path
from typing import cast

import toml

from ....const import LOGGER_NAME
from ....exception import (
    ERROR_CODE_BEATRICE_MODEL_FILES_NOT_FOUND,
    ERROR_CODE_BEATRICE_TOML_NOT_FOUND,
    ERROR_CODE_FILENAME_TOO_LONG,
    ERROR_CODE_IMPORT_MODEL_FAILED,
    ERROR_CODE_UNKNOWN_VOICE_CHANGER_TYPE,
    VCClientError,
)
from ...data_types.slot_manager_data_types import (
    BeatriceV2ModelImportParam,
    BeatriceV2ModelInfo,
    BeatriceV2SlotInfo,
    ModelImportParamMember,
    ReservedForSampleModelImportParam,
    ReservedForSampleSlotInfo,
    RVCModelImportParam,
    RVCSlotInfo,
)
from ...voice_chanager_const import MAX_BEATRICE_MERGED_SPEAKER_WEIGHTS_SLOT, SLOT_PARAM_FILE, ModelDir
from .rvc_model_estimator.rvc_model_estimator import estimate_rvc_model


def import_model(model_dir: Path, model_importer_param: ModelImportParamMember, remove_src: bool = False):
    slot_dir = model_dir / f"{model_importer_param.slot_index}"
    slot_dir.mkdir(parents=True, exist_ok=True)
    try:
        if model_importer_param.voice_changer_type == "RESERVED_FOR_SAMPLE":
            assert isinstance(model_importer_param, ReservedForSampleModelImportParam)
            assert model_importer_param.slot_index is not None
            slot_info = ReservedForSampleSlotInfo(
                slot_index=model_importer_param.slot_index,
                progress=model_importer_param.progress,
            )
        elif model_importer_param.voice_changer_type == "RVC":
            assert isinstance(model_importer_param, RVCModelImportParam)
            for src in cast(
                list[Path | None],
                [model_importer_param.model_file, model_importer_param.index_file, model_importer_param.icon_file],
            ):
                if src is not None:
                    dst = slot_dir / src.name
                    if len(str(src)) > 80 or len(str(dst)) > 80:
                        raise VCClientError(
                            ERROR_CODE_FILENAME_TOO_LONG, detail=f"filename is too long: {src} -> {dst}"
                        )
                    logging.getLogger(LOGGER_NAME).debug(f"copy {src} to {dst}")
                    shutil.copy(src, dst)
                    if remove_src is True:
                        src.unlink()
            assert model_importer_param.slot_index is not None
            model_file = Path(ModelDir / str(model_importer_param.slot_index) / model_importer_param.model_file.name)
            slot_info = estimate_rvc_model(model_file)
            assert isinstance(slot_info, RVCSlotInfo)
            slot_info.slot_index = model_importer_param.slot_index
            slot_info.name = model_importer_param.name
            slot_info.index_file = (
                Path(model_importer_param.index_file.name) if model_importer_param.index_file is not None else None
            )
            slot_info.icon_file = (
                Path(model_importer_param.icon_file.name) if model_importer_param.icon_file is not None else None
            )
            slot_info.terms_of_use_url = model_importer_param.terms_of_use_url
            if model_importer_param.embedder is not None:
                slot_info.embedder = model_importer_param.embedder
        elif model_importer_param.voice_changer_type == "Beatrice_v2":
            assert isinstance(model_importer_param, BeatriceV2ModelImportParam)
            for src in cast(list[Path | None], [model_importer_param.zip_file, model_importer_param.icon_file]):
                if src is not None:
                    dst = slot_dir / src.name
                    if len(str(src)) > 80 or len(str(dst)) > 80:
                        raise VCClientError(
                            ERROR_CODE_FILENAME_TOO_LONG, detail=f"filename is too long: {src} -> {dst}"
                        )
                    logging.getLogger(LOGGER_NAME).debug(f"copy {src} to {dst}")
                    shutil.copy(src, dst)
                    if remove_src is True:
                        src.unlink()
            assert model_importer_param.zip_file is not None
            zip_file = slot_dir / model_importer_param.zip_file.name
            with zipfile.ZipFile(zip_file, "r") as zip_ref:
                extract_dir = slot_dir / "model"
                zip_ref.extractall(extract_dir)
            toml_files = glob.glob(os.path.join(extract_dir, "**", "*.toml"), recursive=True)
            if len(toml_files) != 1:
                raise VCClientError(
                    ERROR_CODE_BEATRICE_TOML_NOT_FOUND,
                    detail=f"toml file not found or multiple toml files found in {extract_dir}",
                )
            toml_file = toml_files[0]
            with open(toml_file, "r", encoding="utf-8") as f:
                toml_data = toml.load(f)
            model_info = BeatriceV2ModelInfo(**toml_data)
            formant_shift_embeddings_file = Path(Path(toml_file).parent / "formant_shift_embeddings.bin")
            if formant_shift_embeddings_file.exists() is False:
                raise VCClientError(
                    ERROR_CODE_BEATRICE_MODEL_FILES_NOT_FOUND,
                    detail=f"formant_shift_embeddings.bin not found at {formant_shift_embeddings_file}",
                )
            phone_extractor_file = Path(Path(toml_file).parent / "phone_extractor.bin")
            if phone_extractor_file.exists() is False:
                raise VCClientError(
                    ERROR_CODE_BEATRICE_MODEL_FILES_NOT_FOUND,
                    detail=f"phone_extractor.bin not found at {phone_extractor_file}",
                )
            pitch_estimator_file = Path(Path(toml_file).parent / "pitch_estimator.bin")
            if pitch_estimator_file.exists() is False:
                raise VCClientError(
                    ERROR_CODE_BEATRICE_MODEL_FILES_NOT_FOUND,
                    detail=f"pitch_estimator.bin not found at {pitch_estimator_file} ",
                )
            speaker_embeddings_file = Path(Path(toml_file).parent / "speaker_embeddings.bin")
            if speaker_embeddings_file.exists() is False:
                raise VCClientError(
                    ERROR_CODE_BEATRICE_MODEL_FILES_NOT_FOUND,
                    detail=f"speaker_embeddings.bin not found  at {speaker_embeddings_file}",
                )
            waveform_generator_file = Path(Path(toml_file).parent / "waveform_generator.bin")
            if waveform_generator_file.exists() is False:
                raise VCClientError(
                    ERROR_CODE_BEATRICE_MODEL_FILES_NOT_FOUND,
                    detail=f"waveform_generator.bin not found at {waveform_generator_file}",
                )
            assert model_importer_param.slot_index is not None
            slot_info = BeatriceV2SlotInfo(
                slot_index=model_importer_param.slot_index,
                name=model_importer_param.name,
                zip_file=Path(model_importer_param.zip_file.name)
                if model_importer_param.zip_file is not None
                else None,
                icon_file=Path(model_importer_param.icon_file.name)
                if model_importer_param.icon_file is not None
                else None,
                toml_file=Path(toml_file),
                model_info=model_info,
                formant_shift_embeddings_file=formant_shift_embeddings_file,
                phone_extractor_file=phone_extractor_file,
                pitch_estimator_file=pitch_estimator_file,
                speaker_embeddings_file=speaker_embeddings_file,
                waveform_generator_file=waveform_generator_file,
                pitch_shifts=[0] * len(toml_data["voice"]),
                formant_shifts=[0] * len(toml_data["voice"]),
                merged_speaker_weights_list=[
                    [0] * len(toml_data["voice"]) for _ in range(MAX_BEATRICE_MERGED_SPEAKER_WEIGHTS_SLOT)
                ],
            )
            slot_info.terms_of_use_url = model_importer_param.terms_of_use_url
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
