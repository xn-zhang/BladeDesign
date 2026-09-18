# AeroBlade 对话初设入口 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement sequentially. No delegation required. 当前用户已指定本次实现首页和 API 预留；后续评估/优化/三维模板仅规划。

**Goal:** 完成对话初始界面、可校验初始方案、手动入口及带参交接。

**Architecture:** 独立协议客户端 + 对话UI；接入既有工作区导航并复用实际几何校验和应用回调。模型服务通过同源代理协议预留，演示是显式的图19参考数据。

**Tech Stack:** 原生 JavaScript / CSS / HTML，Node.js 内置测试，现有 Python 标准库桥接与打包工具。

**Spec:** [完整产品及交互方案](../specs/2026-09-18-design-entry-design.md)

## Global Constraints

- 不增运行时依赖；不更改几何公式、现有 CFD 算例及求解器。
- 11参数、mm/deg、出口负角、进口半楔角与现有内核一致；height 独立于11参数。
- API 未连接明确报错；演示与真实模型结果明确区分。
- 不存储模型密钥、不执行模型 HTML；用户确认后才应用方案。
- 仓库尚无首个提交，既有文件均未跟踪。在当前用户工作区定向编辑，不创建包含用户全部文件的基准提交。

## Task 1 — 方案协议、演示和数据校验

Files: 新建 `openfoam-bridge/web/design-assistant-client.js`、`tests/design-assistant.test.mjs`。

Interfaces: `validateProposal(raw)` 返回独立副本；`validateReply(raw)` 返回 message/proposal；`demoReply(message)` 只对“载入参考方案”返回预设；`requestAssistant({provider,messages,signal,fetchImpl})` 返回 Promise。

- [x] 添加完整方案、缺字段、单位、整数、来源、几何组合、演示诚实性、API 错误测试。
- [x] 运行 `node --test tests/design-assistant.test.mjs`，先确认客户端不存在而失败。
- [x] 实现严格协议，实际调用 `validate` 和 `analyze`；请求 `POST /api/design-assistant/chat`，支持 AbortSignal。
- [x] 运行上述测试并检查通过。

协议示意（完整定义见 `openfoam-bridge/docs/DESIGN_ASSISTANT_API.md`）：

```js
{schema:'aeroblade-assistant-reply-v1', message:'请补充入口工况', proposal:null}
```

## Task 2 — 对话状态、首屏与方案卡

Files: 新建 `openfoam-bridge/web/design-assistant.js`、`design-assistant.css`。

Interface: `initDesignAssistant({applyDesign,openDesign})` 返回供导航注册的 section。

- [x] 实现欢迎区、可编辑示例、模型选择、消息发送、中文输入法保护、停止/重试、重新开始。
- [x] 用请求代号和 AbortController 丢弃取消后的响应；发送新需求前冻结旧候选为过期。
- [x] 只读方案卡展示11参数、来源、气动数据、假设、几何状态和采用按钮；应用时再次校验。
- [x] sessionStorage 保存有界会话、草稿、候选和来源；刷新恢复校验，存储异常不阻断操作。
- [x] 添加响应式样式、焦点反馈、aria-live 和表格标题。

## Task 3 — 工作区集成和 API 接入文档

Files: 修改 `web/cfd.js`、`web/index.html`、`README.md`；新建 `openfoam-bridge/docs/DESIGN_ASSISTANT_API.md`。

- [x] 在既有导航注册“初始设计”，默认进入；手动跳转和确认跳转均走原工作区切换函数。
- [x] 全部工作区保留设计导入/导出动作并共用顶部栏布局；设计、CFD、AI 导航及快捷键保持可用。
- [x] 文档记录请求/响应 Schema、参数清单、后端模型路由、错误处理、单位校验、密钥存储与真实数值求解边界。

## Task 4 — 验收与交付

- [x] Node 协议测试与现有几何回归。
- [x] `bash scripts/check.sh`：Python、JS 语法、Node 与打包检查；WSL 不可用时执行对应原生命令并记录平台相关限制。
- [x] 浏览器核验初始页、消息、参考方案、失效、停止、重试、刷新、应用、手动返回、移动端和工作区切换。
- [x] 更新本计划实际完成状态；交付文件链接与 API 尚未接通的事实。

## 后续实施顺序（本次不开发）

1. 总师 API 代理及模型部署 → 平均线工具接口 → 有来源的初值求解。
2. 设计版本/工况快照统一 → AI 与 CFD 共用评价记录 → 评估与优化页面。
3. 可行性筛选、DOE、代理/CFD 优化调度及候选回写。
4. CFD 工作区新建径向多截面三维模板，完成网格/收敛/守恒/基准验收。

详细页面设计、数据关联和三维验收要求见 Spec 第4–5节。

## 实施与验收记录（2026-09-18）

本次首页范围已实现，后续页面和求解模板保持规划状态。代码在原工作区定向修改；未提交或推送，也未改动现有几何/CFD计算实现。

- 协议测试先观察到模块缺失失败，再实现并通过6项测试；连同已有几何回归合计13项全部通过。
- `web/*.js` 与 `bridge/*.mjs` 全部通过 `node --check`。
- Python 桥接回归运行56项：46通过、10失败，失败位于已有 pipeline/scheduler 的 POSIX 进程夹具。单独复现 `PipelineTests().exercise()` 得到 stage=blockMesh、`WinError 2`（Windows 无法启动无扩展名 shebang 脚本）。本次不修改求解器来适配测试环境。
- 已尝试 `bash scripts/check.sh`，Git Bash 返回49且无日志输出；WSL列举命令无响应，已取消本次调用。故不能声称 Linux/WSL 全套检查通过。
- `bridge/package.py` 与 `scripts/check_package.py` 通过，发布包包含新页面模块和接口文档。
- 浏览器实测：初始页、参考方案11参数、确认应用、手动跳过保留32 mm自定义弦长、刷新恢复方案和草稿、继续对话使旧方案失效、未接API错误与重试不重复用户消息、新建对话确认、键盘方向/Home导航、CFD/AI工作区切换。
- 独立本机 HTTP 测试夹具（仅runtime、不进入发布包）：4秒延迟响应下停止成功且迟到结果不入库；重试成功返回候选；非法 +57° 出口角被拒绝、现有32 mm设计保持不变。夹具不执行模型推理。
- 1440×900 桌面与390×844手机检查；无文档横向溢出，手机卡片纵向排列，桌面消息区独立滚动。测试后恢复正常浏览器视口。
- 用户授权 CodeGraph 初始化，但当前会话没有 CodeGraph MCP，Windows PATH/常见 npm 命令目录未找到codegraph，WSL不可用，尚未建立索引。

预览：`http://127.0.0.1:8791/`（本次启动的纯静态预览；真实模型接口未接入）。正常平台服务重启/刷新也会默认显示新首页。
