from __future__ import annotations

from fastapi import APIRouter, Header, Response

from vcclient.server.api_common import DomainApiRoute, set_etag_header
from vcclient.voice_changer.settings_manager import UserSettings, get_settings, update_settings


class RestAPISettings:
    """Domain API router for pure persisted defaults (`/api/settings`)."""

    def __init__(self) -> None:
        self.router = APIRouter(route_class=DomainApiRoute)
        self.router.add_api_route("/api/settings", self.get_settings, methods=["GET"])
        self.router.add_api_route("/api/settings", self.put_settings, methods=["PUT"])

    def get_settings(self, response: Response) -> UserSettings:
        settings, etag = get_settings()
        set_etag_header(response, etag)
        return settings

    def put_settings(
        self,
        payload: UserSettings,
        response: Response,
        if_match: str | None = Header(default=None, alias="If-Match"),
    ) -> UserSettings:
        updated, etag = update_settings(payload, if_match=if_match)
        set_etag_header(response, etag)
        return updated
