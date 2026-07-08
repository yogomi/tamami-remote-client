"""結果表示の抽象基底クラス.

コンソール表示・TTS・字幕表示など、asr / translation の結果メッセージを
受け取って何らかの形で出力する処理を `TranslationOutput` として抽象化する。
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class TranslationOutput(ABC):
    """asr / translation の結果メッセージを受け取り出力する抽象基底クラス."""

    @abstractmethod
    def handle(
        self,
        message: dict[str, Any],
        latency_ms: Optional[float],
        rtt_ms: Optional[float],
    ) -> None:
        """asr / translation メッセージを 1 件受け取り出力する.

        暫定結果（`is_final: false`）・確定結果（`is_final: true`）の両方が渡る
        （PROTOCOL.md「セグメントのライフサイクルと配信規則」）。TTS など確定情報
        のみ扱う出力は、`message["is_final"]` で選別すればよい。

        Args:
            message: 受信した asr または translation メッセージ。
            latency_ms: 体感遅延（ミリ秒）。計算できない場合は None。
            rtt_ms: 直近の ping / pong で得た RTT（ミリ秒）。未計測なら None。
        """
        raise NotImplementedError

    def close(self) -> None:
        """セッション終了時の後始末を行う.

        デフォルトでは何もしない。リソースの解放が必要な出力先はオーバーライドする。
        """
