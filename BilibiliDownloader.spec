# -*- mode: python ; coding: utf-8 -*-

import sys

from PyInstaller.utils.hooks import collect_submodules


a = Analysis(
    ['bilibili_downloader/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=collect_submodules('keyring.backends'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BilibiliDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BilibiliDownloader',
)

if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='BilibiliDownloader.app',
        icon=None,
        bundle_identifier='com.itsvicoc.bilibili-downloader',
    )
