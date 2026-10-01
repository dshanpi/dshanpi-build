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
所有历史版本默认保留。U-Boot 和 `linux-libc-dev` 不进入在线升级集合。

## 发布门禁

testing 发布必须先通过包集、身份冲突、权限、RPATH、签名和本地 APT 客户端测试。
stable 只能读取 testing 的候选清单并复用相同 SHA-256。硬件启动、显示、相机、无线、
USB/PCIe、DKMS、重启和回滚未验证前不得晋级 stable。

生产私钥只放在本仓库 GitHub Actions Secrets 中；下载站只安装公钥。首版 Debian
源码包为可选项，DShanPI 自研源码包门禁将在后续版本启用。
