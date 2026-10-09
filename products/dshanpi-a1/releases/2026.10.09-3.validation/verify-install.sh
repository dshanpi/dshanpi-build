#!/bin/bash
set -euo pipefail
[[ $(uname -r) == 6.1.115-vendor-rk35xx ]]
grep -Fx BOARD=dshanpi-a1 /etc/armbian-release
for package in dshanpi-a1-aic8800d80 dshanpi-aic8800d80-dkms dshanpi-aic8800d80-firmware; do
    [[ $(dpkg-query -W -f='${Status} ${Version}' "$package") == 'install ok installed 6.4.3.0+dshanpi1' ]]
    [[ -z $(dpkg -V "$package") ]]
done
dkms status -m dshanpi-aic8800d80
for module in aic_load_fw aic8800_fdrv aic_btusb; do
    result=$(modinfo -F vermagic "$module")
    [[ ${result%% *} == "$(uname -r)" ]]
    path=$(modinfo -F filename "$module")
    [[ $path == */updates/dkms/* ]]
    printf 'PASS %s: %s; %s\n' "$module" "$result" "$path"
done
test -f /lib/firmware/dshanpi-aic8800d80/aic8800D80/fw_patch_8800d80_u04.bin
test -f /lib/modprobe.d/dshanpi-aic8800d80.conf
test ! -f /etc/modprobe.d/dshanpi-aic8800d80.conf
dpkg --audit
dpkg-query -W dshanpi-a1-release-core dspi-config linux-image-vendor-rk35xx linux-headers-vendor-rk35xx dshanpi-a1-axcl bluez
lsusb
echo 'Software installation verified; Wi-Fi/Bluetooth functional testing is reserved for the user.'
