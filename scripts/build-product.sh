#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

[[ $# -ge 2 && $# -le 3 ]] || die "usage: $0 PRODUCT RELEASE_LOCK [--print-plan]"
product=$1
lock=$(safe_realpath "$2")
mode=${3:-execute}
[[ "$mode" == execute || "$mode" == --print-plan ]] || die "unknown mode: $mode"
require_command jq
require_product "$product"
validate_release_lock "$product" "$lock"
version=$(jq -r .version "$lock")
revision=$(jq -r .revision "$lock")
board=$(jq -r .armbian.board "$product_config")
branch=$(jq -r .armbian.branch "$product_config")
release=$(jq -r .armbian.release "$product_config")
desktop_environment=$(jq -r .armbian.desktop_environment "$product_config")
desktop_config=$(jq -r .armbian.desktop_config "$product_config")
work_root=${DSHANPI_WORK_ROOT:-$repo_root/work/$product/$version}
output_root=${DSHANPI_OUTPUT_ROOT:-$repo_root/output/$product/$version}

if [[ "$mode" == --print-plan ]]; then
	cat <<- EOF
	product=$product
	version=$version
	revision=$revision
	board=$board
	branch=$branch
	release=$release
	variants=cli desktop
	armbianos_commit=$(jq -r .sources.armbianos.commit "$lock")
	dspi_config_commit=$(jq -r .sources.dspi_config.commit "$lock")
	EOF
	exit 0
fi

[[ -n "${APT_PUBLIC_KEY_FILE:-}" ]] || die "APT_PUBLIC_KEY_FILE is required"
mkdir -p "$work_root/sources" "$output_root/client" "$output_root/packages" "$output_root/images"

prepare_source() {
	local name=$1 override=$2 url commit destination
	url=$(jq -r --arg name "$name" '.sources[$name]' "$product_config")
	commit=$(jq -r --arg name "$name" '.sources[$name].commit' "$lock")
	destination="$work_root/sources/$name"
	if [[ -n "$override" ]]; then
		destination=$(safe_realpath "$override")
	elif [[ ! -d "$destination/.git" ]]; then
		"$script_dir/checkout-source.sh" "$url" "$commit" "$destination"
	fi
	[[ -d "$destination/.git" ]] || die "$name source is not a Git checkout: $destination"
	[[ $(git -C "$destination" rev-parse HEAD) == "$commit" ]] || die "$name source does not match release lock"
	if [[ "${DSHANPI_ALLOW_DIRTY_SOURCES:-no}" != yes && -n "$(git -C "$destination" status --porcelain --untracked-files=no)" ]]; then
		die "$name source has tracked changes"
	fi
	printf '%s\n' "$destination"
}

armbian_dir=$(prepare_source armbianos "${DSHANPI_ARMBIANOS_DIR:-}")
dspi_dir=$(prepare_source dspi_config "${DSHANPI_DSPI_CONFIG_DIR:-}")
dspi_output="$output_root/dspi"
"$dspi_dir/packaging/build-deb.sh" "$dspi_output"
dspi_deb=$(find "$dspi_output" -maxdepth 1 -type f -name 'dspi-config_*_all.deb' -print -quit)
[[ -n "$dspi_deb" ]] || die "dspi-config build did not produce a package"
"$script_dir/build-client-packages.sh" "$product" "$version" "$APT_PUBLIC_KEY_FILE" \
	"${DSHANPI_APT_BASE_URL:-https://dl.100ask.net}" "$output_root/client"

common_args=(build "BOARD=$board" "BRANCH=$branch" "RELEASE=$release" \
	"REVISION=$revision" KERNEL_CONFIGURE=no PREFER_DOCKER=no \
	"DSHANPI_DSPI_CONFIG_DEB=$dspi_deb" \
	"DSHANPI_REPO_CLIENT_PACKAGES_DIR=$output_root/client")

# Artifact pass: create every board-owned package before the release meta-package.
(cd "$armbian_dir" && ./compile.sh "${common_args[@]}" BUILD_DESKTOP=yes \
	DESKTOP_APPGROUPS_SELECTED= "DESKTOP_ENVIRONMENT=$desktop_environment" \
	"DESKTOP_ENVIRONMENT_CONFIG_NAME=$desktop_config")

"$script_dir/collect-packages.sh" "$product" "$output_root/packages" \
	"$armbian_dir/output/debs" "$armbian_dir/output/dshanpi-packages" \
	"$output_root/client" "$dspi_output"
"$script_dir/build-release-meta.sh" "$product" "$version" "$output_root/packages"
core_meta=$(find "$output_root/packages" -maxdepth 1 -name "${product}-release-core_${version}_all.deb" -print -quit)
desktop_meta=$(find "$output_root/packages" -maxdepth 1 -name "${product}-release-desktop_${version}_all.deb" -print -quit)
[[ -n "$core_meta" && -n "$desktop_meta" ]] || die "release meta-package build failed"

# Final images carry a release identity from first boot.
(cd "$armbian_dir" && ./compile.sh "${common_args[@]}" BUILD_DESKTOP=no \
	"DSHANPI_RELEASE_META_DEB=$core_meta")
(cd "$armbian_dir" && ./compile.sh "${common_args[@]}" BUILD_DESKTOP=yes \
	DESKTOP_APPGROUPS_SELECTED= "DESKTOP_ENVIRONMENT=$desktop_environment" \
	"DESKTOP_ENVIRONMENT_CONFIG_NAME=$desktop_config" \
	"DSHANPI_RELEASE_META_DEB=$desktop_meta")

find "$armbian_dir/output/images" -maxdepth 1 -type f \
	\( -name '*.img' -o -name '*.img.sha' -o -name '*.img.gz' \) -exec cp -- {} "$output_root/images/" \;
find "$output_root/packages" -maxdepth 1 -type f -name '*.deb' -print0 | sort -z | xargs -0 sha256sum > "$output_root/packages/SHA256SUMS"
echo "built $product $version into $output_root"
