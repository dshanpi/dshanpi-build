#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ssh-transport.sh"
python3 "$repo_root/tools/check-delivery-policy.py" >/dev/null
[[ $# -ge 1 && $# -le 3 ]] || die "usage: $0 SIGNED_REPOSITORY [PUBLIC_KEY] [--bootstrap]"
repository=$(safe_realpath "$1")
public_key=$(safe_realpath "${2:-$repo_root/keys/dshanpi-archive.asc}")
mode=${3:-publish}
[[ "$mode" == publish || "$mode" == --bootstrap ]] || die "invalid publication mode"
"$script_dir/prepare-apt-site.sh" "$repository" "$public_key"
apt_ssh_init
publication_hash=$(sha256sum "$repository/SHA256SUMS" | cut -d ' ' -f 1)
job_id=${APT_RESUME_JOB_ID:-"$(date -u +%Y%m%dT%H%M%SZ)-${publication_hash:0:16}-${RANDOM}"}
[[ "$job_id" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{16}-[0-9]+$ ]] || die "invalid upload job identifier"
upload="$apt_server_root/incoming/$job_id"
if [[ -z "${APT_RESUME_JOB_ID:-}" ]]; then
    previous=$(apt_remote_run prepare "$apt_server_root" "$job_id" "$mode")
    # --link-dest reuses verified files in the previous snapshot. Never use
    # --inplace: it could modify files hard-linked to a live or retained release.
    link_options=()
    [[ "$previous" == none ]] || link_options=(--link-dest="$previous")
    sshpass -e rsync -rlp --checksum --chmod=D755,F644 --delay-updates \
        "${link_options[@]}" -e "$apt_rsync_shell" "$repository/" "$apt_remote:$upload/repository/"
fi
# A verification-only retry updates the verifier/public key, never the payload.
# The server still checks the complete expected SHA256SUMS, signatures and history.
sshpass -e rsync -rt -e "$apt_rsync_shell" \
    "$script_dir/verify-repository.py" "$public_key" "$apt_remote:$upload/control/"
apt_remote_run "$mode" "$apt_server_root" "$job_id" "$publication_hash" "$(basename "$public_key")"
echo "Published signed APT snapshot $job_id to $apt_server_root/current"
