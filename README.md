# dshanpi-build

`dshanpi-build` 是 DShanPI 产品构建与发行编排仓库。它调用各源码仓库的构建系统，
汇集经过固定版本和校验的产物，生成系统版本元包及签名 APT 仓库；它不保存内核、
设备树或 dspi-config 的源码副本。

## 仓库边界

- `ArmBianOS`：板卡、Kernel/U-Boot DTS、DTBO、BSP 和系统镜像构建引擎。
- `dspi-config`：设备端 overlay、软件源和系统版本管理工具及其 deb。
- `dshanpi-build`：固定源码 commit、调用构建、选择包、制作元包、生成并签名 APT。
- GitHub Pages：当前托管 `https://apt.100ask.net` 的签名仓库。
- `dlfilewebsite`：可选的自建服务器接收端；保留验签与原子导入接口。

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

APT 地址统一为 `https://apt.100ask.net`。stable suite 为 `noble`，testing suite 为
`noble-testing`；公共包位于 `common` component，板卡包位于产品同名 component。
testing 设置 `NotAutomatic`，不会被普通升级命令误装；stable 保持正常 APT 优先级。
所有历史版本默认保留。U-Boot 和 `linux-libc-dev` 不进入在线升级集合。

`DSHANPI_APT_BASE_URL` 表示完整仓库根地址，默认 `https://apt.100ask.net`；
`build-client-packages.sh` 的 `BASE_URL` 参数使用同样语义，不再自动追加 `/apt`。
下载站独立 APT 虚拟主机将该域名的 `/dists/`、`/pool/` 和 `/catalog/` 映射到已有仓库。
域名变更后的客户端包必须使用新的发行版本；历史 release lock 和已发布 deb 不应覆盖。

构建镜像时，本仓库通过 Armbian 的 `EXT` 接口追加板卡 profile、`dspi-config`、产品软件
源和 release 元包安装扩展，不覆盖板卡原有的相机、多媒体或固件扩展。产品 profile 随
板级 BSP 包安装到 `/usr/share/dspi-config/boards/<product>/`；软件源客户端包名为
`<product>-repository`，版本入口为 `<product>-release-core` 与
`<product>-release-desktop`。

## 发布门禁

### GitHub Pages 发布

仓库为 `dshanpi/dshanpi-build`。域名 DNS 配置为 `apt` CNAME → `dshanpi.github.io`，
Pages 使用 Actions 部署，Custom domain 设置为 `apt.100ask.net`。

```bash
# 公钥和指纹纳入源码，私钥只保存在受保护签名环境与 Actions Secrets。
scripts/fetch-pages.sh output/repository keys/dshanpi-archive.asc
# 按上面的 build-apt-repository / promote 命令修改并签名该副本，然后：
scripts/publish-pages.sh output/repository keys/dshanpi-archive.asc
```

`feature/apt-pages-state` 分支保存完整签名仓库快照。大文件按 64 MiB 分块存储，
Actions 重组后验证 GPG、各级元数据及每个 deb 的 SHA-256，再部署到 Pages。
发布前检查旧状态哈希与历史 pool 不变性，普通 Git push 拒绝并发覆盖。
快照不依赖会过期的 Actions artifacts；Pages 内容预算为 950 MB，超限直接停止。
这适用于首阶段闭环；更多板卡和长期版本历史增长后应切换大容量托管。

Actions `Build and publish DShanPI product` 的 `backend` 选择 `github-pages`，即可全程
使用 GitHub；`ssh` 保留原服务器通道。GitHub 分支部署策略需允许运行发布工作流的源码分支，
以及 `feature/apt-pages-state`。testing 与 stable 的构建发布共用串行队列。

签名公钥：[`keys/dshanpi-archive.asc`](keys/dshanpi-archive.asc)，
指纹：[`keys/dshanpi-archive.fingerprint`](keys/dshanpi-archive.fingerprint)。
本次 `2026.10.08-1` / `2026.10.08-2` CM5 候选的精确输入记录在
`products/dshanpi-a1-cm5/releases/*.packages.json`；复用已记录的 9 月 30 日内核产物，
新增包含板卡 profile 的 BSP 和独立域名客户端。两组候选分别使用 dspi-config
`1.0.1-2` / `1.0.2-1`，保留真实升级与降级路径；它们均不代表真机验证已完成。

下次从源码完整构建可在 Actions 中选择 `product=dshanpi-a1-cm5`、
`version=2026.10.08-3`、`channel=testing`、`backend=github-pages`。
对应 release lock 已固定当前板级源码和新版 dspi-config 的提交；该版本尚未构建或发布。
完整新内核包可能触及 Pages 容量预算，门禁会保留已发布历史并停止超限发布。

testing 发布必须先通过包集、身份冲突、权限、RPATH、签名和本地 APT 客户端测试。
stable 只能读取 testing 的候选清单并复用相同 SHA-256。硬件启动、显示、相机、无线、
USB/PCIe、DKMS、重启和回滚未验证前不得晋级 stable。

生产私钥只放在本仓库 GitHub Actions Secrets 中；下载站只安装公钥。首版 Debian
源码包为可选项，DShanPI 自研源码包门禁将在后续版本启用。
