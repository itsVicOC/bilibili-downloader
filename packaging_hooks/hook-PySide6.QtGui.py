"""Keep the standard QtGui hook, except for two unused desktop plugins."""

import sys
from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)

if sys.platform in ("darwin", "win32"):
    # Cover images are validated by Pillow, whose PDF plugin only writes PDFs.
    # The frozen bundle has no QML keyboard resources. Native IMEs are provided
    # by the platform integration and do not depend on Qt Virtual Keyboard.
    unused_plugins = {
        ("imageformats", "qpdf.dll"),
        ("imageformats", "libqpdf.dylib"),
        ("platforminputcontexts", "qtvirtualkeyboardplugin.dll"),
        ("platforminputcontexts", "libqtvirtualkeyboardplugin.dylib"),
    }
    binaries = [
        (source, destination)
        for source, destination in binaries
        if (Path(destination).name, Path(source).name) not in unused_plugins
    ]
