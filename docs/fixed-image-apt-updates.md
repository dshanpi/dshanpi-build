# 固定镜像与持续 APT 更新规范

## 不可突破的交付底线

客户设备在同一个操作系统大版本系列内只要求烧录一次产品黄金基线镜像。此后新增或更新普通软件、运行库、固件、驱动、
DKMS、内核、headers、DTB 和 BSP，默认都必须通过签名 APT 与 `dspi-config` 完成，不能把
重新烧录镜像作为软件更新步骤。

黄金镜像系列按发行版大版本划分，例如 Ubuntu 24、Ubuntu 26、Debian 12、Debian 13。
Ubuntu 24.x 或 Ubuntu 26.x 系列内的小版本、平台 revision 和产品软件更新都属于 APT 更新，
不能因为小版本号变化重新要求客户烧录。新的黄金镜像系列只用于以下场景：

- Ubuntu 24 → Ubuntu 26、Debian 12 → Debian 13 等发行版大版本迁移；
- 分区表、文件系统、引导链或启动介质布局发生无法安全原位迁移的重大变化；
- 已有系统损坏，不能再完成可信的 APT 事务。

同一 OS 大版本可以为新生产设备刷新工厂镜像或提供新的恢复镜像，但这只是缩短首次更新时间，
不能成为老设备获取新 DEB 的前提。仍应为已经交付的兼容设备提供 APT 升级路径。内核或 BSP 更新本身
不等于必须重刷：只要启动布局兼容，就作为一个需要重启的精确软件包 cohort 发布。

## 三种版本身份

版本不能混成一个含义：

| 身份 | 示例 | 用途 |
| --- | --- | --- |
| OS 黄金镜像系列 | `ubuntu24-noble` | 按 Ubuntu 24/26、Debian 12/13 等大版本划分 |
| 系统软件发行版本 | `2026.10.14-1` | 一组已经配套验证的精确 DEB；由 release 元包标识 |
| 单个 DEB 版本 | `camera-demo=1.2.0-1` | 包自身内容身份；内容或依赖变化必须递增 |

系统软件发行版本增加不表示必须产生新镜像。设备当前软件 cohort 以安装的
`<product>-release-core` 或 `<product>-release-desktop` 版本为准，而不是以最初烧录的镜像
文件名为准。

## DEB 分类与升级行为

新增包时必须先分类：

### 产品必装包

加入 `products/<product>/product.json` 的 `required_packages`。新的 release 元包会对它写入
精确 `Depends`，现有客户执行系统更新时自动安装。CLI 和 Desktop 的差异通过
`release_meta.desktop_only_dependencies` 表达。

### 可选功能或可选硬件

作为完整 selector 包组加入 `optional_package_sets`。selector 精确依赖驱动、运行库、固件及
必要平台版本。客户只在首次启用该功能时明确安装 selector；之后发行元包用精确 `Suggests`
声明该版本的兼容 selector，`dspi-config` 只同步本机已经安装的 selector。没有该硬件的设备
不会被自动安装，也不能在 8GB/16GB 等互斥硬件之间静默切换。

### 构建工具或开发包

发布到正确 component，但不放进 release 元包，除非它是设备运行或 DKMS 重建的必要依赖。
例如对外镜像对应的精确 `linux-headers-*` 必须持续可安装，但不一定预装在每台设备上。

## 一次 package-only 发行

1. 修改组件源码或固定上游输入，递增受影响 DEB 版本并补齐依赖、冲突和维护脚本。
2. 为组件提供或更新受控 maintenance adapter。所有 adapter 由
   `scripts/build-maintenance-release.py` 统一登记；不能复制一套新发布 workflow。
3. 新建 `products/<product>/releases/<version>.lock.json`，记录：
   - 新的系统软件发行版本；
   - 产品和平台 revision；
   - 固定源码 commit；
   - `maintenance_adapter`；
   - 基础发行清单及其 SHA-256；
   - 组件输入锁及其 SHA-256。
4. 在 `Build and publish DShanPI product` 选择该 product/version、`channel=testing`。
   流水线复用基础发行中未变化的原始 DEB，只构建变化包，重新生成精确 core/desktop 元包，
   审计、签名并发布到 `noble-testing`。没有 `image_release`，所以不会构建或上传镜像。
5. 验收板执行：

   ```sh
   sudo dspi-config source channel testing
   sudo dspi-config update install <version>
   sudo reboot  # 仅在内核、BSP、驱动或启动配置变化时需要
   ```

6. 记录安装、功能、重启恢复及回滚证据。回滚通过 `dspi-config update rollback` 安装上一版
   release 元包及全部精确依赖，不能只降低版本标记。
7. 提交与候选包清单 SHA-256 绑定的验收记录，再运行同一 workflow、选择
   `channel=stable`。stable 只晋级 testing 中相同的 DEB 字节，不重新构建。

## APT 事务要求

- 发布前必须执行 `apt-get --simulate`，拒绝意外删除、跨板 component、内核/BSP 降级和未解析依赖。
- 平台 cohort 必须同时包含完全一致的 kernel image、headers、DTB、BSP 和受影响 DKMS 包。
- 更新失败不能留下只更新了一半的 release 标记；APT 必须以完整目标列表执行事务。
- testing 必须显式选择；stable 才进入普通客户更新路径。
- 已发布 pool 字节和旧清单不可覆盖。旧 testing 可以撤出索引，但仍保留回滚及来源复用所需的
  不可变 DEB。

## 示例

设备最初烧录 Ubuntu 24 noble 系列的 `2026.10.10-1` 工厂镜像。之后依次发布：

- `2026.10.14-1`：新增必装应用 DEB；APT 安装应用和新 release 元包，不重启、不重刷。
- `2026.10.18-1`：更新 AXCL DKMS；已经安装 AXCL selector 的设备同步驱动，其他设备不动。
- `2026.10.20-1`：更新 kernel/headers/BSP/AXCL cohort；APT 完成事务后重启，仍不重刷。

Ubuntu 24 系列内即使更新到新的小版本或平台 revision，仍走上述 APT 路径。只有迁移到
Ubuntu 26、Debian 新大版本，或确实改变分区/引导布局时，才建立下一代黄金镜像系列；
这属于明确的迁移项目，不能夹带在普通 DEB 发布中。
