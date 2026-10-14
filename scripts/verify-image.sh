#!/usr/bin/env bash
set -euo pipefail
[[ $# -eq 3 ]] || { echo "usage: $0 PRODUCT VERSION IMAGE.img" >&2; exit 2; }
[[ $EUID -eq 0 ]] || { echo 'read-only image inspection requires sudo' >&2; exit 2; }
script_dir=$(cd "$(dirname "$0")" && pwd)
python3 "$script_dir/../tools/check-delivery-policy.py" >/dev/null
image=$(realpath -e "$3")
mount_dir=$(mktemp -d)
loop=
boot_mounted=no
cleanup() {
    if [[ "$boot_mounted" == yes ]] && mountpoint -q "$mount_dir/boot"; then umount "$mount_dir/boot"; fi
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
boot_partition=$(lsblk -lnpo NAME,FSTYPE "$loop" | awk '$2 ~ /^(vfat|fat)$/ {print $1; exit}')
if [[ -n "$boot_partition" ]]; then
    [[ -d "$mount_dir/boot" ]] || { echo 'boot mount point not found in root filesystem' >&2; exit 1; }
    mount -o ro "$boot_partition" "$mount_dir/boot"
    boot_mounted=yes
fi
python3 "$script_dir/verify-image-root.py" "$mount_dir" "$1" "$2"
