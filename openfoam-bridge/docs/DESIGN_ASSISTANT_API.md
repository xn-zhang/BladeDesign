# 初始设计助手 API 接入协议

当前首页已实现对话、参考演示、候选方案校验及设计交接。真实模型后端尚未实现；选择通用/航发模型将调用以下固定同源接口，未接入时显示错误并允许重试。参考演示只有显式载入图19预设，没有自然语言求解能力。

## 请求

`POST /api/design-assistant/chat`，`Content-Type: application/json`。前端使用 same-origin credentials，不读取或保存提供商 API key。部署方在相同源配置服务端代理，密钥从服务器环境读取；可以映射通用与航发模型到不同提供商。不要让浏览器直接访问带密钥的模型 URL。

```json
{
  "schema": "aeroblade-assistant-request-v1",
  "provider": "domain",
  "messages": [{"role": "user", "content": "请先整理初始设计需要的总体条件"}],
  "geometryModel": "pritchard-1985",
  "units": {"length": "mm", "angle": "deg"},
  "parameterContract": [{"key": "radius", "label": "截面所在半径 R", "min": 30, "max": 1000, "unit": "mm"}],
  "angleConvention": "signed-from-axial; negative-outlet; inlet-half-wedge",
  "extrusion": {"key": "height", "min": 30, "max": 160, "unit": "mm", "partOfElevenParameters": false}
}
```

实际请求 parameterContract 自动包含 `pritchard.js` 中全部11字段，上例仅展示一项格式。provider 为 `general` 或 `domain`。messages 是当前会话用户与助手纯文本，最多60条、单条用户6000字符。用户草稿不会发送；参考按钮发送显式“载入参考方案”。当前不使用流式协议，前端60秒超时并支持 AbortSignal 取消；后端长任务应支持取消传播，避免取消后仍耗用模型。

## 响应

成功为200和严格 JSON，不返回 Markdown 代码围栏。

```json
{"schema":"aeroblade-assistant-reply-v1","message":"请补充转速和入口总温。","proposal":null}
```

需要补充条件时保持 `proposal: null`。准备好完整候选后返回同一响应格式，proposal 为：

```js
{
  schema: 'aeroblade-initial-proposal-v1',
  units: {length: 'mm', angle: 'deg'},
  parameters: {
    model: 'pritchard-1985',
    radius: 139.7, bladeCount: 51,
    axialChord: 27.9908, tangentialChord: 15.0114,
    throat: 8.560982297,
    leadingRadius: 0.7874, trailingRadius: 0.4064,
    inletAngle: 35, outletAngle: -57,
    inletHalfWedge: 9, unguidedTurning: 6.5,
    height: 60
  },
  sources: {
    radius: 'Pritchard 图19参考预设，项目毫米尺度',
    bladeCount: 'Pritchard 图19参考预设',
    axialChord: 'Pritchard 图19参考预设，项目毫米尺度',
    tangentialChord: 'Pritchard 图19参考预设，项目毫米尺度',
    throat: 'O = (2πR/N) cos(βout) − 2RTE，参考初始化规则',
    leadingRadius: 'Pritchard 图19参考预设，项目毫米尺度',
    trailingRadius: 'Pritchard 图19参考预设，项目毫米尺度',
    inletAngle: 'Pritchard 图19几何角',
    outletAngle: 'Pritchard 图19几何角，轴向负角',
    inletHalfWedge: 'Pritchard 图19进口半楔角',
    unguidedTurning: 'Pritchard 图19无导向转折角'
  },
  aerodynamic: [],
  assumptions: ['此示例未匹配总体性能要求；60 mm 仅为拉伸展示展宽。'],
  missing: [],
  warnings: ['尚未执行平均线计算与 CFD 气动评估。']
}
```

此处是可用于集成测试的参考几何，不是工程推荐初值。真实气动参数列表格式为 `{label,value,unit,source}`；value 必须为有限数字，source 应写明用户输入、平均线求解器/版本、关联式或参考依据。未计算的参数不要填0或编造数值，留空列表并在 message 说明。label 中应区分流角/金属角、绝对/相对速度三角形，效率注明定义。

长度与角度不做隐式转换，不接受数字字符串、未知参数字段或缺失来源；叶片数须整数。前端先执行几何字段校验，再检查当前内核轮廓可行性。模型必须提供完整方案，不能让前端默默补11参数默认值。height 是必填展示设置，30–160 mm，来源应在 assumptions 说明，不参与11参数计数。

`missing` 非空时整份方案不能应用，应返回 clarification message 与 null proposal。前端验证失败显示错误、保留对话供修改或重试，不修改当前叶片。几何校验不能替代平均线守恒或 CFD 评估；后端应独立校验单位、约束和数值，不信任前端提供的范围作为服务端安全规则。

## 错误及交接

- 401/403：鉴权未配置；404/405/501/503：接口未接入或暂不可用；其他非2xx：请求失败。
- 超时、断网、无效 JSON、格式不符和不可行几何均可重试。停止或新建对话使迟到响应失效，不会应用旧结果。
- 每次提交新要求或切换模型使现有候选失效；只对当前版本展示采用按钮。
- 用户确认后再次校验，并调用与现有 CFD 模板应用共用的 `applyDesign(parameters)`；成功后进入叶片设计。不把气动目标写成 CFD 已计算结果，也不自动提交仿真。
- 会话存在当前标签页 sessionStorage。刷新恢复候选，但设计页仍按原行为初始化基准参数，用户需再次采用候选。不同标签页不承诺共享会话。

## 后端接入建议

在桥接服务或独立同源代理新增上述路由，完成认证、请求限额、提供商适配和 JSON Schema 输出约束。系统提示要求先补足边界条件，再调用平均线工具，逐字段保留来源，严禁将给定效率目标当成预测值。域模型与通用模型共用此业务协议，提供商消息/工具调用格式由后端转换。

第一版前端以整段回复 JSON 作为稳定接入点。若以后增加 SSE，单独扩展客户端传输层，并约定 completed 事件之后才校验候选，不让半成品参数进入几何工作区。
