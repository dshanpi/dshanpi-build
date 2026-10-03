# dshanpi-build

`dshanpi-build` 是 DShanPI 产品构建与发行编排仓库。它调用各源码仓库的构建系统，
汇集经过固定版本和校验的产物，生成系统版本元包及签名 APT 仓库；它不保存内核、
设备树或 dspi-config 的源码副本。

## 仓库边界

- `ArmBianOS`：板卡、Kernel/U-Boot DTS、DTBO、BSP 和系统镜像构建引擎。
- `dspi-config`：设备端 overlay、软件源和系统版本管理工具及其 deb。
- `dshanpi-build`：固定源码 commit、调用构建、选择包、制作元包、生成并签名 APT。
- `dlfilewebsite`：验签、原子导入和静态提供 `https://dl.100ask.net/apt`。

## 产品配置

每个产品使用 `products/<product>/product.json`。新增板卡只新增产品配置和必要的构建
适配器，不复制 APT 发布脚本。一次正式构建还需要 release lock：

| 产品 | Armbian board/branch | 内核包命名空间 | 产品 component |
| --- | --- | --- | --- |
| DShanPI A1 CM5 | `dshanpi-a1-cm5` / `vendor` | `rk3576-dshanpi-a1-cm5` | `dshanpi-a1-cm5` |
| DShanPI A1 | `dshanpi-a1` / `vendor` | `rk35xx` | `dshanpi-a1` |
| DShanPI R1 | `dshanpi-r1` / `vendor` | `rk35xx` | `dshanpi-r1` |
| Avaota A1 | `avaota-a1` / `legacy` | `sun55iw3-syterkit` | `avaota-a1` |

其中 A1 与 R1 使用同一个经过固定 commit/revision 的 RK35xx 内核包，但 BSP、仓库入口和
release 元包均按产品隔离。`avaotaa1` 不是内部标识；配置、包名和发布命令统一使用
`avaota-a1`。

`package_search_paths` 声明该产品允许收集的 ArmBianOS 产物目录。最终进入发布目录的包仍
必须逐项出现在 `required_packages`，同一个“包名 + 版本 + 架构”出现零份或多份都会失败，
因此不会把整个 `output/debs` 中的历史包或其他板卡包误发布。

```json
{
  "schema_version": 1,
  "product": "dshanpi-a1-cm5",
  "version": "2026.09.30-1",
  "revision": "25.11.0-trunk.20260930.1",
  "sources": {
    "armbianos": {"commit": "完整 40 位 SHA"},
    "dspi_config": {"commit": "完整 40 位 SHA"}
  }
}
```

源码必须固定完整 commit，不能使用漂移分支。版本号使用 `YYYY.MM.DD-N`。

## 常用命令

```bash
# 构建 dspi-config、APT 客户端、ArmBian 包和 CLI/Desktop 镜像
scripts/build-product.sh dshanpi-a1-cm5 path/to/release.lock.json

# 其他产品使用完全相同的入口
scripts/build-product.sh dshanpi-a1 products/dshanpi-a1/releases/2026.10.02-1.lock.json
scripts/build-product.sh dshanpi-r1 products/dshanpi-r1/releases/2026.10.02-1.lock.json
scripts/build-product.sh avaota-a1 products/avaota-a1/releases/2026.10.02-1.lock.json

# 从完整包目录生成精确依赖且可独立安装的 core/desktop 元包
scripts/build-release-meta.sh dshanpi-a1-cm5 2026.09.30-1 packages/

# 在已有仓库副本上加入 testing 候选并重新生成/签名 APT
scripts/build-apt-repository.sh testing dshanpi-a1-cm5 2026.09.30-1 \
  packages/ repository/ "$APT_GPG_KEY_FINGERPRINT"

# 真机验证后，将完全相同的候选包晋级 stable；不重新编译
scripts/promote-apt-release.sh dshanpi-a1-cm5 2026.09.30-1 \
  repository/ "$APT_GPG_KEY_FINGERPRINT"

# testing 候选失败时只撤回其产品索引，pool 文件和 stable 均不删除
scripts/withdraw-testing-release.sh dshanpi-a1-cm5 2026.09.30-1 \
  repository/ "$APT_GPG_KEY_FINGERPRINT"

# 上传完整签名仓库候选；下载站只验签并原子导入
scripts/publish-apt.sh repository/
```

APT 地址统一为 `https://dl.100ask.net/apt`。stable suite 为 `noble`，testing suite 为
`noble-testing`；公共包位于 `common` component，板卡包位于产品同名 component。
testing 设置 `NotAutomatic`，不会被普通升级命令误装；stable 保持正常 APT 优先级。
所有历史版本默认保留。U-Boot 和 `linux-libc-dev` 不进入在线升级集合。

构建镜像时，本仓库通过 Armbian 的 `EXT` 接口追加板卡 profile、`dspi-config`、产品软件
源和 release 元包安装扩展，不覆盖板卡原有的相机、多媒体或固件扩展。产品 profile 随
板级 BSP 包安装到 `/usr/share/dspi-config/boards/<product>/`；软件源客户端包名为
`<product>-repository`，版本入口为 `<product>-release-core` 与
`<product>-release-desktop`。

## 发布门禁

testing 发布必须先通过包集、身份冲突、权限、RPATH、签名和本地 APT 客户端测试。
stable 只能读取 testing 的候选清单并复用相同 SHA-256。硬件启动、显示、相机、无线、
USB/PCIe、DKMS、重启和回滚未验证前不得晋级 stable。

生产私钥只放在本仓库 GitHub Actions Secrets 中；下载站只安装公钥。首版 Debian
源码包为可选项，DShanPI 自研源码包门禁将在后续版本启用。
