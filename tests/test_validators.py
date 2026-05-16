"""Tests for URL validators."""

from bilibili_downloader.utils.validators import extract_bvid, extract_aid, is_bilibili_url, sanitize_filename


class TestExtractBVID:
    def test_raw_bv_number(self):
        assert extract_bvid("BV1GJ411x7h7") == "BV1GJ411x7h7"

    def test_lowercase_bv(self):
        assert extract_bvid("bv1GJ411x7h7") == "BV1GJ411x7h7"

    def test_full_url(self):
        assert extract_bvid("https://www.bilibili.com/video/BV1GJ411x7h7") == "BV1GJ411x7h7"

    def test_mobile_url(self):
        assert extract_bvid("https://m.bilibili.com/video/BV1GJ411x7h7") == "BV1GJ411x7h7"

    def test_url_with_params(self):
        result = extract_bvid("https://www.bilibili.com/video/BV1GJ411x7h7?p=1&vd_source=xxx")
        assert result == "BV1GJ411x7h7"

    def test_invalid_returns_none(self):
        assert extract_bvid("not_a_bv_number") is None
        assert extract_bvid("https://youtube.com/watch?v=abc") is None


class TestExtractAID:
    def test_raw_av_number(self):
        assert extract_aid("av123456") == 123456

    def test_av_in_url(self):
        assert extract_aid("https://www.bilibili.com/video/av123456") == 123456

    def test_invalid_returns_none(self):
        assert extract_aid("not_an_av_number") is None


class TestIsBilibiliURL:
    def test_bv_url(self):
        assert is_bilibili_url("https://www.bilibili.com/video/BV1GJ411x7h7") is True

    def test_raw_bv(self):
        assert is_bilibili_url("BV1GJ411x7h7") is True

    def test_short_link(self):
        assert is_bilibili_url("https://b23.tv/abc123") is True

    def test_non_bilibili(self):
        assert is_bilibili_url("https://youtube.com/watch?v=abc") is False


class TestSanitizeFilename:
    def test_basic(self):
        assert sanitize_filename("Hello World") == "Hello World"

    def test_invalid_chars(self):
        assert sanitize_filename('file:name.txt') == "file_name.txt"
        assert sanitize_filename('path/to/file') == "path_to_file"

    def test_control_chars(self):
        result = sanitize_filename("hello\x00world")
        assert "\x00" not in result

    def test_too_long(self):
        name = "a" * 300
        result = sanitize_filename(name)
        assert len(result) <= 200

    def test_empty_after_clean(self):
        assert sanitize_filename("   ") == "untitled"

    def test_windows_reserved_names(self):
        """Windows reserved device names should be prefixed with underscore."""
        assert sanitize_filename("CON") == "_CON"
        assert sanitize_filename("PRN") == "_PRN"
        assert sanitize_filename("NUL") == "_NUL"
        assert sanitize_filename("AUX") == "_AUX"
        assert sanitize_filename("COM1") == "_COM1"
        assert sanitize_filename("LPT9") == "_LPT9"
        assert sanitize_filename("con.txt") == "_con.txt"
        # Normal names should pass through
        assert sanitize_filename("Content") == "Content"
        assert sanitize_filename("Contact") == "Contact"
