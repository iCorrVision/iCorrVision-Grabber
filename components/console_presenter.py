import logging
from PySide6.QtCore import QObject, Signal

from UI.console_view import ConsoleLogView

from UI.utils.theme import THEME

_LEVEL_COLORS = {
    logging.DEBUG: THEME.log.debug,
    logging.INFO: THEME.log.info,
    logging.WARNING: THEME.log.warning,
    logging.ERROR: THEME.log.error,
    logging.CRITICAL: THEME.log.critical,
}


class _LogSignalEmitter(QObject):
    """Carries log records as a Qt signal.

    Kept separate from `_QtLoggingHandler` because `QObject` and
    `logging.Handler` have different metaclasses, which rules out combining
    them through multiple inheritance.
    """

    log_record = Signal(logging.LogRecord)


class _QtLoggingHandler(logging.Handler):
    """Logging handler that passes each record to `callback`.

    With a signal's `emit` as the callback, records logged on any thread are
    delivered to the console on the main (GUI) thread.
    """

    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        """Forward a record that passed the level filter (called on any thread)."""
        self._callback(record)


class ConsolePresenter:
    """Shows the application log in the console view.

    A handler on the root logger captures every module's messages without
    per-module set-up; each record is shown as one line with its time and level,
    coloured by level. The console's level selector filters what is shown.
    """

    def __init__(self, view: ConsoleLogView) -> None:
        self._view = view

        self._emitter = _LogSignalEmitter()
        self._emitter.log_record.connect(self._on_record)

        self._handler = _QtLoggingHandler(self._emitter.log_record.emit)
        self._handler.setLevel(logging.DEBUG)

        root = logging.getLogger()
        root.addHandler(self._handler)
        root.setLevel(logging.DEBUG)

        self._view.log_level_signal.connect(self._on_log_level_changed)

    def _on_record(self, record: logging.LogRecord) -> None:
        """Format a record as a coloured HTML line (runs on the main thread)."""
        color = _LEVEL_COLORS.get(record.levelno, "#c5c9d6")
        time = logging.Formatter().formatTime(record, datefmt="%H:%M:%S")
        self._view.append_message(
            f'<span style="color:{color}">[{time}] [{record.levelname}] {record.getMessage()}</span>'
        )

    def _on_log_level_changed(self, level_name: str) -> None:
        """Show only records at `level_name` or above (INFO if unknown)."""
        level = getattr(logging, level_name, logging.INFO)
        self._handler.setLevel(level)
        logging.debug(f"Console log level changed to {level_name}")
