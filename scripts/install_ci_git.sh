#!/usr/bin/env bash
# Build the Git version required by the real branch-delivery producer tests.
set -euo pipefail

if (( $# < 1 || $# > 2 )); then
    printf 'Usage: %s OUTPUT_DIR [GIT_RELEASE_ARCHIVE]\n' "$0" >&2
    exit 2
fi
output=$1
version=2.52.0
expected=3cd8fee86f69a949cb610fee8cd9264e6873d07fa58411f6060b3d62729ed7c5
mkdir "$output"
output=$(cd "$output" && pwd)
archive=$output/git-$version.tar.xz
if (( $# == 2 )); then
    cp -- "$2" "$archive"
else
    curl --fail --silent --show-error --location --proto '=https' \
        "https://www.kernel.org/pub/software/scm/git/git-$version.tar.xz" -o "$archive"
fi
printf '%s  %s\n' "$expected" "$archive" | sha256sum --check
tar -xJf "$archive" -C "$output"
make -C "$output/git-$version" -j4 prefix="$output/installed" NO_TCLTK=YesPlease CFLAGS='-O2 -g0'
make -C "$output/git-$version" prefix="$output/installed" NO_TCLTK=YesPlease CFLAGS='-O2 -g0' install
test "$("$output/installed/bin/git" --version)" = "git version $version"
