#!/usr/bin/env bash
# Exercise real APT/dpkg package installation without touching host package state.
set -euo pipefail
[[ $# -eq 2 && ${EUID:-$(id -u)} -eq 0 ]] || {
	echo "Usage (as root): $0 REPOSITORY_URI PUBLIC_KEY" >&2; exit 2;
}
uri=${1%/}
public_key=$(realpath "$2")
root=$(mktemp -d)
trap 'rm -rf -- "$root"' EXIT
mkdir -p "$root/etc/apt/sources.list.d" "$root/etc/apt/apt.conf.d" "$root/etc/apt/preferences.d" \
	"$root/var/lib/apt/lists/partial" "$root/var/cache/apt/archives/partial" \
	"$root/var/lib/dpkg/updates" "$root/var/log/apt" "$root/usr/share/keyrings"
# Dependencies are represented by the host's installed-package status snapshot;
# only the tested architecture-independent packages are unpacked into this root.
cp /var/lib/dpkg/status "$root/var/lib/dpkg/status"
gpg --batch --yes --dearmor --output "$root/usr/share/keyrings/dshanpi.gpg" "$public_key"
cat > "$root/etc/apt/sources.list.d/dshanpi.sources" <<EOF
Types: deb
URIs: $uri
Suites: noble-testing
Components: common dshanpi-a1-cm5
Architectures: arm64 all
Signed-By: $root/usr/share/keyrings/dshanpi.gpg
EOF
cat > "$root/apt.conf" <<EOF
Dir "$root";
Dir::State "$root/var/lib/apt";
Dir::State::status "$root/var/lib/dpkg/status";
Dir::Cache "$root/var/cache/apt";
Dir::Etc "$root/etc/apt";
Dir::Log "$root/var/log/apt";
APT::Sandbox::User "root";
DPkg::Options { "--root=$root"; };
EOF
export APT_CONFIG="$root/apt.conf"
apt-get update
for version in 1.0.1-2 1.0.2-1 1.0.1-2; do
	apt-get --yes --allow-downgrades install "dspi-config=$version"
	[[ $(dpkg-query --admindir="$root/var/lib/dpkg" -W -f='${Version}' dspi-config) == "$version" ]]
	[[ -x "$root/usr/sbin/dspi-config" ]]
done
echo 'PASS: signed APT update, real dspi-config install, upgrade and downgrade in an isolated dpkg root'
