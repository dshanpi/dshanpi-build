#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

[[ $# -eq 2 ]] || die "usage: $0 PRODUCT RELEASE_LOCK"
require_command jq
require_product "$1"
lock=$(safe_realpath "$2")
validate_release_lock "$1" "$lock"

jq -e '
  (.required_packages | length > 0) and
  ([.required_packages[].name] | length == (unique | length)) and
  (.package_search_paths | type == "array" and length > 0) and
  (all(.package_search_paths[]; type == "string" and test("^[A-Za-z0-9._/-]+$") and (startswith("/") | not) and (contains("..") | not))) and
  (.architectures == ["arm64", "all"]) and
  (.codename == "noble") and
  (.testing_suite == "noble-testing")
' "$product_config" >/dev/null || die "unsupported or duplicate product package configuration"

echo "validated $1 release $(jq -r .version "$lock")"
