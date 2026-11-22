from __future__ import annotations

from fastapi import APIRouter, Header, Response

from vcclient.server.api_common import DomainApiRoute, set_etag_header
from vcclient.voice_changer.session_manager import (
    SessionSnapshot,
    SessionState,
    delete_session,
    get_session_state,
    put_session,
)


class RestAPISession:
    """Domain API router for snapshot-driven conversion session lifecycle (`/api/session`)."""

    def __init__(self) -> None:
        self.router = APIRouter(route_class=DomainApiRoute)
        self.router.add_api_route("/api/session", self.get_session, methods=["GET"])
        self.router.add_api_route("/api/session", self.put_session, methods=["PUT"])
        self.router.add_api_route("/api/session", self.delete_session, methods=["DELETE"])

    def get_session(self, response: Response) -> SessionState:
        state, etag = get_session_state()
        set_etag_header(response, etag)
        return state

    def put_session(
        self,
        payload: SessionSnapshot,
        response: Response,
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> SessionState:
        state, etag, status_code = put_session(payload, if_match=if_match)
        response.status_code = status_code
        set_etag_header(response, etag)
        return state

    def delete_session(
        self,
        response: Response,
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> SessionState:
        state, etag = delete_session(if_match=if_match)
        set_etag_header(response, etag)
        return state
