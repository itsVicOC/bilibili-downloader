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
        description="Bilibili video and bangumi downloader — CLI and GUI modes.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- test subcommand ---
    test_parser = subparsers.add_parser(
        "test",
        help="Fetch metadata for a BV/AV/ep number or supported URL",
    )
    test_parser.add_argument(
        "source",
        help="BV/AV/ep number, Bilibili URL, or b23.tv short link",
    )

    # --- download subcommand ---
    download_parser = subparsers.add_parser(
        "download",
        help="Download a video or bangumi source",
    )
    download_parser.add_argument(
        "source",
        help="BV/AV/ep/ss/md, supported URL, or b23.tv short link",
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
    download_parser.add_argument(
        "--include-extras",
        action="store_true",
        help="Include PV, specials and other non-main bangumi sections",
    )
    download_parser.add_argument(
        "--acknowledge-copyright",
        action="store_true",
        help="Acknowledge the copyright notice in non-interactive environments",
    )

    args = parser.parse_args()

    if args.command and getattr(sys, "frozen", False):
        from bilibili_downloader.core.installation import WindowsInstallationGuard
        installation_guard = WindowsInstallationGuard()
        try:
            installation_guard.acquire()
        except OSError as exc:
            parser.error(str(exc))

    if args.command == "test":
        from bilibili_downloader.core.update_protocol import RuntimeLease
        from bilibili_downloader.utils.config import DEFAULT_CONFIG_PATH
        with RuntimeLease(DEFAULT_CONFIG_PATH.parent / "runtime.lock"):
            _cli_test(args.source)
    elif args.command == "download":
        from bilibili_downloader.core.update_protocol import RuntimeLease
        from bilibili_downloader.utils.config import DEFAULT_CONFIG_PATH
        with RuntimeLease(DEFAULT_CONFIG_PATH.parent / "runtime.lock"):
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
    from collections import Counter

    from bilibili_downloader.api.client import BilibiliAPIClient
    from bilibili_downloader.api.pgc import BangumiAccessError
    from bilibili_downloader.core.batch import ContentSourceResolver
    from bilibili_downloader.core.copyright import COPYRIGHT_NOTICE_VERSION
    from bilibili_downloader.core.download_service import DownloadService
    from bilibili_downloader.core.errors import classify_error, user_error_message
    from bilibili_downloader.core.models import DownloadItem, OutputMode
    from bilibili_downloader.utils.config import ConfigManager

    quality = VideoQuality(args.quality)

    # Load settings for default output dir and ffmpeg path
    config = ConfigManager()
    settings = config.load()
    if settings.copyright_notice_version < COPYRIGHT_NOTICE_VERSION:
        if not _confirm_cli_copyright(
            bool(getattr(args, "acknowledge_copyright", False))
        ):
            raise SystemExit(2)
        settings.copyright_notice_version = COPYRIGHT_NOTICE_VERSION
        config.save(settings)
    output_dir = args.output or settings.output_dir

    print(f"Downloading {args.source} at {quality.label}...")

    try:
        client = BilibiliAPIClient(
            sessdata=settings.sessdata or None,
            auth_cookies=config.auth_cookies,
        )
    except TypeError:  # Compatibility with external/test client adapters.
        client = BilibiliAPIClient(sessdata=settings.sessdata or None)
    service = None
    try:
        collection = ContentSourceResolver(client).resolve(args.source)
        print(f"Source: {collection.title} ({len(collection.items)} videos)")
        for error in collection.errors:
            print(f"Skipped: {error}")
        if not collection.items:
            raise ValueError("该来源没有可下载的作品，请检查解析详情和内容访问权限")

        page_infos = []
        for info in collection.items:
            if (
                collection.source_type == "bangumi_season"
                and not info.is_main_section
                and not getattr(args, "include_extras", False)
            ):
                continue
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
        if not page_infos:
            raise ValueError(
                "该番剧季度没有默认选中的正片；如需附加章节请传入 "
                "--include-extras"
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
        failures = Counter()
        completed = 0
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
                    getattr(args, "path_template", None)
                    or (
                        settings.bangumi_path_template
                        if page_info.episode_id
                        else settings.path_template
                    )
                ),
                output_path=output_dir,
                download_danmaku=args.danmaku,
                download_subtitle=args.subtitle or getattr(args, "all_subtitles", False),
                download_all_subtitles=getattr(args, "all_subtitles", False),
                download_cover=getattr(args, "cover", False),
                download_metadata=getattr(args, "metadata", False),
                selected_subtitle_lan=args.subtitle_language,
            )
            try:
                outcome = service.download(item, progress)
                completed += 1
                print(f"\nSaved to: {outcome.video_path}")
                for warning in outcome.warnings:
                    print(f"Warning: {warning}")
            except Exception as exc:  # noqa: BLE001
                details = classify_error(exc)
                failure_kind = (
                    exc.reason.value
                    if isinstance(exc, BangumiAccessError)
                    else details.category.value
                )
                failures[failure_kind] += 1
                print(f"\nSkipped: {page_info.title}: {details.user_message}")
        if failures:
            summary = ", ".join(
                f"{category}={count}" for category, count in sorted(failures.items())
            )
            print(f"Batch result: completed={completed}, failed={sum(failures.values())} ({summary})")
            if not completed:
                raise SystemExit(1)
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


def _confirm_cli_copyright(flag_acknowledged: bool) -> bool:
    """Obtain the versioned acknowledgement without accepting piped input."""
    from bilibili_downloader.core.copyright import (
        BILIBILI_TERMS_URL,
        COPYRIGHT_DOCUMENT_URL,
        COPYRIGHT_NOTICE_SUMMARY,
        COPYRIGHT_NOTICE_TITLE,
    )

    if flag_acknowledged:
        return True
    if not sys.stdin.isatty():
        print(
            "首次下载需要确认版权提示；非交互环境请传入 "
            "--acknowledge-copyright。",
            file=sys.stderr,
        )
        return False
    print(f"\n{COPYRIGHT_NOTICE_TITLE}\n{COPYRIGHT_NOTICE_SUMMARY}")
    print(f"项目版权说明：{COPYRIGHT_DOCUMENT_URL}")
    print(f"Bilibili 服务协议：{BILIBILI_TERMS_URL}")
    answer = input("输入 yes 表示已了解并继续：").strip().lower()
    return answer in {"yes", "y"}


def _launch_gui():
    """Launch the PySide6 GUI application."""
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication

        from bilibili_downloader.core.update_protocol import RuntimeLease, atomic_json
        from bilibili_downloader.gui.lifecycle import ApplicationLifecycle
        from bilibili_downloader.gui.main_window import MainWindow
        from bilibili_downloader.gui.resources.paths import asset_path
        from bilibili_downloader.gui.resources.theme import ThemeManager
        from bilibili_downloader.utils.config import ConfigManager
        from bilibili_downloader.utils.update_startup import (
            startup_failure,
            startup_transaction,
        )
    except ImportError:
        print("PySide6 not installed. Install with: pip install PySide6")
        print("Or use CLI mode: python -m bilibili_downloader test <BV_number>")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("BiliFlow")
    app.setOrganizationName("bilibili-downloader")
    app.setWindowIcon(QIcon(asset_path("app_icon.png")))
    config = ConfigManager()
    theme_manager = ThemeManager(app)

    from bilibili_downloader.core.installation import (
        WindowsInstallationGuard,
        macos_installation_notice,
    )
    installation_guard = WindowsInstallationGuard()
    if getattr(sys, "frozen", False):
        try:
            installation_guard.acquire()
        except OSError as exc:
            from bilibili_downloader.gui.widgets.components import MessageBox
            MessageBox("暂时无法启动", str(exc), tone="warning").exec()
            return

    transaction = startup_transaction(config.data_dir)
    failure = startup_failure(config.data_dir)
    lease = RuntimeLease(config.data_dir / "runtime.lock")
    if transaction is None and not lease.acquire():
        from bilibili_downloader.gui.widgets.components import MessageBox
        MessageBox("正在安装更新", "更新程序正在替换应用，请稍后重新打开。", tone="warning").exec()
        return
    try:
        appearance = config.load().appearance
        theme_manager.set_color_theme(appearance.theme)
        theme_manager.set_mode(appearance.mode)
        window = MainWindow(config, startup_paused=transaction is not None, theme_manager=theme_manager, remember_window=True)
        lifecycle = ApplicationLifecycle(app, window)
        window.show_initial()
        if sys.platform == "darwin" and getattr(sys, "frozen", False):
            from pathlib import Path
            notice = macos_installation_notice(Path(sys.executable))
            if notice:
                window._settings_page._update_notice.set_message(notice, "warning")
                window._status_bar.showMessage(notice)
        if transaction:
            path, value = transaction
            window._set_shell_enabled(False)
            QTimer.singleShot(0, lambda: atomic_json(path.parent / "startup-ready.json", {"token": value["token"], "version": value["build"]["version"]}))
            timer = QTimer(window)
            timer.setInterval(100)

            def finish_update_startup():
                import json
                try:
                    commit = json.loads((path.parent / "commit.json").read_text("utf-8"))
                except (OSError, ValueError):
                    return
                if commit.get("token") == value["token"] and lease.acquire():
                    timer.stop()
                    window.resume_startup()
                    window._settings_page._update_notice.set_message("更新安装成功", "success")
                    window._status_bar.showMessage("更新安装成功")

            timer.timeout.connect(finish_update_startup)
            timer.start()
        elif failure:
            QTimer.singleShot(0, lambda: window._on_update_failed(failure, True))
        else:
            QTimer.singleShot(1000, window.start_startup_update_check)
        # Keep the controller alive for system theme change notifications.
        app._theme_manager = theme_manager
        app._lifecycle = lifecycle
        sys.exit(app.exec())
    finally:
        lease.release()


if __name__ == "__main__":
    main()
