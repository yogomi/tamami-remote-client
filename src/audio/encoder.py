"""Audio encoding module for Opus format.

This module provides encoding functionality for converting raw PCM audio
to Opus compressed format using ffmpeg as a subprocess.
"""

import subprocess
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional
import os

import numpy as np


class AudioEncoder(ABC):
    """Abstract base class for audio encoders.

    This class defines the interface for encoding audio data.
    """

    @abstractmethod
    def encode(self, pcm_data: np.ndarray) -> None:
        """Encode PCM audio data.

        Args:
            pcm_data:  PCM audio data as numpy array (float32, -1.0 to 1.0).

        Raises:
            ValueError: If the input data format is invalid.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the encoder and flush remaining data.

        This method should be called when encoding is complete.
        """
        pass

    @property
    @abstractmethod
    def filepath(self) -> str:
        """Get the output file path.

        Returns:
            Absolute path to the output file.
        """
        pass


class OpusFileEncoder(AudioEncoder):
    """Opus file encoder using ffmpeg subprocess.

    This class encodes PCM audio data to Ogg Opus file format by piping
    data to ffmpeg via stdin.

    Args:
        filepath: Path to the output file.  If None, generates timestamped
            filename.
        output_dir: Directory to save the file. Default is 'output/audio'.
        sample_rate: Sample rate in Hz (8000, 12000, 16000, 24000, or 48000).
        channels: Number of audio channels (1 for mono, 2 for stereo).
        bitrate: Opus bitrate in kbps. Default is 64.

    Attributes:
        SAMPLE_RATE: Default sample rate (16000 Hz).
        CHANNELS: Default channel count (1 for mono).
        BITRATE: Default bitrate (64 kbps).

    Examples:
        >>> encoder = OpusFileEncoder(sample_rate=16000, channels=1)
        >>> pcm_audio = np.random.randn(1024).astype(np.float32)
        >>> encoder.encode(pcm_audio)
        >>> encoder.close()
        Opus audio saved to:  /path/to/output/audio/recording_20260109_123456.opus
    """

    SAMPLE_RATE = 16000
    CHANNELS = 1
    BITRATE = 64

    def __init__(
        self,
        filepath: Optional[str] = None,
        output_dir: str = "output/audio",
        sample_rate: int = 16000,
        channels: int = 1,
        bitrate: int = 64,
    ) -> None:
        """Initialize Opus file encoder.

        Args:
            filepath: Path to the output file. If None, auto-generates
                filename.
            output_dir: Directory to save the file.
            sample_rate: Sample rate in Hz.
            channels: Number of audio channels.
            bitrate: Opus bitrate in kbps.

        Raises:
            ValueError:  If parameters are invalid.
            IOError: If the output directory cannot be created or ffmpeg
                cannot be started.
        """
        if sample_rate not in [8000, 12000, 16000, 24000, 48000]:
            raise ValueError(
                f"Invalid sample rate {sample_rate}. "
                "Must be 8000, 12000, 16000, 24000, or 48000."
            )
        if channels not in [1, 2]:
            raise ValueError(f"Invalid channels {channels}. Must be 1 or 2.")
        if bitrate <= 0:
            raise ValueError(f"Invalid bitrate {bitrate}. Must be positive.")

        self._sample_rate = sample_rate
        self._channels = channels
        self._bitrate = bitrate
        self._closed = False

        # Setup output path
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = str(self._output_dir / f"recording_{timestamp}.opus")
        else:
            filepath = str(self._output_dir / filepath)

        self._filepath = filepath

        # Start ffmpeg subprocess
        self._start_ffmpeg()

    def _start_ffmpeg(self) -> None:
        """Start ffmpeg subprocess for Opus encoding.

        Raises:
            IOError: If ffmpeg cannot be started.
        """
        try:
            self._process = subprocess.Popen(
                [
                    "ffmpeg",
                    "-y",  # Overwrite output file
                    "-f",
                    "s16le",  # Input format:  signed 16-bit PCM
                    "-ar",
                    str(self._sample_rate),  # Sample rate
                    "-ac",
                    str(self._channels),  # Number of channels
                    "-i",
                    "-",  # Read from stdin
                    "-c:a",
                    "libopus",  # Opus codec
                    "-b:a",
                    f"{self._bitrate}k",  # Bitrate
                    str(self._filepath),
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
        except FileNotFoundError as e:
            raise IOError("ffmpeg not found. Please install ffmpeg.") from e
        except Exception as e:
            raise IOError(f"Failed to start ffmpeg: {e}") from e

    @property
    def filepath(self) -> str:
        """Get the output file path.

        Returns:
            Absolute path to the output file.
        """
        return os.path.abspath(self._filepath)

    def encode(self, pcm_data: np.ndarray) -> None:
        """Encode PCM audio data and write to Opus file via ffmpeg.

        Args:
            pcm_data: PCM audio data as numpy array (float32, -1.0 to 1.0).

        Raises:
            ValueError: If the input data format is invalid.
            IOError: If the encoder is closed or writing fails.
        """
        if self._closed:
            raise IOError("Cannot encode with closed encoder")

        if pcm_data.dtype != np.float32:
            raise ValueError(f"Invalid dtype {pcm_data.dtype}. Must be float32.")

        # Convert float32 [-1.0, 1.0] to int16 [-32768, 32767]
        pcm_int16 = (np.clip(pcm_data, -1.0, 1.0) * 32767).astype(np.int16)

        # Write to ffmpeg stdin
        try:
            if self._process.stdin is not None:
                self._process.stdin.write(pcm_int16.tobytes())
        except BrokenPipeError as e:
            raise IOError("ffmpeg process terminated unexpectedly") from e
        except Exception as e:
            raise IOError(f"Failed to encode audio: {e}") from e

    def close(self) -> None:
        """Close the encoder and flush remaining data.

        This method closes stdin to signal ffmpeg to finalize the output,
        then waits for the process to complete.
        """
        if not self._closed:
            try:
                if self._process.stdin is not None:
                    self._process.stdin.close()
                self._process.wait(timeout=5)
                self._closed = True
                print(f"Opus audio saved to: {self. filepath}")
            except subprocess.TimeoutExpired:
                print("Warning: ffmpeg did not finish in time, terminating")
                self._process.terminate()
                self._process.wait()
                self._closed = True
            except Exception as e:
                print(f"Warning: Error closing encoder: {e}")
                if self._process.poll() is None:
                    self._process.terminate()
                self._closed = True

    def __enter__(self) -> "OpusFileEncoder":
        """Context manager entry.

        Returns:
            Self reference for context manager.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Exception traceback if an exception occurred.
        """
        self.close()

    def __del__(self) -> None:
        """Destructor to ensure encoder is closed."""
        if hasattr(self, "_closed") and not self._closed:
            self.close()
