#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

[[ $# -eq 1 ]] || die "usage: $0 PACKAGE_DIRECTORY"
package_dir=$(safe_realpath "$1")
require_command dpkg-deb
require_command python3
require_command patchelf
shopt -s nullglob
debs=("$package_dir"/*.deb)
((${#debs[@]} > 0)) || die "package directory contains no deb files"

declare -A identities=()
for deb in "${debs[@]}"; do
	package=$(package_field "$deb" Package)
	version=$(package_field "$deb" Version)
	arch=$(package_field "$deb" Architecture)
	[[ "$arch" == arm64 || "$arch" == all ]] || die "unsupported architecture: $package/$arch"
	identity="$package|$version|$arch"
	hash=$(sha256sum "$deb" | awk '{print $1}')
	[[ -z "${identities[$identity]:-}" || "${identities[$identity]}" == "$hash" ]] ||
		die "conflicting package identity: $identity"
	identities[$identity]=$hash
	if dpkg-deb --contents "$deb" | awk '
		$1 ~ /^-/ && substr($1, 9, 1) == "w" { bad = 1 }
		$1 ~ /^d/ && substr($1, 9, 1) == "w" && substr($1, 10, 1) !~ /[tT]/ { bad = 1 }
		$1 ~ /^-/ && (substr($1, 4, 1) ~ /[sS]/ || substr($1, 7, 1) ~ /[sS]/) { bad = 1 }
		END { exit(bad ? 0 : 1) }
	'; then
		die "unsafe writable or set-id payload mode: $deb"
	fi
	audit_dir=$(mktemp -d)
	dpkg-deb --extract "$deb" "$audit_dir"
	while IFS= read -r -d '' payload; do
		rpath=$(patchelf --print-rpath "$payload" 2>/dev/null || true)
		[[ ! "$rpath" =~ (^|:)/(home|tmp|build)(/|:|$) ]] || {
			rm -rf -- "$audit_dir"
			die "build-host RPATH in $package:${payload#${audit_dir}}: $rpath"
		}
	done < <(python3 - "$audit_dir" <<'PY'
import os
from pathlib import Path
import sys
for directory, _, names in os.walk(sys.argv[1]):
    for name in names:
        path = Path(directory) / name
        if path.is_symlink() or not path.is_file():
            continue
        with path.open('rb') as stream:
            if stream.read(4) == b'\x7fELF':
                sys.stdout.buffer.write(os.fsencode(path) + b'\0')
PY
)
	rm -rf -- "$audit_dir"
done

echo "audited ${#debs[@]} packages"
