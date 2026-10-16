#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ssh-transport.sh"
[[ $# -eq 2 ]] || die "usage: $0 OUTPUT_DIRECTORY PUBLIC_KEY"
[[ ! -e "$1" ]] || die "output directory must not exist"
public_key=$(safe_realpath "$2")
apt_ssh_init
# Resolve current once: a concurrent switch must not mix two snapshots.
previous=$(apt_remote_run current "$apt_server_root")
[[ "$previous" == "$apt_server_root/releases/"* ]] || die "server has not been initialized; run Migrate APT repository to SSH server first"
mkdir -p "$1"
sshpass -e rsync -rlt --safe-links -e "$apt_rsync_shell" "$apt_remote:$previous/" "$1/"
python3 "$script_dir/verify-repository.py" --snapshot "$1" "$public_key" "$1"
