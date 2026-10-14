#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

[[ $# -eq 4 ]] || die "usage: $0 PRODUCT RELEASE_LOCK ASSET_DIRECTORY RELEASE_NOTES"
[[ ${GITHUB_ACTIONS:-false} != true ]] || die "direct image publication is forbidden in GitHub Actions"
require_command gh
require_command jq

product=$1
lock=$(safe_realpath "$2")
assets=$(safe_realpath "$3")
notes=$(safe_realpath "$4")
require_product "$product"
validate_release_lock "$product" "$lock"
python3 "$script_dir/check-release-executor.py" "$lock" testing local
python3 "$script_dir/image-release.py" validate "$product" "$lock"
[[ -d "$assets" && -f "$notes" ]] || die "prepared image assets and release notes are required"

repository=$(jq -r '.image_release.repository' "$lock")
tag=$(jq -r '.image_release.tag' "$lock")
target=$(jq -r '.image_release.target_commit' "$lock")
title=$(jq -r '.image_release.title' "$lock")
mapfile -t names < <(jq -r '.image_release.assets[]' "$lock")
paths=()
for name in "${names[@]}"; do
	[[ "$name" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]*$ ]] || die "unsafe image asset name: $name"
	[[ -f "$assets/$name" ]] || die "missing fixed image asset: $name"
	paths+=("$assets/$name")
done
[[ $(find "$assets" -maxdepth 1 -type f | wc -l) -eq ${#paths[@]} ]] ||
	die "asset directory contains files outside the fixed release plan"
if gh release view "$tag" -R "$repository" >/dev/null 2>&1; then
	die "image release already exists and will not be overwritten: $repository/$tag"
fi

gh release create "$tag" "${paths[@]}" -R "$repository" --target "$target" \
	--title "$title" --notes-file "$notes" --prerelease
gh release view "$tag" -R "$repository" --json url --jq .url
