"""Clipboard extraction is local, ordered, bounded and respects URL boundaries."""

import pytest

from bilibili_downloader.utils.clipboard_sources import extract_clipboard_sources


@pytest.mark.parametrize('source,target', [
    ('BV1GJ411x7h7', 'single'), ('av170001', 'single'), ('ep123', 'single'),
    ('ss123', 'batch'), ('md123', 'batch'), ('https://b23.tv/AbCd123', 'auto'),
    ('https://space.bilibili.com/123/favlist?fid=456', 'batch'),
    ('https://space.bilibili.com/123/lists/456?type=series', 'batch'),
    ('https://www.bilibili.com/video/BV1GJ411x7h7?p=2', 'single'),
])
def test_supported_clipboard_inputs(source, target):
    result = extract_clipboard_sources(f'【分享】{source}，快来看看')
    assert result.sources == (source,)
    assert result.target == target


def test_share_text_deduplicates_without_dropping_parts_or_list_parameters():
    first = 'https://www.bilibili.com/video/BV1GJ411x7h7?p=2&vd_source=tracking'
    second = 'https://www.bilibili.com/video/BV1GJ411x7h7?p=3'
    collection = 'https://www.bilibili.com/video/BV1GJ411x7h7?sid=88'
    result = extract_clipboard_sources(f'{first}\n{first}\n{second}\n{collection}\nAV170001')
    assert result.sources == (first, second, collection, 'AV170001')
    assert result.target == 'batch'


@pytest.mark.parametrize('text', [
    'https://evil.example/video/BV1GJ411x7h7',
    'https://www.bilibili.com.evil.example/video/BV1GJ411x7h7',
    'https://live.bilibili.com/123456', '/tmp/BV1GJ411x7h7.mp4',
    r'C:\Downloads\BV1GJ411x7h7.mp4', 'file:///tmp/BV1GJ411x7h7.mp4',
    'ordinary words', '123456', 'sleep123', '', 'x' * 65537,
])
def test_unsupported_text_is_not_a_download_candidate(text):
    assert extract_clipboard_sources(text) is None


def test_untrusted_url_ids_are_not_extracted_as_separate_sources():
    result = extract_clipboard_sources('https://evil.example/?next=BV1GJ411x7h7\nep123')
    assert result.sources == ('ep123',)


def test_bangumi_url_and_id_are_one_source():
    result = extract_clipboard_sources('ss123\nhttps://www.bilibili.com/bangumi/play/ss123')
    assert result.sources == ('ss123',)
