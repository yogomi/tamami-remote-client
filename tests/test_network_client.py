"""network.client / network.signaling の純粋関数部分のテスト."""

from network.client import compute_perceived_latency_ms, format_result_line
from network.signaling import (
    PROTOCOL_VERSION,
    make_ping,
    make_session_end,
    make_session_start,
    make_webrtc_offer,
)


class TestComputePerceivedLatencyMs:
    """compute_perceived_latency_ms のテスト."""

    def test_basic_latency(self):
        # トラック開始 1000ms、音声タイムライン 2.0s の結果を 3500ms に受信
        # → 発話時刻は 1000 + 2000 = 3000ms なので遅延は 500ms
        latency = compute_perceived_latency_ms(3500, 1000, 2.0)
        assert latency == 500.0

    def test_zero_latency(self):
        latency = compute_perceived_latency_ms(3000, 1000, 2.0)
        assert latency == 0.0


class TestFormatResultLine:
    """format_result_line のテスト."""

    def _asr_message(self, is_final: bool) -> dict:
        return {
            "type": "asr",
            "segment_id": 12,
            "text": "こんにちは",
            "lang": "ja",
            "is_final": is_final,
            "ts_audio_start": 0.0,
            "ts_audio_end": 2.0,
        }

    def test_contains_text_and_latency(self):
        line = format_result_line(self._asr_message(False), 1234.0, None)
        assert "こんにちは" in line
        assert "asr#12" in line
        assert "latency 1.23s" in line
        assert "rtt" not in line

    def test_final_marker_and_rtt(self):
        line = format_result_line(self._asr_message(True), 1234.0, 15.6)
        assert "asr#12*" in line
        assert "rtt 16ms" in line

    def test_without_latency(self):
        line = format_result_line(self._asr_message(False), None, None)
        assert "latency" not in line


class TestControlMessages:
    """上り制御メッセージ生成のテスト."""

    def test_session_start_fields(self):
        message = make_session_start()
        assert message["type"] == "session_start"
        assert message["protocol_version"] == PROTOCOL_VERSION
        assert isinstance(message["client_ts_ms"], int)

    def test_webrtc_offer_fields(self):
        message = make_webrtc_offer("v=0\r\n")
        assert message["type"] == "webrtc_offer"
        assert message["sdp"] == "v=0\r\n"

    def test_session_end_fields(self):
        assert make_session_end() == {"type": "session_end"}

    def test_ping_fields(self):
        message = make_ping()
        assert message["type"] == "ping"
        assert isinstance(message["client_ts_ms"], int)
