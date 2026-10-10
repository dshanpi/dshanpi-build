# DShanPI 交付开发记录与接续入口

遵守 [DELIVERY_POLICY.md](../DELIVERY_POLICY.md)。从 [新服务器手册](new-server.md) 开始，
维护指引见 [仓库 skill](../.agents/skills/maintain-dshanpi-delivery/SKILL.md)。

## 变更和版本证据

- [三仓差异评审](reviews/2026-10-10/README.md) 和同目录 CSV/JSON 为整理前固定快照；
  其中“待合并/未提交”描述快照时点，不代表本次交接后的远端状态。
- A1 镜像为 `2026.10.08-4` CLI/GNOME prerelease；后续 `2026.10.09-1` 至 `-4` 为维护发行。
- [AXCL 初版](../packages/axcl/README.md)、[16GB 版本](../packages/axcl-16g/README.md)、
  [AIC8800D80](../packages/aic8800d80/README.md) 分别保存来源、依赖和安装边界。
- [16GB 公网安装证据](../products/dshanpi-a1/releases/2026.10.09-4.validation.json) 与
  [六路硬件证据](../products/dshanpi-a1/releases/2026.10.09-4.hardware.json) 对应 testing 包集 29 包。
  16GB runtime/PAC 同源固定，四包哈希已经过本地/云端/公网比较，23 个历史包不变。

六路参考应用使用 `dshanpi/ax8850-multistream-demo` 的
`2aa772bbf16b8a904ee6ca57877c0e602208bf49`；复现时先核对该仓库地址、commit 和资源清单。
该应用源码没有作为本次三仓变更修改，模型/视频通过其资源获取入口校验；不是已发布的示例应用 DEB。
有效录像 SHA 为 `ac16bd2df31a5b3046eb350e0aaabe2c1e8030ada05aef2e6acebaad22e0da81`，
实长 18.933333 秒，原视频只保留在旧机 output 与板端 recordings，未纳入源码仓库；
已提交的截图及 JSON/日志足以核对既有结果，重新运行会生成新证据。

## 必须接续的事项

1. 新版本 headers DEB：ArmBianOS BTF 修复已在源码，旧 `25.11.0-trunk.20261008.4`
   headers 仍为历史字节。当前板的恢复不替代全产品新发行。
2. 自动完整镜像 Release：release.yml 目前只保留镜像 artifact 和发布 APT，尚未实现
   自动上传 ArmBianOS Release 及公网资产验收；不能把已有人工作业记录当成流水线实现。
3. 六路长期稳定性：20/20 NPU、六路推理、RTSP/HTTP、录像和重启已通过有限时测试。
   加风扇后升至 85.294°C 被主动停止；首次掉卡原因未确定，未晋级 stable。
4. AIC 蓝牙配对待验收；8GB AXCL 旧发行未提供审定 PAC；16GB 回滚只验证了依赖模拟。
5. 公共 AXCL builder/workflow 重复逻辑待单独重构；不能借整理覆盖原包或隐式切换卡容量。

## 资料管理

实现、政策/维护工具、实板证据分开提交并互相引用 commit/哈希。
小型验证日志保留发行目录；大录像、镜像和 DEB 走发行资产或签名 APT。
临时 SSH 密码、签名私钥、个人 shell 历史和原始 Codex 会话不作为开发记录上传。
根目录 AGENTS 与仓库 skills 为接续入口，不要求从旧服务器复制 ~/.codex。

## 本次原生服务器交接验证

[验证清单与包哈希](validation/2026-10-10-handoff/verification.json) 和同目录 native-build.log
记录原生 Ubuntu 24.04 x86_64、干净 checkout 的软件测试与重建。客户端 1 包、AIC 3 包、
AXCL 16GB 4 包全部与已发布清单哈希一致。客户端需固定历史 umask 0002。
固定版本下载器已实际从 GitHub 下载三仓并通过基线门禁；正式步骤不依赖 Docker。
本次只推送源码与开发记录，没有重新发布包、镜像或执行板端操作。
