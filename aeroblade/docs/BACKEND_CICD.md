# 腾讯云后端自动部署

## 触发与验证

推送到 `main` 后，`Check source and portable package` 工作流在 Python 3.10 / 3.12 上运行检查。全部成功后，`Deploy Tencent backend` 发布该次通过测试的提交。PR 不触发生产发布。也可在 Actions 手动运行部署工作流（仅 main，重新运行检查）。落后于当前 main 的提交跳过部署，同一时间只进行一次发布。

部署目标：`aeroblade-deploy@43.128.67.249`；服务：`aeroblade.service`；监听：`127.0.0.1:8787`。发布程序将归档解压到 `/opt/aeroblade-releases/<完整提交号>`，通过 `90-ci-release.conf` systemd override 切换版本，保留原服务的环境配置与安全限制。

## 一次性 GitHub 配置

在仓库 Settings → Secrets and variables → Actions 添加 Repository secret：

- 名称：`AEROBLADE_DEPLOY_KEY`
- 值：部署专用 Ed25519 **私钥完整内容**，包括 BEGIN / END 行，不是 `.pub` 公钥。

私钥不进入仓库或日志。初次配置的本机路径为 `%USERPROFILE%\.ssh\aeroblade_ci_deploy`。公钥已安装到服务器专用账号，允许的操作只有固定发布程序；禁止交互 shell、SFTP 和端口转发。服务器主机公钥在工作流中固定，换机时须通过可信 SSH 通道核验后更新。

服务器安装文件：

- `/usr/local/sbin/aeroblade-deploy` ← `scripts/deploy_backend.py`，root 所有，755。
- `/usr/local/bin/aeroblade-ci-ssh` ← `scripts/deploy_backend_ssh.sh`，root 所有，755。
- `/etc/sudoers.d/aeroblade-deploy` 仅允许上述固定部署程序。
- `/home/aeroblade-deploy/.ssh/authorized_keys` 使用 `restrict,command="/usr/local/bin/aeroblade-ci-ssh"`。

工作流提交 tar 归档、完整提交号及 SHA256；服务器检查大小、路径、重复条目和文件类型，拒绝链接及路径穿越。发布程序不会自动替换自身；修改部署基础设施时需管理员审核并安装服务器副本。

## 数据、回退与限制

发布前以应用账号预生成 `aeroblade/dist/aeroblade.zip`，然后停止服务，备份 `/var/lib/aeroblade` 到仅 root 可访问的 `/var/backups/aeroblade-ci/<时间及随机后缀>/data`。备份服务配置及前一版 override 后，启动新版本并检查 `/api/session`；验证已有管理员初始化状态，防止误用空数据库。Actions 再检查 Vercel `/api/session` 代理链路。

本机启动或健康检查失败时自动恢复上一版服务配置并重启，**不自动恢复数据库**。数据库迁移须兼容上一版本；若不兼容，应在维护窗口内人工恢复受保护备份，避免覆盖已产生的新数据。Vercel 外部链路失败会标记工作流失败，但不会自动回退已通过本机健康检查的后端。

当前 systemd 单进程部署在备份和重启期间会短暂不可用，不是零停机发布。旧发布目录和备份保留供恢复，目前不自动清理，应定期检查磁盘空间。

Vercel 仍由原 Git 集成独立发布。此工作流不延迟 Vercel 发布，不保证前后端同时切换；接口变更须兼容滚动发布期间的旧前端。以后如要求后端先成功再发布前端，需另外配置 Vercel 发布权限及统一编排。

## 排错

- Actions 提示缺少 Secret：添加 `AEROBLADE_DEPLOY_KEY` 后，在 main 手动运行部署工作流。
- 测试失败：后端不会发布，先修复 `Check source and portable package` 中的失败。
- SSH 拒绝：检查 Secret 是否完整、服务器公钥是否更换、GitHub runner 是否可访问 TCP 22。
- 启动失败：在腾讯云执行 `sudo journalctl -u aeroblade.service -n 80 --no-pager`；查看工作流记录的备份路径。
- 查看当前发布：`systemctl show aeroblade.service -p WorkingDirectory -p ExecStart`。

部署 safeguards 测试：Linux 下运行 `python3 -m unittest discover -s tests -p test_deploy_backend.py -v`，使用临时夹具，不操作生产服务。
