import logging
from typing import Callable


from dataclasses import dataclass, field


class CameraBackendType:
    """Camera backends, registered by the backends themselves when they load.

    `register("OPENCV")` creates the member `CameraBackendType.OPENCV`; a backend
    whose SDK is missing never registers.
    """

    _registry: dict[str, "CameraBackendType"] = {}

    def __init__(self, name: str):
        self._name = name

    @classmethod
    def register(cls, name: str) -> "CameraBackendType":
        """Return the member called `name`, creating it on first registration."""
        if name not in cls._registry:
            instance = cls(name)
            cls._registry[name] = instance
            setattr(cls, name, instance)  # enables CameraBackendType.NAME
        return cls._registry[name]

    @property
    def name(self) -> str:
        return self._name

    def __repr__(self) -> str:
        return f"CameraBackendType.{self._name}"


@dataclass(frozen=True)
class CameraDescriptor:
    """Backend-independent, immutable description of one camera device.

    `backend_id` is the backend's own identifier (OpenCV device index, Vimba
    camera ID); `id` is derived as "<backend>:<backend_id>", so a device keeps
    its identifier across discoveries.
    """

    backend: CameraBackendType
    backend_id: int | str
    display_name: str
    id: str = field(init=False)

    # A frozen dataclass forbids ordinary assignment, hence object.__setattr__.
    def __post_init__(self):
        object.__setattr__(self, "id", f"{self.backend}:{self.backend_id}")


class CameraRegistry:
    """Set of devices currently in use, so that no device is opened twice."""

    def __init__(self):
        self._claimed: set[CameraDescriptor] = set()
        logging.debug("Initialised CameraRegistry with empty claimed set")

    def claim(self, descriptor: CameraDescriptor) -> bool:
        """Claim the device; False if it is already claimed."""
        if descriptor in self._claimed:
            logging.warning(f"Claim failed for camera {descriptor.id}: already in use")
            return False
        self._claimed.add(descriptor)
        logging.debug(f"Claimed camera {descriptor.id} ({descriptor.display_name})")
        return True

    def release(self, descriptor: CameraDescriptor) -> None:
        """Release the device (no effect if it was not claimed)."""
        was_claimed = descriptor in self._claimed
        self._claimed.discard(descriptor)
        if was_claimed:
            logging.debug(
                f"Released camera {descriptor.id} ({descriptor.display_name})"
            )
        else:
            logging.debug(
                f"Attempted to release camera {descriptor.id} that was not claimed"
            )

    def is_claimed(self, descriptor: CameraDescriptor) -> bool:
        """Whether the device is currently claimed."""
        claimed = descriptor in self._claimed
        logging.debug(f"Checked claim status for camera {descriptor.id}: {claimed}")
        return claimed


class EnumerationModel:
    """Discovery of available devices across all loaded backends, minus claimed ones."""

    def __init__(self, registry: CameraRegistry):
        self._registry: CameraRegistry = registry
        logging.debug("Initialised EnumerationModel")
        self._backend_enumerators: list[Callable[[], list[CameraDescriptor]]] = []

    def register_backend(self, fn: Callable[[], list[CameraDescriptor]]) -> None:
        """Add a backend's discovery function (called by `AcquisitionExtension`)."""
        self._backend_enumerators.append(fn)

    def available_cameras(self) -> list[CameraDescriptor]:
        """Run every backend's discovery and return the unclaimed devices."""
        logging.info("Starting camera enumeration")
        result: list[CameraDescriptor] = []
        for enumerator in self._backend_enumerators:
            result += enumerator()
        filtered = [d for d in result if not self._registry.is_claimed(d)]

        logging.info(
            f"Camera enumeration complete: {len(filtered)} available, {len(result) - len(filtered)} claimed"
        )
        return filtered
