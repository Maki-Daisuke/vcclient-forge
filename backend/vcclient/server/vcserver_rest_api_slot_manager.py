from fastapi import APIRouter, Depends, HTTPException, Request

from vcclient.logger import logger
from vcclient.server.server_const import UPLOAD_DIR
from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute
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
from vcclient.voice_changer.slot_manager.slot_manager import SlotManager
from vcclient.voice_changer.voice_chanager_const import MAX_SLOT_INDEX


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

    def delete_slot_info(self, index: int):
        validate_slot_index(index)
        slot_manager = SlotManager.get_instance()
        slot_manager.delete_slot(index)

    def post_move_model(self, param: MoveModelParam):
        validate_slot_index(param.src, "src")
        validate_slot_index(param.dst, "dst")
        slot_manager = SlotManager.get_instance()
        slot_manager.move_model_slot(param)
