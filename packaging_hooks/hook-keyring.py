"""PyInstaller hook that includes only keyring backends for the target OS."""

import sys

from PyInstaller.utils.hooks import copy_metadata

hiddenimports = ["keyring.backends.fail"]
if sys.platform == "darwin":
    hiddenimports.append("keyring.backends.macOS")
elif sys.platform == "win32":
    hiddenimports.append("keyring.backends.Windows")
else:
    hiddenimports.extend([
        "keyring.backends.SecretService",
        "keyring.backends.libsecret",
    ])

datas = copy_metadata("keyring")
