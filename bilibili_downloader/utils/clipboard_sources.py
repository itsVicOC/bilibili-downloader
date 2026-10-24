"""Local extraction of supported download sources from copied share text."""

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlparse

from bilibili_downloader.core.batch import classify_batch_inputs, is_collection_source
from bilibili_downloader.utils.validators import (
    extract_aid,
    extract_bangumi_id,
    extract_bvid,
    is_short_link,
)

MAX_CLIPBOARD_CHARACTERS = 64 * 1024
_URL = re.compile(r"https?://(?:(?!https?://)[^\s<>\"'])+", re.IGNORECASE)
_ASCII_URL = re.compile(r"https?://[A-Za-z0-9:/?#\[\]@!$&()*+,;=%._~\-]+", re.IGNORECASE)
_ID = re.compile(r"(?<![A-Za-z0-9_])(?:BV[A-Za-z0-9]{10}|(?:av|ep|ss|md)\d+)(?![A-Za-z0-9_])", re.IGNORECASE)
_PATH = re.compile(r"(?:^|(?<=\s))(?:file://|/|[A-Za-z]:\\)[^\s]+", re.IGNORECASE)
_TRAILING = ".,;!?)]}，。；！？、）】》」』"
_SEMANTIC_QUERY = {"p", "sid", "season_id", "series_id", "fid", "media_id", "mlid", "type"}


def source_identity(source):
    parsed = urlparse(source)
    query = tuple(sorted((key, value) for key, value in parse_qsl(parsed.query) if key in _SEMANTIC_QUERY))
    bangumi = extract_bangumi_id(source)
    if bangumi:
        return "bangumi", bangumi
    if is_collection_source(source):
        return ("collection", parsed.hostname, parsed.path.rstrip("/").lower(), query) if parsed.hostname else ("bangumi", extract_bangumi_id(source))
    bvid, aid, bangumi = extract_bvid(source), extract_aid(source), extract_bangumi_id(source)
    if bvid:
        return "video", bvid.lower(), query
    if aid:
        return "av", aid, query
    if bangumi:
        return "bangumi", bangumi
    return "short", parsed.hostname, parsed.path.rstrip("/"), query


@dataclass(frozen=True)
class ClipboardCandidate:
    sources: tuple[str, ...]
    target: str

    @property
    def fingerprint(self):
        identities = tuple(source_identity(source) for source in self.sources)
        return hashlib.sha256(repr(identities).encode()).hexdigest()


def extract_clipboard_sources(text: str) -> ClipboardCandidate | None:
    if not text or len(text) > MAX_CLIPBOARD_CHARACTERS:
        return None
    found = []
    masked = list(text)
    for match in _URL.finditer(text):
        raw = match.group().rstrip(_TRAILING)
        candidates = [raw]
        ascii_match = _ASCII_URL.match(raw)
        if ascii_match:
            candidates.insert(0, ascii_match.group().rstrip(_TRAILING))
        for candidate in candidates:
            valid, _ = classify_batch_inputs(candidate)
            if valid:
                found.append((match.start(), valid[0]))
                break
        masked[match.start():match.end()] = " " * (match.end() - match.start())
    remainder = "".join(masked)
    for match in _PATH.finditer(remainder):
        masked[match.start():match.end()] = " " * (match.end() - match.start())
    for match in _ID.finditer("".join(masked)):
        valid, _ = classify_batch_inputs(match.group())
        if valid:
            found.append((match.start(), valid[0]))
    sources, seen = [], set()
    for _, source in sorted(found):
        identity = source_identity(source)
        if identity not in seen:
            seen.add(identity)
            sources.append(source)
    if not sources:
        return None
    target = "batch" if len(sources) > 1 or is_collection_source(sources[0]) else "auto" if is_short_link(sources[0]) else "single"
    return ClipboardCandidate(tuple(sources), target)
