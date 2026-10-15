import json
import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from vcclient.const import LOGGER_NAME
from vcclient.server.server_const import UPLOAD_DIR
from vcclient.server.validation_error_logging_route import ValidationErrorLoggingRoute
from vcclient.voice_changer.data_types.slot_manager_data_types import (
    BeatriceV2ModelImportParam,
    BeatriceV2SlotInfo,
    ExportParam,
    MergeParam,
    ModelImportParam,
    ModelImportParamMember,
    MoveExportedOnnxModelParam,
    MoveMergedModelParam,
    MoveModelParam,
    OnnxExportParam,
    RVCModelImportParam,
    RVCSlotInfo,
    SetBeatriceV2VoiceDescriptionParam,
    SetBeatriceV2VoiceIconFileParam,
    SetBeatriceV2VoiceNameParam,
    SetIconParam,
    SlotInfo,
    SlotInfoMember,
)
from vcclient.voice_changer.slot_manager.slot_manager import SlotManager


async def detect_model(request: Request) -> ModelImportParamMember:
    body = await request.body()
    import_param = ModelImportParam.model_validate_json(body)
    try:
        if import_param.voice_changer_type == "Beatrice_v2":
            return BeatriceV2ModelImportParam.model_validate_json(body)
        elif import_param.voice_changer_type == "RVC":
            return RVCModelImportParam.model_validate_json(body)
        else:
            logging.getLogger(LOGGER_NAME).error(f"unknown voice_changer_type:{import_param.voice_changer_type}")
            raise HTTPException(status_code=400, detail="voice_changer_type must be either 'Beatrice_v2' or 'RVC'")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


async def detect_slot_info(request: Request) -> SlotInfoMember:
    body = await request.body()
    slot_info = SlotInfo.model_validate_json(body)
    if slot_info.voice_changer_type == "RVC":
        return RVCSlotInfo.model_validate_json(body)
    if slot_info.voice_changer_type == "Beatrice_v2":
        return BeatriceV2SlotInfo.model_validate_json(body)
    raise RuntimeError(f"body has slot_info with unknown voice_changer_type:{slot_info.voice_changer_type}")


class RestAPISlotManager:
    def __init__(self):
        self.router = APIRouter()
        self.router.route_class = ValidationErrorLoggingRoute
        self.router.add_api_route("/api/slot-manager/slots", self.get_slots, methods=["GET"])
        self.router.add_api_route("/api/slot-manager/slots/{index}", self.get_slot, methods=["GET"])
        self.router.add_api_route("/api/slot-manager/slots", self.post_slot, methods=["POST"])
        self.router.add_api_route("/api/slot-manager/slots/dummy/rvc", self.post_slot_dummy_rvc, methods=["POST"])
        self.router.add_api_route(
            "/api/slot-manager/slots/dummy/beatricev2", self.post_slot_dummy_beatricev2, methods=["POST"]
        )
        self.router.add_api_route("/api/slot-manager/slots/{index}", self.put_slot_info, methods=["PUT"])
        self.router.add_api_route("/api/slot-manager/slots/{index}", self.delete_slot_info, methods=["DELETE"])
        self.router.add_api_route(
            "/api/slot-manager/slots/operation/merge_models", self.post_merge_models, methods=["POST"]
        )
        self.router.add_api_route(
            "/api/slot-manager/slots/operation/export_onnx", self.post_export_onnx, methods=["POST"]
        )
        self.router.add_api_route(
            "/api/slot-manager/slots/operation/move_model", self.post_move_model, methods=["POST"]
        )
        self.router.add_api_route(
            "/api/slot-manager/slots/operation/move_merged_model", self.post_move_merged_model, methods=["POST"]
        )
        self.router.add_api_route(
            "/api/slot-manager/slots/operation/move_exported_onnx_model",
            self.post_move_export_onnx_model,
            methods=["POST"],
        )
        self.router.add_api_route(
            "/api/slot-manager/slots/operation/set_icon_file", self.post_set_icon_file, methods=["POST"]
        )
        self.router.add_api_route(
            "/api/slot-manager/slots/operation/beatricev2/set_voice_icon_file",
            self.post_beatricev2_set_voice_icon_file,
            methods=["POST"],
        )
        self.router.add_api_route(
            "/api/slot-manager/slots/operation/beatricev2/set_voice_name",
            self.post_beatricev2_set_voice_name,
            methods=["POST"],
        )
        self.router.add_api_route(
            "/api/slot-manager/slots/operation/beatricev2/set_voice_description",
            self.post_beatricev2_set_voice_description,
            methods=["POST"],
        )
        self.router.add_api_route("/api/slot-manager/slots/operation/export", self.post_export, methods=["POST"])

        self.router.add_api_route("/api_slot-manager_slots", self.get_slots, methods=["GET"])
        self.router.add_api_route("/api_slot-manager_slots_{index}", self.get_slot, methods=["GET"])
        self.router.add_api_route("/api_slot-manager_slots", self.post_slot, methods=["POST"])
        self.router.add_api_route("/api_slot-manager_slots_dummy_rvc", self.post_slot_dummy_rvc, methods=["POST"])
        self.router.add_api_route(
            "/api_slot-manager_slots_dummy_beatricev2", self.post_slot_dummy_beatricev2, methods=["POST"]
        )
        self.router.add_api_route("/api_slot-manager_slots_{index}", self.put_slot_info, methods=["PUT"])
        self.router.add_api_route("/api_slot-manager_slots_{index}", self.delete_slot_info, methods=["DELETE"])
        self.router.add_api_route(
            "/api_slot-manager_slots_operation_merge_models", self.post_merge_models, methods=["POST"]
        )
        self.router.add_api_route(
            "/api_slot-manager_slots_operation_export_onnx", self.post_export_onnx, methods=["POST"]
        )
        self.router.add_api_route(
            "/api_slot-manager_slots_operation_move_model", self.post_move_model, methods=["POST"]
        )
        self.router.add_api_route(
            "/api_slot-manager_slots_operation_move_merged_model", self.post_move_merged_model, methods=["POST"]
        )
        self.router.add_api_route(
            "/api_slot-manager_slots_operation_move_exported_onnx_model",
            self.post_move_export_onnx_model,
            methods=["POST"],
        )
        self.router.add_api_route(
            "/api_slot-manager_slots_operation_set_icon_file", self.post_set_icon_file, methods=["POST"]
        )
        self.router.add_api_route(
            "/api_slot-manager_slots_operation_beatricev2_set_voice_icon_file",
            self.post_beatricev2_set_voice_icon_file,
            methods=["POST"],
        )
        self.router.add_api_route(
            "/api_slot-manager_slots_operation_beatricev2_set_voice_name",
            self.post_beatricev2_set_voice_name,
            methods=["POST"],
        )
        self.router.add_api_route(
            "/api_slot-manager_slots_operation_beatricev2_set_voice_description",
            self.post_beatricev2_set_voice_description,
            methods=["POST"],
        )
        self.router.add_api_route("/api_slot-manager_slots_operation_export", self.post_export, methods=["POST"])

    def get_slots(self, reload: bool = False):
        slot_manager = SlotManager.get_instance()
        if reload:
            slot_manager.reload()
        slots = slot_manager.get_slot_infos()
        return slots

    def get_slot(self, index: int, reload: bool = False):
        slot_manager = SlotManager.get_instance()
        if reload:
            slot_manager.reload()
        slot = slot_manager.get_slot_info(index)
        return slot

    def post_slot(self, import_param: ModelImportParamMember = Depends(detect_model)):
        try:
            slot_manager = SlotManager.get_instance()
            if import_param.voice_changer_type == "Beatrice_v2":
                assert isinstance(import_param, BeatriceV2ModelImportParam)
                if import_param.zip_file is not None:
                    import_param.zip_file = UPLOAD_DIR / import_param.zip_file
            elif import_param.voice_changer_type == "RVC":
                assert isinstance(import_param, RVCModelImportParam)
                import_param.model_file = UPLOAD_DIR / import_param.model_file
                if import_param.index_file is not None:
                    import_param.index_file = UPLOAD_DIR / import_param.index_file
            slot_manager.set_new_slot(import_param, remove_src=True)
        except Exception as e:
            logging.getLogger(LOGGER_NAME).error(f"Failed to set_new_slot: {e}")
            logging.getLogger(LOGGER_NAME).error(f"Failed to set_new_slot: {traceback.format_exc()}")
            raise HTTPException(status_code=400, detail=str(e))

    def post_slot_dummy_rvc(self, import_param: RVCModelImportParam):
        raise NotImplementedError("this method is dummy for doc. please use /api/slot-manager/slots")

    def post_slot_dummy_beatricev2(self, import_param: BeatriceV2ModelImportParam):
        raise NotImplementedError("this method is dummy for doc. please use /api/slot-manager/slots")

    def post_set_icon_file(self, param: SetIconParam):
        param.icon_file = UPLOAD_DIR / param.icon_file.name
        slot_manager = SlotManager.get_instance()
        slot_manager.set_icon_file(param)

    def put_slot_info(self, index: int, slot_info: SlotInfoMember = Depends(detect_slot_info)):
        slot_manager = SlotManager.get_instance()
        slot_manager.update_slot_info(slot_info)

    def delete_slot_info(self, index: int):
        slot_manager = SlotManager.get_instance()
        slot_manager.delete_slot(index)

    def post_merge_models(self, merge_param: MergeParam):
        raise HTTPException(
            status_code=400,
            detail=json.dumps({"code": "NOT_SUPPORTED", "message": "Model merge is not supported in VCClient Forge."}),
        )

    def post_export_onnx(self, params: OnnxExportParam):
        slot_manager = SlotManager.get_instance()
        slot_manager.export_onnx(params, UPLOAD_DIR)

    def post_move_merged_model(self, param: MoveMergedModelParam):
        raise HTTPException(
            status_code=400,
            detail=json.dumps({"code": "NOT_SUPPORTED", "message": "Model merge is not supported in VCClient Forge."}),
        )

    def post_move_export_onnx_model(self, param: MoveExportedOnnxModelParam):
        slot_manager = SlotManager.get_instance()
        slot_manager.move_model_slot_from_onnx_exported(param)

    def post_move_model(self, param: MoveModelParam):
        slot_manager = SlotManager.get_instance()
        slot_manager.move_model_slot(param)

    def post_export(self, param: ExportParam):
        slot_manager = SlotManager.get_instance()
        name, buffer = slot_manager.export(param)
        file_content = buffer.read()
        headers = {"Content-Disposition": f"attachment; filename={name}.zip"}
        return Response(content=file_content, media_type="application/zip", headers=headers)

    def post_beatricev2_set_voice_icon_file(self, param: SetBeatriceV2VoiceIconFileParam):
        param.icon_file = UPLOAD_DIR / param.icon_file.name
        slot_manager = SlotManager.get_instance()
        slot_manager.beatrice_set_voice_icon_file(param)

    def post_beatricev2_set_voice_name(self, param: SetBeatriceV2VoiceNameParam):
        slot_manager = SlotManager.get_instance()
        slot_manager.beatrice_set_voice_name(param)

    def post_beatricev2_set_voice_description(self, param: SetBeatriceV2VoiceDescriptionParam):
        slot_manager = SlotManager.get_instance()
        slot_manager.beatrice_set_voice_description(param)
