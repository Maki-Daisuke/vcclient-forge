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

        async def custom_route_handler(request: Request) -> Response:
            try:
                return await original_route_handler(request)
            except RequestValidationError as exc:
                logger.error("RequestValidationError: %s", exc)
                body = await request.body()
                detail = {"errors": exc.errors(), "body": body.decode()}
                raise HTTPException(status_code=422, detail=detail)
            except HTTPException as exc:
                raise exc
            except VCClientError as exc:
                logger.error("VCClientError: %s", exc)
                raise HTTPException(status_code=422, detail=str(exc))
            except Exception as exc:
                logger.error("Exception: %s", exc, exc_info=True)
                try:
                    body = await request.body()
                    detail = {"errors": str(exc), "body": body.decode()}
                    raise HTTPException(status_code=422, detail=detail)
                except Exception as exc2:
                    detail = {"errors": str(exc), "errors2": str(exc2)}
                    raise HTTPException(status_code=422, detail=detail)

        return custom_route_handler
