class CameraFatalError(Exception):
    """Unrecoverable camera failure (timeout, failed read); leads to disconnection."""
