# 仓库强制工作要求

开始修改、构建、发布或评审前，必须读取 [三仓统一交付门禁](DELIVERY_POLICY.md)，并运行
`python3 tools/check-delivery-policy.py`。该政策适用于全部产品及共享代码。

本仓库是唯一发行编排入口：固定源码 → 构建和验证 DEB → 签名发布 apt.100ask.net；
完整系统发行还必须使用同一套包组装镜像并自动发布到 dshanpi/ArmBianOS Releases。
软件包维护发行可复用旧硬件包，但必须更新受影响产品的精确依赖元包。
每个镜像必须按 G12 关联并公开发布精确匹配的 `linux-headers-*` DEB，记录大小、哈希和
APT 后装命令，保留旧版本；缺包或 ABI/版本不匹配不能宣布镜像交付完成。

禁止以临时 artifact、手工传包或单板热修复代替交付完成。发布后核对公开索引、签名、
下载文件和哈希；镜像发行还须核对 Release 状态和全部资产。保留历史不可变包与回滚路径。

共享变更必须评估 A1、A1 CM5、R1、Avaota A1；测试记录区分软件模拟和实板。
stable 只晋级具有适用实板证据的同一组包，不重新构建。

提交前运行政策检查、适用 shell/Python 测试及 `git diff --check`。
跨仓修改同步政策副本并使用 `--peer` 检查，PR 列明关联仓库和未完成环节。
政策检查通过不代表自动镜像发布已经实现；缺少的自动化必须明确记录，不能宣称完整流程已完成。

按 DELIVERY_POLICY.md G13 执行源码归属：板级/内核/设备树归 ArmBianOS，可选驱动
锁定/补丁/DEB/发行归 dshanpi-build，用户交互归 dspi-config，板卡差异用 BSP profile。
组件按目录、短期分支和 PR 管理；实现与验证证据分开提交，历史 lock/包/tag 不覆盖。
暂存后运行 `python3 tools/check-repository-hygiene.py`；只暂存明确审查的文件，
缓存、构建输出、私钥和个人凭据不提交。技能与开发交接记录随仓库维护。

维护本仓库时读取 `.agents/skills/maintain-dshanpi-delivery/SKILL.md`；开发交接见 `docs/development-handoff.md`。
