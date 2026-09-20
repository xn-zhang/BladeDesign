# 登录、持久化与部署

平台现在使用管理员账号与浏览器会话。模型配置页面不再要求平台令牌，也不需要填写平台地址；所有模型请求使用当前网站的 `/api` 路径。模型服务仍由后端转发，供应商 API Key 不进入前端代码或浏览器存储。

## 本地或另一台电脑独立运行

Python 3.10+，在仓库根目录运行（模型服务不需要 OpenFOAM）：

```powershell
python -X utf8 aeroblade/bridge/server.py --model-only --host 127.0.0.1 --port 8791
```

打开 `http://127.0.0.1:8791/`，点击“登录”或“模型配置”。首次创建管理员用户名和密码，以后使用该账号登录。首次创建只允许本地入口；用户名为3–64位字母、数字、点、下划线或短横线，密码至少12个字符。

另一台电脑独立部署时会有自己的数据库和账号；多台电脑访问同一个部署时使用该部署的账号。浏览器不再需要寻找 `api-token` 文件。当前是**单管理员工作台**，不是多租户账号系统。

默认数据保存到 `aeroblade/private/state.sqlite3`，也可通过 `--data-dir` 或 `AEROBLADE_DATA_DIR` 指向指定的持久目录。数据库包含口令哈希、有效会话和模型配置；服务重启后恢复。登录会话有效期12小时，退出即撤销。

模型地址、模型名和供应商 API Key 保存在数据库中；API Key 不加密存储，因此应限制私有目录的操作系统访问权限，并将备份作为敏感文件保护。程序设置数据库文件的POSIX权限为0600，首次创建私有目录为0700；Windows还应使用所在账号的目录ACL。静态服务和发布包不会公开此目录。

## 独立模型后端 / 远程网站

后端部署到有持久磁盘的主机或容器，HTTPS由可信反向代理终止。启动环境示例（值由部署者设置，不提交真实密码）：

```bash
export AEROBLADE_PUBLIC_ORIGIN='https://design.example.com'
export AEROBLADE_DATA_DIR='/var/lib/aeroblade'
export AEROBLADE_ADMIN_USERNAME='admin'
export AEROBLADE_ADMIN_PASSWORD='替换为你的强密码，至少12个字符'
python3 aeroblade/bridge/server.py --model-only --host 0.0.0.0 --port 8787
```

- `AEROBLADE_PUBLIC_ORIGIN` 是**浏览器访问的前端网站来源**，只含协议、域名和可选端口，不含路径。远程部署要求HTTPS来源；在HTTPS网站上Cookie带Secure属性。
- 管理员环境变量只在数据库尚无管理员时初始化账号，不会在每次重启时覆盖已创建的账号。账号初始化后可以从部署环境移除密码变量。
- `AEROBLADE_DATA_DIR` 必须挂载持久卷。不要放在容器临时目录或serverless临时文件系统；容器更新时保留此目录。
- 模型初始化环境变量沿用 `AEROBLADE_LLM_GENERAL_*` / `AEROBLADE_LLM_DOMAIN_*`。数据库已有保存记录时优先使用数据库；清除模型配置也持久生效，不会在下一次启动时被环境默认值覆盖。
- 本实现为单实例SQLite后端。多实例部署前需要共享数据库与相应会话/配置适配，不能让多个实例各自写临时数据库。

会话Cookie采用HttpOnly与SameSite=Lax，写操作还检查CSRF令牌。前端与后端通过同源反向代理连接，用户无需配置跨域认证。供应商Key仅在保存配置时发给自己的后端，由后端发送给模型提供商。

## Vercel 部署前端

仓库已包含 `vercel.json` 与 `scripts/build_vercel.py`。脚本使用 [Vercel Build Output API](https://vercel.com/docs/build-output-api/configuration) 生成公开静态页面，并通过 [外部重写](https://vercel.com/docs/routing/rewrites) 将 `/api/*` 转发给独立后端。

1. 先部署上述有持久磁盘的模型后端，并为它配置HTTPS，例如 `https://backend.example.com`。
2. 在Vercel导入本仓库，Root Directory使用仓库根目录，Framework选择Other，采用仓库中的Build Command。不要把输出目录改成整个仓库。
3. 在Vercel构建环境设置 `AEROBLADE_BACKEND_URL=https://backend.example.com`。这是后端基础地址，不带 `/api`；它不是密钥。未设置或不是HTTPS时构建会明确失败。
4. 后端设置 `AEROBLADE_PUBLIC_ORIGIN=https://你的前端域名`，该来源须与实际访问网站一致。然后启动后端。
5. 部署后访问前端网站，使用后端初始化的管理员账号登录，再配置DeepSeek等模型。不要把管理员密码或供应商Key放到Vercel前端构建环境中。

本方案部署到Vercel的是前端和同源API代理，**不把Python常驻服务或SQLite放进Vercel临时函数实例**。构建输出只复制HTML、JS、CSS，不复制数据库、CFD任务、运行记录、环境文件或令牌。请求耗时仍需满足所用反向代理和部署平台的限制。

本地检查构建：

```powershell
$env:AEROBLADE_BACKEND_URL='https://backend.example.com'
python scripts/build_vercel.py
```

此命令只构建 `.vercel/output`，不会发布到云端。真实云部署需提供实际后端域名与平台项目。

## CFD独立部署与兼容

- `--model-only` 后端只提供登录和模型接口；CFD工作区会明确提示连接独立计算服务。
- 完整Linux/WSL工作台继续使用 `bash scripts/start.sh`；同源CFD连接可以留空服务令牌，自动使用已登录会话。
- 独立CFD服务器继续配置 `AEROBLADE_API_TOKEN`，网页连接它时使用该服务器的服务令牌。该凭据只属于计算服务集成，已从模型配置流程移除。
- 通过同源代理访问独立CFD并隐藏计算令牌可作为下一阶段的后端调度集成；本次保留既有直连模式，不自动改变计算任务或服务器。

## 旧版本迁移

旧版模型配置仅存在进程内存，服务停止后本来就不会保存。升级后首次在登录页面保存一次配置，之后才有数据库持久记录。旧 `runtime/api-token` 文件不会作为账号密码，也不会被自动删除；仍可用于兼容旧的机器接口。

备份时停止平台服务后复制整个私有数据目录；服务停止会按原流程取消它管理的未完成CFD任务，安排升级时应避开运行中的任务。不要删除数据库来“退出登录”：退出操作只撤销会话，不删除账号和模型配置。
