#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

[[ $# -eq 3 ]] || die "usage: $0 REPOSITORY_URL COMMIT DESTINATION"
url=$1
commit=$2
destination=$3
[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || die "source commit must be a full SHA"
[[ ! -e "$destination" ]] || die "source destination already exists: $destination"
mkdir -p "$(dirname "$destination")"
git init -q "$destination"
git -C "$destination" remote add origin "$url"
git -C "$destination" fetch --depth 1 origin "$commit"
git -C "$destination" checkout -q --detach FETCH_HEAD
[[ $(git -C "$destination" rev-parse HEAD) == "$commit" ]] || die "checked out commit does not match lock"
