#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
python3 "$repo_root/tools/check-delivery-policy.py" >/dev/null

[[ $# -eq 4 ]] || die "usage: $0 PRODUCT PLAN_VERSION REPOSITORY_DIR GPG_FINGERPRINT"
product=$1
plan_version=$2
repository_dir=$(safe_realpath "$3")
fingerprint=$4
require_product "$product"
plan="$repo_root/products/$product/purges/$plan_version.json"
[[ -f "$plan" ]] || die "purge plan does not exist: $plan"
suite=$(jq -r .testing_suite "$product_config")
stable_suite=$(jq -r .codename "$product_config")
component=$(jq -r .component "$product_config")
base_state=${DSHANPI_EXPECTED_BASE_STATE_SHA256:-none}
if [[ "$base_state" == none ]]; then
	[[ ! -f "$repository_dir/SHA256SUMS" ]] || base_state=$(sha256sum "$repository_dir/SHA256SUMS" | awk '{print $1}')
else
	[[ "$base_state" =~ ^[0-9a-f]{64}$ ]] || die "invalid expected public base state"
fi
result=$(mktemp)
trap 'rm -f -- "$result"' EXIT

python3 "$script_dir/repository_tool.py" purge "$product_config" "$plan" "$repository_dir" --result "$result"
python3 "$script_dir/repository_tool.py" render "$repository_dir" \
	--ensure-suite "$stable_suite" --ensure-suite "$suite" \
	--ensure-component common --ensure-component "$component" \
	--manual-suite "$suite"
jq -n \
	--arg suite "$suite" \
	--arg product "$product" \
	--arg component "$component" \
	--arg plan_version "$plan_version" \
	--arg expected_base_state_sha256 "$base_state" \
	--argjson purge_versions "$(jq -c .purge_versions "$plan")" \
	--argjson removed_pool_files "$(jq -c .removed_pool_files "$result")" \
	'{schema_version: 1, channel: "testing", operation: "purge", suite: $suite,
	  product: $product, component: $component, version: $plan_version,
	  purge_versions: $purge_versions, removed_pool_files: $removed_pool_files,
	  expected_base_state_sha256: $expected_base_state_sha256}' \
	> "$repository_dir/PUBLICATION.json"
"$script_dir/sign-repository.sh" "$repository_dir" "$fingerprint"
echo "purged the planned legacy $product testing releases and unreferenced pool payloads"
