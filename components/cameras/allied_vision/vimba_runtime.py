"""Availability and lifetime of the Vimba X SDK (Allied Vision cameras).

VIMBA_AVAILABLE is set when VmbPy imports; without it the application runs
with OpenCV cameras only. VIMBA_FUNCTIONAL is set once the system started.
"""

import logging

VIMBA_AVAILABLE: bool = False
VIMBA_FUNCTIONAL: bool = False

try:
    from vmbpy import *

    VIMBA_AVAILABLE = True
    logging.debug("Vimba SDK (vmbpy) import successful")
except (ImportError, ModuleNotFoundError):
    logging.warning(
        "Vimba SDK (vmbpy) not found. Allied Vision camera support disabled."
    )


_vmb = None


def get_vmb():
    """Return the running Vimba system, starting it on the first call.

    Returns None if VmbPy is unavailable or no transport layer could be loaded.
    The system stays open until `shutdown_vmb`.
    """
    global _vmb, VIMBA_FUNCTIONAL
    if not VIMBA_AVAILABLE:
        return None
    if _vmb is not None:
        return _vmb
    try:
        vmb = VmbSystem.get_instance()
        vmb.__enter__()
        _vmb = vmb
        VIMBA_FUNCTIONAL = True
        logging.info("Vimba system initialised successfully")
        return _vmb
    except VmbTransportLayerError as e:
        logging.error(f"Failed to initialise Vimba system: {e}")
        return None


def shutdown_vmb() -> None:
    """Shut down the Vimba system started by `get_vmb`, if any.

    `get_vmb` enters the system's context without a `with` block, so the
    matching exit must be called explicitly before the process ends; otherwise
    the SDK aborts the process at interpreter shutdown. Close all cameras first.
    """
    global _vmb, VIMBA_FUNCTIONAL
    if _vmb is None:
        return
    try:
        _vmb.__exit__(None, None, None)
        logging.info("Vimba system shut down")
    except Exception as e:
        logging.error(f"Failed to shut down Vimba system: {e}")
    finally:
        _vmb = None
        VIMBA_FUNCTIONAL = False
