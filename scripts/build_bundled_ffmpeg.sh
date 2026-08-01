#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "usage: $0 <ffmpeg-source.tar.gz> <output-directory>" >&2
    exit 2
fi

source_archive=$1
output_dir=$2
mkdir -p "$output_dir"
output_dir=$(cd "$output_dir" && pwd -P)
build_root=$(mktemp -d "${TMPDIR:-/tmp}/biliflow-ffmpeg-build.XXXXXX")

cleanup() {
    rm -rf -- "$build_root"
}
trap cleanup EXIT

tar -xzf "$source_archive" -C "$build_root"
source_dir=$(find "$build_root" -mindepth 1 -maxdepth 1 -type d -print -quit)
if [[ -z "$source_dir" || ! -x "$source_dir/configure" ]]; then
    echo "FFmpeg source archive has an unexpected layout" >&2
    exit 1
fi

cd "$source_dir"
configure_args=(
    --disable-everything
    --disable-autodetect
    --disable-doc
    --disable-debug
    --disable-network
    --disable-x86asm
    --disable-ffplay
    --disable-ffprobe
    --enable-ffmpeg
    --enable-protocol=file
    --enable-demuxer=mov
    --enable-muxer=mp4
    --enable-muxer=ipod
    --enable-muxer=flac
)
if [[ $(uname -s) == "Darwin" ]]; then
    configure_args+=(
        --extra-cflags=-mmacosx-version-min=12.0
        --extra-ldflags=-mmacosx-version-min=12.0
    )
fi
./configure "${configure_args[@]}"

jobs=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)
make -j"$jobs" ffmpeg

if [[ -f ffmpeg.exe ]]; then
    install -m 755 ffmpeg.exe "$output_dir/ffmpeg.exe"
else
    install -m 755 ffmpeg "$output_dir/ffmpeg"
fi
install -m 644 COPYING.LGPLv2.1 "$output_dir/COPYING.LGPLv2.1"
install -m 644 LICENSE.md "$output_dir/FFMPEG-LICENSE.md"
