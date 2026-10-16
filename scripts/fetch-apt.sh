#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ssh-transport.sh"
[[ $# -eq 2 || $# -eq 3 ]] || die "usage: $0 OUTPUT_DIRECTORY PUBLIC_KEY [VERIFIED_LOCAL_CACHE]"
[[ ! -e "$1" ]] || die "output directory must not exist"
public_key=$(safe_realpath "$2")
transfer_options=(-t)
if [[ $# -eq 3 ]]; then
    cache=$(safe_realpath "$3")
    python3 "$script_dir/verify-repository.py" --snapshot "$cache" "$public_key" "$cache"
    # Compare remote contents, not timestamps. Reuse identical verified files
    # without downloading them again; the final full signature/SHA check remains.
    transfer_options=(--checksum --link-dest="$cache")
fi
apt_ssh_init
# Resolve current once: a concurrent switch must not mix two snapshots.
previous=$(apt_remote_run current "$apt_server_root")
[[ "$previous" == "$apt_server_root/releases/"* ]] || die "server has not been initialized; run Migrate APT repository to SSH server first"
mkdir -p "$1"
sshpass -e rsync -rl "${transfer_options[@]}" --safe-links -e "$apt_rsync_shell" "$apt_remote:$previous/" "$1/"
python3 "$script_dir/verify-repository.py" --snapshot "$1" "$public_key" "$1"
