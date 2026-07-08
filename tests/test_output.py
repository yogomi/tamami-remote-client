"""output.console のテスト."""

from output.console import LINE_MIN_WIDTH, ConsoleOutput, format_result_line


def _asr_message(is_final: bool, text: str = "こんにちは", segment_id: int = 12) -> dict:
    return {
        "type": "asr",
        "segment_id": segment_id,
        "text": text,
        "lang": "ja",
        "is_final": is_final,
        "ts_audio_start": 0.0,
        "ts_audio_end": 2.0,
    }


class TestFormatResultLine:
    """format_result_line のテスト."""

    def test_contains_text_and_latency(self):
        line = format_result_line(_asr_message(False), 1234.0, None)
        assert "こんにちは" in line
        assert "asr#12" in line
        assert "latency 1.23s" in line
        assert "rtt" not in line

    def test_final_marker_and_rtt(self):
        line = format_result_line(_asr_message(True), 1234.0, 15.6)
        assert "asr#12*" in line
        assert "rtt 16ms" in line

    def test_without_latency(self):
        line = format_result_line(_asr_message(False), None, None)
        assert "latency" not in line


class TestConsoleOutput:
    """ConsoleOutput.handle のテスト."""

    def test_interim_result_uses_carriage_return_without_newline(self, capsys):
        output = ConsoleOutput()
        output.handle(_asr_message(False), None, None)
        captured = capsys.readouterr()
        assert captured.out.startswith("\r")
        assert not captured.out.endswith("\n")

    def test_final_result_ends_with_newline(self, capsys):
        output = ConsoleOutput()
        output.handle(_asr_message(True), None, None)
        captured = capsys.readouterr()
        assert captured.out.startswith("\r")
        assert captured.out.endswith("\n")

    def test_short_line_after_long_line_erases_residual(self, capsys):
        output = ConsoleOutput()
        long_text = "あ" * (LINE_MIN_WIDTH + 20)
        output.handle(_asr_message(True, text=long_text), None, None)
        first = capsys.readouterr()
        # 前行の表示幅（改行前の末尾の空白を除いた長さ）を確認しておく
        first_width = len(first.out.strip("\r\n"))

        output.handle(_asr_message(False, text="短い"), None, None)
        second = capsys.readouterr()
        second_line = second.out.lstrip("\r")
        assert len(second_line) == first_width
