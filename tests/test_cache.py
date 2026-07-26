"""Tests for resumable cache inspection and cleanup."""

from bilibili_downloader.core.cache import clear_download_cache, inspect_download_cache


def test_cache_summary_and_cleanup(tmp_path):
    cache = tmp_path / ".biliflow-parts" / "task"
    cache.mkdir(parents=True)
    (cache / "video.m4s").write_bytes(b"1234")
    (cache / "audio.m4s").write_bytes(b"56")

    summary = inspect_download_cache(tmp_path)
    assert summary.file_count == 2
    assert summary.size_bytes == 6

    cleared = clear_download_cache(tmp_path)
    assert cleared.size_bytes == 6
    assert not (tmp_path / ".biliflow-parts").exists()
