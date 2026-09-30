#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

[[ $# -eq 5 ]] || die "usage: $0 PRODUCT VERSION PUBLIC_KEY BASE_URL OUTPUT_DIR"
product=$1
version=$2
public_key=$(safe_realpath "$3")
base_url=${4%/}
output_dir=$5
require_product "$product"
require_command gpg
require_command dpkg-deb
dpkg --validate-version "$version" 2>/dev/null || die "invalid package version: $version"
[[ "$base_url" == https://* || "$base_url" == http://127.0.0.1:* ]] || die "APT base URL must use HTTPS"
mkdir -p "$output_dir"
output_dir=$(realpath "$output_dir")
work_dir=$(mktemp -d)
trap 'rm -rf -- "$work_dir"' EXIT
source_date_epoch=${SOURCE_DATE_EPOCH:-1790726400}
components="common $(jq -r .component "$product_config")"
codename=$(jq -r .codename "$product_config")
repository_package="${product}-repository"

build_deb() {
	local root=$1 output=$2
	find "$root" -exec touch -h -d "@$source_date_epoch" {} +
	SOURCE_DATE_EPOCH=$source_date_epoch dpkg-deb --root-owner-group --build "$root" "$output" >/dev/null
}

key_root="$work_dir/keyring"
mkdir -p "$key_root/DEBIAN" "$key_root/usr/share/keyrings"
gpg --batch --yes --dearmor --output "$key_root/usr/share/keyrings/dshanpi-archive-keyring.gpg" "$public_key"
cat > "$key_root/DEBIAN/control" <<- EOF
Package: dshanpi-archive-keyring
Version: $version
Architecture: all
Maintainer: DShanPI <support@dshanpi.com>
Section: misc
Priority: optional
Description: DShanPI APT archive signing key
 Public key used to authenticate packages from dl.100ask.net/apt.
EOF
build_deb "$key_root" "$output_dir/dshanpi-archive-keyring_${version}_all.deb"

source_root="$work_dir/source"
mkdir -p "$source_root/DEBIAN" "$source_root/etc/apt/sources.list.d"
cat > "$source_root/DEBIAN/control" <<- EOF
Package: $repository_package
Version: $version
Architecture: all
Maintainer: DShanPI <support@dshanpi.com>
Depends: dshanpi-archive-keyring (= $version)
Section: misc
Priority: optional
Description: DShanPI $product signed APT source
 Installs the signed stable source for the DShanPI product platform stack.
EOF
cat > "$source_root/etc/apt/sources.list.d/dshanpi.sources" <<- EOF
Types: deb
URIs: ${base_url}/apt
Suites: ${codename}
Components: ${components}
Architectures: arm64 all
Signed-By: /usr/share/keyrings/dshanpi-archive-keyring.gpg
EOF
build_deb "$source_root" "$output_dir/${repository_package}_${version}_all.deb"

sha256sum "$output_dir/dshanpi-archive-keyring_${version}_all.deb" \
	"$output_dir/${repository_package}_${version}_all.deb"
