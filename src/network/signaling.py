"""WebSocket シグナリング・制御チャネルのクライアント.

上り制御メッセージ（session_start / webrtc_offer / ping / session_end）の生成と、
JSON テキストフレームの送受信を行う。プロトコルはバージョン 1（PROTOCOL.md）。
"""

import json
import time
from typing import Any, Optional

import websockets
from websockets.asyncio.client import ClientConnection

PROTOCOL_VERSION = 1


def now_ms() -> int:
    """現在時刻を Unix epoch ミリ秒で返す.

    Returns:
        Unix epoch からの経過ミリ秒。
    """
    return int(time.time() * 1000)


def make_session_start() -> dict[str, Any]:
    """session_start メッセージを生成する.

    Returns:
        session_start メッセージ。
    """
    return {
        "type": "session_start",
        "protocol_version": PROTOCOL_VERSION,
        "client_ts_ms": now_ms(),
    }


def make_webrtc_offer(sdp: str) -> dict[str, Any]:
    """webrtc_offer メッセージを生成する.

    Args:
        sdp: ICE 候補を含む offer の SDP。

    Returns:
        webrtc_offer メッセージ。
    """
    return {"type": "webrtc_offer", "sdp": sdp}


def make_session_end() -> dict[str, Any]:
    """session_end メッセージを生成する.

    Returns:
        session_end メッセージ。
    """
    return {"type": "session_end"}


def make_ping() -> dict[str, Any]:
    """ping メッセージを生成する.

    Returns:
        ping メッセージ（client_ts_ms は現在時刻）。
    """
    return {"type": "ping", "client_ts_ms": now_ms()}


class SignalingChannel:
    """tamami サーバーとの WebSocket 制御チャネル.

    シグナリング（SDP 交換）・セッション制御・結果受信を 1 本の WebSocket で行う。

    Examples:
        >>> channel = await SignalingChannel.connect("ws://localhost:8765/ws")
        >>> await channel.send(make_session_start())
        >>> message = await channel.recv()
        >>> await channel.close()
    """

    def __init__(self, ws: ClientConnection) -> None:
        """チャネルを初期化する.

        Args:
            ws: 接続済みの WebSocket コネクション。
        """
        self._ws = ws

    @classmethod
    async def connect(cls, url: str) -> "SignalingChannel":
        """サーバーへ接続してチャネルを作る.

        Args:
            url: 接続先（例: "ws://localhost:8765/ws"）。

        Returns:
            接続済みの SignalingChannel。

        Raises:
            OSError: 接続に失敗した場合。
        """
        ws = await websockets.connect(url)
        return cls(ws)

    async def send(self, message: dict[str, Any]) -> None:
        """JSON メッセージを送信する.

        Args:
            message: 送信するメッセージ。

        Raises:
            websockets.exceptions.ConnectionClosed: 接続が閉じている場合。
        """
        await self._ws.send(json.dumps(message, ensure_ascii=False))

    async def recv(self) -> Optional[dict[str, Any]]:
        """JSON メッセージを 1 件受信する.

        バイナリフレームは無視して次のテキストフレームを待つ。

        Returns:
            受信したメッセージ。接続が閉じられた場合は None。
        """
        while True:
            try:
                raw = await self._ws.recv()
            except websockets.exceptions.ConnectionClosed:
                return None
            if isinstance(raw, bytes):
                continue
            return json.loads(raw)

    async def close(self) -> None:
        """接続を閉じる."""
        await self._ws.close()
