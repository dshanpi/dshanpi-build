#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

[[ $# -eq 3 ]] || die "usage: $0 PRODUCT RELEASE_VERSION PACKAGE_DIRECTORY"
product=$1
release_version=$2
package_dir=$(safe_realpath "$3")
require_product "$product"
require_command jq
require_command dpkg-deb
dpkg --validate-version "$release_version" 2>/dev/null || die "invalid release version: $release_version"
work_dir=$(mktemp -d)
trap 'rm -rf -- "$work_dir"' EXIT
source_date_epoch=${SOURCE_DATE_EPOCH:-1790726400}

package_dependency() {
	local wanted=$1 wanted_arch=$2 candidate package arch
	local -a matches=()
	while IFS= read -r -d '' candidate; do
		package=$(package_field "$candidate" Package 2>/dev/null || true)
		arch=$(package_field "$candidate" Architecture 2>/dev/null || true)
		[[ "$package" == "$wanted" && "$arch" == "$wanted_arch" ]] && matches+=("$candidate")
	done < <(find "$package_dir" -maxdepth 1 -type f -name '*.deb' -print0)
	((${#matches[@]} == 1)) || die "expected exactly one $wanted/$wanted_arch package in $package_dir"
	printf '%s (= %s)' "$wanted" "$(package_field "${matches[0]}" Version)"
}

mapfile -t desktop_only < <(jq -r '.release_meta.desktop_only_dependencies[]' "$product_config")
is_desktop_only() {
	local wanted=$1 item
	for item in "${desktop_only[@]}"; do [[ "$item" == "$wanted" ]] && return 0; done
	return 1
}

core_dependencies=()
desktop_dependencies=()
while IFS=$'\t' read -r package arch; do
	dependency=$(package_dependency "$package" "$arch")
	if is_desktop_only "$package"; then
		desktop_dependencies+=("$dependency")
	else
		core_dependencies+=("$dependency")
	fi
done < <(jq -r '.required_packages[] | [.name, .arch] | @tsv' "$product_config")

join_dependencies() {
	local result= item
	for item in "$@"; do
		[[ -z "$result" ]] || result+=", "
		result+="$item"
	done
	printf '%s\n' "$result"
}

core_package=$(jq -r .release_meta.core "$product_config")
desktop_package=$(jq -r .release_meta.desktop "$product_config")
core_depends=$(join_dependencies "${core_dependencies[@]}")
# Keep both release markers independently installable while an image is being
# assembled.  The product APT repository is intentionally not enabled until
# the final image stage, so making the desktop marker depend on the core marker
# would require an unpublished package to be discoverable by APT.  Expanding
# the tested core cohort here preserves the same exact-version lock without
# introducing that bootstrap dependency.
desktop_depends=$(join_dependencies "${core_dependencies[@]}" "${desktop_dependencies[@]}")

build_meta() {
	local package=$1 depends=$2 description=$3 root="$work_dir/$package"
	mkdir -p "$root/DEBIAN"
	cat > "$root/DEBIAN/control" <<- EOF
	Package: $package
	Version: $release_version
	Architecture: all
	Maintainer: DShanPI <support@dshanpi.com>
	Depends: $depends
	Section: metapackages
	Priority: optional
	Description: $description
	 Locks one tested DShanPI platform package cohort for controlled upgrade
	 and rollback through dspi-config.
	EOF
	find "$root" -exec touch -h -d "@$source_date_epoch" {} +
	SOURCE_DATE_EPOCH=$source_date_epoch dpkg-deb --root-owner-group --build \
		"$root" "$package_dir/${package}_${release_version}_all.deb" >/dev/null
}

build_meta "$core_package" "$core_depends" "DShanPI $product tested core system release"
build_meta "$desktop_package" "$desktop_depends" "DShanPI $product tested desktop system release"
sha256sum "$package_dir/${core_package}_${release_version}_all.deb" \
	"$package_dir/${desktop_package}_${release_version}_all.deb"
