#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

[[ $# -eq 1 ]] || die "usage: $0 SIGNED_REPOSITORY_DIRECTORY"
repository=$(safe_realpath "$1")
require_command jq
require_command sshpass
require_command rsync
for variable in DL_HOST DL_PORT DL_USERNAME DL_PASSWORD; do
	[[ -n "${!variable:-}" ]] || die "$variable is required"
done
jq -e '.schema_version == 1 and (.channel == "testing" or .channel == "stable")' \
	"$repository/PUBLICATION.json" >/dev/null || die "invalid publication manifest"
[[ -s "$repository/SHA256SUMS" && -s "$repository/SHA256SUMS.asc" ]] || die "repository is not signed"
publication_hash=$(sha256sum "$repository/SHA256SUMS" | awk '{print $1}')
job_id="$(date -u +%Y%m%dT%H%M%SZ)-${publication_hash:0:16}"
[[ "$job_id" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{16}$ ]] || die "unsafe upload job id"
remote="${DL_USERNAME}@${DL_HOST}"
remote_dir="/home1/dlfile/_apt-upload/$job_id"
export SSHPASS=$DL_PASSWORD
ssh_options=(-p "$DL_PORT" -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${DL_KNOWN_HOSTS:?DL_KNOWN_HOSTS is required}")
sshpass -e rsync -az --delete -e "ssh ${ssh_options[*]}" "$repository/" "$remote:$remote_dir/"
sshpass -e ssh "${ssh_options[@]}" "$remote" \
	"sudo /usr/local/libexec/dl-apt-import '$job_id'"
echo "published APT job $job_id"
