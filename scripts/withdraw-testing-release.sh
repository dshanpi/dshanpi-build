#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
python3 "$repo_root/tools/check-delivery-policy.py" >/dev/null

[[ $# -eq 4 ]] || die "usage: $0 PRODUCT VERSION REPOSITORY_DIR GPG_FINGERPRINT"
product=$1
version=$2
repository_dir=$(safe_realpath "$3")
fingerprint=$4
require_product "$product"
suite=$(jq -r .testing_suite "$product_config")
stable_suite=$(jq -r .codename "$product_config")
component=$(jq -r .component "$product_config")
base_state=none
[[ ! -f "$repository_dir/SHA256SUMS" ]] || base_state=$(sha256sum "$repository_dir/SHA256SUMS" | awk '{print $1}')

python3 "$script_dir/repository_tool.py" withdraw "$product_config" "$version" "$repository_dir"
python3 "$script_dir/repository_tool.py" render "$repository_dir" \
	--ensure-suite "$stable_suite" --ensure-suite "$suite" \
	--ensure-component common --ensure-component "$component" \
	--manual-suite "$suite"
cat > "$repository_dir/PUBLICATION.json" <<- EOF
{
  "schema_version": 1,
  "channel": "testing",
  "operation": "withdraw",
  "suite": "$suite",
  "product": "$product",
  "component": "$component",
  "version": "$version",
  "expected_base_state_sha256": "$base_state"
}
EOF
"$script_dir/sign-repository.sh" "$repository_dir" "$fingerprint"
echo "withdrew $product $version from testing indexes; immutable pool files were retained"
