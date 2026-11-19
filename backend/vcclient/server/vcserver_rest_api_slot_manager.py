import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from vcclient.exception import VCClientError
from vcclient.logger import logger
from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute
from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.data_types.slot_manager_data_types import (
    RVCModelImportParam,
    RVCSlotInfo,
    SlotInfo,
    SlotInfoMember,
)
from vcclient.voice_changer.slot_manager.reorder_transaction import ModelTransaction, ModelTransactionError
from vcclient.voice_changer.slot_manager.slot_manager import SlotManager
from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
from vcclient.voice_changer.voice_change_manager.vc_pipelines.rvc_pipeline import RVCPipeline
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger
from vcclient.voice_changer.voice_changer_const import MAX_SLOT_INDEX, ConfigFile, ModelDir


class OrganizeModelsParam(BaseModel):
    order: list[int]


_MODEL_SUFFIXES = {".pth", ".onnx"}
_INDEX_SUFFIXES = {".index"}
_ICON_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".bmp"}
_UPLOAD_COPY_CHUNK_BYTES = 1024 * 1024


def _save_upload(
    upload: UploadFile,
    tmp_dir: Path,
    *,
    prefix: str,
    allowed_suffixes: set[str],
    field_name: str,
    require_image_mime: bool = False,
) -> Path:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in allowed_suffixes:
        raise HTTPException(status_code=400, detail=f"Unsupported file type for {field_name}: {suffix or '(none)'}")
    if require_image_mime and upload.content_type:
        content_type = upload.content_type.lower()
        if not content_type.startswith("image/") and content_type != "application/octet-stream":
            raise HTTPException(status_code=400, detail=f"Invalid content type for {field_name}: {upload.content_type}")

    dst = tmp_dir / f"{prefix}_{uuid4().hex[:12]}{suffix}"
    size = 0
    try:
        with dst.open("wb") as out:
            while chunk := upload.file.read(_UPLOAD_COPY_CHUNK_BYTES):
                size += len(chunk)
                out.write(chunk)
    finally:
        upload.file.close()

    if size == 0:
        dst.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Uploaded {field_name} is empty.")
    return dst


async def detect_slot_info(request: Request) -> SlotInfoMember:
    body = await request.body()
    slot_info = SlotInfo.model_validate_json(body)
    if slot_info.voice_changer_type == "RVC":
        return RVCSlotInfo.model_validate_json(body)
    raise RuntimeError(f"body has slot_info with unknown voice_changer_type:{slot_info.voice_changer_type}")


def validate_slot_index(index: int, param_name: str = "index") -> None:
    if index < 0 or index >= MAX_SLOT_INDEX:
        raise HTTPException(
            status_code=400,
            detail=f"{param_name} {index} is out of range (must be 0 <= index < {MAX_SLOT_INDEX})",
        )


class RestAPISlotManager:
    def __init__(self):
        self.router = APIRouter()
        self.router.route_class = ValidationErrorLoggingRoute
        self.router.add_api_route("/api/slot-manager/operation/organize", self.organize_models, methods=["POST"])
        self.router.add_api_route("/api/slot-manager/slots", self.get_slots, methods=["GET"])
        self.router.add_api_route("/api/slot-manager/slots/{index}", self.get_slot, methods=["GET"])
        self.router.add_api_route("/api/slot-manager/slots/{index}", self.delete_slot, methods=["DELETE"])
        self.router.add_api_route("/api/slot-manager/slots", self.post_slot, methods=["POST"])
        self.router.add_api_route("/api/slot-manager/slots/{index}", self.put_slot_info, methods=["PUT"])
        self.router.add_api_route("/api/slot-manager/slots/{index}", self.patch_slot_info, methods=["PATCH"])

    def get_slots(self, reload: bool = False):
        slot_manager = SlotManager.get_instance()
        if reload:
            slot_manager.reload()
        slots = slot_manager.get_slot_infos()
        return slots

    def organize_models(self, param: OrganizeModelsParam):
        return self._organize_models(param.order)

    def delete_slot(self, index: int):
        validate_slot_index(index)
        return self._organize_models(None, delete_index=index)

    def _organize_models(self, order: list[int] | None, *, delete_index: int | None = None):
        local = LocalVoiceChangerInterface.get_instance()
        with local.lifecycle_lock:
            self._assert_local_audio_stopped_locked(local, "Audio must be stopped before organizing models")
            manager = SlotManager.get_instance()
            configuration = ConfigurationManager.get_instance().get_voice_changer_configuration()
            voice = VoiceChanger.peek_instance()
            self._assert_bulk_stopped(voice)
            if voice is not None and voice.vc_pipeline is not None and not isinstance(voice.vc_pipeline, RVCPipeline):
                raise HTTPException(status_code=409, detail="Unsupported active model pipeline")
            slots = [slot for slot in manager.get_slot_infos() if slot.voice_changer_type is not None]
            if any(slot.voice_changer_type == "RESERVED_FOR_SAMPLE" for slot in slots):
                raise HTTPException(status_code=409, detail="A model import is in progress")
            originals = [slot.slot_index for slot in slots]
            selected = configuration.current_slot_index
            expected = set(originals)
            if delete_index is not None:
                if delete_index not in expected:
                    raise HTTPException(status_code=404, detail="Model does not exist")
                expected.remove(delete_index)
            if order is None:
                order = [index for index in originals if index in expected]
            if len(order) != len(expected) or set(order) != expected:
                raise HTTPException(status_code=409, detail="Model list changed; reload before trying again")
            try:
                new_selected = ModelTransaction(ModelDir, ConfigFile).apply(originals, order, selected)
            except (ModelTransactionError, OSError, ValueError) as error:
                logger.error("Could not organize models: %s", error, exc_info=True)
                raise HTTPException(status_code=409, detail=str(error)) from error
            manager.reload()
            configuration.current_slot_index = new_selected
            if voice is not None:
                if new_selected == -1:
                    voice.vc_pipeline = None
                    voice.vc_info.voice_changer_type = None
                    voice.vc_info.pitch_estimator_type = None
                    voice.vc_info.pipeline_info = None
                elif isinstance(voice.vc_pipeline, RVCPipeline):
                    voice.vc_pipeline.slot_index = new_selected
                voice.vc_info.slot_index = new_selected
            return {"current_slot_index": new_selected}

    def get_slot(self, index: int, reload: bool = False):
        validate_slot_index(index)
        slot_manager = SlotManager.get_instance()
        if reload:
            slot_manager.reload()
        slot = slot_manager.get_slot_info(index)
        return slot

    @staticmethod
    def _assert_local_audio_stopped_locked(local: LocalVoiceChangerInterface, detail: str) -> None:
        if local.local_voice_changer_enabled or local.stream_running:
            raise HTTPException(status_code=409, detail=detail)

    @staticmethod
    def _assert_bulk_stopped(voice: VoiceChanger | None) -> None:
        if voice is not None and voice.is_convert_chunk_bulk_started():
            raise HTTPException(status_code=409, detail="Audio conversion is still running")

    def _ensure_audio_stopped(self, detail: str) -> None:
        local = LocalVoiceChangerInterface.get_instance()
        with local.lifecycle_lock:
            self._assert_local_audio_stopped_locked(local, detail)
            self._assert_bulk_stopped(VoiceChanger.peek_instance())

    def post_slot(
        self,
        model_file: UploadFile = File(...),
        name: str = Form(...),
        voice_changer_type: str = Form("RVC"),
        index_file: UploadFile | None = File(None),
        icon_file: UploadFile | None = File(None),
        slot_index: int | None = Form(None),
        terms_of_use_url: str = Form(""),
        embedder: str | None = Form(None),
    ) -> SlotInfoMember:
        if voice_changer_type != "RVC":
            raise HTTPException(status_code=400, detail="voice_changer_type must be 'RVC'")
        normalized_name = name.strip()
        if not normalized_name:
            raise HTTPException(status_code=400, detail="Model name must not be empty.")
        if slot_index is not None:
            validate_slot_index(slot_index, "slot_index")
        self._ensure_audio_stopped("Audio must be stopped before uploading models")

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_dir = Path(tmpdir)
                model_path = _save_upload(
                    model_file, tmp_dir, prefix="model", allowed_suffixes=_MODEL_SUFFIXES, field_name="model_file"
                )
                index_path = (
                    _save_upload(
                        index_file, tmp_dir, prefix="index", allowed_suffixes=_INDEX_SUFFIXES, field_name="index_file"
                    )
                    if index_file is not None
                    else None
                )
                icon_path = (
                    _save_upload(
                        icon_file,
                        tmp_dir,
                        prefix="icon",
                        allowed_suffixes=_ICON_SUFFIXES,
                        field_name="icon_file",
                        require_image_mime=True,
                    )
                    if icon_file is not None
                    else None
                )

                import_kwargs: dict[str, object] = {
                    "voice_changer_type": "RVC",
                    "name": normalized_name,
                    "terms_of_use_url": terms_of_use_url,
                    "slot_index": slot_index,
                    "model_file": model_path,
                    "index_file": index_path,
                    "icon_file": icon_path,
                }
                if embedder is not None:
                    import_kwargs["embedder"] = embedder
                import_param = RVCModelImportParam.model_validate(import_kwargs)
                return SlotManager.get_instance().set_new_slot(import_param, remove_src=True)
        except HTTPException:
            raise
        except VCClientError:
            raise
        except Exception as e:
            logger.error("Failed to set_new_slot: %s", e, exc_info=True)
            raise HTTPException(status_code=400, detail=str(e))

    def patch_slot_info(
        self,
        index: int,
        name: str | None = Form(None),
        icon_file: UploadFile | None = File(None),
    ) -> SlotInfoMember:
        validate_slot_index(index, "slot_index")
        if name is None and icon_file is None:
            raise HTTPException(status_code=400, detail="At least one of name or icon_file must be provided.")
        if name is not None and not name.strip():
            raise HTTPException(status_code=400, detail="Model name must not be empty.")
        self._ensure_audio_stopped("Audio must be stopped before updating model info")

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_dir = Path(tmpdir)
                icon_path = (
                    _save_upload(
                        icon_file,
                        tmp_dir,
                        prefix="icon",
                        allowed_suffixes=_ICON_SUFFIXES,
                        field_name="icon_file",
                        require_image_mime=True,
                    )
                    if icon_file is not None
                    else None
                )
                return SlotManager.get_instance().update_slot_metadata(
                    index,
                    name=name,
                    icon_file=icon_path,
                )
        except HTTPException:
            raise
        except VCClientError:
            raise
        except Exception as e:
            logger.error("Failed to update_slot_metadata: %s", e, exc_info=True)
            raise HTTPException(status_code=400, detail=str(e))

    def put_slot_info(self, index: int, slot_info: SlotInfoMember = Depends(detect_slot_info)):
        validate_slot_index(index)
        slot_manager = SlotManager.get_instance()
        slot_manager.update_slot_info(slot_info)
        VoiceChanger.get_instance().check_and_update_pipeline()
