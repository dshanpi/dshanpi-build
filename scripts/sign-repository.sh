#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

[[ $# -eq 2 ]] || die "usage: $0 REPOSITORY_DIRECTORY GPG_FINGERPRINT"
repository=$(safe_realpath "$1")
fingerprint=${2^^}
[[ "$fingerprint" =~ ^[0-9A-F]{40}$ ]] || die "GPG fingerprint must contain exactly 40 hex characters"
require_command gpg
gpg --batch --list-secret-keys "$fingerprint" >/dev/null 2>&1 || die "APT signing secret key is unavailable"
gpg_sign=(gpg --batch --yes --pinentry-mode loopback --local-user "$fingerprint" --digest-algo SHA256)
if [[ -n "${APT_GPG_PASSPHRASE:-}" ]]; then
	gpg_sign+=(--passphrase "$APT_GPG_PASSPHRASE")
fi

while IFS= read -r -d '' release; do
	directory=$(dirname "$release")
	"${gpg_sign[@]}" \
		--clearsign --output "$directory/InRelease" "$release"
	"${gpg_sign[@]}" \
		--armor --detach-sign --output "$directory/Release.gpg" "$release"
done < <(find "$repository/dists" -mindepth 2 -maxdepth 2 -type f -name Release -print0 | sort -z)

while IFS= read -r -d '' manifest; do
	"${gpg_sign[@]}" \
		--armor --detach-sign --output "${manifest}.asc" "$manifest"
done < <(find "$repository/catalog/releases" -type f -name '*.json' -print0 2>/dev/null | sort -z)

(
	cd "$repository"
	find PUBLICATION.json catalog dists pool -type f ! -name SHA256SUMS ! -name SHA256SUMS.asc -print0 |
		sort -z | xargs -0 sha256sum > SHA256SUMS
)
"${gpg_sign[@]}" \
	--armor --detach-sign --output "$repository/SHA256SUMS.asc" "$repository/SHA256SUMS"

echo "signed repository with $fingerprint"
