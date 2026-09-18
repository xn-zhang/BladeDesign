# 涡轮叶片智能设计与仿真优化平台

AeroBlade 是一个本地运行的叶片参数化设计与 OpenFOAM CFD 工作台。前端使用原生 JavaScript，计算桥接服务仅依赖 Python 标准库。

## 当前功能

- 对话式初始设计入口：总师智能体需求对话、图19参考演示、11参数方案审阅与校验、带参进入叶片设计及手动跳过。支持会话恢复、停止和重试；真实大模型后端待接入，见[接口协议](aeroblade/docs/DESIGN_ASSISTANT_API.md)。
- Pritchard 1985十一参数截面设计、五段解析轮廓、派生几何指标与直线拉伸三维展示。
- 新旧模型显式切换、设计JSON及STL/截面CSV导出，旧版概念几何保留兼容。
- OpenFOAM 服务连接、二维冷态周期叶栅网格生成、检查及求解。
- 多算例并行、可配置计算槽位、算例命名、队列自动刷新、独立取消与结果下载。
- 任务残差与日志、二维速度/压力/温度逐单元流场显示。
- 三维有限展宽端壁叶栅探索：真实体网格、三分量速度求解及VTK导出；首轮3000步尚未收敛。
- AI 预测工作区布局：数据与输入、三条模型路线、建模流程、流场预览、六项气动指标、训练状态及基线对比。当前为前端界面预览，支持路线切换与面板展开；数据处理、训练和预测尚未接入，业务按钮保持禁用。

当前Pritchard参考截面已完成7092单元二维计算，在2092步报告收敛；严格几何诊断仍发现290个凹单元，详见[Pritchard验证记录](aeroblade/docs/PRITCHARD_VALIDATION.md)。尚未实现经验证的三维CFD、自动优化或工程精度验证。旧模型验证记录单独保留，原始任务数据不随仓库发布，应在本机复算验证。

## 克隆与启动（Linux / WSL）

需要 Git、Python 3.10+、Node.js 20+、OpenCFD OpenFOAM（当前真实验证 v2512），无需 npm/pip 安装依赖。Windows 用户先进入 WSL，以下命令在 Bash 中执行：

```bash
git clone https://github.com/xn-zhang/BladeDesign.git
cd BladeDesign
# 模板已存在时跳过生成
test -f aeroblade/templates/pritchard-cascade-2d/aeroblade-template.json || \
  python3 aeroblade/bridge/create_pritchard_cascade.py
bash scripts/start.sh --max-parallel 2 --max-pending 16
```

打开 [本地工作台](http://127.0.0.1:8787/)，在“CFD 仿真”中填写同一服务地址与令牌。仅一个逻辑 CPU 时使用 `--max-parallel 1`。默认加载 `/usr/lib/openfoam/openfoam2512/etc/bashrc`，其他位置使用 `FOAM_BASHRC=/实际路径/etc/bashrc bash scripts/start.sh`。

**停止**：在服务终端按 `Ctrl+C`，等待退出。**重启**：先停止，再运行启动命令。服务停止会取消未完成任务；关闭网页不会停止计算。保持后台会话、定位遗留进程及远程服务的操作见下方完整指南。

## 获取 API token

API token 由 **AeroBlade 桥接服务**生成，不是 OpenFOAM 账号或 SSH 密码。首次用启动脚本运行后，在同一 Linux 用户的另一个终端执行：

```bash
cat "${XDG_STATE_HOME:-$HOME/.local/state}/aeroblade/api-token"
```

将内容填入页面令牌框，不带 `Bearer ` 前缀。远程服务需登录求解机，以运行服务的账号读取该机文件；如果管理员设置了 `AEROBLADE_API_TOKEN`，应使用管理员配置的值，文件可能不代表当前令牌。令牌不要提交到 Git 或发到聊天中。

## 设计导入与批量计算

- **单份设计**：叶片设计 → 导入参数 JSON。Pritchard 使用 `aeroblade-pritchard-v1`，长度 mm、角度 deg；可先导出有效设计作为格式模板。
- **批量设计**：目前网页一次只导入一个文件；多份设计通过 `POST /api/jobs` 逐个提交，由服务按计算槽位并行运行。完整指南提供可复制的批量提交 Python 示例及提交记录、队列满和重试处理说明。
- **Excel/CSV**：需先逐行转换为设计 JSON。截面坐标 CSV 和 STL 不是可重新导入的参数文件。

**[完整操作指南：克隆、启停、远程连接、令牌、参数格式与批量提交](aeroblade/docs/GETTING_STARTED.md)**

## 项目结构

```text
.github/workflows/       GitHub 自动检查
scripts/                 仓库级启动、检查和打包入口
tests/                   共享几何引擎回归测试
aeroblade/
  web/                   网页源码与共享几何引擎
  bridge/                Python API、任务执行、几何调用与算例生成器
    tests/               单元测试和流程夹具
    examples/            模板配置示例
  docs/                  算例、真实验证和流场可视化说明
  templates/             可复用算例配置（不含计算结果）
  dist/                  生成的便携发布包（忽略）
  jobs/                  本机网格、求解记录与结果（忽略）
  runtime/               本机日志、截图与调试文件（忽略）
```

`aeroblade/` 是完整的 AeroBlade 工作台应用目录，包含叶片设计界面、AI 工作区、CFD 服务与算例模板，可独立打包部署。

## 开发与验证

```bash
bash scripts/check.sh
bash scripts/package.sh
```

自动检查包括 Python 测试、JavaScript 语法和发布包结构，不需要 OpenFOAM。流程夹具模拟命令输出，不代表真实 CFD 验证。发布包输出到 `aeroblade/dist/aeroblade.zip`，可解压独立运行。

- [计算服务及接口说明](aeroblade/bridge/README.md)
- [多算例并行计算与配置](aeroblade/docs/PARALLEL_CASES.md)
- [三维探索结果与未通过项](aeroblade/docs/THREE_D_VALIDATION.md)
- [Pritchard参数定义与公式](aeroblade/docs/PRITCHARD.md)
- [二维算例说明](aeroblade/docs/CASCADE.md)
- [真实计算验证记录](aeroblade/docs/CASCADE_VALIDATION.md)
- [流场可视化](aeroblade/docs/FLOW_VIEW.md)
- [贡献与开发约定](CONTRIBUTING.md)

## GitHub 同步范围

提交源码、模板配置、测试与文档。`jobs/`、`runtime/`、`dist/`、令牌和环境私有配置已加入忽略规则。发布包可在需要时作为 GitHub Release 附件上传。当前尚未选择开源许可证；公开使用授权需由项目所有者确定。
