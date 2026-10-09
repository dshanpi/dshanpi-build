> DShanPI 开发、构建与发布必须遵守 [三仓统一交付门禁](DELIVERY_POLICY.md)，工作入口见 [AGENTS.md](AGENTS.md)。

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

所有产品同时受 [三仓统一交付门禁](DELIVERY_POLICY.md) 约束。完整系统发行必须自动发布
到 `dshanpi/ArmBianOS` GitHub Releases，并关联相同 DEB 的 APT 发布与公开下载验证。
后续维护发行可只构建 DEB 和精确元包。每次构建/发布入口与 CI 均先执行政策一致性检查。

当前自动化缺口：`release.yml` 会保留镜像 artifact 并发布 APT，但尚未实现自动 GitHub
镜像 Release 上传及发布后验证。这是 G06/G11 的待实现项；本次门禁接入不代表该环节已完成。
后续实现必须把它接入同一版本计划，不能把手工上传作为常规完成步骤。

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

CM5 `2026.10.08-3` 的 21 个软件包已发布到 testing，精确文件校验值记录在
`products/dshanpi-a1-cm5/releases/2026.10.08-3.packages.json`。A1、R1 和 Avaota A1
也分别提供 `2026.10.08-1` 候选；网站支持按板卡、版本和 CLI／桌面类型生成整组
精确安装命令。HTTPS、签名、四款板卡页面和全部 12 组版本／类型依赖解析均已验证。

CM5 `2026.10.08-3` 的 CLI 和 GNOME 桌面镜像已完成构建及只读验收，原始镜像与
gzip 压缩包的校验值见 `products/dshanpi-a1-cm5/releases/2026.10.08-3.images.json`。
验收包括完整精确依赖、启动 DTB、AIC8800 模块、三路相机节点、IQ 文件和签名源配置。
本次镜像保存在构建工作区 `output/dshanpi-a1-cm5/2026.10.08-3/images/`，未上传 GitHub
Release；实际硬件启动、外设和升级／重启／回滚测试仍待完成。

后续构建先提交新的 release lock，使用尚未发布的版本号和单调递增的 Armbian revision，
再在 Actions 中选择对应 `product`、`version`、`channel=testing`、`backend=github-pages`。
不要复用已发布版本号写入不同内容。Pages 预算检查会保留历史并停止超限发布。

testing 发布必须先通过包集、身份冲突、权限、RPATH、签名和本地 APT 客户端测试。
stable 只能读取 testing 的候选清单并复用相同 SHA-256。硬件启动、显示、相机、无线、
USB/PCIe、DKMS、重启和回滚未验证前不得晋级 stable。

生产私钥只放在本仓库 GitHub Actions Secrets 中；下载站只安装公钥。首版 Debian
源码包为可选项，DShanPI 自研源码包门禁将在后续版本启用。

## 发行管理与镜像验收

网站 `apt.100ask.net` 根据已验签的发布清单生成板卡、版本和软件包列表。
仓库管理员从 Actions 的 **Build and publish DShanPI product** 选择产品和版本：

- `testing`：按 release lock 构建包和 CLI/Desktop 镜像，再发布候选。
- `stable`：填写真机验证记录，仅晋级已经发布的相同包；不重新编译。
- `withdraw`：撤回指定 testing 候选，保留其他版本仍需要的依赖和所有历史 pool 文件。

完整构建只收集当前 `REVISION` 的生成包，继续拒绝同一版本的多个候选，
不会从缓存里猜选“最新”包。未发布的无压缩 deb 会转为 xz；控制 tar 和数据 tar
分别核对 SHA-256，不改文件内容，也不重写已发布的包。A1 的 RKAIQ 适配器使用
已经固定输入 SHA-256 的清理脚本，不修改原 A1 板卡配置或相机安装扩展。

最终镜像从本地安装 release 元包及其所有精确依赖，不要求候选先出现在公开源。
构建时可设置 `DSHANPI_PUBLISHED_REPOSITORY` 指向已签名的历史仓库；Actions 自动传入。
工具验证签名后，对相同版本、相同安装内容的软件包复用已发布文件，仅容许
`Installed-Size` 和校验清单排序等打包元数据差异。安装文件、权限、依赖或维护脚本
发生变化仍会拒绝复用，必须提高软件包版本号。
`verify-image.sh PRODUCT VERSION IMAGE.img` 只读挂载镜像，检查元包、每个依赖的
已安装版本、板卡身份、DTB、配置工具 profile、域名和签名配置。CLI 和 Desktop
都通过后才复制到本次发行的输出目录。Actions 构建产物保留 7 天；长期镜像托管
仍使用独立下载渠道，不计入 Pages 的 1 GB 配额。

示例：

```bash
sudo scripts/verify-image.sh dshanpi-a1-cm5 2026.10.08-3 /absolute/path/to/image.img
```

镜像内容检查和 APT 安装测试不能替代真机启动、外设、升级后重启和回滚验证。
