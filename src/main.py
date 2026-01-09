from typing import Optional
from types import FrameType
import signal
import argparse
import threading

from visualize_waveform_web import WaveformVisualizerWeb

from audio import MicrophoneInput

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
    parser.add_argument("--waveform", action="store_true")
    parser.add_argument("--waveform-port", type=int, default=50000)
    args = parser.parse_args()

    visualizer = None
    if args.waveform:
        visualizer = WaveformVisualizerWeb(
            sample_rate=16000,
            channels=1,
            window_seconds=2,
            decimate=4,
            port=args.waveform_port
        )
        visualizer.start()

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
    finally:
        mic.close()

if __name__ == "__main__":
    main()
