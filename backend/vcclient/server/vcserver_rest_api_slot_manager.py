from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from vcclient.logger import logger
from vcclient.server.server_const import UPLOAD_DIR
from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute
from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.data_types.slot_manager_data_types import (
    ModelImportParam,
    ModelImportParamMember,
    MoveModelParam,
    RVCModelImportParam,
    RVCSlotInfo,
    SetIconParam,
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
    delete_selected: bool = False


async def detect_model(request: Request) -> ModelImportParamMember:
    body = await request.body()
    import_param = ModelImportParam.model_validate_json(body)
    try:
        if import_param.voice_changer_type == "RVC":
            return RVCModelImportParam.model_validate_json(body)
        else:
            logger.error("unknown voice_changer_type: %s", import_param.voice_changer_type)
            raise HTTPException(status_code=400, detail="voice_changer_type must be 'RVC'")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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
        self.router.add_api_route("/api/slot-manager/slots", self.post_slot, methods=["POST"])
        self.router.add_api_route("/api/slot-manager/slots/{index}", self.put_slot_info, methods=["PUT"])
        self.router.add_api_route("/api/slot-manager/slots/{index}", self.delete_slot_info, methods=["DELETE"])
        self.router.add_api_route(
            "/api/slot-manager/slots/operation/move_model", self.post_move_model, methods=["POST"]
        )
        self.router.add_api_route(
            "/api/slot-manager/slots/operation/set_icon_file", self.post_set_icon_file, methods=["POST"]
        )

    def get_slots(self, reload: bool = False):
        slot_manager = SlotManager.get_instance()
        if reload:
            slot_manager.reload()
        slots = slot_manager.get_slot_infos()
        return slots

    def organize_models(self, param: OrganizeModelsParam):
        local = LocalVoiceChangerInterface.get_instance()
        with local.lifecycle_lock:
            if local.local_voice_changer_enabled or local.stream_running:
                raise HTTPException(status_code=409, detail="Audio must be stopped before organizing models")
            manager = SlotManager.get_instance()
            configuration = ConfigurationManager.get_instance().get_voice_changer_configuration()
            voice = VoiceChanger.get_instance()
            if voice.is_convert_chunk_bulk_started():
                raise HTTPException(status_code=409, detail="Audio conversion is still running")
            if voice.vc_pipeline is not None and not isinstance(voice.vc_pipeline, RVCPipeline):
                raise HTTPException(status_code=409, detail="Unsupported active model pipeline")
            slots = [slot for slot in manager.get_slot_infos() if slot.voice_changer_type is not None]
            if any(slot.voice_changer_type == "RESERVED_FOR_SAMPLE" for slot in slots):
                raise HTTPException(status_code=409, detail="A model import is in progress")
            originals = [slot.slot_index for slot in slots]
            selected = configuration.current_slot_index
            expected = set(originals)
            if param.delete_selected:
                if selected not in expected:
                    raise HTTPException(status_code=409, detail="No selected model to delete")
                expected.remove(selected)
            if len(param.order) != len(expected) or set(param.order) != expected:
                raise HTTPException(status_code=409, detail="Model list changed; reload before trying again")
            try:
                new_selected = ModelTransaction(ModelDir, ConfigFile).apply(originals, param.order, selected)
            except (ModelTransactionError, OSError, ValueError) as error:
                logger.error("Could not organize models: %s", error, exc_info=True)
                raise HTTPException(status_code=409, detail=str(error)) from error
            manager.reload()
            configuration.current_slot_index = new_selected
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

    def post_slot(self, import_param: ModelImportParamMember = Depends(detect_model)):
        if import_param.slot_index is not None:
            validate_slot_index(import_param.slot_index, "slot_index")
        try:
            slot_manager = SlotManager.get_instance()
            if import_param.voice_changer_type == "RVC":
                if not isinstance(import_param, RVCModelImportParam):
                    raise HTTPException(status_code=400, detail="Invalid RVC model import parameters.")
                import_param.model_file = UPLOAD_DIR / import_param.model_file
                if import_param.index_file is not None:
                    import_param.index_file = UPLOAD_DIR / import_param.index_file
            slot_manager.set_new_slot(import_param, remove_src=True)
        except Exception as e:
            logger.error("Failed to set_new_slot: %s", e, exc_info=True)
            raise HTTPException(status_code=400, detail=str(e))

    def post_set_icon_file(self, param: SetIconParam):
        validate_slot_index(param.slot_index, "slot_index")
        param.icon_file = UPLOAD_DIR / param.icon_file.name
        slot_manager = SlotManager.get_instance()
        slot_manager.set_icon_file(param)

    def put_slot_info(self, index: int, slot_info: SlotInfoMember = Depends(detect_slot_info)):
        validate_slot_index(index)
        slot_manager = SlotManager.get_instance()
        slot_manager.update_slot_info(slot_info)
        VoiceChanger.get_instance().check_and_update_pipeline()

    def delete_slot_info(self, index: int):
        validate_slot_index(index)
        slot_manager = SlotManager.get_instance()
        slot_manager.delete_slot(index)

    def post_move_model(self, param: MoveModelParam):
        validate_slot_index(param.src, "src")
        validate_slot_index(param.dst, "dst")
        slot_manager = SlotManager.get_instance()
        slot_manager.move_model_slot(param)
