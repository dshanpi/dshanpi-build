---
record_id: CR-2026-10-15-axcl-user-access
date: 2026-10-15
repository: dshanpi-build
requirements:
  - REQ-AXCL-USER-ACCESS-001
---

# AXCL 16GB 普通用户访问权限

## 需求与范围

REQ-AXCL-USER-ACCESS-001：用户授权访问维护虚拟机，阅读源码与发行手册后重构安装包，
解决普通用户 axcl-smi 的设备和日志 Permission denied。范围为 A1 的 16GB 可选包；
8GB 历史包、A1 CM5、R1、Avaota A1 的配方与硬件支持不变。无新硬件兼容声明。
用户授权构建和测试；本会话未授权签名发布或 stable 晋级，不操作公共仓库。

## 业务逻辑

权限配置由 selector DEB 拥有：udev 精确匹配四个 misc 节点，仅授权 render 组；
tmpfiles 创建/修正日志目录和文件，服务在初始化前再次应用并设置 UMask。
postinst 创建缺失的组，修复日志和当前节点，不加载驱动或启用服务。初始化命令等待
udev 完成后再查询设备。postrm 仅刷新规则/服务缓存，保留日志、成员关系和管理员覆盖。
管理员显式选择账号加入 render；默认镜像既有成员关系不修改。

组件包版本提高至 3.16.0+dshanpi.2026.10.15.1，驱动/固件来源和 SHA 不变，精确内核
依赖仍为 25.11.0-trunk.20261010.1。构建器拒绝使用更早包身份装入新权限内容；旧
发行 lock 不修改。维护与完整四包路径均由同一 selector 模板获得权限修复。

## 流程

```mermaid
flowchart TD
 A[安装或升级新版本四包] --> B[校验精确依赖及上游哈希]
 B -->|失败| X[停止并保留错误]
 B -->|通过| C[配置 selector 创建或读取 render 组]
 C --> D[tmpfiles 设置日志权限]
 D -->|失败| X
 D --> E{udev 守护进程和设备存在}
 E -->|是| F[刷新已有节点权限]
 E -->|否| G[等待后续设备创建]
 F --> H[管理员确认卡容量与散热并启动服务]
 G --> H
 H --> I[初始化前恢复日志权限并等待 udev]
 I --> J[普通用户查询和 NPU 测试]
 J -->|失败| K[检查组和覆盖文件 保留日志后修复重试]
 J -->|通过| L[重启后复验]
```

## 安全与失败分支

不使用 chmod 777，不删除日志，不自动猜测和授权用户，不在安装阶段启动卡或模型。
组创建/tmpfiles/在线 udev 失败均中止 configure；解决根因后可重试 dpkg 配置。
离线镜像没有运行中的 udev/systemd 时跳过守护进程刷新，日志配置仍执行。
未知容量、PAC/ABI 不匹配仍由原检查拒绝。8GB 与 16GB 冲突关系不变。
不修改同事已有的 README 和下载器工作区变更；只暂存本次明确审查的文件。
重刷/回滚旧包会回到旧行为；正式回滚必须整套精确依赖一致，不能将 8GB 套件当回滚。

## 测试报告

| 类型 | 命令/检查 | 结果 | 证据 |
| --- | --- | --- | --- |
| 静态 | check-delivery-policy.py --peer 两个同级仓库；sh/bash -n | PASS | 本机任务证据 09-tests-build.json |
| 软件模拟 | unittest discover -s tests -p 'test_axcl*.py' | PASS，16 项；包括权限生命周期、ABI 和依赖 | tests/test_axcl_access.py；09-tests-build.json |
| 构建/包 | build-axcl-16g-packages.py，固定三个历史输入 SHA，完整四包 | PASS，4 包审计通过；当前内核精确绑定 | output/axcl-access-20261015/packages/axcl-16g-build.json |
| 负向 | 使用旧版 3.16.0+dshanpi.2026.10.10.1 请求新配方 | PASS，拒绝且未创建输出目录 | 11-audit.json |
| 软件回归 | unittest discover -s tests -p 'test_*.py'；bash tests/test.sh | PASS，79 项 Python 及 Shell 回归 | 10-regression.json |
| 构建/包 | 解包核对模板、0644/0755 权限、无 /etc 覆盖；对比历史 runtime/PAC | PASS，182 个运行时文件及 1 个 PAC 内容未变 | output/axcl-access-20261015/package-verification.json |
| 工作区门禁 | check-change-record.py | BLOCKED，同事已有未提交 CR-2026-10-14-public-verifier-range-download.md 缺少流程章节；本次记录单独校验 PASS | 12-docs.json；13-package-check.json |
| 实板 | 原测试板 SSH 探测 | BLOCKED，连接超时，等待用户确认开机/IP | 当前任务板端连接记录 |
| 公开端点 | testing 发布后验签与包下载 | NOT-RUN，本次未发布 | 不适用 |

## 未完成项

等待原板恢复连接后移开既有 /etc 手动补丁，测试候选包升级、普通用户访问和重启；
未验证新包前不能引用旧板端补丁的成功作为本包验收。干净安装和回滚单独记录。
正式 APT 发行需新 release lock、基础签名清单、精确元包、testing 发布及公共验证；
本次本地候选包不代表在线交付完成。其他板卡与 8GB 未执行硬件验证。

## 交付影响

仅修改 dshanpi-build 的 16GB 组件、构建器、测试和本记录。无需修改 ArmBianOS
内核/设备树或 dspi-config。8GB 不借此扩大支持范围；其历史包仍要求管理员访问。
本机候选与源码改动供评审，旧源包、历史 DEB、release lock 和 tag 均保留。
包进入正式 testing 并通过验收后，独立客户指南方可移除该新版本的手工权限配置。
