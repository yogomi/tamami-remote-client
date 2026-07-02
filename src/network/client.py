"""ストリーミング送信クライアント本体.

マイク音声を WebRTC で tamami サーバーへ送り、認識・翻訳結果をコンソールへ
表示する。暫定結果（is_final: false）は行を書き換え、確定結果で改行する。
あわせて体感遅延（PROTOCOL.md「遅延計測」）と RTT を表示する。
"""

import asyncio
import signal
from typing import Any, Optional

from aiortc import RTCSessionDescription

from audio.input import MicrophoneInput
from network.signaling import (
    SignalingChannel,
    make_ping,
    make_session_end,
    make_session_start,
    make_webrtc_offer,
    now_ms,
)
from network.webrtc_client import (
    MicrophoneStreamTrack,
    create_offer_sdp,
    create_peer_connection,
)

# ping の送信間隔（秒）
PING_INTERVAL_SEC = 5.0

# session_end 送信後にサーバーのフラッシュ結果を待つ最大秒数
DRAIN_TIMEOUT_SEC = 5.0

# 暫定結果の書き換えで前の行の残骸を消すための最小表示幅
LINE_MIN_WIDTH = 70


def compute_perceived_latency_ms(
    received_at_ms: int, track_start_ms: int, ts_audio_end: float
) -> float:
    """体感遅延（発話から結果表示までのミリ秒）を計算する.

    PROTOCOL.md「遅延計測」に定義された
    `now_ms - (t0_ms + ts_audio_end * 1000)` を計算する。

    Args:
        received_at_ms: 結果メッセージを受信した時刻（クライアント時計・ミリ秒）。
        track_start_ms: トラック送出開始時刻（クライアント時計・ミリ秒）。
        ts_audio_end: 結果メッセージの音声タイムライン上の終了秒。

    Returns:
        体感遅延（ミリ秒）。
    """
    return received_at_ms - (track_start_ms + ts_audio_end * 1000.0)


def format_result_line(
    message: dict[str, Any],
    latency_ms: Optional[float],
    rtt_ms: Optional[float],
) -> str:
    """asr / translation メッセージの表示行を組み立てる.

    Args:
        message: 受信した asr または translation メッセージ。
        latency_ms: 体感遅延（ミリ秒）。計算できない場合は None。
        rtt_ms: 直近の ping / pong で得た RTT（ミリ秒）。未計測なら None。

    Returns:
        コンソール 1 行分の文字列。
    """
    kind = message["type"]
    marker = "*" if message.get("is_final") else " "
    text = message.get("text", "")
    parts = [f"[{kind}#{message.get('segment_id')}{marker}] {text}"]
    if latency_ms is not None:
        parts.append(f"latency {latency_ms / 1000.0:.2f}s")
    if rtt_ms is not None:
        parts.append(f"rtt {rtt_ms:.0f}ms")
    return " | ".join(parts)


class StreamingClient:
    """接続 1 回分のストリーミング送信クライアント.

    Args:
        url: 接続先（例: "ws://localhost:8765/ws"）。
    """

    def __init__(self, url: str) -> None:
        """クライアントを初期化する.

        Args:
            url: 接続先 URL。
        """
        self._url = url
        self._channel: Optional[SignalingChannel] = None
        self._track: Optional[MicrophoneStreamTrack] = None
        self._rtt_ms: Optional[float] = None
        self._last_line_width = LINE_MIN_WIDTH

    async def run(self) -> None:
        """セッションを実行する（Ctrl+C で終了する）.

        接続 → セッション開始 → SDP 交換 → 結果受信の順に進み、
        Ctrl+C で session_end を送ってフラッシュ結果を待ってから閉じる。

        Raises:
            RuntimeError: ハンドシェイクがプロトコルどおりに進まなかった場合。
        """
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, stop_event.set)

        print(f"Connecting to {self._url} ...")
        channel = await SignalingChannel.connect(self._url)
        self._channel = channel
        microphone = MicrophoneInput()
        pc = None
        ping_task: Optional[asyncio.Task] = None
        try:
            await self._handshake_session(channel)

            track = MicrophoneStreamTrack(microphone)
            self._track = track
            pc = create_peer_connection(track)
            offer_sdp = await create_offer_sdp(pc)
            await channel.send(make_webrtc_offer(offer_sdp))
            await self._handshake_webrtc(channel, pc)

            print("Streaming. Speak into the microphone (Ctrl+C to stop)...")
            print("-" * 50)
            ping_task = asyncio.create_task(self._ping_loop(channel))
            receive_task = asyncio.create_task(self._receive_loop(channel))
            stop_task = asyncio.create_task(stop_event.wait())
            done, _ = await asyncio.wait(
                [receive_task, stop_task], return_when=asyncio.FIRST_COMPLETED
            )

            if receive_task in done:
                # サーバー側から接続が閉じられた
                stop_task.cancel()
            else:
                # Ctrl+C: 送出を止めて session_end を送り、フラッシュ結果を待つ
                print("\nStopping...")
                track.stop()
                await channel.send(make_session_end())
                try:
                    await asyncio.wait_for(receive_task, DRAIN_TIMEOUT_SEC)
                except asyncio.TimeoutError:
                    receive_task.cancel()
        finally:
            if ping_task is not None:
                ping_task.cancel()
            if pc is not None:
                await pc.close()
            await channel.close()
            microphone.close()
            loop.remove_signal_handler(signal.SIGINT)
            print("Closed.")

    async def _handshake_session(self, channel: SignalingChannel) -> None:
        """session_start を送り、session_ready を待つ.

        Args:
            channel: 接続済みの制御チャネル。

        Raises:
            RuntimeError: session_ready 以外が返った・接続が閉じられた場合。
        """
        await channel.send(make_session_start())
        message = await channel.recv()
        if message is None or message.get("type") != "session_ready":
            raise RuntimeError(f"expected session_ready, got: {message}")
        print(f"Session ready: id={message.get('session_id')}")

    async def _handshake_webrtc(self, channel: SignalingChannel, pc: Any) -> None:
        """webrtc_answer を待って RTCPeerConnection に適用する.

        Args:
            channel: 接続済みの制御チャネル。
            pc: offer 済みの RTCPeerConnection。

        Raises:
            RuntimeError: webrtc_answer 以外が返った・接続が閉じられた場合。
        """
        message = await channel.recv()
        if message is None or message.get("type") != "webrtc_answer":
            raise RuntimeError(f"expected webrtc_answer, got: {message}")
        answer = RTCSessionDescription(sdp=message["sdp"], type="answer")
        await pc.setRemoteDescription(answer)
        print("WebRTC connected.")

    async def _ping_loop(self, channel: SignalingChannel) -> None:
        """一定間隔で ping を送り続ける.

        Args:
            channel: 接続済みの制御チャネル。
        """
        while True:
            await asyncio.sleep(PING_INTERVAL_SEC)
            await channel.send(make_ping())

    async def _receive_loop(self, channel: SignalingChannel) -> None:
        """結果メッセージを受信して表示する（接続が閉じるまで）.

        Args:
            channel: 接続済みの制御チャネル。
        """
        while True:
            message = await channel.recv()
            if message is None:
                break
            message_type = message.get("type")
            if message_type in ("asr", "translation"):
                self._show_result(message)
            elif message_type == "pong":
                self._rtt_ms = float(now_ms() - message["client_ts_ms"])
            elif message_type == "error":
                print(
                    f"\nServer error [{message.get('code')}]: {message.get('message')}"
                )
                if message.get("fatal"):
                    break

    def _show_result(self, message: dict[str, Any]) -> None:
        """asr / translation を 1 行で表示する.

        暫定結果はキャリッジリターンで行を書き換え、確定結果で改行する
        （PROTOCOL.md「クライアント実装の指針」）。

        Args:
            message: 受信した asr または translation メッセージ。
        """
        latency_ms: Optional[float] = None
        if self._track is not None and self._track.start_ts_ms is not None:
            latency_ms = compute_perceived_latency_ms(
                now_ms(), self._track.start_ts_ms, message["ts_audio_end"]
            )
        line = format_result_line(message, latency_ms, self._rtt_ms)
        width = max(self._last_line_width, len(line))
        self._last_line_width = max(LINE_MIN_WIDTH, len(line))
        if message.get("is_final"):
            print(f"\r{line.ljust(width)}")
        else:
            print(f"\r{line.ljust(width)}", end="", flush=True)


async def run_client(url: str) -> None:
    """ストリーミング送信クライアントを実行する.

    Args:
        url: 接続先（例: "ws://localhost:8765/ws"）。
    """
    client = StreamingClient(url)
    await client.run()
