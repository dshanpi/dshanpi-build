# Ubuntu 24.04 新服务器交接

适用 Ubuntu 24.04 x86_64，普通 sudo 用户，能访问 GitHub、Ubuntu 源、Hugging Face 与
apt.100ask.net。执行 [DELIVERY_POLICY.md](../DELIVERY_POLICY.md) 和仓库内 skills。
本手册不依赖旧机路径、代理、缓存或全局 Codex 配置。

## 1 获取固定版本的三仓

三仓维护分支统一为 main。正式复现使用交付时提供的完整 commit；后续 main 会继续变化。
先取得 dshanpi-build 的交付 commit，再用其中的下载器取得全部代码：

```bash
git clone --single-branch --branch main https://github.com/dshanpi/dshanpi-build.git dshanpi-bootstrap
cd dshanpi-bootstrap
# 将交接回复中的 dshanpi-build 完整 SHA 设置为 BUILD_COMMIT
git checkout --detach "$BUILD_COMMIT"
python3 scripts/checkout-workspace.py "$HOME/dshanpi-workspace"
cd "$HOME/dshanpi-workspace/dshanpi-build"
```

`handoff/sources.json` 固定 ArmBianOS 与 dspi-config；dshanpi-build 的 `self` 解析为运行
下载器的 checkout commit，避免清单引用自身 SHA 的循环。工作区根的 workspace-lock.json
记录最终三仓完整 SHA。下载器保留 main 历史，必要时补取指定 commit；不拉取 APT 数据分支。
它拒绝覆盖任何已有仓库，不安装依赖或发布。
失败时保留部分 checkout 便于诊断；重试使用另一个空目录，不自动删除用户数据。
不要只下载 GitHub ZIP：source 门禁需要原 A1 Git 基线。

## 2 主机工具和预检

软件包构建至少预留 5 GiB 空间；镜像预检起始要求 100 GiB，完整多板构建建议另预留更多空间。
建议 16 GiB 或更多主机内存；这里的主机内存与 AX8850 卡的 16GB 容量是不同概念。
完整镜像构建由 Armbian 安装更多依赖、准备 ARM64 rootfs，需要 sudo 和外网，不是离线构建。

```bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates python3 python3-yaml jq \
  dpkg-dev gnupg patchelf xz-utils build-essential ripgrep rsync \
  qemu-user-static binfmt-support device-tree-compiler pigz sudo
python3 scripts/preflight-host.py --mode packages --network
sudo -v
python3 scripts/preflight-host.py --mode images
```

预检只报告环境，不安装或修改配置。磁盘阈值不是峰值保证；APT 状态快照和多个镜像都占空间。
网络检查只证明入口可访问，实际固定源文件仍须下载并校验 SHA。代理如有需要由操作者配置，
不能把旧机代理地址、令牌或密码写进仓库。

## 3 门禁与软件测试

以下命令均从 dshanpi-build 根运行，默认三个目录同级：

```bash
python3 tools/check-delivery-policy.py --peer ../ArmBianOS --peer ../dspi-config
python3 tools/check-repository-hygiene.py
python3 ../ArmBianOS/tools/check-repository-hygiene.py
python3 ../dspi-config/tools/check-repository-hygiene.py
bash ../ArmBianOS/.agents/skills/guard-dshanpi-a1-cm5/scripts/a1_cm5_gate.sh source "$(realpath ../ArmBianOS)"
python3 ../ArmBianOS/tools/test-kernel-headers-btf.py
python3 -m unittest discover -s tests -p 'test_*.py'
bash tests/test.sh
bash ../dspi-config/tests/test.sh
```

源码卫生检查读取 Git 索引，包括已暂存文件，不会删除本地未跟踪缓存。
Git 合并 main 不代表旧镜像或历史 lock 已自动升级到 main。

## 4 构建客户端和可选包

```bash
(umask 0002; bash ../dspi-config/packaging/build-deb.sh output/replay/client)
python3 scripts/build-aic8800d80-packages.py output/replay/aic8800d80
python3 scripts/build-axcl-16g-packages.py output/replay/axcl-16g
sha256sum output/replay/client/*.deb output/replay/aic8800d80/*.deb output/replay/axcl-16g/*.deb
```

AIC 原始源码已按 SHA 固定并纳入 vendor 目录；AXCL builder 从上游完整 commit URL 下载并
校验源 DEB 与 PAC。输出目录应为新的专用目录。x86_64 上打包 ARM64 来源不代表已编译或
加载 ARM64 DKMS 模块；DKMS 在匹配内核的 A1 上验收。

历史参考：客户端 `1.0.2-3`，AIC `6.4.3.0+dshanpi1`，AXCL 16GB `3.16.0+dshanpi2`。
历史客户端打包需显式 `umask 0002`（默认 0022 会改变目录权限），详见客户端开发记录。
本次维护资料不应改变这些包字节；候选包与签名历史清单不一致时停止，不能覆盖原版本。
对应清单与哈希在 products/dshanpi-a1/releases 的 `2026.10.09-3`、`2026.10.09-4` 记录中。

## 5 验证和复现历史包维护发行

不需要私钥即可读取、验签历史状态并组装维护候选：

```bash
bash scripts/fetch-pages.sh output/previous keys/dshanpi-archive.asc
python3 scripts/build-axcl-16g-release.py 2026.10.09-4 output/previous
```

fetch-pages 使用当前仓库 origin 中的 `feature/apt-pages-state` 数据分支，该分支是不可变包
快照的存储入口，不是组件开发分支。已有 destination 会被拒绝；APT 状态下载较大。
组装器复用签名历史字节、校验 base manifest，重新生成的候选只用于对照，不会自动发布。
本手册不重复上传已有版本。其他 maintenance_adapter 使用对应 build-*-release.py。

## 6 完整镜像构建

历史 A1 完整镜像计划为 `2026.10.08-4`；`2026.10.09-4` 是可选包维护计划，不能作为
完整镜像输入。先查看计划，再执行耗时构建：

```bash
bash scripts/build-product.sh dshanpi-a1 products/dshanpi-a1/releases/2026.10.08-4.lock.json --print-plan
(umask 0002
APT_PUBLIC_KEY_FILE="$PWD/keys/dshanpi-archive.asc" \
  DSHANPI_PUBLISHED_REPOSITORY="$PWD/output/previous" \
  bash scripts/build-product.sh dshanpi-a1 products/dshanpi-a1/releases/2026.10.08-4.lock.json
)
```

构建器从 lock 获取历史源码，不能用本次 main checkout 冒充历史 commit。
历史计划包含旧 headers 行为；此命令用于复现，不用于宣称 BTF 修复已进入发行。
若非完全相同字节，必须先调查环境与上游输入漂移；禁止用重建结果覆盖旧包。

要制作包含最新修复的新镜像，应新增发行 lock、提高 revision，固定修复后的源码，
同步更新精确内核/headers/可选 DKMS 依赖，先审查计划再构建。不得修改旧 lock 来切换源码。
输出位于 output/<product>/<version>/，其中 CLI/desktop 镜像经过挂载检查。
完整镜像还必须验证 G12 headers 对应关系、外部模块编译及实板；x86 主机上的打包成功不能替代。

## 7 签名与发布配置

优先使用 dshanpi-build GitHub Actions 的现有 testing 工作流。需要仓库配置：

| 配置 | 用途 |
| --- | --- |
| APT_GPG_PRIVATE_KEY | 现有仓库签名身份的私钥，通过受保护 Secrets 配置，禁止入 Git |
| APT_GPG_KEY_FINGERPRINT | 与 keys/dshanpi-archive.fingerprint 一致 |
| GitHub Pages Actions 环境 | 部署已签名的 APT；域名 apt.100ask.net |
| contents/pages/id-token 工作流权限 | 状态分支写入与 Pages 发布 |

服务器只做本地构建、哈希对比和验签时无需私钥。已有 Secrets 在 GitHub 仓库端，换构建服务器
无需把它们下载到本地。若采用 SSH 后端，再按 publish-apt.sh 配置 DL_*，不得复用文档示例为真实密码。

**当前 release.yml 尚未实现镜像自动上传 ArmBianOS GitHub Release 及公开资产校验。**
它的镜像 artifact 只有临时保存期限，不能算正式镜像发行。跨仓 Release 发布身份和版本计划
是后续自动化实现的一部分，不在本次交接中冒充已配置完成。

## 8 实板验证与剩余项

新服务器构建完成后，按对应产品说明由签名 APT 安装，检查精确内核/headers、BTF、DKMS、
PCIe/USB 枚举，再验证功能、重启和回滚。AXCL 16GB 必须选配套 runtime/PAC，不能装 8GB
cohort 当回滚。不要把服务器的测试结果写成 A1 硬件通过。

当前源码修复尚待新版 headers DEB 发布；AIC 蓝牙配对、六路长期稳定性、自动镜像 Release
仍未完成。详见 [开发交接](development-handoff.md) 和其中的原始证据链接。
每次新测试分别记录环境、三仓 SHA、包/镜像 SHA、命令、退出结果与未完成项。
