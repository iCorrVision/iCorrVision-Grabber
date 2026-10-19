from abc import ABC, abstractmethod
import numpy as np


class CameraModel(ABC):
    """Camera interface every backend implements: open, read one frame, close."""

    @abstractmethod
    def open(self) -> None:
        """Open the device and configure it for acquisition."""
        ...

    @abstractmethod
    def read_frame(self) -> np.ndarray | None:
        """Return one frame, or None after a recoverable failure (incomplete frame).

        An unrecoverable failure raises `CameraFatalError`.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the device."""
        ...
