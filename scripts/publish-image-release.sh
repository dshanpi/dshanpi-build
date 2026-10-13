#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
python3 "$repo_root/tools/check-delivery-policy.py" >/dev/null

[[ $# -ge 4 && $# -le 5 ]] || die "usage: $0 PRODUCT RELEASE_LOCK ASSET_DIR TESTING|STABLE [HARDWARE_EVIDENCE]"
product=$1
lock=$(safe_realpath "$2")
asset_argument=$3
channel=${4,,}
hardware_evidence=${5:-}
[[ "$channel" == testing || "$channel" == stable ]] || die "image release channel must be testing or stable"
[[ "$channel" != stable || -n "$hardware_evidence" ]] || die "stable image promotion requires hardware evidence"

require_command gh
require_command jq
require_command curl
require_command sha256sum
[[ -n "${GH_TOKEN:-}" ]] || die "GH_TOKEN is required"
python3 "$script_dir/image-release.py" validate "$product" "$lock" >/dev/null

repository=$(jq -r .image_release.repository "$lock")
tag=$(jq -r .image_release.tag "$lock")
target=$(jq -r .image_release.target_commit "$lock")
title=$(jq -r .image_release.title "$lock")
draft=$(jq -r --arg channel "$channel" '.image_release[$channel].draft' "$lock")
prerelease=$(jq -r --arg channel "$channel" '.image_release[$channel].prerelease' "$lock")
mapfile -t expected_assets < <(jq -r '.image_release.assets[]' "$lock" | sort)

api() {
	gh api -H 'Accept: application/vnd.github+json' -H 'X-GitHub-Api-Version: 2026-03-10' "$@"
}

resolve_tag_commit() {
	local object type sha
	object=$(api "repos/$repository/git/ref/tags/$tag")
	type=$(jq -r .object.type <<<"$object")
	sha=$(jq -r .object.sha <<<"$object")
	while [[ "$type" == tag ]]; do
		object=$(api "repos/$repository/git/tags/$sha")
		type=$(jq -r .object.type <<<"$object")
		sha=$(jq -r .object.sha <<<"$object")
	done
	[[ "$type" == commit ]] || die "release tag does not resolve to a commit"
	printf '%s\n' "$sha"
}

release_json() {
	api "repos/$repository/releases/tags/$tag"
}

verify_asset_names() {
	local release=$1 actual
	actual=$(jq -r '.assets[].name' <<<"$release" | sort)
	[[ "$actual" == "$(printf '%s\n' "${expected_assets[@]}")" ]] || die "GitHub Release asset set differs from the fixed plan"
}

asset_json() {
	local release=$1 name=$2
	jq -c --arg name "$name" '.assets[] | select(.name == $name)' <<<"$release"
}

download_asset() {
	local release=$1 name=$2 destination=$3 item id
	item=$(asset_json "$release" "$name")
	[[ -n "$item" ]] || die "release asset is missing: $name"
	id=$(jq -r .id <<<"$item")
	api -H 'Accept: application/octet-stream' "repos/$repository/releases/assets/$id" > "$destination"
}

verify_local_assets() {
	local release=$1 directory=$2 name item remote_digest local_digest temporary
	verify_asset_names "$release"
	for name in "${expected_assets[@]}"; do
		item=$(asset_json "$release" "$name")
		local_digest=$(sha256sum "$directory/$name" | awk '{print $1}')
		remote_digest=$(jq -r '.digest // ""' <<<"$item")
		if [[ "$remote_digest" == sha256:* ]]; then
			[[ "${remote_digest#sha256:}" == "$local_digest" ]] || die "release asset digest mismatch: $name"
		else
			temporary=$(mktemp)
			download_asset "$release" "$name" "$temporary"
			[[ $(sha256sum "$temporary" | awk '{print $1}') == "$local_digest" ]] || {
				rm -f -- "$temporary"
				die "downloaded release asset digest mismatch: $name"
			}
			rm -f -- "$temporary"
		fi
	done
}

verify_remote_assets() (
	local release=$1 temporary sums name item expected remote_digest payload
	temporary=$(mktemp -d)
	trap 'rm -rf -- "$temporary"' EXIT
	verify_asset_names "$release"
	download_asset "$release" SHA256SUMS "$temporary/SHA256SUMS"
	download_asset "$release" release-lock.json "$temporary/release-lock.json"
	cmp -s "$lock" "$temporary/release-lock.json" || die "published release lock differs from the requested lock"
	for name in "${expected_assets[@]}"; do
		[[ "$name" == SHA256SUMS ]] && continue
		expected=$(awk -v name="$name" '$2 == name {print $1}' "$temporary/SHA256SUMS")
		[[ "$expected" =~ ^[0-9a-f]{64}$ ]] || die "published SHA256SUMS has no safe entry for $name"
		item=$(asset_json "$release" "$name")
		remote_digest=$(jq -r '.digest // ""' <<<"$item")
		if [[ "$remote_digest" == sha256:* ]]; then
			[[ "${remote_digest#sha256:}" == "$expected" ]] || die "release asset digest mismatch: $name"
		else
			payload="$temporary/$name"
			download_asset "$release" "$name" "$payload"
			[[ $(sha256sum "$payload" | awk '{print $1}') == "$expected" ]] || die "downloaded release asset digest mismatch: $name"
		fi
	done
)

api "repos/$repository/commits/$target" >/dev/null
if current_tag=$(resolve_tag_commit 2>/dev/null); then
	[[ "$current_tag" == "$target" ]] || die "release tag already points to a different commit"
fi

if [[ "$channel" == testing ]]; then
	assets=$(safe_realpath "$asset_argument")
	[[ -f "$assets/SHA256SUMS" ]] || die "prepared image release assets are missing"
	mapfile -t local_assets < <(find "$assets" -maxdepth 1 -type f -printf '%f\n' | sort)
	[[ "$(printf '%s\n' "${local_assets[@]}")" == "$(printf '%s\n' "${expected_assets[@]}")" ]] || die "local release asset set differs from the fixed plan"
	(cd "$assets" && sha256sum -c SHA256SUMS)
	notes="$assets/../release-notes.md"
	[[ -s "$notes" ]] || die "release notes are missing"

	if ! release=$(release_json 2>/dev/null); then
		gh release create "$tag" --repo "$repository" --target "$target" --title "$title" \
			--notes-file "$notes" --draft
		release=$(release_json)
	fi
	[[ $(jq -r .target_commitish <<<"$release") == "$target" ]] || die "existing release target differs from the fixed plan"
	if [[ $(jq -r .draft <<<"$release") != true ]]; then
		verify_local_assets "$release" "$assets"
	else
		for name in "${expected_assets[@]}"; do
			if item=$(asset_json "$release" "$name") && [[ -n "$item" ]]; then
				remote_digest=$(jq -r '.digest // ""' <<<"$item")
				local_digest=$(sha256sum "$assets/$name" | awk '{print $1}')
				if [[ "$remote_digest" == sha256:* ]]; then
					[[ "$remote_digest" == "sha256:$local_digest" ]] || die "existing draft asset cannot be safely reused: $name"
				else
					temporary=$(mktemp)
					download_asset "$release" "$name" "$temporary"
					[[ $(sha256sum "$temporary" | awk '{print $1}') == "$local_digest" ]] || {
						rm -f -- "$temporary"
						die "existing draft asset cannot be safely reused: $name"
					}
					rm -f -- "$temporary"
				fi
			else
				gh release upload "$tag" "$assets/$name" --repo "$repository"
			fi
		done
		release=$(release_json)
		verify_local_assets "$release" "$assets"
	fi
	body=$(cat "$notes")
else
	release=$(release_json) || die "testing image release does not exist"
	[[ $(jq -r .draft <<<"$release") == false ]] || die "cannot promote an incomplete draft image release"
	[[ $(jq -r .prerelease <<<"$release") == true ]] || die "image release is not a testing prerelease"
	verify_remote_assets "$release"
	body=$(jq -r .body <<<"$release")
	if grep -Fq '## Stable hardware evidence' <<<"$body"; then
		grep -Fq -- "- $hardware_evidence" <<<"$body" || die "stable release already records different hardware evidence"
	else
		body+=$'\n\n## Stable hardware evidence\n\n'
		body+="- $hardware_evidence"
		body+=$'\n'
	fi
fi

release_id=$(jq -r .id <<<"$release")
jq -n --arg name "$title" --arg body "$body" --argjson draft "$draft" --argjson prerelease "$prerelease" \
	'{name: $name, body: $body, draft: $draft, prerelease: $prerelease}' |
	api --method PATCH "repos/$repository/releases/$release_id" --input - >/dev/null

release=$(release_json)
[[ $(resolve_tag_commit) == "$target" ]] || die "published tag commit mismatch"
[[ $(jq -r .draft <<<"$release") == "$draft" ]] || die "published draft state mismatch"
[[ $(jq -r .prerelease <<<"$release") == "$prerelease" ]] || die "published prerelease state mismatch"
if [[ "$channel" == testing ]]; then
	verify_local_assets "$release" "$assets"
else
	verify_remote_assets "$release"
fi
curl --fail --silent --show-error --location --head "$(jq -r .html_url <<<"$release")" >/dev/null
echo "verified $channel image release: $(jq -r .html_url <<<"$release")"
