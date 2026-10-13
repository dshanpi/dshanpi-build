# Release locks

正式发行前在本目录增加 `<YYYY.MM.DD-N>.lock.json`。文件必须固定 ArmBianOS 和
dspi-config 的完整 commit SHA；构建脚本拒绝分支名、tag 和短 SHA。

完整镜像计划还必须包含 `image_release`：固定 `dshanpi/ArmBianOS` 的唯一产品 tag、
目标 ArmBianOS commit、标题、testing/stable 的 draft 与 prerelease 状态、CLI/desktop
原始镜像名、压缩资产名及完整资产清单。`release.yml` 先验证公开签名 APT 包集，再用
受保护的 `ARMBIANOS_RELEASE_TOKEN` 创建 prerelease；stable 只晋级同一 tag 和资产，
不得重建或覆盖。发布脚本会再次核对 tag commit、资产集合和 SHA-256。

本目录遵守 [三仓统一交付门禁](../../../DELIVERY_POLICY.md)。相同要求适用于所有产品的版本记录。
