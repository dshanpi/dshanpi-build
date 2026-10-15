# DShanPI A1 AX8850 8GB 软件包

为 AX8850 M.2 8GB / 4266 配置提供独立安装入口 `dshanpi-a1-axcl-8g`。
配套平台为 `25.11.0-trunk.20261010.1`，运行内核 `6.1.115-vendor-rk35xx`。
维护包版本为 `3.16.0+dshanpi.2026.10.15.3`；发布及实板状态见本次变更记录。

## 安装与自检

确认卡为 8GB，断电安装，开启风扇后启动开发板。包公开到所选 APT 通道后执行：

```sh
sudo apt update
sudo apt install -y dshanpi-a1-axcl-8g
sudo systemctl enable --now dshanpi-axcl.service
axcl-smi
axcl_ut_npu
```

四个包分别提供固件、运行库、DKMS 驱动和安装入口。安装不会自动启动推理；普通用户需
属于 `render` 组，配套镜像的 baiwen 已满足。udev、tmpfiles 和服务权限配置与修复后的
16GB 版本共用，无需手工权限补丁。`axcl-smi` 必须实际列出 AX8850，NPU 应 20/20 通过。

## 容量选择与切换

8GB 与 16GB 四包互斥，不能混用运行库或 PAC。安装前先停止使用算力卡的应用。
更换容量时先停用服务并关机断电，更换硬件，再显式安装对应 selector，检查 APT 删除与
安装计划；安装后重启主机，确保旧驱动和卡端状态已清理。没有更换硬件时不能用另一容量
的包做推理验证。首次 8GB 发行尚无旧版 8GB 可回退，回滚路径为卸载四包恢复未安装状态。
16GB 既有包和历史签名清单保持原样；本次不把 8GB 自动加入所有镜像。

## 固定输入与构建

`upstream.lock.json` 固定原厂 ARM64 DEB、独立 PAC、平台依赖和 SHA-256。
原始 PAC 为用户提供的 `AX8850_card_V3.16.0_8GB_4266_RELEASE.pac`，以可逆 XZ
压缩存于 vendor，解压后逐字节校验。它与原厂 DEB 内嵌 PAC 不同，构建明确排除内嵌 PAC。

```sh
python3 scripts/build-axcl-8g-packages.py output/axcl-8g \
  --upstream /path/to/axcl_host_aarch64_V3.16.0_20260731020156_NO5288.deb
python3 scripts/build-maintenance-release.py dshanpi-a1 2026.10.15-3 output/repository
```

第一个命令可省略 `--upstream` 从固定厂商 commit 下载。也可用 `--firmware` 指定原始
PAC，但哈希必须相同。容量入口共用 `build-axcl-16g-packages.py` 和
`build-axcl-16g-release.py` 的实现及 `packages/axcl-16g` 权限模板，避免两套权限逻辑
分叉；原 16GB 入口默认行为保留，并使用既有包哈希做重建回归。

维护发行复用已签名的 16GB 和平台包，添加 8GB 四包及新发行元包。testing 通过后仅晋级
相同字节到 stable；8GB 验收必须含独立 NPU 证据，不能用以前的 16GB 记录替代。

[变更、测试与发布记录](../../docs/change-records/CR-2026-10-15-axcl-8gb.md)
