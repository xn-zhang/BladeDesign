# AeroBlade Multi-user Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 测试者凭邀请码注册，独立配置模型，保存和恢复个人设计、工况与对话，且不能访问其他用户的数据。

**Architecture:** 将单管理员 SQLite 迁移为带稳定 user_id 的用户、邀请、会话及个人资源表。每个已认证请求先解析身份，再获得该用户的模型服务和评估目录；不复用全局“当前用户”。保留现有管理员的配置与任务，前端登录、个人数据和管理员界面复用原生模块。

**Tech Stack:** Python 3.10+ 标准库、SQLite、原生 JavaScript ES modules、Node.js 20+、unittest 与 node:test；Vercel 前端、Ubuntu/systemd/Caddy 后端。

**Spec:** `docs/superpowers/specs/2026-09-22-multi-user-design.md`（2026-09-22 用户已确认首版范围）

## Global Constraints

- 邀请码由管理员生成，一码一人，默认 7 天有效，可撤销；数据库仅保存摘要。
- 密码至少 12 字符；保留加盐 PBKDF2，不降低现有哈希强度。
- 初始默认配额：每用户 100 份设计、50 份对话；每份对话不超过 1 MiB。
- 普通用户不继承服务器环境或管理员的模型密钥；资源所有权来自会话。
- 普通用户模型地址仅允许公网 HTTPS，禁用重定向并防范 DNS 重绑定。
- 保留现有管理员账号及旧数据，撤销迁移前会话；部署前备份匹配版本的数据。
- 全局 CFD、计算令牌、队列管理仅管理员可用；腾讯云保留 model-only 模式。
- 不引入邮箱验证、邮件找回、付费系统或第三方登录。
- 业务代码与测试不得输出实际密码、邀请明文、供应商密钥。

## Review Focus

1. 两个数据库连接同时消费同一码：只能成功一次；任务 2 并发测试覆盖。
2. DNS 首次公网而后变为内网、HTTPS 代理环境干扰：实际 socket 必须仍连接已校验公网 IP；任务 4 覆盖。
3. A 退出、B 登录时 A 的响应才返回：不得修改 B 界面或数据；任务 6/7 覆盖。
4. 已用邀请码遇到用户名冲突或数据库异常：事务回滚，不错误消耗有效邀请；任务 2 覆盖。
5. 迁移中断、重复启动及已禁用用户仍有运行任务：迁移可重复、禁用撤销会话并阻止新请求，旧任务保留原所属；任务 1/5 覆盖。

## 文件边界

| 文件 | 责任 |
|---|---|
| `aeroblade/bridge/session_store.py` | 用户、会话、角色、邀请码、模型设置及事务迁移 |
| `aeroblade/bridge/personal_store.py`（新） | 个人设计/对话结构校验、配额和所有权 CRUD |
| `aeroblade/bridge/model_transport.py`（新） | 普通用户模型公网地址解析、固定 IP TLS 连接、限流 |
| `aeroblade/bridge/user_services.py`（新） | 按用户实例化服务、私有目录、总量限制与关闭 |
| `aeroblade/bridge/account_routes.py`（新） | 注册、账号管理与个人资源路由，保持 server 分发简洁 |
| `aeroblade/bridge/server.py` | 请求身份解析、路由集成、CFD 管理员权限 |
| `aeroblade/bridge/design_assistant.py` | 注入用户存储和受限传输；保留回复校验 |
| `aeroblade/web/session.js`、`session.css` | 注册登录、密码修改、按身份更新与请求失效 |
| `aeroblade/web/account-admin.js`（新） | 邀请生成/撤销与普通账号禁用/恢复 |
| `aeroblade/web/personal-workspace.js`、`personal-workspace.css`（新） | 个人设计/对话列表及保存/恢复交互 |
| `aeroblade/web/app.js`、`cfd.js`、`design-assistant.js`、`model-settings.js`、`evaluation.js`、`batch.js` | 个人工作区接入与账号切换清理 |

## Task 1: 用户表与旧数据事务迁移

**Files:** 修改 `session_store.py`、`tests/test_sessions.py`；新增 `aeroblade/bridge/tests/test_user_migration.py`。

**Interfaces:**
- `StateStore.user(user_id: str) -> dict` 返回 id、username、role、disabled；不返回哈希、salt。
- `StateStore.admin_id() -> str | None`；`create_admin(username, password)` 保留本机初始化入口。
- `login(username,password,address) -> (token,session)` 和 `session(token)` 返回增加 user_id、role，禁用用户返回无会话。
- `StateStore.model_store(user_id) -> UserModelStore`；适配器提供现有 `load_models()`、`save_models(configs)` 接口。

- [ ] 新建真实旧表 SQLite 夹具，保存旧 admin 的 salt/digest、全局模型设置和会话；测试迁移后密码仍有效、旧会话失效、模型设置只属于 admin。
- [ ] 添加二次打开数据库及迁移异常回滚测试。先运行 `python -m unittest discover -s aeroblade/bridge/tests -p test_user_migration.py -v`，确认失败来自缺失迁移。
- [ ] 实现以 `PRAGMA user_version` 管理的事务迁移；新 users 使用随机不可变 ID，用户名保存规范化唯一索引。保留旧显示用户名，对登录输入统一 strip/casefold。

```python
self.db.execute('BEGIN IMMEDIATE')
try:
    # users.id 是不可变的 secrets.token_hex(16)；旧密码哈希逐字节复制。
    # 将旧 settings['models'] 复制到 user_settings(admin_id, 'models')。
    # 重建 sessions 关联 user_id；本次迁移撤销旧 sessions。
    self.db.execute('PRAGMA user_version = 1')
    self.db.commit()
except Exception:
    self.db.rollback()
    raise
```

- [ ] 将完整 DDL 与迁移实现放进存储模块；禁止 `executescript` 在已有迁移事务中造成隐式提交。模型设置按 `(user_id,name)` 主键保存，不能使用全局 name 查询。
- [ ] 扩展测试：迁移失败不改变版本、反复启动不新增管理员、普通用户不能命中 admin 的设置；修正现有 session 测试以显式指定 owner。
- [ ] 通过相关 unittest 后提交 `feat: migrate account storage to isolated users`。

## Task 2: 邀请注册与账号管理 API

**Files:** 修改 `session_store.py`、`server.py`；新增 `account_routes.py`、`tests/test_invites.py`、`tests/test_user_api.py`。

**Interfaces:**
- `create_invite(admin_id, expires_in=604800) -> {id,code,expires_at}`，仅创建时返回 code。
- `list_invites(admin_id) -> list`、`revoke_invite(admin_id,invite_id)`。
- `register(username,password,invite,address) -> user`，不接收 role。
- `list_users(admin_id)`、`set_disabled(admin_id,user_id,disabled)`、`change_password(user_id,current_password,new_password)`。
- `account_routes.dispatch(handler,path,principal) -> bool`；返回是否已处理，全部响应经现有 JSON/Cookie helpers。

API：`POST /api/session/register`、`POST /api/session/password`；`GET/POST /api/admin/invites`；`POST /api/admin/invites/{id}/revoke`；`GET /api/admin/users`；`POST /api/admin/users/{id}/status`。

- [ ] 先写过期、撤销、重用、大小写用户名冲突、额外 role 字段、伪造 Origin、缺失 CSRF 测试；注册成功创建普通用户并直接登录。
- [ ] 用两个 StateStore 连接同一临时数据库并发注册，断言一个成功、一个冲突。注册码事务的核心约束为：

```sql
UPDATE invites SET used_by = ?, used_at = ?
WHERE digest = ? AND used_by IS NULL AND revoked = 0 AND expires_at > ?;
```

- [ ] 在 `BEGIN IMMEDIATE` 内执行邀请条件消费与用户插入；影响行数不是 1 就回滚；用户名冲突也整体回滚。邀请通过 `secrets.token_urlsafe(32)` 生成，存 SHA-256 摘要。
- [ ] 对预认证操作分别设置端点/用户名限流和总量限制；不使用未经验证的 X-Forwarded-For，不让某普通账号的失败计数轻易锁住所有用户。
- [ ] 禁用不允许作用于 admin 或自己；会话查询每次联查 users.disabled。密码修改验证当前密码，撤销本人所有会话并要求重新登录。
- [ ] 运行 `python -m unittest discover -s aeroblade/bridge/tests -p 'test_*api.py' -v` 及 test_invites.py；全部通过后提交。

## Task 3: 个人设计与对话持久化

**Files:** 新增 `personal_store.py`、`tests/test_personal_store.py`；修改 `account_routes.py`、`test_user_api.py`。

**Interfaces:** `PersonalStore(state)` 提供 `list(user_id,kind)`、`get(user_id,kind,item_id)`、`save(user_id,kind,name,payload,item_id=None)`、`rename(user_id,kind,item_id,name)`、`delete(user_id,kind,item_id)`；kind 仅 designs/conversations。

API：`GET/POST /api/personal/{kind}`、`GET /api/personal/{kind}/{id}`、`POST .../{id}/rename`、`POST .../{id}/delete`。响应不泄漏他人资源是否存在，跨用户 ID 一律 404。

- [ ] 先写 A/B 用户隔离测试，覆盖列表、读取、保存覆盖、重命名、删除、配额竞争、服务重启恢复。
- [ ] 定义白名单 JSON：设计 `{schema:'aeroblade-saved-design-v1',parameters,conditions,notes}`；对话 `{schema:'aeroblade-saved-conversation-v1',messages,provider,candidate,draft}`。名称 1–120 字符，备注最多 4000 字符；禁止供应商密钥、HTML 和任意文件路径字段。对话正文作为文本渲染，不声称能自动识别人为粘贴的所有秘密。
- [ ] 设计调用现有 Pritchard/legacy 校验路径，工况沿用当前工况协议；对话校验角色、消息数量、单条长度和方案结构，拒绝 NaN/Infinity。限制 UTF-8 JSON 编码字节数，不能只数 Python 字符。
- [ ] 所有数据库操作均带所有者条件，例如：

```sql
SELECT payload FROM personal_items WHERE user_id = ? AND kind = ? AND id = ?;
DELETE FROM personal_items WHERE user_id = ? AND kind = ? AND id = ?;
```

- [ ] 配额检查和创建放入同一事务，更新不占新增配额。测试第 101 份设计和第 51 份对话失败，重命名不改变内容。
- [ ] 运行 test_personal_store.py 与 test_user_api.py，提交个人数据后端。

## Task 4: 按用户模型配置与公网请求边界

**Files:** 新增 `model_transport.py`、`tests/test_model_transport.py`；修改 `design_assistant.py`、`test_design_assistant.py`。

**Interfaces:** `PublicModelTransport.open(request,timeout)` 与现有 opener 返回值兼容；`resolve_public(host,port) -> list[tuple]` 提供已验证地址；`ModelService(environ=None,store=None,transport=None,slots=None)` 支持显式传输和全局并发 semaphore。

- [ ] 写测试：两个用户不同 key，通过受控 HTTPS transport fixture 验证 Authorization 隔离；空用户不能回退管理员环境 key；describe、错误响应均不含 key。
- [ ] 写 SSRF 测试覆盖 127.0.0.1、IPv6 ::1、IPv4-mapped IPv6、私网 DNS、链路本地、重定向与 DNS 重绑定。
- [ ] URL 先要求 HTTPS、无 userinfo/query/fragment，解析所有地址且全部必须 `ipaddress.ip_address(ip).is_global`。实际 socket 连接固定已验证 IP，TLS `server_hostname` 使用原始域名、默认 CA 验证，HTTP Host 保留原域名；不在 urllib 中二次解析域名，不读取系统 HTTPS_PROXY。
- [ ] 每请求重新检查配置目标，严格拒绝 3xx，限制响应体大小及连接/读取超时。管理员沿用现有受控私有模型连接能力，不能由普通请求选择该模式。
- [ ] 普通 ModelService 传 `environ={}`，管理员可读取服务器配置；原环境配置只迁移给管理员一次。设置每用户最多 2 个模型请求、全局最多 8 个，满额返回 429。
- [ ] 使用模拟 DNS/socket/本地测试证书固定断言实际目标与 TLS 主机，不向真实内网或付费模型发测试请求。运行 test_model_transport.py 与 test_design_assistant.py，通过后提交。

## Task 5: 用户服务实例、任务目录与管理员 CFD 边界

**Files:** 新增 `user_services.py`、`tests/test_user_services.py`；修改 `server.py`、`account_routes.py`、原 session/server/batch/evaluation API 测试。

**Interfaces:** `UserServices(state,root,manager,admin_evaluation,admin_batches)`；`for_user(principal) -> {models,evaluation,batches}`；`close()` 关闭所有创建的服务。principal 至少含 user_id、role。

- [ ] 先写 A/B 创建同名资源、相同参数包摘要以及互猜任务 ID 的 API 测试；所有列表/详情/下载/控制必须不串数据。
- [ ] 认证后设置 handler.principal，禁止通过 URL/body 覆写。机器 Bearer 兼容仅用于既有 CFD 接口，不可调用用户注册、个人数据、管理员账号或模型配置接口。
- [ ] 管理员使用原目录，普通用户目录为 `/var/lib/aeroblade/users/<immutable_id>/`；子服务独立 evaluation/jobs，普通 BatchService 的 manager 为 None。普通用户的 /api/jobs、/api/scheduler 返回 403。
- [ ] 服务实例懒创建但加锁，不能每请求重复启动后台线程；关闭服务器时关闭全部实例。拒绝符号链接逃逸；按用户和总量限制活动任务（每用户 2、全局 4），按确定次序获取限额并在取消/异常时释放。
- [ ] 禁用用户后禁止新请求和排队启动，通知已有服务取消用户任务，保留任务记录所属；不将旧任务结果转给新登录用户。
- [ ] 运行多用户隔离测试及原 batch/evaluation/session 回归；通过后提交。

## Task 6: 注册、账号管理及会话切换

**Files:** 修改 `session.js`、`session.css`、`model-settings.js`；新增 `account-admin.js`、`tests/session-state.test.mjs`，必要时新增 `web/session-state.js` 保存纯状态逻辑；修改 server 静态文件 allowlist。

**Interfaces:** 会话数据含 user_id、role、username、csrf。`aeroblade:sessionchange` 事件提供 authenticated、userId、generation；`sessionFetch()` 在发出请求和返回响应时核对同一身份 generation。

- [ ] 写 node:test：同为 authenticated 的 A→B 也触发变化；A 请求在 logout/B login 后完成应抛 AbortError；未登录请求不携带旧 csrf。
- [ ] 登录窗口移除默认 admin 用户名；增加邀请码注册切换、确认密码、个人修改密码入口。管理员视图增加创建/复制/撤销邀请码、用户禁用恢复，邀请码成功创建后只显示一次。
- [ ] 所有提交按钮处理重复点击；账号密码错误保留可重试提示，不清空用户设计。服务器端 role 校验不可用“隐藏按钮”替代。
- [ ] 用户名和邀请码状态使用 textContent；注销关闭个人和模型弹窗，清空密码/密钥表单。管理员禁用用户操作失败时不提前修改列表状态。
- [ ] 浏览器本地联调注册、密码修改、禁止普通账号打开 admin API、失效邀请错误提示；运行 node tests 和 JS 语法检查后提交。

## Task 7: 我的设计、保存对话与跨账号缓存清理

**Files:** 新增 `personal-workspace.js`、`personal-workspace.css`、`tests/personal-workspace-state.test.mjs`；修改 app.js、cfd.js、design-assistant.js、evaluation.js、batch.js、index.html 及 server 静态 allowlist。

**Interfaces:** `initPersonalWorkspace({getDesign,applyDesign,getConditions,applyConditions})` 接入真实工况与几何；对话模块提供 `getConversationSnapshot()`、`restoreConversationSnapshot(snapshot)`，恢复前调用既有方案校验。

- [ ] 先测试保存使用当前身份、载入保存的工况与设计、过期响应丢弃、跨用户 sessionStorage 不复用、配额错误不覆盖编辑草稿。
- [ ] 新增我的设计列表与保存命名窗口，支持载入、重命名、删除；删除前显示明确项目名称确认。保存快照后继续编辑不会修改已存副本，载入前提示替换未保存编辑。
- [ ] 初始设计添加保存/打开对话，保存时冻结 snapshot；含方案的恢复沿用前端 validateProposal，不直接执行存储内容。
- [ ] storage key 包含 user_id；匿名演示草稿只属于 anonymous，不自动复制给下一位登录用户。账户切换清除全局设计、候选、任务详情、数据列表、模型表单，重新加载该账户状态。
- [ ] 列表和恢复请求使用 Task 6 的 generation 检查；测试 A 晚到响应不能覆盖 B，并且退出后不自动重新保存 A 草稿。
- [ ] 用两个浏览器上下文端到端：A/B 注册、不同模型配置、分别保存/打开设计与对话、重启后恢复，禁止互猜资源 ID。通过后提交。

## Task 8: 全量验证、迁移演练与生产上线

**Files:** 更新 README.md、aeroblade/docs/DEPLOYMENT.md、MODEL_CONFIGURATION.md；新增 `aeroblade/docs/MULTI_USER.md` 与 `scripts/verify_multi_user.py`，测试凭据临时生成且不打印。

- [ ] 先在隔离执行环境运行 `bash scripts/check.sh`（Linux，涵盖 Python 全量、JavaScript、Node tests、ZIP 检查），不得把历史 Windows subprocess 失败当成此次通过证据。
- [ ] 验证两个 Vercel 构建入口，并设置 `AEROBLADE_BACKEND_URL=https://zhangxn.cloud`；检查输出仅公开前端资源、不含数据库/私有目录/密钥。
- [ ] 用旧数据库夹具进行完整迁移、登录、保存、重启和恢复演练，提交身份/任务/模型权限测试证据。部署到服务器前读取最新生产版本和任务状态。
- [ ] 停止 AeroBlade 服务，创建带时间戳且权限为 0700 的备份目录，完整备份 `/var/lib/aeroblade` 和现有源码版本；不复制明文秘密到本地或 Git。
- [ ] 上传经过检查的 Git 提交到独立 release 目录，在服务器离线运行迁移/会话/模型隔离测试，再切换 systemd 工作目录。保存旧服务配置以便回退。
- [ ] 升级数据库并启动后端，检查 trusted HTTPS、admin 原密码登录、用户数据隔离、服务重启后的持久性。失败时停止新版，恢复整个匹配备份及旧源码，而不是只回滚代码。
- [ ] 推送 GitHub 触发 Vercel，核对前端部署对应提交与 /api/session；新旧前端升级间隙不丢弃已保存数据，旧会话提示重新登录。
- [ ] 线上生成临时邀请注册两位测试用户，验证全链路后禁用测试账号并撤销剩余邀请。记录检查项目，不记录明文凭据。
- [ ] 交付管理员入口、生成邀请码步骤、测试者注册步骤与版本号。CFD 仍未部署、真实模型调用是否验证分别明确说明。

## 自查结论

- 设计范围覆盖：邀请码、账号管理、个人模型、设计/工况/对话、任务目录、旧数据迁移、缓存隔离、部署回退均有对应任务。
- 五项 Review Focus 分别纳入 Task 1/2/4/5/6/7 测试。
- UserModelStore 保持原模型存储接口；个人资源操作统一显式 user_id；跨模块状态统一使用 generation。
- 后端身份与隔离完成前不向生产公开注册入口；中间提交可以单独审阅，但完整通过 Task 8 后才上线。
- 执行建议：本会话顺序实现，末尾独立审查整个变更。各任务高度依赖统一身份接口，顺序实施可减少接口合并冲突。
