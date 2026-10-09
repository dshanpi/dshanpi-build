#!/bin/bash
set -euo pipefail
[[ $(uname -r) == 6.1.115-vendor-rk35xx ]]
grep -Fx BOARD=dshanpi-a1 /etc/armbian-release
for package in dshanpi-a1-axcl dshanpi-axcl-dkms dshanpi-axcl-runtime; do
    [[ $(dpkg-query -W -f='${Status} ${Version}' "$package") == 'install ok installed 3.16.0+dshanpi1' ]]
done
dkms status -m axcl
for module in ax_pcie_host_dev ax_pcie_msg ax_pcie_mmb axcl_host ax_pcie_p2p_rc; do
    result=$(modinfo -F vermagic "$module")
    [[ ${result%% *} == "$(uname -r)" ]]
    echo "PASS $module: $result"
done
/usr/bin/axcl-smi --version
for program in /usr/bin/axcl/axcl-smi /usr/bin/axcl/ut/axcl_ut_npu; do
    result=$(ldd "$program")
    if grep -q 'not found' <<< "$result"; then printf '%s\n' "$result"; exit 1; fi
    echo "PASS dynamic libraries: $program"
done
test ! -e /etc/apt/apt.conf.d/10sandbox
echo PASS_APT_SANDBOX_PRESERVED
dpkg --audit
if /usr/sbin/dshanpi-axcl check; then
    echo HARDWARE_READY_FOR_INFERENCE
else
    result=$?
    [[ $result == 3 || $result == 4 ]] || exit "$result"
    echo "HARDWARE_PENDING_CODE=$result"
fi
dpkg-query -W dshanpi-a1-release-core dspi-config linux-image-vendor-rk35xx
