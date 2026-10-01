#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

[[ $# -eq 6 ]] || die "usage: $0 testing PRODUCT VERSION PACKAGE_DIR REPOSITORY_DIR GPG_FINGERPRINT"
[[ "$1" == testing ]] || die "new packages may only be published to testing"
product=$2
version=$3
package_dir=$(safe_realpath "$4")
repository_dir=$5
fingerprint=$6
require_product "$product"
require_command python3
mkdir -p "$repository_dir"
repository_dir=$(safe_realpath "$repository_dir")
suite=$(jq -r .testing_suite "$product_config")
component=$(jq -r .component "$product_config")
base_state=none
[[ ! -f "$repository_dir/SHA256SUMS" ]] || base_state=$(sha256sum "$repository_dir/SHA256SUMS" | awk '{print $1}')

"$script_dir/audit-packages.sh" "$package_dir"
python3 "$script_dir/repository_tool.py" add "$product_config" "$version" "$package_dir" "$repository_dir"
python3 "$script_dir/repository_tool.py" render "$repository_dir" \
	--ensure-suite "$(jq -r .codename "$product_config")" \
	--ensure-suite "$suite" --ensure-component common --ensure-component "$component" \
	--manual-suite "$suite"
cat > "$repository_dir/PUBLICATION.json" <<- EOF
{
  "schema_version": 1,
  "channel": "testing",
  "suite": "$suite",
  "product": "$product",
  "component": "$component",
  "version": "$version",
  "expected_base_state_sha256": "$base_state"
}
EOF
"$script_dir/sign-repository.sh" "$repository_dir" "$fingerprint"
echo "prepared testing publication for $product $version"
