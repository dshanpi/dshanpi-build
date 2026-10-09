#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 3 ]] || { echo "usage: $0 PRODUCT VERSION IMAGE.img" >&2; exit 2; }
[[ $EUID -eq 0 ]] || { echo 'read-only image inspection requires sudo' >&2; exit 2; }
script_dir=$(cd "$(dirname "$0")" && pwd)
python3 "$script_dir/../tools/check-delivery-policy.py" >/dev/null
image=$(realpath -e "$3")
mount_dir=$(mktemp -d)
loop=
cleanup() {
    if mountpoint -q "$mount_dir"; then umount "$mount_dir"; fi
    if [[ -n "$loop" ]]; then losetup -d "$loop"; fi
    rmdir "$mount_dir"
}
trap cleanup EXIT
loop=$(losetup --read-only --partscan --find --show "$image")
udevadm settle
partition=$(lsblk -lnpo NAME,FSTYPE "$loop" | awk '$2 ~ /^ext[234]$/ {print $1; exit}')
[[ -n "$partition" ]] || { echo 'root partition not found' >&2; exit 1; }
mount -o ro,noload "$partition" "$mount_dir"
python3 "$script_dir/verify-image-root.py" "$mount_dir" "$1" "$2"
