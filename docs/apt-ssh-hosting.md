# apt.100ask.net 服务器托管与 CI 上传

GitHub Actions 继续构建、审计和签名；签名后的完整仓库通过 SSH/rsync 发布到
`/www/wwwroot/apt.100ask.net/`。服务器只运行 CI 传来的命令，不需要安装自定义导入程序。
所有板型、AXCL、AXCL 16GB、AIC 维护发行共用 `release.yml`，默认 `backend=ssh`。

## 服务器与 Secrets

服务器需要 Linux、Python 3.9 或更新版本（包括 lzma）、rsync、gpg 和 gpgv。
Ubuntu/Debian 可执行 `sudo apt-get install python3 rsync gnupg`。
SSH 登录账户需要创建、读写站点目录的权限；CI 不调用 sudo。
Web 服务账户需要读取目录及文件的权限，站点目录及其父目录应允许目录遍历。

在 `dshanpi-build` 的 Actions Secrets 配置：

| Secret | 内容 |
| --- | --- |
| `HOST` | 服务器公网 IPv4 或主机名，不带协议或端口 |
| `USERNAME` | SSH 登录账户 |
| `PASSWORD` | SSH 密码 |
| `PORT` | SSH 端口 |

连接使用 `HOST`，不依赖 `apt.100ask.net` 已经完成 DNS 切换。
这些是四个新增的部署凭据；构建发布仍沿用 `APT_GPG_PRIVATE_KEY`、
`APT_GPG_KEY_FINGERPRINT` 等已有 Secrets。APT 私钥留在 GitHub，服务器只有验签公钥。
SSH 首次连接接受并记录主机公钥，同一 checkout 后续连接拒绝公钥变化。
可将经独立核对的主机公钥作为非敏感配置放入 `keys/apt-server-known-hosts`，
让不同 runner 也固定使用该公钥，不需要第五个 Secret。

## 目录和网站配置

CI 自动维护以下子目录：

```text
/www/wwwroot/apt.100ask.net/
├── incoming/<job>/repository/    # 上传中的候选
├── incoming/<job>/control/       # 本次任务的校验代码与公钥
├── releases/<job>/              # 发布后保留的完整快照
├── .publication.lock            # 服务端发布锁
└── current -> releases/<job>    # 当前已验证版本
```

**网站根目录必须设置为 `/www/wwwroot/apt.100ask.net/current`**，并允许读取该符号链接。
不能将上一级作为网站根目录，否则会暴露暂存文件，而且 APT 根路径不正确。
配置域名 `apt.100ask.net` 和有效的 HTTPS 证书；不要将不存在的文件重写成首页。
包索引和清单不应长期缓存，示例 Nginx location：

```nginx
root /www/wwwroot/apt.100ask.net/current;

location / {
    try_files $uri $uri/ =404;
    add_header Cache-Control "no-cache";
}

location /pool/ {
    try_files $uri =404;
    add_header Cache-Control "public, max-age=31536000, immutable";
}
```

保留站点现有的 TLS 等配置，只调整根目录和对应 location。
上传目录、快照目录和 current 必须处于同一文件系统，不得使用符号链接重定向存储目录。

## 首次迁移

1. 创建站点目录、安装基础工具、设置账户权限和上面的四个 Secrets。
2. 在包含这些脚本的分支运行 Actions **Migrate APT repository to SSH server**。
3. 工作流取得 `feature/apt-pages-state` 中完整的历史仓库，核对已有签名和所有包哈希，
   生成首页/公钥下载文件，再上传；不重建、不重签、不删除任何历史 DEB。
4. 工作流在服务器验签并切换 current，然后通过 SSH 下载已发布快照，核对签名及原始校验清单。
5. 核对站点根目录与 HTTPS。可在域名切换前使用
   `curl --resolve apt.100ask.net:443:服务器IPv4 https://apt.100ask.net/archive-key.asc`
   检查新服务器站点路由；这只是连接检查，不代替包集验证。
6. 将 `apt.100ask.net` 的 DNS 指向新服务器，确认公网可获取 InRelease、清单及 DEB。
   后续发布使用 `backend=ssh`，公开验证仍访问原域名。

迁移不会自动修改 DNS 或 Web 配置。首次切换期间暂停其他旧分支的发布操作，避免迁移后
Pages 又产生新的仓库状态；DNS 传播期间也不要立即下线旧站。
迁移入口拒绝覆盖已有的不同仓库状态；相同签名清单的迁移重试仅核对，不重新切换。
普通发行发现服务器为空时停止，必须先迁移，不会以空仓库覆盖已有多板历史。

## 后续自动发布及传输优化

主工作流选择 `product`、`version`、`channel`，`backend` 默认 `ssh`。
三个可选驱动工作流也调用主工作流，不再单独发布 Pages。

1. `fetch-apt.sh` 将 current 解析为一个固定快照路径，再下载并验签，避免下载中混入两次发行。
2. 原有构建器在完整旧状态上加入候选，生成索引和签名；stable 仍只晋级同一组包。
3. `prepare-apt-site.sh` 验证仓库并生成首页、浏览目录、公钥及 keyring。
4. `publish-apt.sh` 创建独立暂存目录，通过 rsync 校验内容，利用 `--link-dest` 复用旧快照文件。
   对相同内容不重复传输，也不重复占用 DEB 磁盘空间；不额外压缩已压缩的 DEB。
   SSH 路径只保留签名清单等小型 CI 证据，不再每次打包、上传整个历史仓库为 Actions artifact。
5. CI 通过 SSH 运行本仓库的 `ssh-repository.py`：取得服务端锁，检查签名、索引、包哈希、
   构建时的前置状态和历史 pool 不变性，再使用同一文件系统上的 rename 原子切换 current。
6. 正式 testing/stable 发布继续执行 `verify-product-public.py`，验证域名下的目标完整包集。

线上快照和保留快照不使用 `rsync --inplace` 或对在线目录的 `--delete`。
普通发布保留全部历史 pool；仅已评审、签名清单明确列出的 purge 可以从新快照移除包。
所有旧快照仍保留，磁盘空间主要随新增包增长，也会保留被 purge 包的旧快照占用。
CI 不自动清理历史快照；磁盘不足时发布失败，不以删除旧包来继续发布。

## 失败与恢复

上传中断、错误签名、损坏文件、历史包被替换、未授权删除或前置状态已变，均停止并保留原 current。
CI 和服务器两层锁保护发布；前置状态不匹配时，重新拉取最新状态后构建候选。
完全相同的已签名仓库再次上传会验签后结束，不重复切换。
失败的 incoming 和切换前未启用的快照保留供排查，可在确认无任务使用时人工移除。

公网验证失败时，任务标为失败，服务器可能已经完成切换；应先检查 DNS、证书、缓存和
下载链路，不自动回滚或覆盖。旧快照可用于恢复，但恢复前需要明确目标，确认没有后续成功发布。

本次迁移不修改客户端软件源地址、签名信任、板型隔离、包版本或实板验收要求。
GitHub Pages 后端暂留作兼容入口，不在 SSH 日常发布时更新其 950 MB 快照。
