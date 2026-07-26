"""Entry point for the Bilibili downloader application."""

import argparse
import logging
import sys

from bilibili_downloader.core.models import AUDIO_CODEC_MAP, VideoQuality

logger = logging.getLogger(__name__)


def main():
    """Main entry point. Supports both CLI and GUI modes."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        prog="bilibili-downloader",
        description="Bilibili video downloader — CLI and GUI modes.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- test subcommand ---
    test_parser = subparsers.add_parser(
        "test",
        help="Fetch video metadata for a BV/AV number or URL",
    )
    test_parser.add_argument(
        "source",
        help="BV/AV number, Bilibili URL, or b23.tv short link",
    )

    # --- download subcommand ---
    download_parser = subparsers.add_parser(
        "download",
        help="Download a video by BV/AV number or URL",
    )
    download_parser.add_argument(
        "source",
        help="BV/AV number, video/collection/favorite URL, or b23.tv short link",
    )
    download_parser.add_argument(
        "--quality", "-q",
        type=int,
        default=VideoQuality.Q1080P,
        choices=[q.value for q in VideoQuality],
        help=f"Video quality code (default: {VideoQuality.Q1080P})",
    )
    download_parser.add_argument(
        "--output", "-o",
        help="Output directory (default: from settings or ./downloads)",
    )
    download_parser.add_argument(
        "--danmaku", "-d",
        action="store_true",
        help="Download danmaku (ASS format)",
    )
    download_parser.add_argument(
        "--subtitle", "-s",
        action="store_true",
        help="Download subtitles (SRT format)",
    )
    download_parser.add_argument(
        "--codec", "-c",
        type=int,
        choices=[7, 12, 13],
        help="Video codec code: 7=AVC, 12=HEVC, 13=AV1 (default: settings)",
    )
    download_parser.add_argument(
        "--page", "-p",
        default="1",
        help="Multi-part page number, or 'all' (default: 1)",
    )
    download_parser.add_argument(
        "--subtitle-language",
        default="zh-Hans",
        help="Preferred Bilibili subtitle language code (default: zh-Hans)",
    )
    download_parser.add_argument(
        "--all-subtitles",
        action="store_true",
        help="Download every available subtitle language",
    )
    download_parser.add_argument(
        "--audio-only",
        action="store_true",
        help="Save only audio (M4A, or FLAC for Hi-Res)",
    )
    download_parser.add_argument(
        "--audio-quality",
        type=int,
        choices=list(AUDIO_CODEC_MAP),
        help="Audio quality code (default: settings)",
    )
    download_parser.add_argument(
        "--cover",
        action="store_true",
        help="Save the validated cover image beside the media",
    )
    download_parser.add_argument(
        "--metadata",
        action="store_true",
        help="Save a portable JSON metadata manifest",
    )
    download_parser.add_argument(
        "--path-template",
        help="Relative output template, e.g. '{author}/{title}{part_suffix}'",
    )

    args = parser.parse_args()

    if args.command == "test":
        _cli_test(args.source)
    elif args.command == "download":
        _cli_download(args)
    else:
        # Default: launch GUI
        _launch_gui()


def _cli_test(source: str):
    """CLI test: fetch video info for a given input."""

    from bilibili_downloader.api.client import BilibiliAPIClient
    from bilibili_downloader.core.batch import BatchResolver
    from bilibili_downloader.core.errors import user_error_message
    from bilibili_downloader.core.ffmpeg import FFmpegManager

    print(f"Fetching info for {source}...")

    # Check FFmpeg
    available, msg = FFmpegManager.check_available()
    print(f"FFmpeg: {'OK' if available else 'NOT FOUND'} - {msg}")

    # Fetch video info
    client = BilibiliAPIClient()
    try:
        info = BatchResolver(client).resolve_one(source)
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
        print(f"\nError: {user_error_message(e)}")
        sys.exit(1)
    finally:
        client.close()


def _cli_download(args: argparse.Namespace):
    """CLI download: download a video by BV/AV number or URL."""
    from bilibili_downloader.api.client import BilibiliAPIClient
    from bilibili_downloader.core.batch import ContentSourceResolver
    from bilibili_downloader.core.download_service import DownloadService
    from bilibili_downloader.core.errors import user_error_message
    from bilibili_downloader.core.models import DownloadItem, OutputMode
    from bilibili_downloader.utils.config import ConfigManager

    quality = VideoQuality(args.quality)

    # Load settings for default output dir and ffmpeg path
    config = ConfigManager()
    settings = config.load()
    output_dir = args.output or settings.output_dir

    print(f"Downloading {args.source} at {quality.label}...")

    client = BilibiliAPIClient(sessdata=settings.sessdata or None)
    service = None
    try:
        collection = ContentSourceResolver(client).resolve(args.source)
        print(f"Source: {collection.title} ({len(collection.items)} videos)")

        page_infos = []
        for info in collection.items:
            if str(args.page).lower() == "all":
                page_infos.extend([info.for_page(page) for page in info.pages] or [info])
                continue
            try:
                page_number = int(args.page)
            except ValueError as exc:
                raise ValueError("--page must be a positive page number or 'all'") from exc
            if page_number < 1 or page_number > max(1, len(info.pages)):
                raise ValueError(
                    f"--page must be between 1 and {max(1, len(info.pages))} "
                    f"for {info.title}"
                )
            page_infos.append(
                info.for_page(info.pages[page_number - 1]) if info.pages else info
            )

        def progress(pct, text):
            bar_len = 30
            filled = int(bar_len * pct)
            bar = "=" * filled + "-" * (bar_len - filled)
            print(f"\r[{bar}] {pct * 100:5.1f}%  {text}", end="", flush=True)

        service = DownloadService(
            client, output_dir, ffmpeg_path=settings.ffmpeg_path or None,
        )
        codec = args.codec or settings.default_video_codec
        for index, page_info in enumerate(page_infos, start=1):
            if len(page_infos) > 1:
                print(f"\n[{index}/{len(page_infos)}] CID {page_info.cid}")
            item = DownloadItem(
                video_info=page_info,
                selected_quality=quality,
                selected_video_codec=codec,
                selected_audio_quality=(
                    args.audio_quality
                    if getattr(args, "audio_quality", None) is not None
                    else settings.default_audio_quality
                ),
                output_mode=(
                    OutputMode.AUDIO
                    if getattr(args, "audio_only", False)
                    else settings.default_output_mode
                ),
                path_template=(
                    getattr(args, "path_template", None) or settings.path_template
                ),
                output_path=output_dir,
                download_danmaku=args.danmaku,
                download_subtitle=args.subtitle or getattr(args, "all_subtitles", False),
                download_all_subtitles=getattr(args, "all_subtitles", False),
                download_cover=getattr(args, "cover", False),
                download_metadata=getattr(args, "metadata", False),
                selected_subtitle_lan=args.subtitle_language,
            )
            outcome = service.download(item, progress)
            print(f"\nSaved to: {outcome.video_path}")
            for warning in outcome.warnings:
                print(f"Warning: {warning}")
    except KeyboardInterrupt:
        if service is not None:
            service.cancel()
        print("\nDownload cancelled")
        raise SystemExit(130)
    except Exception as e:
        print(f"\nError: {user_error_message(e)}")
        sys.exit(1)
    finally:
        client.close()


def _launch_gui():
    """Launch the PySide6 GUI application."""
    try:
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication

        from bilibili_downloader.gui.main_window import MainWindow
        from bilibili_downloader.gui.resources.paths import asset_path
        from bilibili_downloader.gui.resources.theme import ThemeManager
    except ImportError:
        print("PySide6 not installed. Install with: pip install PySide6")
        print("Or use CLI mode: python -m bilibili_downloader test <BV_number>")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("Bilibili Downloader")
    app.setOrganizationName("bilibili-downloader")
    app.setWindowIcon(QIcon(asset_path("app_icon.png")))
    theme_manager = ThemeManager(app)

    window = MainWindow()
    window.show()

    # Keep the controller alive for system theme change notifications.
    app._theme_manager = theme_manager
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
