# A small independent executable, without Qt or third-party dependencies.
import os
from pathlib import Path

project_root = str(Path(SPECPATH))
a = Analysis(
    ['scripts/update_helper.py'], pathex=[project_root], binaries=[], datas=[],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['PySide6', 'httpx', 'pydantic', 'keyring', 'PIL', 'numpy', 'packaging'],
    noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name='biliflow-updater',
    debug=False, strip=False, upx=False, console=False,
    codesign_identity=os.environ.get('MACOS_UPDATER_SIGNING_IDENTITY') or None,
)
