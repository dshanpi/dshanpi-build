#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
[[ $# -eq 2 ]] || die "usage: $0 OUTPUT_DIRECTORY PUBLIC_KEY"
destination=$1
public_key=$(safe_realpath "$2")
[[ ! -e "$destination" ]] || die "output directory must not exist"
remote=${DSHANPI_PAGES_GIT_REMOTE:-origin}
branch=feature/apt-pages-state
temporary=$(mktemp -d)
trap 'rm -rf -- "$temporary"' EXIT
remote_ref=$(git -C "$repo_root" ls-remote --heads "$remote" "$branch") ||
	die "cannot read Pages state; refusing to treat a transport/authentication failure as an empty repository"
if [[ -z "$remote_ref" ]]; then
	mkdir -p "$destination"
	exit 0
fi
git init -q "$temporary"
git -C "$temporary" fetch -q --depth=1 "$(git -C "$repo_root" remote get-url "$remote")" "$branch"
git -C "$temporary" checkout -q FETCH_HEAD
python3 "$script_dir/pages/snapshot.py" decode "$temporary/snapshot" "$destination"
python3 "$script_dir/verify-repository.py" --snapshot "$destination" "$public_key" "$destination"
