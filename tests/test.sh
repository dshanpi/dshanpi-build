#!/usr/bin/env bash
set -euo pipefail

source_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
test_root=$(mktemp -d)
trap 'rm -rf -- "$test_root"' EXIT
export GNUPGHOME="$test_root/gnupg"
export SOURCE_DATE_EPOCH=1790726400
mkdir -m 0700 "$GNUPGHOME"
gpg --batch --passphrase '' --quick-gen-key 'DShanPI APT Test <apt-test@dshanpi.invalid>' rsa2048 sign 0 >/dev/null 2>&1
fingerprint=$(gpg --batch --with-colons --list-secret-keys | awk -F: '$1 == "fpr" {print $10; exit}')
gpg --batch --armor --export "$fingerprint" > "$test_root/public.asc"

lock="$test_root/release.lock.json"
cat > "$lock" <<'EOF'
{
  "schema_version": 1,
  "product": "dshanpi-a1-cm5",
  "version": "2026.09.30-1",
  "revision": "25.11.0-trunk.20260930.1",
  "sources": {
    "armbianos": {"commit": "1111111111111111111111111111111111111111"},
    "dspi_config": {"commit": "2222222222222222222222222222222222222222"}
  }
}
EOF
"$source_root/scripts/validate-config.sh" dshanpi-a1-cm5 "$lock" >/dev/null
"$source_root/scripts/build-product.sh" dshanpi-a1-cm5 "$lock" --print-plan | grep -Fx 'variants=cli desktop' >/dev/null

raw="$test_root/raw"
mkdir -p "$raw"
build_dummy() {
	local package=$1 arch=$2 version=${3:-1.0.0-1} root="$test_root/pkg-$package-$arch"
	mkdir -p "$root/DEBIAN" "$root/usr/share/$package"
	cat > "$root/DEBIAN/control" <<- EOF
	Package: $package
	Version: $version
	Architecture: $arch
	Maintainer: Test <test@dshanpi.invalid>
	Section: misc
	Priority: optional
	Description: fixture package for dshanpi-build tests
	EOF
	printf '%s\n' "$package $version" > "$root/usr/share/$package/payload"
	dpkg-deb --root-owner-group --build "$root" "$raw/${package}_${version}_${arch}.deb" >/dev/null
}

while IFS=$'\t' read -r package arch; do
	case "$package" in
		dshanpi-archive-keyring | dshanpi-a1-cm5-repository | dspi-config) continue ;;
	esac
	build_dummy "$package" "$arch"
done < <(jq -r '.required_packages[] | [.name, .arch] | @tsv' "$source_root/products/dshanpi-a1-cm5/product.json")

client="$test_root/client"
"$source_root/scripts/build-client-packages.sh" dshanpi-a1-cm5 2026.09.30-1 \
	"$test_root/public.asc" https://dl.100ask.net "$client" >/dev/null
build_dummy dspi-config all 1.0.0-1

packages="$test_root/packages"
"$source_root/scripts/collect-packages.sh" dshanpi-a1-cm5 "$packages" "$raw" "$client" >/dev/null
"$source_root/scripts/build-release-meta.sh" dshanpi-a1-cm5 2026.09.30-1 "$packages" >/dev/null
dpkg-deb -f "$packages/dshanpi-a1-cm5-release-core_2026.09.30-1_all.deb" Depends |
	grep -F 'linux-image-vendor-rk3576-dshanpi-a1-cm5 (= 1.0.0-1)' >/dev/null
dpkg-deb -f "$packages/dshanpi-a1-cm5-release-core_2026.09.30-1_all.deb" Depends |
	grep -F 'armbian-bsp-desktop' && { echo 'desktop dependency leaked into core meta' >&2; exit 1; } || true
desktop_depends=$(dpkg-deb -f "$packages/dshanpi-a1-cm5-release-desktop_2026.09.30-1_all.deb" Depends)
grep -F 'linux-image-vendor-rk3576-dshanpi-a1-cm5 (= 1.0.0-1)' <<<"$desktop_depends" >/dev/null
grep -F 'armbian-bsp-desktop-dshanpi-a1-cm5-vendor (= 1.0.0-1)' <<<"$desktop_depends" >/dev/null
grep -F 'dshanpi-a1-cm5-release-core' <<<"$desktop_depends" && {
	echo 'desktop meta must be independently installable during image assembly' >&2
	exit 1
} || true

repository="$test_root/repository"
"$source_root/scripts/build-apt-repository.sh" testing dshanpi-a1-cm5 2026.09.30-1 \
	"$packages" "$repository" "$fingerprint" >/dev/null
gpg --batch --yes --dearmor --output "$test_root/public.gpg" "$test_root/public.asc"
gpgv --keyring "$test_root/public.gpg" "$repository/dists/noble-testing/InRelease" >/dev/null 2>&1
grep -Fx 'NotAutomatic: yes' "$repository/dists/noble-testing/Release" >/dev/null
grep -Fx 'ButAutomaticUpgrades: no' "$repository/dists/noble-testing/Release" >/dev/null
if grep -Eq '^(NotAutomatic|ButAutomaticUpgrades):' "$repository/dists/noble/Release"; then
	echo 'stable suite unexpectedly disables automatic upgrades' >&2
	exit 1
fi
xz -dc "$repository/dists/noble-testing/dshanpi-a1-cm5/binary-arm64/Packages.xz" |
	grep -Fx 'Package: linux-image-vendor-rk3576-dshanpi-a1-cm5' >/dev/null
xz -dc "$repository/dists/noble-testing/common/binary-all/Packages.xz" |
	grep -Fx 'Package: dspi-config' >/dev/null
if [[ -n "${DL_APT_VERIFY_SCRIPT:-}" ]]; then
	empty_repository="$test_root/empty-repository"
	mkdir -p "$empty_repository"
	python3 "$DL_APT_VERIFY_SCRIPT" "$repository" "$test_root/public.gpg" "$empty_repository" >/dev/null
fi

before=$(sha256sum "$repository/pool/dshanpi-a1-cm5"/*/*/*.deb | sha256sum | awk '{print $1}')
testing_state="$test_root/testing-state"
cp -a "$repository" "$testing_state"
"$source_root/scripts/promote-apt-release.sh" dshanpi-a1-cm5 2026.09.30-1 \
	"$repository" "$fingerprint" >/dev/null
after=$(sha256sum "$repository/pool/dshanpi-a1-cm5"/*/*/*.deb | sha256sum | awk '{print $1}')
[[ "$before" == "$after" ]]
gpgv --keyring "$test_root/public.gpg" "$repository/dists/noble/InRelease" >/dev/null 2>&1
if grep -Eq '^(NotAutomatic|ButAutomaticUpgrades):' "$repository/dists/noble/Release"; then
	echo 'promoted stable suite unexpectedly disables automatic upgrades' >&2
	exit 1
fi
if [[ -n "${DL_APT_VERIFY_SCRIPT:-}" ]]; then
	python3 "$DL_APT_VERIFY_SCRIPT" "$repository" "$test_root/public.gpg" "$testing_state" >/dev/null
fi
xz -dc "$repository/dists/noble/dshanpi-a1-cm5/binary-all/Packages.xz" |
	grep -Fx 'Package: dshanpi-a1-cm5-release-core' >/dev/null

"$source_root/scripts/withdraw-testing-release.sh" dshanpi-a1-cm5 2026.09.30-1 \
	"$repository" "$fingerprint" >/dev/null
if xz -dc "$repository/dists/noble-testing/dshanpi-a1-cm5/binary-all/Packages.xz" |
	grep -Fx 'Package: dshanpi-a1-cm5-release-core' >/dev/null; then
	echo "withdrawn testing release is still indexed" >&2
	exit 1
fi
xz -dc "$repository/dists/noble/dshanpi-a1-cm5/binary-all/Packages.xz" |
	grep -Fx 'Package: dshanpi-a1-cm5-release-core' >/dev/null

apt_root="$test_root/apt-root"
mkdir -p "$apt_root/etc/apt/sources.list.d" "$apt_root/state/lists/partial" "$apt_root/cache/archives/partial"
cat > "$apt_root/etc/apt/sources.list.d/dshanpi.sources" <<- EOF
Types: deb
URIs: file:$repository
Suites: noble
Components: common dshanpi-a1-cm5
Architectures: arm64 all
Signed-By: $test_root/public.gpg
EOF
apt-get -o "Dir=$apt_root" -o "Dir::State=$apt_root/state" -o "Dir::Cache=$apt_root/cache" \
	-o "Dir::Etc=$apt_root/etc/apt" -o APT::Architecture=arm64 update >/dev/null

bad="$test_root/bad"
cp -a "$packages" "$bad"
build_dummy linux-u-boot-dshanpi-a1-cm5-vendor arm64
cp "$raw"/linux-u-boot-*.deb "$bad/"
if "$source_root/scripts/build-apt-repository.sh" testing dshanpi-a1-cm5 2026.09.30-2 \
	"$bad" "$test_root/bad-repository" "$fingerprint" >/dev/null 2>&1; then
	echo "forbidden U-Boot package unexpectedly passed" >&2
	exit 1
fi

echo "dshanpi-build tests passed"
