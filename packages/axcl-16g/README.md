# A1 AX8850 16GB

## 普通用户权限修复候选

`3.16.0+dshanpi.2026.10.15.1` 在 16GB selector 包中内置权限配置，解决
普通用户 `axcl-smi` 无法打开 `/dev/axcl_host`、消息设备和日志文件的问题。
新版本不改变上游运行库、驱动来源或 PAC，不扩大板卡与容量适用范围。

| 包内配置 | 行为 |
| --- | --- |
| `/usr/lib/udev/rules.d/70-dshanpi-axcl-access.rules` | 仅将四个 AXCL misc 设备设为 `root:render 0660` |
| `/usr/lib/tmpfiles.d/dshanpi-axcl-access.conf` | 日志目录 `root:render 2770`、日志文件 `root:render 0660`；保留日志内容 |
| `dshanpi-axcl.service` | 初始化前恢复日志权限，使用 `UMask=0007` |
| selector `postinst` | 必要时创建 render 组，应用日志配置并刷新已存在设备；不自动启用服务或运行模型 |

默认镜像的 baiwen 已属于 render 组。安装包不猜测登录账户、不自动授予其他用户硬件
访问权。其他账户由管理员使用 `sudo usermod -aG render <用户名>` 加入后重新登录。
安装/升级成功后，确认 16GB 卡和风扇，再执行：

```sh
sudo systemctl enable --now dshanpi-axcl.service
axcl-smi
cd /usr/bin/axcl
timeout 180 ./ut/axcl_ut_npu
```

`sudo dshanpi-axcl test` 仍为管理员管理入口。上面的普通用户测试必须实际显示设备且
无权限错误，不能只检查 SMI 的退出码。新建节点在初始化脚本中等待 udev 完成配置。

从旧版升级时会刷新已经存在的设备和日志；无设备或离线镜像安装时跳过设备触发。
权限创建失败会使包配置失败，修正根因后可 `sudo dpkg --configure -a` 重试。
卸载不删除日志、render 组或管理员 `/etc` 覆盖文件，不强制卸载应用占用的驱动。
旧手工修复文件仍有 `/etc` 优先级，包不会擅自删除；验证新包时应先备份移开这些文件。

### 构建与发行

从固定上游归档完整构建：

```sh
python3 scripts/build-axcl-16g-packages.py output/axcl-access/packages \
  --package-version 3.16.0+dshanpi.2026.10.15.1 \
  --platform-version 25.11.0-trunk.20261010.1
```

也可提供 `--previous-driver`、`--previous-runtime` 和 `--previous-firmware`，
从组件锁中校验过的三个历史包提取原始输入。三者同时提供时输出四个同版本包；仅提供
driver 的旧维护路径仍复用锁定的历史 runtime/PAC 字节。不能只升级 selector 而忽略其
精确依赖。低于本次修复版本的构建请求会被拒绝，历史重建须使用对应历史源码。

本候选已在 16GB A1 上完成四包升级、普通用户 20 项 NPU 自检、重启、旧版整套回滚、
清除四包后的重新安装及最终重启。验收全程没有 /etc 手动权限补丁，旧版回滚后可复现
权限错误，新版恢复后普通用户调用正常。结果与包哈希见
[实板验证清单](../../docs/validation/2026-10-15-axcl-user-access/hardware-verification.json)。

这是候选源码与包验证，不表示已经进入公共 APT。正式发行还需新增 maintenance lock、
固定组件锁哈希和签名基础清单，生成新的 core/desktop 精确元包，走现有 testing 发布
流程并验签、核对公开下载；stable 只能晋级同一组完成实板验收的包。不要修改历史
release lock 或覆盖旧包。当前验证范围与未完成项见
[权限修复变更记录](../../docs/change-records/CR-2026-10-15-axcl-user-access.md)。


Explicit 16GB option, paired AXCL 3.16.0 runtime and PAC from the immutable
vendor input in upstream.lock.json. The generic 8GB packages remain unchanged.
All four packages conflict with the old generic cohort, so APT must remove that
optional cohort when selecting 16GB. The core system and Wi-Fi packages remain.

For a normal platform release, `release.yml` invokes
`scripts/build-release-optionals.py`. The product release lock is the only
platform version source: its `revision` becomes the exact kernel, headers and
BSP dependency, while the AXCL package revision is derived from the product
release version. The component lock retains only immutable upstream/source and
runtime/firmware inputs. `axcl-16g.yml` and its explicit component version fields
remain a legacy emergency-maintenance path and must not be used to assemble a
new platform release.

New packages enter noble-testing; publication alone does not establish hardware
acceptance. No service is automatically started by package installation. After
confirming card capacity and cooling:

```sh
sudo dspi-config source channel testing
sudo dspi-config update install <release-version>
sudo dshanpi-axcl check
sudo dshanpi-axcl test
```

The helper checks board/kernel, BTF configuration and the module structure size
against the original pwm_fan module before loading any AXCL modules. The driver
package depends exactly on the release lock's `linux-headers-vendor-rk35xx`
revision; the selector binds the matching image and BSP revision. Unchanged
runtime and firmware may be reused only at the exact version and SHA-256 pinned
in the component lock.

The original `dshanpi2` source has compiled successfully against the new headers
and produced all five expected modules with matching vermagic and module layout.
That is a build compatibility result, not a claim that module loading, PAC
initialization or NPU inference has passed on the new image.

The six-stream reference is pinned separately to demo commit
2aa772bbf16b8a904ee6ca57877c0e602208bf49. Real inference, RTSP/HTTP decoding,
recording and restart must be recorded before calling the complete path verified.
A1 CM5, R1 and Avaota A1 are excluded from this optional package set.
