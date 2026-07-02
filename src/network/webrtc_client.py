"""WebRTC 送信（マイク音声の Opus トラック化）.

マイク入力を aiortc のオーディオトラックとして送出する。Opus エンコードと
RTP 化は aiortc が行うため、このモジュールは PCM フレームの供給に徹する。
"""

import asyncio
import time
from fractions import Fraction
from typing import Optional

import numpy as np
from aiortc import RTCPeerConnection, RTCRtpSender
from aiortc.mediastreams import MediaStreamError, MediaStreamTrack
from av.audio.frame import AudioFrame

from audio.input import AudioInputStream

# Opus 標準のフレーム長（PROTOCOL.md「上り: 音声」を参照）
FRAME_DURATION_SEC = 0.02


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
        try:
            pcm_float = await loop.run_in_executor(
                None, self._source.read_chunk, self._frame_samples
            )
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


def create_peer_connection(track: MicrophoneStreamTrack) -> RTCPeerConnection:
    """音声トラックを載せた RTCPeerConnection を作る.

    PROTOCOL.md に従い、SDP では Opus のみを提示する。

    Args:
        track: 送出するマイクトラック。

    Returns:
        トラック追加・コーデック制限済みの RTCPeerConnection。
    """
    pc = RTCPeerConnection()
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
