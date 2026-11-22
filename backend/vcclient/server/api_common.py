from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from vcclient.exception import VCClientError
from vcclient.logger import logger
from vcclient.voice_changer.configuration_manager.configuration_manager import ConfigurationManager
from vcclient.voice_changer.voice_change_manager.local_voice_changer_interface import LocalVoiceChangerInterface
from vcclient.voice_changer.voice_change_manager.voice_changer import VoiceChanger


class ApiErrorResponse(BaseModel):
    """Unified JSON error envelope returned by domain API endpoints."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class DomainApiError(Exception):
    """HTTP-mapped domain error producing the unified JSON error envelope."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details: dict[str, Any] = details if details is not None else {}
        super().__init__(message)

    def to_response(self) -> JSONResponse:
        body = ApiErrorResponse(code=self.code, message=self.message, details=self.details)
        return JSONResponse(status_code=self.status_code, content=body.model_dump())


def compute_etag(payload: Any) -> str:
    """Compute a deterministic quoted ETag string from any JSON-encodable payload."""
    encoded = jsonable_encoder(payload)
    canonical = json.dumps(encoded, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f'"{digest[:16]}"'


def _normalize_etag(tag: str) -> str:
    stripped = tag.strip()
    if stripped.startswith("W/"):
        stripped = stripped[2:].strip()
    return stripped


def verify_if_match(if_match: str | None, current_etag: str) -> None:
    """Validate an optional HTTP If-Match precondition against the current resource ETag."""
    if if_match is None or not if_match.strip():
        return
    candidates = [_normalize_etag(part) for part in if_match.split(",") if part.strip()]
    if "*" in candidates or _normalize_etag(current_etag) in candidates:
        return
    raise DomainApiError(
        409,
        "etag_mismatch",
        "Resource state has changed; reload and retry.",
        {"current_etag": current_etag},
    )


def set_etag_header(response: Response, etag: str) -> None:
    """Attach a strong ETag header to an HTTP response."""
    response.headers["ETag"] = etag


def set_active_model_id_getter(getter: Callable[[], str | None] | None) -> None:
    """Register or clear the callback returning the active session's model_id."""
    global _active_model_id_getter
    _active_model_id_getter = getter


_active_model_id_getter: Callable[[], str | None] | None = None


def get_active_model_id() -> str | None:
    """Return the model_id currently held by a starting or running session, if any."""
    if _active_model_id_getter is not None:
        return _active_model_id_getter()
    from vcclient.voice_changer.session_manager import get_active_session_model_id

    session_model_id = get_active_session_model_id()
    if session_model_id is not None:
        return session_model_id
    if is_session_active():
        voice = VoiceChanger.peek_instance()
        if voice is not None and voice.vc_info.model_id is not None:
            return voice.vc_info.model_id
        return ConfigurationManager.get_instance().get_voice_changer_configuration().model_id
    return None


def is_model_in_use(model_id: str) -> bool:
    """Return True when `model_id` is actively held by a starting or running session."""
    return get_active_model_id() == model_id


def ensure_model_not_in_use(model_id: str, message: str) -> None:
    """Raise DomainApiError(409, 'model_in_use') when `model_id` is in use by a session."""
    if is_model_in_use(model_id):
        raise DomainApiError(409, "model_in_use", message, {"model_id": model_id})


def is_session_active() -> bool:
    """Return True when a conversion session, native audio, or client bulk conversion is active."""
    from vcclient.voice_changer.session_manager import is_session_starting_or_running

    if is_session_starting_or_running():
        return True
    local = LocalVoiceChangerInterface.get_instance()
    if local.local_voice_changer_enabled or local.stream_running:
        return True
    voice = VoiceChanger.peek_instance()
    return voice is not None and voice.is_convert_chunk_bulk_started()


def ensure_session_stopped(
    message: str = "Operation is not allowed while a conversion session is active.",
) -> None:
    """Raise DomainApiError(409, 'session_active') if any conversion session is active."""
    if is_session_active():
        raise DomainApiError(409, "session_active", message)


def is_recording_active() -> bool:
    """Return True when server recording is enabled or currently running."""
    from vcclient.voice_changer.session_manager import is_session_recording_active

    if is_session_recording_active():
        return True
    conf = ConfigurationManager.get_instance().get_voice_changer_configuration()
    if conf.recording_started:
        return True
    voice = VoiceChanger.peek_instance()
    return voice is not None and voice.vc_info.recording_start_flag


class DomainApiRoute(APIRoute):
    """APIRoute subclass translating exceptions into the unified Domain API error envelope."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request) -> Response:
            try:
                return await original_route_handler(request)
            except DomainApiError as exc:
                return exc.to_response()
            except RequestValidationError as exc:
                logger.warning("Domain API request validation failed: %s", exc)
                return DomainApiError(
                    422,
                    "validation_error",
                    "Request validation failed.",
                    {"errors": jsonable_encoder(exc.errors())},
                ).to_response()
            except VCClientError as exc:
                logger.warning("Domain API VCClientError: %s", exc)
                return DomainApiError(
                    422,
                    "vcclient_error",
                    exc.info.reason,
                    exc.info.model_dump(),
                ).to_response()
            except Exception as exc:
                logger.error("Unhandled Domain API exception: %s", exc, exc_info=True)
                return DomainApiError(
                    500,
                    "internal_error",
                    "Internal server error.",
                    {"error": str(exc)},
                ).to_response()

        return custom_route_handler
