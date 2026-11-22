from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, Header, Request, Response, UploadFile
from fastapi.responses import FileResponse

from vcclient.server.api_common import DomainApiError, DomainApiRoute, is_session_active, set_etag_header
from vcclient.voice_changer.model_catalog import (
    ICON_SUFFIXES,
    Model,
    ModelOrder,
    ModelUpdate,
    create_model,
    delete_icon,
    delete_model,
    get_icon_path,
    get_model,
    list_models,
    set_icon,
    set_order,
    update_model,
)
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger
from vcclient.voice_changer.voice_changer_const import EmbedderType

_MODEL_SUFFIXES = {".onnx", ".pth"}
_INDEX_SUFFIXES = {".index"}
_UPLOAD_COPY_CHUNK_BYTES = 1024 * 1024
_IMAGE_MIME_TO_SUFFIX = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
    "image/bmp": ".bmp",
}


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
        raise DomainApiError(
            422,
            "validation_error",
            f"Unsupported file type for {field_name}: {suffix or '(none)'}",
            {"field": field_name},
        )
    if require_image_mime and upload.content_type:
        content_type = upload.content_type.split(";", 1)[0].strip().lower()
        if not content_type.startswith("image/") and content_type != "application/octet-stream":
            raise DomainApiError(
                422,
                "validation_error",
                f"Invalid content type for {field_name}: {upload.content_type}",
                {"field": field_name},
            )

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
        raise DomainApiError(422, "validation_error", f"Uploaded {field_name} is empty.", {"field": field_name})
    return dst


class RestAPIModels:
    """Domain API router for NanoID model catalog, uploads, icons, and ordering."""

    def __init__(self) -> None:
        self.router = APIRouter(route_class=DomainApiRoute)
        self.router.add_api_route("/api/models", self.get_models, methods=["GET"])
        self.router.add_api_route("/api/models", self.post_model, methods=["POST"], status_code=201)
        self.router.add_api_route("/api/models/order", self.put_models_order, methods=["PUT"])
        self.router.add_api_route("/api/models/{model_id}", self.get_model, methods=["GET"])
        self.router.add_api_route("/api/models/{model_id}", self.put_model, methods=["PUT"])
        self.router.add_api_route("/api/models/{model_id}", self.delete_model, methods=["DELETE"])
        self.router.add_api_route("/api/models/{model_id}/icon", self.get_model_icon, methods=["GET"])
        self.router.add_api_route("/api/models/{model_id}/icon", self.put_model_icon, methods=["PUT"])
        self.router.add_api_route("/api/models/{model_id}/icon", self.delete_model_icon, methods=["DELETE"])

    def get_models(self) -> list[Model]:
        return list_models()

    def post_model(
        self,
        response: Response,
        model_file: UploadFile = File(...),
        name: str = Form(...),
        index_file: UploadFile | None = File(None),
        icon_file: UploadFile | None = File(None),
        embedder: EmbedderType | None = Form(None),
    ) -> Model:
        normalized_name = name.strip()
        if not normalized_name:
            raise DomainApiError(422, "validation_error", "Model name must not be empty.", {"field": "name"})

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dir = Path(tmpdir)
            model_path = _save_upload(
                model_file,
                tmp_dir,
                prefix="model",
                allowed_suffixes=_MODEL_SUFFIXES,
                field_name="model_file",
            )
            index_path = (
                _save_upload(
                    index_file,
                    tmp_dir,
                    prefix="index",
                    allowed_suffixes=_INDEX_SUFFIXES,
                    field_name="index_file",
                )
                if index_file is not None
                else None
            )
            icon_path = (
                _save_upload(
                    icon_file,
                    tmp_dir,
                    prefix="icon",
                    allowed_suffixes=ICON_SUFFIXES,
                    field_name="icon_file",
                    require_image_mime=True,
                )
                if icon_file is not None
                else None
            )
            model, etag = create_model(
                name=normalized_name,
                model_path=model_path,
                index_path=index_path,
                icon_path=icon_path,
                embedder=embedder,
            )

        response.status_code = 201
        set_etag_header(response, etag)
        return model

    def put_models_order(
        self,
        payload: ModelOrder,
        response: Response,
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> ModelOrder:
        order, etag = set_order(payload.model_ids, if_match=if_match)
        set_etag_header(response, etag)
        return ModelOrder(model_ids=order)

    def get_model(self, model_id: str, response: Response) -> Model:
        model, etag = get_model(model_id)
        set_etag_header(response, etag)
        return model

    def put_model(
        self,
        model_id: str,
        payload: ModelUpdate,
        response: Response,
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> Model:
        model, etag = update_model(model_id, payload, if_match=if_match)
        if not is_session_active() and (payload.pitch_estimator is not None or payload.chunk_sec is not None):
            voice = VoiceChanger.peek_instance()
            if voice is not None and voice.vc_pipeline is not None and voice.vc_info.model_id == model_id:
                voice.check_and_update_pipeline()
        set_etag_header(response, etag)
        return model

    def delete_model(
        self,
        model_id: str,
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> Response:
        delete_model(model_id, if_match=if_match)
        return Response(status_code=204)

    def get_model_icon(self, model_id: str) -> FileResponse:
        icon_path, media_type, etag = get_icon_path(model_id)
        return FileResponse(path=str(icon_path), media_type=media_type, headers={"ETag": etag})

    async def put_model_icon(
        self,
        model_id: str,
        request: Request,
        response: Response,
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> Model:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dir = Path(tmpdir)
            if content_type == "multipart/form-data":
                form = await request.form()
                upload = form.get("icon_file") or form.get("file")
                if upload is None or not hasattr(upload, "file"):
                    raise DomainApiError(
                        422,
                        "validation_error",
                        "Multipart request must contain an 'icon_file' or 'file' upload.",
                    )
                icon_path = _save_upload(
                    upload,  # type: ignore[arg-type]
                    tmp_dir,
                    prefix="icon",
                    allowed_suffixes=ICON_SUFFIXES,
                    field_name="icon_file",
                    require_image_mime=True,
                )
            elif content_type.startswith("image/"):
                suffix = _IMAGE_MIME_TO_SUFFIX.get(content_type)
                if suffix is None:
                    raise DomainApiError(
                        422,
                        "validation_error",
                        f"Unsupported image MIME type: {content_type}",
                    )
                raw_bytes = await request.body()
                if not raw_bytes:
                    raise DomainApiError(422, "validation_error", "Uploaded icon body is empty.")
                icon_path = tmp_dir / f"icon_{uuid4().hex[:12]}{suffix}"
                icon_path.write_bytes(raw_bytes)
            else:
                raise DomainApiError(
                    422,
                    "validation_error",
                    "Icon upload requires Content-Type 'multipart/form-data' or 'image/*'.",
                )

            model, etag = set_icon(
                model_id,
                icon_path,
                if_match=if_match,
            )

        set_etag_header(response, etag)
        return model

    def delete_model_icon(
        self,
        model_id: str,
        response: Response,
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> Model:
        model, etag = delete_icon(model_id, if_match=if_match)
        set_etag_header(response, etag)
        return model
