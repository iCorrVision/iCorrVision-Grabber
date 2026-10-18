import logging

from PySide6.QtWidgets import QApplication, QSplashScreen, QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QColor

from UI.main_view import MainView
from components.cameras.opencv.opencv_acquisition_extension import (
    OpencvAquisitionExtension,
)
from components.cameras.opencv.opencv_view import OpencvView
from components.cameras.template.acquisition_extender import AcquisitionExtension
from core.main_presenter import MainPresenter

import components.cameras.allied_vision.vimba_runtime as vimba_runtime


from UI.utils.theme import THEME


class AppLoader:
    """Builds the application behind a splash screen.

    The slow steps run once the event loop is running, so the splash screen is
    drawn first. The Allied Vision backend is added only if VmbPy imported.
    """

    def __init__(self, app: QApplication) -> None:
        self._app = app
        self._splash = self._build_splash()
        self._view: MainView | None = None
        self._presenter: MainPresenter | None = None
        self._update_splash("Initialising application")

    def start(self) -> None:
        """Show the splash screen and schedule the start-up for the event loop."""
        self._splash.show()
        QTimer.singleShot(0, self._startup)  # runs once the event loop has started

    def _startup(self) -> None:
        """Start the Vimba system, build views and presenters, and add the backends.

        Starting the Vimba system loads its transport layers, which takes a
        noticeable time; doing it here keeps that delay behind the splash screen.
        """
        self._update_splash("Initialising Vimba runtime...")
        vimba_runtime.get_vmb()

        self._update_splash("Building interface...")
        self._view = MainView()
        self._presenter = MainPresenter(self._view)
        self._app.aboutToQuit.connect(self._shutdown)

        if vimba_runtime.VIMBA_AVAILABLE:
            from components.cameras.allied_vision.allied_view import AlliedOptionsView
            from components.cameras.allied_vision.vimba_acquisition_extension import (
                VimbaAcquisitionExtension,
            )

            self._add_camera_type(
                "Allied Vision", AlliedOptionsView, VimbaAcquisitionExtension
            )

        self._add_camera_type("Generic", OpencvView, OpencvAquisitionExtension)

        self._splash.finish(self._view)
        self._view.show()

    def _shutdown(self) -> None:
        """Release the cameras (writing queued frames), then shut down the Vimba system.

        The Vimba system may only be shut down once no camera is open.
        """
        logging.info("Shutting down")
        if self._presenter is not None:
            self._presenter.shutdown()
        vimba_runtime.shutdown_vmb()

    def _update_splash(self, message: str) -> None:
        """Show `message` on the splash screen immediately."""
        self._splash.showMessage(
            message,
            Qt.AlignmentFlag.AlignCenter,
            QColor(THEME.splash.text),
        )
        self._app.processEvents()  # repaint now; the next step blocks the event loop

    @staticmethod
    def _build_splash() -> QSplashScreen:
        """Plain splash screen in the theme's colours."""
        pixmap = QPixmap(400, 80)
        pixmap.fill(QColor(THEME.splash.background))
        return QSplashScreen(pixmap)

    def _add_camera_type(
        self, panel_name: str, panel_ui: type[QWidget], extension: AcquisitionExtension
    ) -> None:
        """Add a backend: settings panel to the view, extension to the presenter."""
        self._view.append_camera_panel(panel_name, panel_ui)
        self._presenter.append_camera_extension(
            self._view.get_mode_view(panel_name), extension
        )
