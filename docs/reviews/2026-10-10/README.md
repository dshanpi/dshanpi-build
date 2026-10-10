# 三仓交付改动与差异管理评审

快照时间：2026-10-10 UTC（北京时间 2026-10-10，美国东部 2026-10-09）。

当前改动可按板级适配、发行编排、设备端工具三条线维护。代码已推送，但合并状态不同：
ArmBianOS 的总体 PR #1 仍待合入 main；dshanpi-build 与 dspi-config 的相关 PR 已合入 main。
最需要审查的是 Armbian 共享框架、内核 headers ABI、精确包依赖和发布流程。
发行清单、测试日志占了大量文件，不能把总行数直接当作实现复杂度。

本次整理新增本目录三个文件，未修改业务代码、软件包、板端状态或已发布历史。
逐文件清单见 [files.csv](files.csv)，固定 commit、分组统计和非合并提交历史见
[inventory.json](inventory.json)。本目录暂留工作区供评审，未提交或推送。

## 统计口径与当前分支

统计为 `git diff --numstat BASE HEAD` 的最终净差异，不累计中间重写，也不计本次整理文件。
两个新仓库从各自初始占位提交开始统计；不是把这些行数都算成现有大型项目的侵入修改。
二进制只计文件数和字节数，不计文本行。非合并提交数包含文档和证据提交。

| 仓库 | 比较起点 | 当前 HEAD | 文件数 | 增加 / 删除行 | 非合并提交 | 合并状态 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| ArmBianOS | `9a3ce1500` 原 A1 基线 | `fb69b29b9` | 47 | 3968 / 7 | 17 | `feature/dshanpi-a1-cm5`，PR #1 待合并 |
| dshanpi-build | `1d389e8` 初始提交 | `8bb1317` | 157 | 10130 / 1 | 35 | main，PR #1 至 #19 已合并 |
| dspi-config | `3d4f930` 初始提交 | `2412c45` | 15 | 1123 / 2 | 8 | main，PR #1 至 #6 已合并 |

合计 219 个文件，15221 行增加、10 行删除。Armbian 为 38 个新增、9 个修改；
构建仓库为 156 个新增、1 个修改；客户端为 14 个新增、1 个修改。

已核对远端：ArmBianOS main 仍为 `9a3ce1500`，feature 分支与本地 HEAD 一致。
dshanpi-build main 与本地 `8bb1317` 一致；本地显示 ahead 7 是 origin/main 跟踪引用过期，
并非有 7 个未推送提交。dspi-config main 也与本地一致。

## 按实际职责拆分复杂度

### ArmBianOS

| 分组 | 文件数 | 增加 / 删除行 | 评审重点 |
| --- | ---: | ---: | --- |
| CM5 板级实现 | 13 | 2699 / 0 | 独立 board、DTS/DTSI、U-Boot patch、相机与无线扩展、BSP |
| 镜像集成与其他板 profile | 10 | 144 / 0 | 精确本地 DEB、工具/源/元包安装顺序；四板 profile |
| 现有共享框架修改 | 4 | 47 / 7 | 小范围但影响面大，应优先评审 |
| 文档、门禁、测试 | 20 | 1078 / 0 | 基线保护、检查脚本、政策与 BTF 回归测试 |

共享框架四个文件分别是：

| 文件 | 变更作用 | 影响范围 |
| --- | --- | --- |
| `lib/functions/general/extensions.sh` | 合并 board 的 ENABLE_EXTENSIONS 与调用方 EXT，追加发行扩展 | 共享构建机制；需要防止原板扩展丢失或重复执行 |
| `extensions/rockchip-multimedia.sh` | 按 BOARDFAMILY 识别 rk35xx | 使用该扩展的 Rockchip 板型 |
| `lib/functions/general/apt-utils.sh` | 上游包元数据缺失时回退读取 Packages 索引 | 条件明确限定 CM5 |
| `lib/functions/compilation/kernel-debs.sh` | BTF 内核 headers 声明 pahole 依赖，拒绝安装时静默改变 BTF 配置 | 共享 headers 打包逻辑；所有适用内核都需评估 |

原 A1 四个受保护路径与基线完全一致。CM5 使用独立 DTB 和内核包命名空间。
这证明保护路径未变，不代表共享代码不影响 A1。A1 可选 AIC8800D80 USB 包与 CM5 的
`extensions/dshanpi-aic8800.sh` 是不同集成，不应合并为一种板级实现。

总体评审入口：[ArmBianOS PR #1](https://github.com/dshanpi/ArmBianOS/pull/1)。
PR #2、#3、#4 都合入 feature 分支，尚未进入 main。
最新 headers 修复 [PR #4](https://github.com/dshanpi/ArmBianOS/pull/4) 单独为 4 文件、+95/-1，
其中实际打包逻辑 +13/-1，其余为说明、测试和 CI。

### dshanpi-build

| 分组 | 文件数 | 增加 / 删除行 | 评审重点 |
| --- | ---: | ---: | --- |
| 构建发布实现 | 39 | 3154 / 0 | 构建脚本、工作流、签名 APT、不可变历史包、镜像校验 |
| 包源码锁定与辅助程序 | 9 | 301 / 0 | AXCL 8GB/16GB、AIC 原始源码归档、容量与内核约束 |
| 产品配置 | 4 | 235 / 0 | A1、CM5、R1、Avaota A1 的包/板型映射 |
| 发行清单与验证证据 | 83 | 5126 / 0 | lock、包/镜像清单、签名、安装与硬件日志、截图 |
| 回归测试 | 12 | 802 / 0 | 依赖、发布恢复、镜像、复现性、驱动 ABI 防护 |
| 文档、门禁、仓库配置 | 10 | 512 / 1 | 三仓政策、说明、CI、公钥 |

两个二进制文件合计 4308132 字节，约 4.11 MiB：AIC 原始源码压缩包 1978244 字节，
六路测试截图 2329888 字节。数 GB 的镜像和录像没有纳入这里的源码统计。
最近可选包阶段（`24d2215..8bb1317`，含 headers 政策及证据）为 88 文件、+4745/-5。

| PR 范围 | 内容 | 阅读建议 |
| --- | --- | --- |
| #1 至 #8 | Pages APT、多板发行、精确包集复用、镜像交付记录 | 建立发行框架背景；证据与实现分别阅读 |
| #9 至 #10、#14 | 四板源锁修复发行、统一政策、headers 要求 | 和客户端及 Armbian 关联检查 |
| [#11](https://github.com/dshanpi/dshanpi-build/pull/11) 至 #13 | 初版 AXCL、Pages 失败处理、可复现构建 | 先看依赖与发布失败处理，再看证据 |
| [#15](https://github.com/dshanpi/dshanpi-build/pull/15) 至 #16 | AIC8800D80 DKMS/固件和安装记录 | USB 模块；WiFi 与蓝牙分别验收 |
| [#17](https://github.com/dshanpi/dshanpi-build/pull/17) | 显式 AXCL 16GB runtime/PAC/DKMS/元包及 ABI 防护 | 当前 A1 主要可选包实现 |
| [#18](https://github.com/dshanpi/dshanpi-build/pull/18) 至 [#19](https://github.com/dshanpi/dshanpi-build/pull/19) | 16GB 公网安装及六路实板证据 | 不把功能通过扩大成长期稳定性通过 |

### dspi-config

客户端与打包 5 文件、488 行；回归测试 2 文件、271 行；文档与门禁等 8 文件、+364/-2。
主体是 442 行 `bin/dspi-config`，按 BSP profile 识别产品，管理 Overlay、签名源及整组升级/回滚。
主要后续修复为域名迁移、完整回滚依赖、apt-cache SIGPIPE 和 sources.list.d 锁文件残留。
源锁回归覆盖四板 profile；软件覆盖不等于四块实板均已测试。

客户端 [PR #1](https://github.com/dshanpi/dspi-config/pull/1) 至
[#6](https://github.com/dshanpi/dspi-config/pull/6) 已合并。没有需要再次提交的客户端业务代码。

## 已交付内容和还没有闭合的环节

| 项目 | 当前事实 | 未完成内容 |
| --- | --- | --- |
| A1 系统镜像 | GitHub prerelease `dshanpi-a1-2026.10.08-4`，CLI/GNOME 两变体有镜像清单 | 旧镜像不包含后续全部维护包；不能等同当前 APT 包集 |
| 自动完整镜像发行 | release.yml 已构建镜像、保留 artifact、发布 APT | **尚无自动上传 ArmBianOS GitHub Release 及公开资产校验实现**，G06/G11 未闭合 |
| A1 testing APT | `2026.10.09-4`，29 包；16GB 发布记录证明本地/云端/公网哈希一致，23 个历史包不变 | 未晋级 stable；本次是包维护发行，没有新镜像 |
| AXCL 16GB | 4 包，`3.16.0+dshanpi2`；固定同源 runtime 与 PAC；APT 安装、5 个 DKMS 模块与 ABI 检查通过 | 长时间稳定性未验收；回滚只做依赖模拟，8GB 不是这张 16GB 卡的实板回滚目标 |
| 六路示例 | 20/20 NPU 测试，六路推理、7 路 RTSP、HTTP、录像和应用重启已验证；overview 约 30 FPS | 加风扇后约一分钟仍升至 85.294°C，主动停止；首次掉卡原因未确定 |
| AIC8800D80 | 3 包，`6.4.3.0+dshanpi1`；USB 枚举、DKMS；先前实板 WiFi 连接和传输已测 | 蓝牙配对及完整验收待完成 |
| headers BTF ABI | 根因与源码修复已记录；当前板经恢复和重建模块可用 | **包含源码修复的新版本 headers DEB 尚未发布**；旧发布字节不得覆盖 |
| 初版 AXCL 8GB | `3.16.0+dshanpi1` 历史包保留 | 没有随该包集交付已审定 PAC，不能宣称该容量完整推理验收 |
| 六路应用交付 | 固定 demo commit 原生构建使用，未修改应用源码 | 示例尚未做成可由 APT 安装的应用包，不能把 git 编译说成应用 DEB 交付 |

APT 与安装详情：[16GB validation](../../../products/dshanpi-a1/releases/2026.10.09-4.validation.json)。
功能及温升原始证据：[hardware.json](../../../products/dshanpi-a1/releases/2026.10.09-4.hardware.json)。
自动 Release 缺口在 [.github/workflows/release.yml](../../../.github/workflows/release.yml) 明确写明。
当前内核是 `6.1.115-vendor-rk35xx` vendor 分支，不应因镜像名为 Armbian 就标为 upstream mainline 内核。

## 源码和差异应该放在哪里

| 内容 | 归属与现有位置 | 管理方式 |
| --- | --- | --- |
| 板卡、内核、DTB/DTBO、BSP | ArmBianOS 的 config、patch、extensions、packages/bsp | 板型独立目录；共享修复单独 PR；保留原 A1 基线 |
| 可选驱动打包与上游锁定 | 本仓库 packages、scripts/build-*-packages.py | 同一主干下按组件目录管理，短期 feature 分支提交；不为每个驱动保留长期分支 |
| 厂商原始源码 | AIC 已存 `packages/aic8800d80/vendor/aic8800d80.tar.gz` | 原包保持不变，lock 固定 SHA；后续补丁放组件 patches 目录，不直接覆盖归档 |
| AXCL 厂商大文件 | packages/axcl*/upstream.lock.json | 固定上游完整 commit、URL、SHA；构建下载校验，必要时做不可变镜像备份 |
| 卡容量差异 | 当前 axcl 和 axcl-16g 两套目录与包名 | runtime/PAC 成对锁定，显式冲突；容量不是另一个板型，也不能隐式切换 |
| 用户配置工具 | dspi-config/bin 与 tests | 按板 profile 数据驱动；板级硬件清单随 BSP 交付 |
| 发行版本与已验收证据 | 本仓库 products/<board>/releases | 新增版本记录，保留旧清单和哈希；不要重写旧包和已发布 tag |
| DEB、镜像、大日志和录像 | 签名 APT、GitHub Release、受控归档 | Git 保存配方、锁定、摘要、哈希和稳定链接；大体积证据逐步转发行资产 |

现有 AIC 驱动适配等部分源码转换嵌在 builder 内；后续适合提取为有编号和说明的补丁。
这是待做的整理，不代表目前已有 patches 目录。新驱动建议沿用如下结构：

```text
packages/<component>/
  README.md               适用板卡、内核、安装与验证
  upstream.lock.json      原始来源、版本和哈希
  patches/                对厂商源码的可审查补丁
  packaging/              控制文件与维护脚本
  variants/               硬件差异数据，仅需要时添加
```

统一元数据应分别表达 board、kernel release/包版本、硬件 variant、上游版本、Debian 版本和发行版本。
同名 `uname -r` 不足以证明外部模块 ABI 相容；BTF 和原始模块结构检查的教训必须保留。
未来扩展到其他板型仍需声明支持矩阵、各板精确依赖和实板证据，不能仅删除 A1 限制就宣称支持。

## 建议的提交与评审安排

1. **先评审已存在的 Armbian PR #1。** 按“CM5 专属、共享框架、镜像集成、门禁”四组阅读。
   分支总体已经超出最初纯 CM5 支持的标题范围。合并时应让标题/描述覆盖最终共享修复和交付接入。
   已有 lock 引用了分支 commit，不建议为美化历史而直接 rebase 或 squash 原分支。
   若评审制度要求拆 PR，从 main 新建评审分支按依赖迁移，同时保留原 commit 可达和历史锁定。
2. **补发 headers 修复包，优先级高、跨仓风险高。** Armbian 固定修复 commit；构建仓库提高版本，
   记录精确内核对应关系，更新可选包的精确 headers 依赖及元包；干净安装、DKMS、实板重启验收。
   共享逻辑按四板评估，只发布有实际构建和验证证据的组合。不能只给现有板安装 pahole 后结束。
3. **自动镜像 Release 单独实现，工作量中高。** 版本计划固定 tag/commit/变体/资产；建立跨仓发布身份，
   支持失败后恢复、拒绝不同内容覆盖，并核对公网资产、哈希、headers 映射及同套 APT 包。
   完成实际流水线验收后才能关闭 G06/G11 缺口。
4. **可选包共享代码整理单独提交，工作量中。** AXCL 8GB/16GB 的逐行相似度为：工作流 92.3%、
   包 builder 92.3%、发行 builder 89.4%、公网验证器 94.6%（SequenceMatcher，关闭 autojunk）。
   可先提取构建/发布公共函数和可复用 workflow，保留变体独立输入、冲突关系及 ABI 防护。
   重构要求候选 DEB 与已发布哈希相同；如任何包字节改变，按政策提高版本。
5. **证据与功能分开提交。** PR #18/#19 已采用此方式。后续每个功能 PR 列关联仓库 commit、影响板型、
   包版本、测试方式、回滚边界和未验收项；测试记录 PR 引用实际源码与运行记录。

新增驱动一般只需动 dshanpi-build；增加 DTBO 或内核能力才联动 Armbian；
新增通用配置交互才改 dspi-config。板卡差异用 profile，硬件容量用 variant，厂商差异用 patches，
用户升级边界用 DEB 依赖及版本表达。这样能避免每块板复制完整构建脚本。

三仓政策以本仓库 DELIVERY_POLICY.md 为维护源，修改时同步副本并运行 --peer。
本次的目录管理与重构建议尚未写成新的强制政策，也尚未执行重构。

## 本地资料与复查命令

Armbian 工作区保留用户原始 `aic8800d80.tar.gz` 和生成的 `lib/tools/common/__pycache__/`，均未提交。
demo checkout 固定 `2aa772bbf16b8a904ee6ca57877c0e602208bf49`，应用源码未修改；
本次 status 检查显示三项视频资产为 modified，属于演示资源工作区状态，不计入三仓源码统计。
后续提交前需核对这些资产的 LFS/工作区状态，避免混入源码提交。
录像及原始日志保存在 `/home/ubuntu/dshanpi-build/output/six-streams-validation/`，
有效录像 `16g-overview-20s.mp4` 实长 18.933333 秒。

可复查固定快照，后续 HEAD 变化不会改变本次比较：

```bash
git -C /home/ubuntu/armbian/ArmBianOS diff --stat 9a3ce1500 fb69b29b9
git -C /home/ubuntu/dshanpi-build diff --stat 1d389e8 8bb1317
git -C /home/ubuntu/dspi-config diff --stat 3d4f930 2412c45
python3 tools/check-delivery-policy.py --peer /home/ubuntu/armbian/ArmBianOS --peer /home/ubuntu/dspi-config
```

本次通过三仓政策一致性和 A1/CM5 source 门禁，核对了文件统计与 Git 快照。
这些是资料与源码边界检查，不能替代上述待完成的发行和实板验收。
