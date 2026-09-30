#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)

die() {
	echo "dshanpi-build: $*" >&2
	exit 1
}

require_command() {
	command -v "$1" >/dev/null || die "missing required command: $1"
}

require_product() {
	local product=$1
	product_config="$repo_root/products/$product/product.json"
	[[ -f "$product_config" ]] || die "unknown product: $product"
	jq -e --arg product "$product" \
		'.schema_version == 1 and .product == $product' "$product_config" >/dev/null ||
		die "invalid product configuration: $product_config"
}

validate_release_lock() {
	local product=$1 lock=$2
	[[ -f "$lock" ]] || die "release lock is missing: $lock"
	jq -e --arg product "$product" '
		.schema_version == 1 and
		.product == $product and
		(.version | test("^[0-9]{4}\\.[0-9]{2}\\.[0-9]{2}-[1-9][0-9]*$")) and
		(.revision | type == "string" and length > 0) and
		(.sources.armbianos.commit | test("^[0-9a-f]{40}$")) and
		(.sources.dspi_config.commit | test("^[0-9a-f]{40}$"))
	' "$lock" >/dev/null || die "invalid or unpinned release lock: $lock"
}

package_field() {
	dpkg-deb -f "$1" "$2"
}

package_identity() {
	printf '%s\t%s\t%s\n' \
		"$(package_field "$1" Package)" \
		"$(package_field "$1" Version)" \
		"$(package_field "$1" Architecture)"
}

safe_realpath() {
	local path
	path=$(realpath -e "$1")
	[[ "$path" == /* && "$path" != / ]] || die "unsafe path: $1"
	printf '%s\n' "$path"
}
