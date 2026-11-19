from __future__ import annotations

from typing import Callable

from fastapi import HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from vcclient.exception import VCClientError
from vcclient.logger import logger


class ValidationErrorLoggingRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original_route_handler = super().get_route_handler()

        async def _read_error_body_preview(request: Request) -> str:
            if request.headers.get("content-type", "").lower().startswith("multipart/"):
                return ""
            try:
                body = await request.body()
            except Exception:
                return ""
            return body[:4096].decode("utf-8", errors="replace")

        async def custom_route_handler(request: Request) -> Response:
            try:
                return await original_route_handler(request)
            except RequestValidationError as exc:
                logger.error("RequestValidationError: %s", exc)
                detail = {"errors": exc.errors(), "body": await _read_error_body_preview(request)}
                raise HTTPException(status_code=422, detail=detail)
            except HTTPException as exc:
                raise exc
            except VCClientError as exc:
                logger.error("VCClientError: %s", exc)
                raise HTTPException(status_code=422, detail=str(exc))
            except Exception as exc:
                logger.error("Exception: %s", exc, exc_info=True)
                detail = {"errors": str(exc), "body": await _read_error_body_preview(request)}
                raise HTTPException(status_code=422, detail=detail)

        return custom_route_handler
