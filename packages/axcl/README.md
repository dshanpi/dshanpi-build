# DShanPI A1 AXCL 软件包

遵守根目录 [DELIVERY_POLICY.md](../../DELIVERY_POLICY.md)。本适配器固定 AXERA AXCL
3.16.0 ARM64 输入及 SHA-256，由 dshanpi-build 构建和发布。当前适用原版 A1、Noble、
`6.1.115-vendor-rk35xx`，内核与 headers 包精确固定为 `25.11.0-trunk.20261008.4`。
不修改原 A1/CM5 的 DTS、Overlay 或 U-Boot。

**当前 `3.16.0+dshanpi1` 固定上游 8GB 发行输入。** 对照上游 16GB 发行发现运行库
也有差异，不能只更换 PAC 就宣称支持 16GB。16GB 必须另行固定对应运行库、固件与
版本包并完成实卡验收；容量未知时，当前包仅可用于主机安装和 DKMS 验证。

| 包 | 内容 |
| --- | --- |
| dshanpi-axcl-runtime | ARM64 库、头文件、SMI、示例和 NPU 单元测试 |
| dshanpi-axcl-dkms | 五个主机模块的源代码、DKMS 安装和移除钩子 |
| dshanpi-a1-axcl | 精确依赖上述两包和 A1 内核/BSP；提供检查与启动命令 |

这些是 A1 的可选包集。发布新系统元包以记录该次维护发行，但普通 A1 系统升级不会
强制安装算力卡软件。其他三款板卡不能借用 A1 component；其适配和实板验证另行进行。

## 自动构建与发布

运行 Actions **Build and publish A1 AXCL packages**，版本使用已提交的 A1 release lock。
流水线验证历史签名和包哈希，原样复用基础包，构建三个可选包和新的 core/desktop
版本元包，审计、签名并部署 testing。它与其他 APT 发布共享并发队列。
这是软件包维护发行，不生成新镜像；使用已发布的 A1 `2026.10.08-4` 镜像即可更新。

`2026.10.09-2` 已自动发布 testing，并在原版 A1 完成公网 APT 安装、五模块 DKMS
编译、卸载回退、重装和重启检查。见[签名包清单](../../products/dshanpi-a1/releases/2026.10.09-2.packages.json)
与[验收记录及日志索引](../../products/dshanpi-a1/releases/2026.10.09-2.validation.json)。
验收时未连接 AX650，实卡固件、NPU 测试和模型推理尚未完成，未晋级 stable。

本地可复现入口：

```sh
python3 scripts/build-axcl-packages.py output/axcl-packages
python3 scripts/build-axcl-release.py 2026.10.09-2 /path/to/verified-repository
```

## A1 安装与检查

先明确选择 testing，并使用现有 Signed-By 源（common 加 dshanpi-a1）。

```sh
sudo dspi-config source channel testing
sudo apt update
sudo apt install -t noble-testing dshanpi-a1-release-core=2026.10.09-2 dshanpi-a1-axcl=3.16.0+dshanpi1
dkms status -m axcl
axcl-smi --help
sudo dshanpi-axcl check
```

DKMS 应为 installed，五个模块 vermagic 与当前内核完全相同。
`dshanpi-axcl check` 在无 PCIe 卡时返回 3；缺少经审查的固件包或校验文件时返回 4。
这两种结果均不是硬件验收通过。不会在安装 DEB 时重启、修改 APT 沙箱或执行模型。
设备节点保持内核默认权限；硬件命令使用 sudo。

## 固件与硬件验收边界

上游 ARM64 文档要求使用随卡配套的 PAC，8GB/16GB 不能混用。本版**不部署包内默认
PAC**，也不把它当成随卡固件。收到可核对版本、容量和 SHA-256 的 PAC 后，须经同一
编排入口制作独立固件 DEB，提供 `/lib/firmware/axcl/ax650_card.pac` 和
`/usr/share/dshanpi-axcl/firmware.sha256`，再启用 `dshanpi-axcl.service`。
主机软件升级不会覆盖用户现有 PAC。固件包仍是当前硬件交付的待完成项。

断电接卡并保持散热。PCIe 应出现 `1f4b:0650`，之后执行：

```sh
sudo dshanpi-axcl test
```

该命令先检查板型、ABI、PCIe、固件哈希，再加载模块、运行 SMI 和限时 NPU 测试。
还必须分别记录 CMM 容量、NPU 20 项测试、重启恢复，以及真实输入模型推理结果；
不将库加载、安装或无卡提示称为推理通过。

## 移除、失败恢复和后续更新

停止卡上任务后执行：

```sh
sudo systemctl stop dshanpi-axcl.service
sudo apt remove dshanpi-a1-axcl dshanpi-axcl-dkms dshanpi-axcl-runtime
```

DKMS 按模块名及版本清理其文件，不通配删除其他驱动。不强制卸载正在被应用使用的
模块；已加载的旧模块在停止使用后重启清除。不存在旧 AXCL 发行时，回退基线是
移除这三个新增包，保留原系统版本和现有 PAC。未来有新包版本后，先更新精确依赖
入口，再验证整套升级、降级与重启；不发布同名同版本的不同 DEB。

若 DKMS 编译失败，查看 `/var/lib/dkms/axcl/<version>/build/make.log`，修复源码或
匹配 headers 后运行 `sudo dpkg --configure -a`。不得用手工复制 `.ko` 绕过包管理。
