"""asr / translation 結果のコンソール表示.

暫定結果（is_final: false）は行を書き換え、確定結果で改行する
（PROTOCOL.md「クライアント実装の指針」）。
"""

from typing import Any, Optional

from output.base import TranslationOutput

# 暫定結果の書き換えで前の行の残骸を消すための最小表示幅
LINE_MIN_WIDTH = 70


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


class ConsoleOutput(TranslationOutput):
    """asr / translation を 1 行のコンソール出力として表示する."""

    def __init__(self) -> None:
        """出力状態を初期化する."""
        self._last_line_width = LINE_MIN_WIDTH

    def handle(
        self,
        message: dict[str, Any],
        latency_ms: Optional[float],
        rtt_ms: Optional[float],
    ) -> None:
        """asr / translation を 1 行で表示する.

        暫定結果はキャリッジリターンで行を書き換え、確定結果で改行する
        （PROTOCOL.md「クライアント実装の指針」）。

        Args:
            message: 受信した asr または translation メッセージ。
            latency_ms: 体感遅延（ミリ秒）。計算できない場合は None。
            rtt_ms: 直近の ping / pong で得た RTT（ミリ秒）。未計測なら None。
        """
        line = format_result_line(message, latency_ms, rtt_ms)
        width = max(self._last_line_width, len(line))
        self._last_line_width = max(LINE_MIN_WIDTH, len(line))
        if message.get("is_final"):
            print(f"\r{line.ljust(width)}")
        else:
            print(f"\r{line.ljust(width)}", end="", flush=True)
