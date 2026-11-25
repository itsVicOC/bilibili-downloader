#!/usr/bin/env bash

set -euo pipefail

if [[ $# -ne 3 ]]; then
    echo "usage: $0 <ffmpeg-source.tar.gz> <dav1d-source.tar.xz> <output-directory>" >&2
    exit 2
fi

source_archive=$1
dav1d_archive=$2
output_dir=$3
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

mkdir "$build_root/dav1d-source"
tar -xf "$dav1d_archive" -C "$build_root/dav1d-source" --strip-components=1
if [[ $(uname -s) == Darwin ]]; then
    export MACOSX_DEPLOYMENT_TARGET=12.0
fi
jobs=$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)
meson setup "$build_root/dav1d-build" "$build_root/dav1d-source" \
    --prefix="$build_root/dav1d-install" --libdir=lib --buildtype=release \
    --default-library=static --wrap-mode=nodownload \
    -Denable_asm=false -Denable_tools=false -Denable_tests=false
meson compile -C "$build_root/dav1d-build" -j "$jobs"
meson install -C "$build_root/dav1d-build" --no-rebuild
export PKG_CONFIG_LIBDIR="$build_root/dav1d-install/lib/pkgconfig"
unset PKG_CONFIG_PATH

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
    --enable-protocol=pipe
    --enable-demuxer=mov
    --enable-demuxer=flv
    --enable-demuxer=mpegts
    --enable-demuxer=concat
    --enable-parser=h264
    --enable-parser=aac
    --enable-parser=hevc,av1
    --enable-decoder=aac
    --enable-decoder=h264,hevc,libdav1d
    --enable-libdav1d
    --pkg-config-flags=--static
    --enable-encoder=mjpeg
    --enable-swscale
    --enable-filter=scale,format,transpose,hflip,vflip,rotate
    --enable-bsf=aac_adtstoasc
    --enable-bsf=extract_extradata
    --enable-bsf=h264_mp4toannexb
    --enable-muxer=mp4
    --enable-muxer=ipod
    --enable-muxer=flac
    --enable-muxer=image2pipe
)
case $(uname -s) in
    Darwin)
        configure_args+=(
            --extra-cflags=-mmacosx-version-min=12.0
            --extra-ldflags=-mmacosx-version-min=12.0
        )
        ;;
    MINGW*|MSYS*|CYGWIN*)
        # Use the native Windows threading backend so the standalone executable
        # does not depend on MSYS2's libwinpthread-1.dll at runtime.
        configure_args+=(
            --disable-pthreads
            --enable-w32threads
            --extra-ldflags=-static
        )
        ;;
esac
./configure "${configure_args[@]}"

make -j"$jobs"

if [[ -f ffmpeg.exe ]]; then
    install -m 755 ffmpeg.exe "$output_dir/ffmpeg.exe"
else
    install -m 755 ffmpeg "$output_dir/ffmpeg"
fi
install -m 644 COPYING.LGPLv2.1 "$output_dir/COPYING.LGPLv2.1"
install -m 644 LICENSE.md "$output_dir/FFMPEG-LICENSE.md"
install -m 644 "$build_root/dav1d-source/COPYING" "$output_dir/DAV1D-LICENSE.txt"
