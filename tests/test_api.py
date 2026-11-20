"""API client: error classification and the WebSocket write path."""

from __future__ import annotations

import json
from typing import Any

import aiohttp
import pytest

from custom_components.vasco_ventilation.api import VascoApiClient, _is_auth_error
from custom_components.vasco_ventilation.exceptions import (
    VascoApiError,
    VascoAuthError,
    VascoConnectionError,
)

from .conftest import ACCOUNT_CONFIG, DEVICE


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("FAILED/LOGIN_FAILED", True),  # observed for a wrong password
        ("LOGIN_FAILED_ACCOUNT_NOT_VERIFIED", True),
        ("CLOUD_ERROR_BRIDGETOKEN_OR_USERTOKEN_INVALID", True),
        ("TOO_MANY_LOGIN_ATTEMPTS", False),
        ("FAILED", False),
        ("INTERNAL ERROR", False),
    ],
)
def test_is_auth_error(code: str, expected: bool) -> None:
    assert _is_auth_error(code) is expected


class _Resp:
    def __init__(self, data: Any) -> None:
        self._data = data
        self.status = 200

    async def __aenter__(self) -> _Resp:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def json(self, content_type: str | None = None) -> Any:
        return self._data


class _Msg:
    def __init__(self, data: dict) -> None:
        self.type = aiohttp.WSMsgType.BINARY
        self.data = json.dumps(data).encode()


class _WS:
    def __init__(self, before: list[dict], after: list[dict]) -> None:
        self._before = before
        self._after = after
        self.sent: list[dict] = []
        self._phase = 0

    async def __aenter__(self) -> _WS:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def __aiter__(self) -> _WS:
        self._queue = list(self._before if not self.sent else self._after)
        return self

    async def __anext__(self) -> _Msg:
        if not self._queue:
            raise StopAsyncIteration
        return _Msg(self._queue.pop(0))

    async def send_bytes(self, data: bytes) -> None:
        self.sent.append(json.loads(data))


class _Session:
    def __init__(self, posts: list[Any], sockets: list[_WS] | None = None) -> None:
        self.posts = posts
        self.sockets = sockets or []
        self.ws_params: list[dict] = []

    def post(self, url: str, **kwargs: Any) -> _Resp:
        return _Resp(self.posts.pop(0))

    def ws_connect(self, url: str, params: dict) -> _WS:
        self.ws_params.append(params)
        return self.sockets.pop(0)


def _login_ok(token: str = "tok") -> dict:
    return {"status": "success", "payload": {"userToken": token}}


async def test_login_wrong_password_is_auth_error() -> None:
    session = _Session(
        [{"status": "failed", "payload": {"errorCode": "FAILED", "extraInfo": "LOGIN_FAILED"}}]
    )
    with pytest.raises(VascoAuthError):
        await VascoApiClient(session, "a@b.c", "x").async_login()


async def test_login_server_error_is_not_auth_error() -> None:
    session = _Session([{"status": "failed", "payload": {"errorCode": "INTERNAL ERROR"}}])
    with pytest.raises(VascoApiError) as err:
        await VascoApiClient(session, "a@b.c", "x").async_login()
    assert not isinstance(err.value, VascoAuthError)


async def test_rest_reauthenticates_once_on_token_error() -> None:
    session = _Session(
        [
            _login_ok("old"),
            {"status": "failed", "payload": {"errorCode": "TOKEN EXPIRED"}},
            _login_ok("new"),
            {"status": "success", "payload": ACCOUNT_CONFIG},
        ]
    )
    client = VascoApiClient(session, "a@b.c", "x")
    assert await client.async_get_account_configuration() == ACCOUNT_CONFIG
    assert client.token == "new"


async def test_write_sends_level_and_waits_for_ack() -> None:
    ws = _WS(
        [{"functionName": "connectionStatus", "status": "OK"}],
        [{"functionName": "dataWritten", "parameterName": "requestedLevel"}],
    )
    session = _Session([_login_ok()], [ws])
    await VascoApiClient(session, "a@b.c", "x").async_set_level(ACCOUNT_CONFIG, DEVICE, 3, -1)
    props, write = ws.sent
    assert json.loads(props["payload"])[0]["manualSettingActiveTill"] == -1
    assert write["parameterName"] == "requestedLevel"
    assert write["data"] == 4  # cloud level 3 (High) is wire value 4


async def test_write_relogs_in_when_bridge_rejects_token() -> None:
    rejected = _WS([{"functionName": "connectionStatus", "status": "INVALID"}], [])
    accepted = _WS(
        [{"functionName": "connectionStatus", "status": "OK"}],
        [{"functionName": "dataWritten", "parameterName": "overrideTimeSpeed3"}],
    )
    session = _Session([_login_ok("old"), _login_ok("new")], [rejected, accepted])
    client = VascoApiClient(session, "a@b.c", "x")
    await client.async_write_parameter(ACCOUNT_CONFIG, DEVICE, "overrideTimeSpeed3", 30)
    assert [p["userToken"] for p in session.ws_params] == ["old", "new"]
    assert accepted.sent[1]["data"] == 30


async def test_write_bridge_closes_before_ready() -> None:
    session = _Session([_login_ok()], [_WS([], [])])
    with pytest.raises(VascoConnectionError, match="before it was ready"):
        await VascoApiClient(session, "a@b.c", "x").async_set_level(ACCOUNT_CONFIG, DEVICE, 2)
