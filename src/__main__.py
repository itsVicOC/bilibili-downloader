"""Entry point for the Bilibili downloader application."""

import logging
import sys

logger = logging.getLogger(__name__)


def main():
    """Main entry point. Supports both CLI and GUI modes."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s: %(message)s",
    )

    args = sys.argv[1:]

    if args and args[0] == "test":
        # CLI test mode
        _cli_test(args[1:])
        return

    if args and args[0] == "download":
        # CLI download mode
        _cli_download(args[1:])
        return

    # Default: launch GUI
    _launch_gui()


def _cli_test(args):
    """CLI test: fetch video info for a given BV number."""
    if not args:
        print("Usage: python -m src test <BV_number>")
        print("Example: python -m src test BV1GJ411x7h7")
        sys.exit(1)

    bvid = args[0]
    if not bvid.upper().startswith("BV"):
        bvid = f"BV{bvid}"

    from src.api.client import BilibiliAPIClient
    from src.core.ffmpeg import FFmpegManager

    print(f"Fetching info for {bvid}...")

    # Check FFmpeg
    available, msg = FFmpegManager.check_available()
    print(f"FFmpeg: {'OK' if available else 'NOT FOUND'} - {msg}")

    # Fetch video info
    client = BilibiliAPIClient()
    try:
        info = client.get_video_info(bvid)
        print(f"\nTitle:     {info.title}")
        print(f"Author:    {info.author}")
        print(f"Duration:  {info.duration_str}")
        print(f"BVID:      {info.bvid}")
        print(f"PID:       {info.cid}")
        print(f"Pages:     {len(info.pages)}")
        print(f"Subtitles: {len(info.subtitle_list)}")
        if info.subtitle_list:
            for s in info.subtitle_list:
                print(f"  - {s.lan}: {s.lan_doc}")
        print("\nSuccess!")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


def _cli_download(args):
    """CLI download: download a video by BV number."""
    if not args:
        print("Usage: python -m src download <BV_number> [--quality <qn>] [--output <dir>] [--danmaku] [--subtitle]")
        print("Example: python -m src download BV1GJ411x7h7 --quality 80 --output ./videos --danmaku")
        sys.exit(1)

    from src.api.client import BilibiliAPIClient
    from src.core.downloader import StreamDownloader
    from src.core.models import DownloadItem, VideoQuality
    from src.utils.config import ConfigManager

    bvid = args[0]
    if not bvid.upper().startswith("BV"):
        bvid = f"BV{bvid}"

    quality = VideoQuality.Q1080P
    output_dir = None
    download_danmaku = False
    download_subtitle = False

    i = 1
    while i < len(args):
        if args[i] == "--quality" and i + 1 < len(args):
            try:
                quality = VideoQuality(int(args[i + 1]))
            except ValueError:
                print(f"Invalid quality: {args[i + 1]}")
                sys.exit(1)
            i += 2
        elif args[i] in ("--output", "-o") and i + 1 < len(args):
            output_dir = args[i + 1]
            i += 2
        elif args[i] == "--danmaku":
            download_danmaku = True
            i += 1
        elif args[i] in ("--subtitle", "-s"):
            download_subtitle = True
            i += 1
        else:
            i += 1

    # Load settings for default output dir and ffmpeg path
    config = ConfigManager()
    settings = config.load()
    if output_dir is None:
        output_dir = settings.output_dir

    print(f"Downloading {bvid} at {quality.label}...")

    client = BilibiliAPIClient()
    info = client.get_video_info(bvid)
    print(f"Title: {info.title}")

    item = DownloadItem(
        video_info=info,
        selected_quality=quality,
        output_path=output_dir,
        download_danmaku=download_danmaku,
        download_subtitle=download_subtitle,
    )

    def progress(pct, text):
        bar_len = 30
        filled = int(bar_len * pct)
        bar = "=" * filled + "-" * (bar_len - filled)
        print(f"\r[{bar}] {pct * 100:5.1f}%  {text}", end="", flush=True)

    downloader = StreamDownloader(client, output_dir, ffmpeg_path=settings.ffmpeg_path or None)
    try:
        output = downloader.download(item, progress)
        print(f"\nSaved to: {output}")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
    finally:
        client.close()


def _launch_gui():
    """Launch the PySide6 GUI application."""
    try:
        from PySide6.QtWidgets import QApplication
        from src.gui.main_window import MainWindow
    except ImportError:
        print("PySide6 not installed. Install with: pip install PySide6")
        print("Or use CLI mode: python -m src test <BV_number>")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("Bilibili Downloader")
    app.setOrganizationName("bilibili-downloader")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
