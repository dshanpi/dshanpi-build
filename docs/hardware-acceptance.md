# 真机发行验收

完整发行只有一个版本计划：
`products/<product>/releases/<version>.lock.json`。testing 构建从该文件取得产品版本、
ArmBianOS revision 以及 ArmBianOS/dspi-config commit；A1 的 AXCL 包版本自动由产品版本
派生，内核、头文件和 BSP 依赖自动绑定同一 revision，不再单独手改 AXCL 平台版本。

## 固定流程

1. 在 Actions 运行 `Build and publish DShanPI product`，选择 lock 中的 product/version、
   `channel=testing`。工作流构建并发布签名 APT 候选及同版本 CLI/Desktop 镜像。
2. 实板切换到 testing，执行 `dspi-config update install <version>`。未安装 AXCL selector
   的设备只更新系统；已安装 selector 的设备会同步本发行的精确 AXCL 依赖。
3. 验证启动、重启和回滚。A1 AXCL 设备还必须验证 DKMS、五个模块加载、`axcl-smi`、
   `dshanpi-axcl test` 和重启后恢复。所有命令输出保存到版本证据目录。
4. 提交 `<version>.hardware-acceptance.json` 及它引用的证据文件，再运行同一工作流并选择
   `channel=stable`。工作流校验候选软件包清单和每份证据的 SHA-256 后，原样晋级；
   不重新编译包或镜像。

推荐的板端命令骨架如下；具体外设测试仍按产品验收矩阵执行：

```sh
sudo dspi-config source channel testing
sudo dspi-config update install 2026.10.10-1
dpkg-query -W dshanpi-a1-release-core linux-image-vendor-rk35xx \
  linux-headers-vendor-rk35xx armbian-bsp-cli-dshanpi-a1-vendor \
  dshanpi-a1-axcl-16g dshanpi-axcl-dkms-16g
dkms status
sudo dshanpi-axcl check
sudo dshanpi-axcl test
sudo reboot
# 重连后再次执行 check/test，并确认 axcl-smi 和五个模块。
sudo dspi-config update rollback
sudo reboot
# 验证旧版本恢复后，再安装候选版本并完成最后一次重启恢复检查。
```

## 验收记录

文件名必须是
`products/<product>/releases/<version>.hardware-acceptance.json`。`package_manifest_sha256`
取 testing 仓库中 `catalog/releases/<product>/<version>.json` 的 SHA-256。证据路径相对于
该 JSON 所在目录，不能越出该目录；stable 门禁会读取文件并复算哈希。

```json
{
  "schema_version": 1,
  "product": "dshanpi-a1",
  "release": "2026.10.10-1",
  "verdict": "passed",
  "package_manifest_sha256": "64位小写SHA-256",
  "checks": {
    "apt_install": "passed",
    "release_meta": "passed",
    "boot": "passed",
    "reboot": "passed",
    "rollback": "passed",
    "axcl-16g": {
      "dkms": "passed",
      "module_load": "passed",
      "axcl_smi": "passed",
      "npu": "passed",
      "reboot_recovery": "passed"
    }
  },
  "evidence": [
    {
      "path": "2026.10.10-1.hardware-acceptance/board.log",
      "sha256": "64位小写SHA-256"
    }
  ]
}
```

本地可在已验签的仓库副本上预检：

```sh
python3 scripts/validate-hardware-evidence.py dshanpi-a1 2026.10.10-1 \
  products/dshanpi-a1/releases/2026.10.10-1.hardware-acceptance.json \
  output/repository
```

编译成功、vermagic 一致或 APT 模拟安装成功都只能作为前置证据，不能把上述运行项标成
`passed`。没有真实板卡结果时，候选保留在 testing，不得创建虚假验收文件。
