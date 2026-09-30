#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

[[ $# -eq 4 ]] || die "usage: $0 PRODUCT VERSION REPOSITORY_DIR GPG_FINGERPRINT"
product=$1
version=$2
repository_dir=$(safe_realpath "$3")
fingerprint=$4
require_product "$product"
suite=$(jq -r .codename "$product_config")
component=$(jq -r .component "$product_config")
testing_suite=$(jq -r .testing_suite "$product_config")
base_state=none
[[ ! -f "$repository_dir/SHA256SUMS" ]] || base_state=$(sha256sum "$repository_dir/SHA256SUMS" | awk '{print $1}')

python3 "$script_dir/repository_tool.py" promote "$product_config" "$version" "$repository_dir"
python3 "$script_dir/repository_tool.py" render "$repository_dir" \
	--ensure-suite "$suite" --ensure-suite "$testing_suite" \
	--ensure-component common --ensure-component "$component"
cat > "$repository_dir/PUBLICATION.json" <<- EOF
{
  "schema_version": 1,
  "channel": "stable",
  "suite": "$suite",
  "product": "$product",
  "component": "$component",
  "version": "$version",
  "expected_base_state_sha256": "$base_state"
}
EOF
"$script_dir/sign-repository.sh" "$repository_dir" "$fingerprint"
echo "prepared stable promotion for $product $version without rebuilding packages"
