{
  pkgs,
  lib,
  ...
}: {
  packages = with pkgs; [
    # --- Build and development tools ---
    cmake
    pkg-config
    gcc
    git
    just
    gitleaks
    ruff

    # --- Runtime libs needed for PySide6/Qt at runtime ---
    libGL
    libGLU
    libusb1
    glib
    dbus
    fontconfig
    libxkbcommon
    zlib
    stdenv.cc.cc.lib
    systemd
    freetype
    zstd
    wayland

    # X11 libs (needed even under Wayland for XWayland/fallback apps)
    xorg.libX11
    xorg.libXext
    xorg.libXrender
    xorg.libXtst
    xorg.libXi
    xorg.libxcb
    xorg.xcbutil
    xorg.xcbutilimage
    xorg.xcbutilkeysyms
    xorg.xcbutilwm
    xorg.xcbutilrenderutil
    xorg.xcbutilcursor
  ];

  languages.python = {
    enable = true;
    package = pkgs.python312; # the version the application was tested with (README)

    venv = {
      enable = true;
      requirements = ./requirements.txt;
    };
  };

  env = {
    QT_QPA_PLATFORM = "wayland;xcb";

    PKG_CONFIG_PATH = lib.makeSearchPathOutput "dev" "lib/pkgconfig" (with pkgs; [
      zlib
      glib
    ]);
  };

  # `grabber` starts the application with the Qt libraries of the PySide6 wheel on the
  # library path, which NixOS does not provide in the usual system locations.
  scripts.grabber.exec = ''
    PYSIDE6_DIR="$(python -c 'import PySide6, os; print(os.path.dirname(PySide6.__file__))')"
    export LD_LIBRARY_PATH="$PYSIDE6_DIR/Qt/lib:${lib.makeLibraryPath (with pkgs; [
      libGL
      libGLU
      freetype
      zstd
      glib
      dbus
      zlib
      stdenv.cc.cc.lib
      fontconfig
      libxkbcommon
      wayland
      xorg.libX11
      xorg.libXext
      xorg.libXrender
      xorg.libXtst
      xorg.libXi
      xorg.libxcb
      xorg.xcbutil
      xorg.xcbutilimage
      xorg.xcbutilkeysyms
      xorg.xcbutilwm
      xorg.xcbutilrenderutil
      xorg.xcbutilcursor
    ])}"
    export QT_PLUGIN_PATH="$PYSIDE6_DIR/Qt/plugins"
    python3 -m core.main
  '';

  enterShell = ''
    source $DEVENV_ROOT/.devenv/state/venv/bin/activate
    echo "Python venv ready"
    echo "  Python  : $(python --version)"
    echo "  Venv    : $VIRTUAL_ENV"
  '';
}
