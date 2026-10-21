"""Give hosted desktop CI enough space for real 1320x860 window captures."""

import ctypes
import os
import sys


def _configure_windows_display():
    from ctypes import wintypes

    class DevMode(ctypes.Structure):
        _fields_ = [
            ("dmDeviceName", wintypes.WCHAR * 32),
            ("dmSpecVersion", wintypes.WORD), ("dmDriverVersion", wintypes.WORD),
            ("dmSize", wintypes.WORD), ("dmDriverExtra", wintypes.WORD),
            ("dmFields", wintypes.DWORD), ("displayFields", wintypes.BYTE * 16),
            ("dmColor", ctypes.c_short), ("dmDuplex", ctypes.c_short),
            ("dmYResolution", ctypes.c_short), ("dmTTOption", ctypes.c_short),
            ("dmCollate", ctypes.c_short), ("dmFormName", wintypes.WCHAR * 32),
            ("dmLogPixels", wintypes.WORD), ("dmBitsPerPel", wintypes.DWORD),
            ("dmPelsWidth", wintypes.DWORD), ("dmPelsHeight", wintypes.DWORD),
            ("dmDisplayFlags", wintypes.DWORD), ("dmDisplayFrequency", wintypes.DWORD),
            ("dmICMMethod", wintypes.DWORD), ("dmICMIntent", wintypes.DWORD),
            ("dmMediaType", wintypes.DWORD), ("dmDitherType", wintypes.DWORD),
            ("dmReserved1", wintypes.DWORD), ("dmReserved2", wintypes.DWORD),
            ("dmPanningWidth", wintypes.DWORD), ("dmPanningHeight", wintypes.DWORD),
        ]

    user32 = ctypes.windll.user32
    user32.EnumDisplaySettingsW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(DevMode)]
    user32.EnumDisplaySettingsW.restype = wintypes.BOOL
    user32.ChangeDisplaySettingsW.argtypes = [ctypes.POINTER(DevMode), wintypes.DWORD]
    user32.ChangeDisplaySettingsW.restype = wintypes.LONG
    candidates = []
    index = 0
    while True:
        mode = DevMode()
        mode.dmSize = ctypes.sizeof(mode)
        if not user32.EnumDisplaySettingsW(None, index, ctypes.byref(mode)):
            break
        if mode.dmPelsWidth >= 1600 and mode.dmPelsHeight >= 1000 and mode.dmBitsPerPel == 32:
            candidates.append(mode)
        index += 1
    if not candidates:
        raise RuntimeError("The CI desktop needs a display mode of at least 1600x1000")
    mode = min(candidates, key=lambda m: m.dmPelsWidth * m.dmPelsHeight)
    # Flags=0 changes only this ephemeral desktop session, not the registry.
    result = user32.ChangeDisplaySettingsW(ctypes.byref(mode), 0)
    if result:
        raise RuntimeError(f"Cannot set CI display mode: DISP_CHANGE {result}")
    print(f"Native UI desktop: {mode.dmPelsWidth}x{mode.dmPelsHeight}")


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Display configuration is restricted to GitHub Actions")
    if sys.platform == "win32":
        _configure_windows_display()
    elif sys.platform == "darwin":
        graphics = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        foundation = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        graphics.CGMainDisplayID.restype = ctypes.c_uint32
        graphics.CGDisplayCopyAllDisplayModes.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        graphics.CGDisplayCopyAllDisplayModes.restype = ctypes.c_void_p
        for name in ("CGDisplayModeGetWidth", "CGDisplayModeGetHeight"):
            function = getattr(graphics, name)
            function.argtypes = [ctypes.c_void_p]
            function.restype = ctypes.c_size_t
        graphics.CGBeginDisplayConfiguration.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        graphics.CGBeginDisplayConfiguration.restype = ctypes.c_int32
        graphics.CGConfigureDisplayWithDisplayMode.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
        graphics.CGConfigureDisplayWithDisplayMode.restype = ctypes.c_int32
        graphics.CGCompleteDisplayConfiguration.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        graphics.CGCompleteDisplayConfiguration.restype = ctypes.c_int32
        graphics.CGCancelDisplayConfiguration.argtypes = [ctypes.c_void_p]
        foundation.CFArrayGetCount.argtypes = [ctypes.c_void_p]
        foundation.CFArrayGetCount.restype = ctypes.c_long
        foundation.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
        foundation.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
        foundation.CFRelease.argtypes = [ctypes.c_void_p]
        display = graphics.CGMainDisplayID()
        modes = graphics.CGDisplayCopyAllDisplayModes(display, None)
        if not modes:
            raise RuntimeError("No desktop display modes available")
        try:
            candidates = []
            for index in range(foundation.CFArrayGetCount(modes)):
                mode = foundation.CFArrayGetValueAtIndex(modes, index)
                width = graphics.CGDisplayModeGetWidth(mode)
                height = graphics.CGDisplayModeGetHeight(mode)
                if width >= 1600 and height >= 1000:
                    candidates.append((width * height, width, height, mode))
            if not candidates:
                raise RuntimeError("The CI desktop needs a display mode of at least 1600x1000")
            _, width, height, mode = min(candidates)
            configuration = ctypes.c_void_p()
            result = graphics.CGBeginDisplayConfiguration(ctypes.byref(configuration))
            if result:
                raise RuntimeError(f"Cannot begin CI display configuration: CGError {result}")
            result = graphics.CGConfigureDisplayWithDisplayMode(configuration, display, mode, None)
            if result:
                graphics.CGCancelDisplayConfiguration(configuration)
                raise RuntimeError(f"Cannot configure CI display mode: CGError {result}")
            # kCGConfigureForSession: keep the ephemeral runner desktop large
            # when the configuring process exits or another test app activates.
            # Do not use kCGConfigurePermanently.
            result = graphics.CGCompleteDisplayConfiguration(configuration, 1)
            if result:
                raise RuntimeError(f"Cannot set CI display mode: CGError {result}")
            print(f"Native UI desktop: {width}x{height}")
        finally:
            foundation.CFRelease(modes)
    else:
        raise RuntimeError("Native desktop UI CI supports Windows and macOS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
