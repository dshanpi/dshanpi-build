# 原版 A1 / AX8850 转接板 AIC8800D80

遵守 [DELIVERY_POLICY.md](../../DELIVERY_POLICY.md)。固定用户提供的原始 tar.gz 和
SHA-256；驱动版本 6.4.3.0，包版本 6.4.3.0+dshanpi1。本包对应 USB 无线模块，
不因转接板使用 PCIe 就选择 PCIe 无线驱动；不替代 AX650 推理软件和 PAC。

适用原版 DShanPI A1、Noble arm64、内核 `6.1.115-vendor-rk35xx`，内核和 headers
Debian 版本精确固定为 `25.11.0-trunk.20261008.4`。CM5 的 SDIO 驱动独立维护。

## 安装

```sh
sudo dspi-config source channel testing
sudo apt update
sudo apt install -t noble-testing dshanpi-a1-release-core=2026.10.09-3 dshanpi-a1-aic8800d80=6.4.3.0+dshanpi1
dkms status -m dshanpi-aic8800d80
```

入口包自动安装 DKMS 驱动包、配套固件包和 BlueZ/iw/rfkill/usbutils。三个模块为
`aic_load_fw`、`aic8800_fdrv`、`aic_btusb`；固件放在私有目录
`/lib/firmware/dshanpi-aic8800d80/aic8800D80`。安装脚本仅编译和登记模块，不重启、
不切换网络、不主动加载模块；接入硬件或重启后正常 USB 自动绑定仍会生效。
不黑名单整个 btusb；通过 softdep 让 AIC 专用蓝牙驱动优先于通用 btusb 注册。
现有 aic8800 SDIO/USB/PCIe DKMS 包与本包冲突，不得混装同名模块。

## 用户功能测试

先断电接好模块及其 USB 数据通路，保持散热和远程访问通路，再上电测试。
`lsusb` 应可看到 AIC 设备；初始化阶段 D80 ID 为 `a69c:8d80`，下载固件后可能变化。
若 USB 未枚举，先检查硬件连接，不把安装 DEB 成功视为设备可用。

```sh
lsusb
sudo modprobe aic_load_fw
sudo modprobe aic8800_fdrv
sudo modprobe aic_btusb
modinfo -F vermagic aic8800_fdrv
iw dev
nmcli device status
nmcli device wifi list
bluetoothctl list
sudo rfkill list
sudo journalctl -k -b | grep -Ei 'aic|firmware|bluetooth'
```

选择新出现的无线接口再使用 NetworkManager 连接测试 SSID；在 `bluetoothctl` 中
执行 `power on`、`scan on`，扫描后 `scan off`，再对自己的设备配对和连接。
分别记录 2.4/5 GHz 连接、吞吐、蓝牙扫描/配对/传输、Wi-Fi/蓝牙并发和重启恢复。
功能测试由用户执行，未通过前保持 testing，不宣称硬件验收完成。

## 卸载与恢复

停止使用新无线接口和蓝牙设备后：

```sh
sudo apt remove dshanpi-a1-aic8800d80 dshanpi-aic8800d80-dkms dshanpi-aic8800d80-firmware
```

DKMS 只清理自己的版本；不强行卸载正在使用的模块。重启可清除已加载的旧模块。
若要连同配置彻底删除，使用 `apt purge`。编译失败查看
`/var/lib/dkms/dshanpi-aic8800d80/6.4.3.0+dshanpi1/build/make.log`，修复后通过
`dpkg --configure -a` 恢复；不要手工覆盖内核模块。
