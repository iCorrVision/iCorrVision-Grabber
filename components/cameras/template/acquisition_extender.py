from components.enumeration_model import CameraDescriptor


class AcquisitionExtension:
    """Base class of a camera backend, loaded only if its SDK imports.

    Registers its discovery function (`enumerate`) with the shared enumeration
    model; subclasses also register their presenter class. Extensions read the
    acquisition presenter's camera slots but never replace them.
    """

    def __init__(self, cameras: dict, presenter_registry: dict, enumeration) -> None:
        self._cameras = cameras
        self._presenter_registry = presenter_registry
        self._enumeration = enumeration
        self._enumeration.register_backend(self.enumerate)

    def enumerate(self) -> list[CameraDescriptor]:
        """Return the devices of this backend (to be overridden)."""
        return []
