#!/usr/bin/env bash
# Compress unpublished Armbian artifacts without changing either tar payload.
set -euo pipefail
[[ $# -eq 2 ]] || { echo "usage: $0 INPUT.deb OUTPUT.deb" >&2; exit 2; }
input=$(realpath -e "$1")
output=$(realpath -m "$2")
[[ "$input" != "$output" && ! -e "$output" ]] || { echo 'output must be a new file' >&2; exit 1; }
temporary=$(mktemp -d)
trap 'rm -rf -- "$temporary"' EXIT
mkdir -p "$(dirname "$output")"
printf '2.0\n' > "$temporary/debian-binary"
dpkg-deb --ctrl-tarfile "$input" | xz -T2 -6 > "$temporary/control.tar.xz"
dpkg-deb --fsys-tarfile "$input" | xz -T2 -6 > "$temporary/data.tar.xz"
ar rcsD "$temporary/package.deb" "$temporary/debian-binary" "$temporary/control.tar.xz" "$temporary/data.tar.xz"
for kind in --ctrl-tarfile --fsys-tarfile; do
    before=$(dpkg-deb "$kind" "$input" | sha256sum)
    after=$(dpkg-deb "$kind" "$temporary/package.deb" | sha256sum)
    [[ "$before" == "$after" ]] || { echo "tar payload changed: $kind" >&2; exit 1; }
done
mv "$temporary/package.deb" "$output"
