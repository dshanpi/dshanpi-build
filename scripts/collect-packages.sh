#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

[[ $# -ge 3 ]] || die "usage: $0 PRODUCT OUTPUT_DIR SEARCH_ROOT..."
product=$1
output_dir=$2
shift 2
require_product "$product"
require_command jq
require_command dpkg-deb
mkdir -p "$output_dir"
output_dir=$(realpath "$output_dir")
if find "$output_dir" -mindepth 1 -maxdepth 1 -type f -name '*.deb' -print -quit | grep -q .; then
	die "output package directory must not already contain deb files: $output_dir"
fi

declare -A candidates=()
while IFS= read -r -d '' deb; do
	package=$(package_field "$deb" Package 2>/dev/null || true)
	arch=$(package_field "$deb" Architecture 2>/dev/null || true)
	[[ -n "$package" && -n "$arch" ]] || continue
	key="$package|$arch"
	candidates[$key]+="$deb"$'\n'
done < <(find "$@" -type f -name '*.deb' -print0)

while IFS=$'\t' read -r package arch; do
	key="$package|$arch"
	mapfile -t matches < <(printf '%s' "${candidates[$key]:-}" | sed '/^$/d')
	((${#matches[@]} == 1)) || die "expected exactly one $package/$arch package, found ${#matches[@]}"
	filename=$(basename "${matches[0]}")
	[[ ! -e "$output_dir/$filename" ]] || die "duplicate output filename: $filename"
	cp -- "${matches[0]}" "$output_dir/$filename"
done < <(jq -r '.required_packages[] | [.name, .arch] | @tsv' "$product_config")

for deb in "$output_dir"/*.deb; do
	package=$(package_field "$deb" Package)
	while IFS= read -r pattern; do
		[[ "$package" =~ $pattern ]] && die "forbidden OTA package: $package"
	done < <(jq -r '.forbidden_package_patterns[]' "$product_config")
done

find "$output_dir" -maxdepth 1 -type f -name '*.deb' -print0 | sort -z | xargs -0 sha256sum > "$output_dir/SHA256SUMS"
cat "$output_dir/SHA256SUMS"
