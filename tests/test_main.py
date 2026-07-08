"""main.build_parser の引数解釈のテスト."""

from main import build_parser


class TestBuildParser:
    """build_parser のテスト."""

    def test_defaults(self):
        args = build_parser().parse_args([])
        assert args.connect is None
        assert args.waveform is False
        assert args.waveform_port == 50000
        assert args.save_audio is False
        assert args.output_filename is None
        assert args.opus_bitrate == 64

    def test_connect_url(self):
        args = build_parser().parse_args(["--connect", "ws://localhost:8765/ws"])
        assert args.connect == "ws://localhost:8765/ws"

    def test_waveform_options(self):
        args = build_parser().parse_args(["--waveform", "--waveform-port", "50001"])
        assert args.waveform is True
        assert args.waveform_port == 50001
