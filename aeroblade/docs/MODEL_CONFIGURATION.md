# 真实大模型连接配置

入口：**初始设计 → 模型配置**。现在使用平台账号登录，页面不再要求填写平台令牌或平台服务地址。模型请求自动走当前网站的同源 `/api` 后端。

## 使用步骤

1. 打开平台，点击“登录”。首次本地使用时创建管理员账号；远程部署使用部署者初始化的账号。
2. 点击“模型配置”，页面自动读取服务器上保存的配置。
3. 选择通用模型或航发领域模型，填写 **模型 Base URL、Model ID 和供应商 API Key**。DeepSeek API Key填在此处，不是平台登录密码。
4. 平台自动在Base URL后追加 `/chat/completions`，保留服务商要求的API前缀。完整端点也可输入，平台会去除重复后缀。公网使用HTTPS，本机或私有IP自部署服务可用HTTP；不需要Key的服务选择“无鉴权”。
5. 可点击“测试连接”，然后点击“保存并使用”。测试使用当前表单草稿，不自动保存，可能消耗少量供应商额度。
6. 关闭配置窗口，即可对话。刷新页面或重启后端后，已保存配置仍在服务器；会话过期时重新登录。

支持兼容 [Chat Completions](https://developers.openai.com/api/reference/resources/chat) 的服务。具体Base URL与Model ID以提供商控制台为准。超时可设5–120秒，默认45秒；JSON模式默认关闭，服务支持 `response_format` 时可开启。

## 保存与密钥

- 配置保存到服务器私有SQLite数据库，不写入浏览器存储，也不进入设计导出文件。
- API只返回是否已设置Key，不回显Key。保存或关闭弹窗后Key输入框清空；留空可保留同一服务地址的已有Key，修改地址后需重新填写。
- 清除操作会删除服务器上的该模型配置，重启后仍保持清除状态。
- 登录Cookie为HttpOnly，有效期12小时；退出会撤销当前会话。账号与服务器模型配置保留。
- 私有数据库包含供应商密钥，未做数据库级加密；目录、磁盘和备份必须限制访问。部署和备份说明见 [登录与部署](DEPLOYMENT.md)。
- 停止生成只停止前端等待、丢弃迟到回复，不保证供应商取消推理或计费。

## 环境变量初始化

前缀为 `AEROBLADE_LLM_GENERAL_` 或 `AEROBLADE_LLM_DOMAIN_`：

| 后缀 | 含义 | 默认 |
|---|---|---|
| `BASE_URL` | 模型API基础地址 | 未设置 |
| `MODEL` | 模型ID | 必填 |
| `API_KEY` | 上游模型Key | Bearer模式必填 |
| `AUTH` | `bearer`或`none` | `bearer` |
| `TIMEOUT` | 5–120秒整数 | `45` |
| `JSON_MODE` | `true`或`false` | `false` |

环境变量用于没有数据库配置记录时的初始化。用户在页面保存或清除后，数据库记录优先，不会被重启时的环境默认值覆盖。`.env`文件不会自动读取，不要提交真实密钥。

## API

浏览器使用登录Cookie。写请求附带从 `GET /api/session` 获取的 `X-CSRF-Token`；前端已自动完成。机器接口仍可使用服务端显式配置的Bearer令牌。

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/session` | 登录状态和CSRF标识 |
| POST | `/api/session/setup` | 首次本地管理员初始化 |
| POST | `/api/session/login` | 用户名、密码登录 |
| POST | `/api/session/logout` | 撤销会话 |
| GET | `/api/design-assistant/config` | 读取模型配置，隐藏Key |
| POST | `/api/design-assistant/config` | 持久保存配置 |
| POST | `/api/design-assistant/test` | 测试表单草稿，不保存 |
| POST | `/api/design-assistant/clear` | 持久清除指定provider |
| POST | `/api/design-assistant/chat` | 使用保存的配置生成回复 |

保存/测试字段：`provider,base_url,model,api_key,auth,timeout,json_mode`。401表示未登录或登录过期，403表示来源或CSRF校验失败，503表示未配置模型，502表示上游响应错误，504表示网络或超时，429表示限流。

几何候选继续由前后端校验。当前接通的是模型建议，不代表已经接入平均线求解器或CFD工具调用。详细响应结构见 [初始设计助手协议](DESIGN_ASSISTANT_API.md)。
