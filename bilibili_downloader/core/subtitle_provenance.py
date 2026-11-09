"""Bind saved subtitles to a discovered page and the bytes actually published."""

import hashlib
import os
import shutil
import stat
import tempfile
from pathlib import Path

from bilibili_downloader.core.models import SubtitleProvenance

SUBTITLE_PROTOCOL_VERSION = 1


def subtitle_identity(info):
    identity = info.content_identity
    return identity if info.bvid or identity.startswith("ep:") else f"av:{info.aid}:{info.cid}"


def subtitle_path_key(path):
    return os.path.normcase(os.path.abspath(os.path.expanduser(str(path))))


def subtitle_proof(outcome, path):
    key = subtitle_path_key(path)
    return next((proof for saved, proof in outcome.subtitle_provenance.items()
                 if subtitle_path_key(saved) == key), None)


def file_digest(path):
    path = Path(path)
    if not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size == 0:
        raise ValueError("字幕文件为空或不是普通文件")
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def subtitle_verified(info, outcome, path, track_id=None):
    proof = subtitle_proof(outcome, path)
    if (proof is None or proof.protocol_version != SUBTITLE_PROTOCOL_VERSION
            or proof.content_identity != subtitle_identity(info) or proof.cid != info.cid
            or not proof.track_id or (track_id is not None and proof.track_id != track_id)):
        return False
    try:
        return file_digest(path) == proof.sha256
    except (OSError, ValueError):
        return False


def verified_languages(info, outcome):
    return {lan: path for lan, path in outcome.subtitle_languages.items()
            if subtitle_verified(info, outcome, path)}


def discovery_verified(info, outcome):
    return (outcome.subtitle_discovery_identity == subtitle_identity(info)
            and outcome.subtitle_discovery_version == SUBTITLE_PROTOCOL_VERSION)


def publish_subtitle(info, track, destination, converter, *, expected_sha256=None):
    """Convert off to the side, preserve any old file, then publish atomically."""
    destination = Path(destination).absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix=".subtitle-", dir=destination.parent)
    staging = Path(temporary.name) / destination.name
    backup = None
    try:
        report = converter(track.url, staging)
        proof = SubtitleProvenance(content_identity=subtitle_identity(info), cid=info.cid,
                                   track_id=track.track_id, sha256=file_digest(staging))
        if expected_sha256 is not None and proof.sha256 != expected_sha256:
            raise ValueError("复制期间字幕内容已变化，请重新获取字幕后重试")
        if destination.exists():
            if destination.is_symlink() or not destination.is_file():
                raise ValueError("字幕目标不是普通文件，请另选保存位置")
            index = 0
            while True:
                suffix = "" if index == 0 else f".{index}"
                candidate = destination.with_name(f"{destination.name}.unverified{suffix}.bak")
                try:
                    with candidate.open("xb") as out:
                        try:
                            with destination.open("rb") as source:
                                shutil.copyfileobj(source, out)
                        except BaseException:
                            candidate.unlink(missing_ok=True)
                            raise
                    backup = candidate
                    break
                except FileExistsError:
                    index += 1
        os.replace(staging, destination)
        return report, proof
    except BaseException:
        # A partial backup is never advertised as a preserved subtitle.
        if backup is not None:
            backup.unlink(missing_ok=True)
        raise
    finally:
        temporary.cleanup()
