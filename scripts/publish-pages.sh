#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
[[ $# -eq 2 ]] || die "usage: $0 SIGNED_REPOSITORY PUBLIC_KEY"
repository=$(safe_realpath "$1")
public_key=$(safe_realpath "$2")
branch=feature/apt-pages-state
remote=${DSHANPI_PAGES_GIT_REMOTE:-origin}
temporary=$(mktemp -d)
trap 'rm -rf -- "$temporary"' EXIT
git init -q "$temporary/checkout"
git -C "$temporary/checkout" remote add origin "$(git -C "$repo_root" remote get-url "$remote")"
if [[ -n $(git -C "$repo_root" ls-remote --heads "$remote" "$branch") ]]; then
	git -C "$temporary/checkout" fetch -q --depth=1 origin "$branch"
	git -C "$temporary/checkout" checkout -q -b "$branch" FETCH_HEAD
	python3 "$script_dir/pages/snapshot.py" decode "$temporary/checkout/snapshot" "$temporary/previous"
	python3 "$script_dir/verify-repository.py" --snapshot "$temporary/previous" "$public_key" "$temporary/previous"
	rm -rf "$temporary/checkout/snapshot"
else
	git -C "$temporary/checkout" checkout -q --orphan "$branch"
	mkdir "$temporary/previous"
fi
python3 "$script_dir/verify-repository.py" "$repository" "$public_key" "$temporary/previous"
python3 - "$temporary/previous" "$repository" <<'PY'
import hashlib
from pathlib import Path
import sys
old, new = map(Path, sys.argv[1:])
for path in (old / 'pool').rglob('*'):
    if path.is_file():
        target = new / path.relative_to(old)
        if not target.is_file():
            raise SystemExit(f'Historical pool file removed: {target}')
        def digest(p):
            with p.open('rb') as f:
                return hashlib.file_digest(f, 'sha256').digest()
        if digest(path) != digest(target):
            raise SystemExit(f'Historical pool file changed: {target}')
PY
python3 "$script_dir/pages/snapshot.py" encode "$repository" "$temporary/checkout/snapshot"
mkdir -p "$temporary/checkout/tools" "$temporary/checkout/.github/workflows" "$temporary/checkout/site"
cp "$script_dir/pages/snapshot.py" "$script_dir/verify-repository.py" "$temporary/checkout/tools/"
cp "$script_dir/pages/deploy.yml" "$temporary/checkout/.github/workflows/deploy.yml"
cp "$script_dir/pages/index.html" "$temporary/checkout/site/"
cp "$public_key" "$temporary/checkout/archive-key.asc"
printf '%s\n' apt.100ask.net > "$temporary/checkout/site/CNAME"
git -C "$temporary/checkout" add .
git -C "$temporary/checkout" -c user.name='DShanPI APT Publisher' -c user.email='apt@dshanpi.com' \
	commit -q -m "Publish signed APT snapshot $(sha256sum "$repository/SHA256SUMS" | cut -c1-16)"
# Ordinary fast-forward push rejects concurrent publications; never force.
git -C "$temporary/checkout" push origin "HEAD:refs/heads/$branch"
echo "Published signed snapshot to $branch; GitHub Actions will deploy Pages."
