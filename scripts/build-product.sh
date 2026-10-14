#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
python3 "$repo_root/tools/check-delivery-policy.py" >/dev/null

[[ $# -ge 2 && $# -le 3 ]] || die "usage: $0 PRODUCT RELEASE_LOCK [--print-plan|--packages-only|--images-only]"
product=$1
lock=$(safe_realpath "$2")
mode=${3:-execute}
[[ "$mode" == execute || "$mode" == --print-plan || "$mode" == --packages-only || "$mode" == --images-only ]] || die "unknown mode: $mode"
packages_only=no
[[ "$mode" != --packages-only ]] || packages_only=yes
images_only=no
[[ "$mode" != --images-only ]] || images_only=yes
images_only_lib_config=
cleanup_images_only_config() {
	[[ -z "$images_only_lib_config" ]] || rm -f -- "$images_only_lib_config"
}
trap cleanup_images_only_config EXIT
require_command jq
require_product "$product"
validate_release_lock "$product" "$lock"
if jq -e 'has("maintenance_adapter")' "$lock" >/dev/null; then
	die "package maintenance lock: use the matching scripts/build-<adapter>-release.py, not the image builder"
fi
version=$(jq -r .version "$lock")
revision=$(jq -r .revision "$lock")
board=$(jq -r .armbian.board "$product_config")
branch=$(jq -r .armbian.branch "$product_config")
release=$(jq -r .armbian.release "$product_config")
desktop_environment=$(jq -r .armbian.desktop_environment "$product_config")
desktop_config=$(jq -r .armbian.desktop_config "$product_config")
work_root=${DSHANPI_WORK_ROOT:-$repo_root/work/$product/$version}
output_root=${DSHANPI_OUTPUT_ROOT:-$repo_root/output/$product/$version}
release_extensions=dshanpi-product-profile,dshanpi-dspi-config,dshanpi-repository

if [[ "$mode" == --print-plan ]]; then
	cat <<- EOF
	product=$product
	version=$version
	revision=$revision
	board=$board
	branch=$branch
	release=$release
	variants=cli desktop
	armbian_extensions=$release_extensions,dshanpi-release-meta
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
	elif ! git -C "$destination" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
		"$script_dir/checkout-source.sh" "$url" "$commit" "$destination"
	fi
	[[ $(git -C "$destination" rev-parse --is-inside-work-tree 2>/dev/null) == true ]] ||
		die "$name source is not a Git checkout: $destination"
	[[ $(git -C "$destination" rev-parse HEAD) == "$commit" ]] || die "$name source does not match release lock"
	if [[ "${DSHANPI_ALLOW_DIRTY_SOURCES:-no}" != yes && -n "$(git -C "$destination" status --porcelain --untracked-files=no)" ]]; then
		die "$name source has tracked changes"
	fi
	printf '%s\n' "$destination"
}

armbian_dir=$(prepare_source armbianos "${DSHANPI_ARMBIANOS_DIR:-}")
dspi_dir=$(prepare_source dspi_config "${DSHANPI_DSPI_CONFIG_DIR:-}")
if [[ "$images_only" == yes ]]; then
	# Armbian sources lib.config after board/family configuration.  A private,
	# short-lived override is therefore the supported way to prevent the normal
	# artifact pass from rebuilding a kernel that the signed release meta-package
	# will install below.  Never replace a caller-owned user override.
	images_only_config_target="$armbian_dir/userpatches/lib.config"
	[[ ! -e "$images_only_config_target" ]] ||
		die "images-only build refuses to replace existing user configuration: $images_only_config_target"
	mkdir -p "$(dirname "$images_only_config_target")"
	cat > "$images_only_config_target" <<- 'EOF'
		[[ -n "${DSHANPI_RELEASE_PACKAGES_DIR:-}" ]] || {
			echo "images-only user configuration requires DSHANPI_RELEASE_PACKAGES_DIR" >&2
			exit 1
		}
		KERNELSOURCE=none
	EOF
	images_only_lib_config=$images_only_config_target
	python3 "$script_dir/fetch-public-release.py" \
		"${DSHANPI_APT_BASE_URL:-https://apt.100ask.net}" "$product_config" "$lock" \
		"$output_root/packages" "$APT_PUBLIC_KEY_FILE"
	# Seed the normal Armbian revisioned cache with the same verified public
	# bytes.  This prevents firmware/base/BSP artifact resolution from cloning
	# sources or substituting a separately rebuilt package during image assembly.
	while IFS= read -r -d '' package_file; do
		package_name=$(package_field "$package_file" Package)
		case "$package_name" in
			armbian-firmware | armbian-bsp-cli-*)
				cache_dir="$armbian_dir/output/debs" ;;
			base-files)
				cache_dir="$armbian_dir/output/debs/extra/$release-utils" ;;
			armbian-bsp-desktop-*)
				cache_dir="$armbian_dir/output/debs/extra/$release-desktop" ;;
			*) continue ;;
		esac
		cache_file="$cache_dir/$(basename "$package_file")"
		mkdir -p "$cache_dir"
		if [[ -e "$cache_file" ]]; then
			cmp -s -- "$package_file" "$cache_file" ||
				die "Armbian cache contains different bytes for signed package: $cache_file"
		else
			cp -- "$package_file" "$cache_file"
		fi
	done < <(find "$output_root/packages" -maxdepth 1 -type f -name '*.deb' -print0)
	dspi_deb=$(find "$output_root/packages" -maxdepth 1 -type f -name 'dspi-config_*_all.deb' -print -quit)
	client_packages_dir="$output_root/packages"
else
	dspi_output="$output_root/dspi"
	"$dspi_dir/packaging/build-deb.sh" "$dspi_output"
	dspi_deb=$(find "$dspi_output" -maxdepth 1 -type f -name 'dspi-config_*_all.deb' -print -quit)
	"$script_dir/build-client-packages.sh" "$product" "1:$version" "$APT_PUBLIC_KEY_FILE" \
		"${DSHANPI_APT_BASE_URL:-https://apt.100ask.net}" "$output_root/client"
	client_packages_dir="$output_root/client"
fi
[[ -n "$dspi_deb" ]] || die "fixed package cohort does not contain dspi-config"

common_args=("BOARD=$board" "BRANCH=$branch" "RELEASE=$release" \
	"REVISION=$revision" KERNEL_CONFIGURE=no PREFER_DOCKER=no BUILD_MINIMAL=no \
	DEB_COMPRESS=xz COLUMNS=160 "MAKE_FOLDERS=dshanpi-$version" \
	"DSHANPI_PRODUCT=$product" \
	"DSHANPI_DSPI_CONFIG_DEB=$dspi_deb" \
	"DSHANPI_REPO_CLIENT_PACKAGES_DIR=$client_packages_dir")

# Artifact pass: create every board-owned package before the release meta-package.
# Package-only CI deliberately invokes artifact commands and never enters Armbian's
# rootfs/image assembler. The controlled local full build uses the normal image
# command so the candidate image exercises the same package-producing path.
if [[ "$images_only" == yes ]]; then
	: # The signed public cohort is the complete image input; do not rebuild DEBs.
elif [[ "$packages_only" == yes ]]; then
	for artifact in kernel firmware armbian-base-files armbian-bsp-cli armbian-bsp-desktop; do
		artifact_args=()
		if [[ "$artifact" == armbian-bsp-desktop ]]; then
			artifact_args+=(BUILD_DESKTOP=yes "DESKTOP_ENVIRONMENT=$desktop_environment" \
				"DESKTOP_ENVIRONMENT_CONFIG_NAME=$desktop_config")
		fi
		(cd "$armbian_dir" && ./compile.sh "$artifact" "${common_args[@]}" \
			"EXT=$release_extensions" "${artifact_args[@]}")
	done
else
	(cd "$armbian_dir" && ./compile.sh build "${common_args[@]}" "EXT=$release_extensions" BUILD_DESKTOP=yes \
		DESKTOP_APPGROUPS_SELECTED= "DESKTOP_ENVIRONMENT=$desktop_environment" \
		"DESKTOP_ENVIRONMENT_CONFIG_NAME=$desktop_config")
fi

if [[ "$images_only" != yes ]]; then
while IFS= read -r adapter; do
	case "$adapter" in
		rkaiq-reviewed)
			"$script_dir/build-reviewed-camera.sh" "$armbian_dir" "$output_root/adapters" "$version" ;;
		*) die "unknown product package adapter: $adapter" ;;
	esac
done < <(jq -r '.package_adapters // [] | .[]' "$product_config")

package_search_roots=()
release_optionals="$output_root/release-optionals"
if jq -e '.release_package_sets // [] | length > 0' "$product_config" >/dev/null; then
	[[ -n "${DSHANPI_PUBLISHED_REPOSITORY:-}" ]] ||
		die "release-bound optional packages require DSHANPI_PUBLISHED_REPOSITORY"
	python3 "$script_dir/verify-repository.py" --snapshot \
		"$DSHANPI_PUBLISHED_REPOSITORY" "$APT_PUBLIC_KEY_FILE" "$DSHANPI_PUBLISHED_REPOSITORY"
	python3 "$script_dir/build-release-optionals.py" "$product" "$lock" \
		"$DSHANPI_PUBLISHED_REPOSITORY" "$release_optionals"
	package_search_roots+=("$release_optionals")
fi
generated_packages="$output_root/generated-packages"
mkdir -p "$generated_packages"
while IFS= read -r relative_path; do
	[[ "$relative_path" =~ ^[A-Za-z0-9._/-]+$ && "$relative_path" != /* && "$relative_path" != *..* ]] ||
		die "unsafe package search path in product configuration: $relative_path"
	if [[ "$relative_path" == output/debs ]]; then
		# Armbian's cache also contains older revisions and unrelated boards.
		# Retain strict duplicate checks within this release's revision.
		while IFS= read -r -d '' deb; do
			package_version=$(package_field "$deb" Version)
			[[ "$package_version" == "$revision" || "$package_version" == "$revision-"* ]] || continue
			cp -- "$deb" "$generated_packages/"
		done < <(find "$armbian_dir/$relative_path" -type f -name "*_${revision}*.deb" -print0)
		package_search_roots+=("$generated_packages")
	elif [[ "$relative_path" == output/dshanpi-packages ]] &&
		jq -e '.package_adapters // [] | index("rkaiq-reviewed") != null' "$product_config" >/dev/null; then
		package_search_roots+=("$output_root/adapters")
	elif [[ -d "$armbian_dir/$relative_path" ]]; then
		package_search_roots+=("$armbian_dir/$relative_path")
	fi
done < <(jq -r '.package_search_paths[]' "$product_config")
package_search_roots+=("$output_root/client" "$dspi_output")
"$script_dir/collect-packages.sh" "$product" "$output_root/packages" "${package_search_roots[@]}"
# Cached Armbian artifacts can still use uncompressed tar members even when
# DEB_COMPRESS=xz was requested. Normalize only these unpublished copies.
for deb in "$output_root/packages"/*.deb; do
	if ar t "$deb" | grep -Fxq data.tar; then
		"$script_dir/compress-deb.sh" "$deb" "$deb.compressed"
		mv "$deb.compressed" "$deb"
	fi
done
if [[ -n "${DSHANPI_PUBLISHED_REPOSITORY:-}" ]]; then
	python3 "$script_dir/reuse-published-packages.py" "$output_root/packages" \
		"$DSHANPI_PUBLISHED_REPOSITORY" "$APT_PUBLIC_KEY_FILE" "$product_config"
fi
"$script_dir/audit-packages.sh" "$output_root/packages"
"$script_dir/build-release-meta.sh" "$product" "$version" "$output_root/packages"
core_meta=$(find "$output_root/packages" -maxdepth 1 -name "${product}-release-core_${version}_all.deb" -print -quit)
desktop_meta=$(find "$output_root/packages" -maxdepth 1 -name "${product}-release-desktop_${version}_all.deb" -print -quit)
[[ -n "$core_meta" && -n "$desktop_meta" ]] || die "release meta-package build failed"
find "$output_root/packages" -maxdepth 1 -type f -name '*.deb' -print0 | sort -z | xargs -0 sha256sum > "$output_root/packages/SHA256SUMS"
else
	"$script_dir/audit-packages.sh" "$output_root/packages"
fi

core_meta=$(find "$output_root/packages" -maxdepth 1 -name "${product}-release-core_${version}_all.deb" -print -quit)
desktop_meta=$(find "$output_root/packages" -maxdepth 1 -name "${product}-release-desktop_${version}_all.deb" -print -quit)
[[ -n "$core_meta" && -n "$desktop_meta" ]] || die "release meta-package cohort is incomplete"

if [[ "$packages_only" == yes ]]; then
	echo "built $product $version package cohort into $output_root/packages"
	exit 0
fi

# Final images carry a release identity from first boot.
(cd "$armbian_dir" && ./compile.sh build "${common_args[@]}" "EXT=$release_extensions,dshanpi-release-meta" BUILD_DESKTOP=no \
	"DSHANPI_RELEASE_PACKAGES_DIR=$output_root/packages" \
	"DSHANPI_RELEASE_META_DEB=$core_meta")
(cd "$armbian_dir" && ./compile.sh build "${common_args[@]}" "EXT=$release_extensions,dshanpi-release-meta" BUILD_DESKTOP=yes \
	DESKTOP_APPGROUPS_SELECTED= "DESKTOP_ENVIRONMENT=$desktop_environment" \
	"DESKTOP_ENVIRONMENT_CONFIG_NAME=$desktop_config" \
	"DSHANPI_RELEASE_PACKAGES_DIR=$output_root/packages" \
	"DSHANPI_RELEASE_META_DEB=$desktop_meta")

image_dir="$armbian_dir/output/images/$board/dshanpi-$version"
if jq -e '.image_release' "$lock" >/dev/null; then
	# An images-only assembly deliberately skips kernel source checkout and lets
	# the signed release meta-package install the exact kernel cohort. Armbian
	# therefore labels its temporary output "generic" even though verification
	# below confirms the installed ABI. Normalize those outputs to the immutable
	# filenames fixed in the release lock before they leave the builder.
	cli_image=$(find "$image_dir" -maxdepth 1 -type f -name '*.img' ! -name '*_desktop.img' -print -quit)
	desktop_image=$(find "$image_dir" -maxdepth 1 -type f -name '*_desktop.img' -print -quit)
	[[ -n "$cli_image" && -n "$desktop_image" ]] || die "cannot identify one CLI and one desktop image"
	for variant in cli desktop; do
		if [[ "$variant" == cli ]]; then source_image=$cli_image; else source_image=$desktop_image; fi
		expected_name=$(jq -r --arg variant "$variant" \
			'.image_release.variants[] | select(.name == $variant) | .image' "$lock")
		[[ "$expected_name" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]*\.img$ ]] ||
			die "unsafe fixed image filename for $variant: $expected_name"
		if [[ $(basename "$source_image") != "$expected_name" ]]; then
			[[ -f "$source_image.sha" ]] || die "image checksum sidecar is missing: $source_image.sha"
			(cd "$image_dir" && sha256sum -c "$(basename "$source_image").sha")
			[[ ! -e "$image_dir/$expected_name" && ! -e "$image_dir/$expected_name.sha" ]] ||
				die "fixed image target already exists: $expected_name"
			mv -- "$source_image" "$image_dir/$expected_name"
			rm -- "$source_image.sha"
			(cd "$image_dir" && sha256sum "$expected_name" > "$expected_name.sha")
		fi
	done
fi

image_count=0
while IFS= read -r -d '' image; do
    sudo "$script_dir/verify-image.sh" "$product" "$version" "$image"
    image_count=$((image_count + 1))
done < <(find "$image_dir" -maxdepth 1 -type f -name '*.img' -print0)
[[ "$image_count" -eq 2 ]] || die "expected exactly two verified CLI/Desktop images, found $image_count"
find "$image_dir" -maxdepth 1 -type f \
	\( -name '*.img' -o -name '*.img.sha' -o -name '*.img.gz' \) -exec cp -- {} "$output_root/images/" \;
echo "built $product $version into $output_root"
