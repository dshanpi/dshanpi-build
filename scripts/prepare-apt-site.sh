#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
[[ $# -eq 2 ]] || die "usage: $0 SIGNED_REPOSITORY PUBLIC_KEY"
repository=$(safe_realpath "$1")
public_key=$(safe_realpath "$2")
python3 "$script_dir/verify-repository.py" --snapshot "$repository" "$public_key" "$repository"
cp "$public_key" "$repository/archive-key.asc"
gpg --batch --yes --dearmor --output "$repository/dshanpi-archive-keyring.gpg" "$public_key"
python3 "$script_dir/pages/catalog.py" "$repository"
cp "$script_dir/pages/index.html" "$repository/"
touch "$repository/.nojekyll"
