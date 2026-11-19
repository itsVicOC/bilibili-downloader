# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from bilibili_downloader import __version__

assets = Path('bilibili_downloader/gui/assets')
if sys.platform == 'darwin':
    app_icon = assets / 'app_icon.icns'
elif sys.platform == 'win32':
    app_icon = assets / 'app_icon.ico'
else:
    app_icon = assets / 'app_icon.png'

datas = [(str(assets), assets.as_posix())]
excludes = ['numpy']
if sys.platform in ('darwin', 'win32'):
    # The .app gets its Finder icon from BUNDLE. The Windows tray loads the ICO at runtime.
    unused_assets = {
        'alien.png', 'app_icon.icns', 'app_icon_source.png', 'artist_palette.png',
        'chevron.svg', 'clapper.png', 'nebula.jpg', 'sparkle.png',
    }
    if sys.platform == 'darwin':
        unused_assets.add('app_icon.ico')
    unused_paths = {assets / name for name in unused_assets}
    datas = [
        (str(path), path.parent.as_posix())
        for path in sorted(assets.rglob('*'))
        if path.is_file() and path not in unused_paths
    ]
    # HTTPX's own CLI is separate from BiliFlow's CLI and pulls in Pygments.
    excludes.append('httpx._main')

a = Analysis(
    ['bilibili_downloader/__main__.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=['packaging_hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
    icon=str(app_icon),
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
        icon=str(app_icon),
        bundle_identifier='com.itsvicoc.bilibili-downloader',
        info_plist={
            'CFBundleDisplayName': 'BiliFlow',
            'CFBundleName': 'BiliFlow',
            'CFBundleShortVersionString': __version__,
            'CFBundleVersion': __version__,
            'NSHighResolutionCapable': True,
        },
    )
