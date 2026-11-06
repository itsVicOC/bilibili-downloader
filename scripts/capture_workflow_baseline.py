"""Reproduce the pre-polish UI with identical offline fixtures from git."""

import argparse
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

BASELINE = '61754828a85e1cff099c3425e12e0496cb1ef2c1'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--output-dir', type=Path, default=Path('build/workflow-polish/before'))
    parser.add_argument('--native', action='store_true')
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.source_root is None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='biliflow-ui-baseline-') as directory:
            snapshot = Path(directory)
            archive = snapshot / 'source.tar'
            with archive.open('wb') as handle:
                subprocess.run(['git', 'archive', '--format=tar', BASELINE], cwd=root, stdout=handle, check=True)
            source_root = snapshot / 'source'
            source_root.mkdir()
            with tarfile.open(archive) as source:
                source.extractall(source_root, filter='data')
            command = [sys.executable, str(Path(__file__).resolve()), '--source-root', str(source_root), '--output-dir', str(output)]
            if args.native:
                command.append('--native')
            return subprocess.run(command, cwd=source_root, check=False).returncode
    sys.path.insert(0, str(args.source_root))
    os.environ['QT_QPA_PLATFORM'] = ('cocoa' if sys.platform == 'darwin' else 'windows') if args.native else 'offscreen'
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from bilibili_downloader.core.models import DownloadOutcome
    from bilibili_downloader.gui.dialogs.attachments import choose_attachments
    from bilibili_downloader.gui.resources.theme import ThemeManager
    from scripts import capture_docs_screenshots as capture
    assert str(capture.__file__).startswith(str(args.source_root))
    app = QApplication([])
    app.setProperty('uiAnimationsEnabled', False)
    theme = ThemeManager(app)
    capture.OUTPUT_DIR = output
    with tempfile.TemporaryDirectory(prefix='biliflow-before-fixture-') as directory:
        fixture = Path(directory)
        app.setProperty('docsTempRoot', str(fixture))
        window = capture._make_main_window(fixture / 'window')
        capture._capture_archive(app, theme, window, fixture)
        record = max((record for record in window._task_repository.list_tasks() if record.outcome), key=lambda record: record.id)
        media_dir = fixture / '示例课程'
        media_dir.mkdir()
        media = media_dir / '星轨旅记_夜航篇.mp4'
        media.write_bytes(b'offline UI fixture; not a real video')
        cover = media.with_suffix('.jpg')
        cover.write_bytes(b'offline cover fixture')
        outcome = DownloadOutcome(video_path=str(media), cover_path=str(cover), actual_quality=80,
                                  actual_video_codec=12, actual_audio_quality=30280,
                                  missing_artifacts=['danmaku', 'subtitle', 'metadata'],
                                  warnings=['字幕来源暂时不可用，可单独重试；已有媒体和封面保留。'])
        window._library.record_download(record.item, outcome)
        window._library_page.refresh()
        for mode in ('light', 'dark'):
            theme.set_mode(mode)
            window.resize(900, 640)
            window._show_tasks(3)
            window._library_page.table.selectRow(0)
            capture._save_widget(app, window, f'polish-files-{mode}-900.png')
            def capture_attachment(mode=mode):
                dialog = QApplication.activeModalWidget()
                assert dialog is not None
                capture._save_widget(app, dialog, f'polish-attachments-{mode}.png')
                dialog.reject()
            QTimer.singleShot(0, capture_attachment)
            choose_attachments(record.item, window)
        window._live_controller.shutdown()
        window.request_quit(confirmed=True)
        window._service_pool.waitForDone(15000)
        app.processEvents()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
