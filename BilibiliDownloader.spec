# -*- mode: python ; coding: utf-8 -*-

import sys

from bilibili_downloader import __version__

if sys.platform == 'darwin':
    app_icon = 'bilibili_downloader/gui/assets/app_icon.icns'
elif sys.platform == 'win32':
    app_icon = 'bilibili_downloader/gui/assets/app_icon.ico'
else:
    app_icon = 'bilibili_downloader/gui/assets/app_icon.png'

a = Analysis(
    ['bilibili_downloader/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[('bilibili_downloader/gui/assets', 'bilibili_downloader/gui/assets')],
    hiddenimports=[],
    hookspath=['packaging_hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy'],
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
    icon=app_icon,
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
        icon=app_icon,
        bundle_identifier='com.itsvicoc.bilibili-downloader',
        info_plist={
            'CFBundleDisplayName': 'BiliFlow',
            'CFBundleShortVersionString': __version__,
            'CFBundleVersion': __version__,
            'NSHighResolutionCapable': True,
        },
    )
