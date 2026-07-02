"""Audio output module for file writing.

This module provides functionality for writing encoded audio data to files.
"""

import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional


class AudioFileWriter(ABC):
    """Abstract base class for audio file writers.

    This class defines the interface for writing audio data to files.
    """

    @abstractmethod
    def write(self, data: bytes) -> None:
        """Write encoded audio data to file.

        Args:
            data: Encoded audio data as bytes.

        Raises:
            IOError: If writing to file fails.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the file and release resources.

        This method should be called when writing is complete.
        """
        pass


class OpusFileWriter(AudioFileWriter):
    """Opus file writer.

    This class writes Opus-encoded audio data to a . opus file.
    Note:  This writes raw Opus packets without OGG container.
    For full OGG Opus compatibility, use OpusOggFileWriter instead.

    Args:
        filepath: Path to the output file.  If None, generates timestamped
            filename.
        output_dir: Directory to save the file. Default is 'output/audio'.

    Examples:
        >>> writer = OpusFileWriter()
        >>> encoded_data = b'\\x00\\x01\\x02'
        >>> writer.write(encoded_data)
        >>> writer.close()
        >>> print(writer.filepath)
        output/audio/recording_20260109_123456.opus
    """

    def __init__(
        self,
        filepath: Optional[str] = None,
        output_dir: str = "output/audio",
    ) -> None:
        """Initialize Opus file writer.

        Args:
            filepath: Path to the output file. If None, auto-generates
                filename.
            output_dir: Directory to save the file.

        Raises:
            IOError: If the output directory cannot be created.
        """
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = str(self._output_dir / f"recording_{timestamp}.opus")
        else:
            filepath = str(self._output_dir / filepath)

        self._filepath = filepath
        self._file = open(self._filepath, "wb")
        self._closed = False

    @property
    def filepath(self) -> str:
        """Get the output file path.

        Returns:
            Absolute path to the output file.
        """
        return os.path.abspath(self._filepath)

    def write(self, data: bytes) -> None:
        """Write Opus-encoded data to file.

        Args:
            data: Opus-encoded audio data as bytes.

        Raises:
            IOError: If file is closed or writing fails.
        """
        if self._closed:
            raise IOError("Cannot write to closed file")

        if not data:
            return

        try:
            self._file.write(data)
        except Exception as e:
            raise IOError(f"Failed to write to file: {e}") from e

    def close(self) -> None:
        """Close the file and release resources.

        After calling this method, no more data can be written.
        """
        if not self._closed:
            self._file.close()
            self._closed = True
            print(f"Opus audio saved to: {self. filepath}")

    def __enter__(self) -> "OpusFileWriter":
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
        """Destructor to ensure file is closed."""
        if not self._closed:
            self.close()
