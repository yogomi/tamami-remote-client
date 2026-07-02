from typing import Optional
from types import FrameType
import asyncio
import signal
import argparse

from visualize_waveform_web import WaveformVisualizerWeb

from audio import MicrophoneInput
from audio.encoder import OpusFileEncoder


def main():
    # Setup signal handler for graceful shutdown
    running = True

    def signal_handler(sig: int, frame: Optional[FrameType]) -> None:
        nonlocal running
        print("\nShutting down...")
        running = False

    signal.signal(signal.SIGINT, signal_handler)

    parser = argparse.ArgumentParser()
    parser = argparse.ArgumentParser(description="tamami-remote-client (with waveform)")
    parser.add_argument(
        "--connect",
        type=str,
        default=None,
        metavar="URL",
        help=(
            "Stream microphone audio to tamami server via WebRTC "
            "(e.g. ws://localhost:8765/ws). "
            "Other options are ignored in this mode."
        ),
    )
    parser.add_argument("--waveform", action="store_true")
    parser.add_argument("--waveform-port", type=int, default=50000)
    parser.add_argument(
        "--save-audio", action="store_true", help="Save audio input to Opus file"
    )
    parser.add_argument(
        "--output-filename",
        type=str,
        default=None,
        help="Output filename for Opus file",
    )
    parser.add_argument(
        "--opus-bitrate",
        type=int,
        default=64,
        help="Opus bitrate in kbps (default: 64)",
    )
    args = parser.parse_args()

    # Streaming mode: send microphone audio to tamami server via WebRTC
    if args.connect:
        from network.client import run_client

        asyncio.run(run_client(args.connect))
        return

    visualizer = None
    if args.waveform:
        visualizer = WaveformVisualizerWeb(
            sample_rate=16000,
            channels=1,
            window_seconds=2,
            decimate=4,
            port=args.waveform_port,
        )
        visualizer.start()

    # Initialize Opus encoder if requested
    opus_encoder = None
    if args.save_audio:
        opus_encoder = OpusFileEncoder(
            filepath=args.output_filename,
            sample_rate=16000,
            channels=1,
            bitrate=args.opus_bitrate,
        )
        print(f"Opus recording enabled.  Output:  {opus_encoder.filepath}")

    # # Example sounddevice callback integration
    # def audio_callback(indata, frames, time, status) -> None:
    #     # indata: numpy array shape (frames, channels)
    #     if status:
    #         # handle overflow / error status if needed
    #         pass
    #     if visualizer is not None:
    #         # copy to avoid referencing memory that sounddevice reuses
    #         visualizer.add_frames(indata.copy())
    #
    #     # ここで既存処理（エンコード -> 送信 等）を続ける

    mic = MicrophoneInput()
    try:
        while running:
            chunk = mic.read_chunk(1024)
            if visualizer is not None:
                visualizer.add_frames(chunk.reshape(-1, 1))
            print(f"Read audio chunk of shape: {chunk.shape}")
            print(f"Sample rate: {mic.get_sample_rate()} Hz")

            # Encode and save to Opus if enabled
            if opus_encoder is not None:
                opus_encoder.encode(chunk)

    finally:
        mic.close()
        if opus_encoder is not None:
            opus_encoder.close()


if __name__ == "__main__":
    main()
