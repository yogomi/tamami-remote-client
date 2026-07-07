"""WebRTC 送信（マイク音声の Opus トラック化）.

マイク入力を aiortc のオーディオトラックとして送出する。Opus エンコードと
RTP 化は aiortc が行うため、このモジュールは PCM フレームの供給に徹する。
"""

import asyncio
import time
from fractions import Fraction
from typing import Optional

import numpy as np
from aiortc import RTCConfiguration, RTCPeerConnection, RTCRtpSender
from aiortc.mediastreams import MediaStreamError, MediaStreamTrack
from av.audio.frame import AudioFrame

from audio.input import AudioInputStream

# Opus 標準のフレーム長（PROTOCOL.md「上り: 音声」を参照）
FRAME_DURATION_SEC = 0.02

# drain() で実行中のマイク読み取りの完了を待つ最大秒数。
# 1 回の読み取りは高々フレーム数フレーム分（100ms 未満）で返るため、十分な余裕を持たせた値。
READ_DRAIN_TIMEOUT_SEC = 1.0


class MicrophoneStreamTrack(MediaStreamTrack):
    """AudioInputStream を aiortc のオーディオトラックとして公開する.

    read_chunk() はブロッキングのため executor で実行する。送出ペースは
    マイクの取得ペース（実時間）に律速される。

    Args:
        source: 音声入力（float32 / mono を前提とする）。

    Attributes:
        start_ts_ms: 最初のフレームを取得した時刻（Unix epoch ミリ秒）。
            体感遅延の計算に用いる。取得前は None。
            なお pyaudio はストリーム開始からバッファに溜め続けるため、
            シグナリング中に溜まったバックログ分だけ実際の発話時刻より
            遅い値になる（LAN では数百 ms 以内で、秒単位の遅延目標の
            判定には影響しない）。
    """

    kind = "audio"

    def __init__(self, source: AudioInputStream) -> None:
        """トラックを初期化する.

        Args:
            source: 音声入力。
        """
        super().__init__()
        self._source = source
        self._sample_rate = source.get_sample_rate()
        self._frame_samples = int(self._sample_rate * FRAME_DURATION_SEC)
        self._pts = 0
        # 実行中の読み取りの有無をスレッド側で記録する（drain() が参照）。
        # asyncio future はタスクのキャンセルで「完了」扱いになり、executor
        # スレッド上の実際の読み取り状態を反映しないため、future では追跡しない
        self._read_active = False
        self.start_ts_ms: Optional[int] = None

    async def recv(self) -> AudioFrame:
        """PCM フレームを 1 つ返す.

        Returns:
            20ms 分の s16 / mono の AudioFrame。

        Raises:
            MediaStreamError: トラックが停止済み、またはマイクの読み取りに
                失敗した場合。
        """
        if self.readyState != "live":
            raise MediaStreamError

        loop = asyncio.get_running_loop()
        # 投入前にフラグを立てる（未開始のジョブも「実行中」として drain() に待たせる）
        self._read_active = True
        try:
            pcm_float = await loop.run_in_executor(None, self._tracked_read)
        except IOError as e:
            self.stop()
            raise MediaStreamError(f"microphone read failed: {e}") from e

        if self.start_ts_ms is None:
            self.start_ts_ms = int(time.time() * 1000)

        pcm_int16 = (np.clip(pcm_float, -1.0, 1.0) * 32767.0).astype(np.int16)
        frame = AudioFrame(format="s16", layout="mono", samples=len(pcm_int16))
        frame.planes[0].update(pcm_int16.tobytes())
        frame.sample_rate = self._sample_rate
        frame.pts = self._pts
        frame.time_base = Fraction(1, self._sample_rate)
        self._pts += len(pcm_int16)
        return frame

    def _tracked_read(self) -> np.ndarray:
        """read_chunk() を実行し、終了時に必ず実行中フラグを下ろす（executor 上で走る）.

        Returns:
            read_chunk() の戻り値。

        Raises:
            IOError: read_chunk() が失敗した場合。
        """
        try:
            return self._source.read_chunk(self._frame_samples)
        finally:
            self._read_active = False

    async def drain(self) -> None:
        """実行中のマイク読み取りの完了を待つ.

        PyAudio の読み取り中に別スレッドからストリームを閉じると読み取りが
        戻らなくなることがあり、インタープリタ終了時の executor スレッドの
        join が固まる。source.close() の前に必ず呼ぶこと。

        recv() の await がキャンセルされても executor 上の読み取りは走り続ける
        （このとき asyncio future はキャンセル＝完了扱いになる）ため、実スレッド
        側のフラグをポーリングして完了を待つ。

        Raises:
            なし（タイムアウト時は諦めて戻る）。
        """
        deadline = time.monotonic() + READ_DRAIN_TIMEOUT_SEC
        while self._read_active and time.monotonic() < deadline:
            await asyncio.sleep(0.005)


def create_peer_connection(track: MicrophoneStreamTrack) -> RTCPeerConnection:
    """音声トラックを載せた RTCPeerConnection を作る.

    PROTOCOL.md に従い、SDP では Opus のみを提示する。

    ICE サーバーは設定しない（LAN 内のホスト候補のみで接続する）。
    aiortc のデフォルトは Google の STUN サーバーで、aioice がその DNS 解決を
    タイムアウトなしの executor ジョブとして実行するため、DNS が応答しない
    環境ではスレッドが残り続けプロセス終了時の join が固まる。
    NAT 越えが必要になったら、STUN / TURN は IP アドレス指定で設定すること。

    Args:
        track: 送出するマイクトラック。

    Returns:
        トラック追加・コーデック制限済みの RTCPeerConnection。
    """
    pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
    pc.addTrack(track)
    capabilities = RTCRtpSender.getCapabilities("audio")
    opus_codecs = [c for c in capabilities.codecs if c.mimeType.lower() == "audio/opus"]
    for transceiver in pc.getTransceivers():
        if transceiver.kind == "audio":
            transceiver.setCodecPreferences(opus_codecs)
    return pc


async def create_offer_sdp(pc: RTCPeerConnection) -> str:
    """offer を作成し、ICE 候補収集完了後の SDP を返す.

    aiortc は setLocalDescription 内で ICE 候補の収集完了を待つため、
    返される SDP は候補を含む（non-trickle。PROTOCOL.md を参照）。

    Args:
        pc: create_peer_connection で作成した RTCPeerConnection。

    Returns:
        ICE 候補を含む offer の SDP。
    """
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    return pc.localDescription.sdp
