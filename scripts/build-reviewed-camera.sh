#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 2 ]] || { echo 'usage: build-reviewed-camera.sh ARMBIAN_SOURCE OUTPUT_DIR' >&2; exit 2; }
armbian=$(realpath -e "$1")
mkdir -p "$2"
output=$(realpath "$2")
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
version=6.6.3+dshanpi2
"$armbian/packages/bsp/dshanpi-a1-cm5/repack-camera-engine.sh" \
    "$armbian/debs/camera/camera_engine_rkaiq_rk3576_arm64.deb" "$work" "$version"
dpkg-deb --raw-extract "$work/camera-engine-rkaiq_${version}_arm64.deb" "$work/package"
cat > "$work/package/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = configure ]; then
    # dpkg preserves permissions on existing directories. Older vendor images
    # shipped these package-owned trees as 0777; repair them during upgrades.
    for path in /etc/iqfiles /usr/include/IspFec /usr/include/rkaiq; do
        directory=${DPKG_ROOT:-}$path
        if [ -d "$directory" ] && [ ! -L "$directory" ]; then
            find -P "$directory" -type d -exec chmod 0755 {} +
        fi
    done
fi
EOF
chmod 0755 "$work/package/DEBIAN/postinst"
find "$work/package" -exec touch -h -d @1687086060 {} +
SOURCE_DATE_EPOCH=1687086060 dpkg-deb --root-owner-group --build \
    "$work/package" "$output/camera-engine-rkaiq_${version}_arm64.deb" >/dev/null
sha256sum "$output/camera-engine-rkaiq_${version}_arm64.deb"
