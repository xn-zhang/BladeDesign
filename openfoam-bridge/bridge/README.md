# AeroBlade × OpenFOAM 计算桥接服务

首次使用请先阅读 [克隆后的启动与停止、令牌获取、远程连接及批量参数导入](../docs/GETTING_STARTED.md)。下文命令以 `openfoam-bridge/` 或解压目录为工作目录。

当前默认设计方法为 [Pritchard 1985](../docs/PRITCHARD.md)，使用 `python3 bridge/create_pritchard_cascade.py` 生成配套模板。下文冷态旧模板及2026-09-08验证属于历史概念几何，不是Pritchard截面的验证结果。

本交付包括网页工作台、Python 桥接服务及自建二维冷态周期叶栅生成器。2026-09-08 已在本机 OpenCFD v2512 完成真实计算链路验证，见 [实测报告](../docs/CASCADE_VALIDATION.md)。这不代表三维叶片或发动机性能已经验证；单元测试夹具仍不是 CFD 结果。

## 本机新增冷态周期叶栅（2026-09-08）

已添加自建算例生成器与严格结果审计工具，详见 [CASCADE.md](../docs/CASCADE.md)。原始交付的无算例说明描述的是初始状态；当前新增模板的实测状态以 `CASCADE_VALIDATION.md` 和对应任务的 `validation.json` 为准。

在 WSL 从交付目录执行 `bash bridge/start-local.sh`，即可加载默认 v2512 和本机 NVM Node，使用本机私有令牌启动。默认令牌文件为 `~/.local/state/aeroblade/api-token`，在自己的终端读取后填入网页，勿发到聊天中。服务已经占用 8787 端口时无需重复启动。

首次安装可执行 `python3 bridge/create_cascade.py`；已有模板时不会覆盖。网页连接后选择冷态周期叶栅并点击“应用模板推荐叶片”。

## 工作区布局

顶部“叶片设计 / CFD 仿真”用于切换工作区，切换保留设计参数、连接和任务状态。桌面端按视口高度伸缩，长参数和日志在面板内滚动；CFD 提交按钮固定在配置栏底部。窄屏改为正常纵向布局，无需缩小浏览器缩放比例。

## 能做什么

- 网页连接计算服务并检测实际 OpenFOAM 环境与模板。
- 从服务器模板读取工况字段、单位、范围和数值约束。
- 冻结叶片参数、工况和算例，使用同一几何引擎在服务器生成 **米制 STL**。
- 按模板执行 `blockMesh → surfaceFeatureExtract（可选）→ snappyHexMesh → checkMesh → 求解器 → foamToVTK（可选）`。
- 多算例并行执行，默认2个并发、运行与排队合计最多16个任务；支持独立取消、超时终止、磁盘持久化、重启中断标记。
- 显示真实日志和初始残差；右侧显示已完成二维任务的逐单元速度、压力、温度云图；下载真实算例及可选 VTK 结果。
- 网格检查必须输出 `Mesh OK.`；正常进程退出还需 `End`。仅当求解器明确报告 `converged in` 才显示“求解器报告收敛”，这仍不代替质量守恒与网格独立性评估。

## 运行要求

- Linux，Python **3.10 或更高**，Node.js **20 或更高**；Python 服务无需第三方包。
- 已安装并加载环境的 OpenFOAM。适配对象为 OpenCFD 命令体系，包括 `rhoSimpleFoam` / `rhoPimpleFoam` / `simpleFoam`；这不表示已跨版本验证。请先提供实际分支和版本，特别是 OpenCFD v2512 与 Foundation 分支不能混为一谈。
- 当前支持算例级并行；单算例未接入 MPI，也未接入 Slurm、旋转接口、MRF 自动构建或动网格。转子/非定常建模需另行配置并验证模板，网页不会自动推导边界条件。
- 对托管网页接入，需要浏览器可达且证书有效的 HTTPS 服务；仅有 SSH 地址不能直接填入网页。可以先通过本机 SSH 端口转发，在本地工作台验证，再配置 HTTPS。

解压后应保留 `bridge/`、`web/` 与 `docs/` 同级；几何生成器依赖 `web/geometry.js`。

## 1. 启动服务

先在终端加载你现有 OpenFOAM 的 `etc/bashrc`。随后检查环境：

```bash
command -v blockMesh
command -v snappyHexMesh
command -v checkMesh
command -v rhoSimpleFoam
node --version
python3 --version
```

从解压目录运行：

```bash
export AEROBLADE_API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export AEROBLADE_ALLOWED_ORIGINS='https://your-workbench.example'
python3 bridge/server.py --templates ./templates --jobs ./jobs --port 8787
```

令牌须通过你自己的安全方式保留并输入网页；不要发在聊天里，不要放在 URL、公开源码或网页存储中。服务不会打印令牌。前台按 `Ctrl+C` 停止，等待清理结束后重新启动；停止服务会取消未完成任务。关闭终端可能结束前台服务；持续运行时可按实验室方式配置 systemd，确保进程继承 OpenFOAM 环境和上述变量。

默认仅监听 `127.0.0.1`，不要直接将这个开发 HTTP 服务暴露到公网。通过你管理的 Nginx/Caddy HTTPS 反向代理转发到 `127.0.0.1:8787`。代理需保留 Authorization，并转发 OPTIONS。`AEROBLADE_ALLOWED_ORIGINS` 为逗号分隔的精确网页源；如果从求解服务自身的 HTTPS 页面打开工作台，也把该源加入列表。不要使用通配来源。

没有模板时服务依然可以启动，健康检测会诚实返回 `ready: false`，提交按钮不会启用。

## 2. 本机或 SSH 转发验证

服务直接提供整套工作台。浏览器打开 `http://127.0.0.1:8787`，进入“CFD 仿真”，填同一地址与令牌。

如果服务在远程 Linux 主机，且已经获得该主机访问授权，可在你的电脑执行：

```bash
ssh -L 8787:127.0.0.1:8787 your-user@your-compute-host
```

然后仍在电脑浏览器打开 `http://127.0.0.1:8787`。这是本地工作台路径；托管 HTTPS 工作台不能用它直接跨源访问 HTTP 服务。令牌无需在 SSH 命令里传递。

## 3. 安装自己的叶栅算例模板

`bridge/examples/aeroblade-template.json` **只是模板描述符示例，不是 CFD 算例，未被自动注册，也不能单独求解**。示例数值、范围及几何包络都必须根据你的实际算例调整。

每个模板位于 `templates/<name>/`，目录至少包含：

```text
0/                           已验证初始场与边界条件
constant/                    已验证热物性、湍流及其他模型
system/controlDict           求解控制与后处理函数
system/blockMeshDict         背景计算域与边界命名
system/snappyHexMeshDict     引用 constant/triSurface/blade.stl
system/surfaceFeatureExtractDict   使用特征提取时需要
system/fvSchemes
system/fvSolution
aeroblade-template.json       模板描述符
```

这是受信任的管理员模板：禁止接收网页上传的命令、字典或脚本；管理员需审查模板中的 OpenFOAM 动态代码、函数对象与加载库。服务以普通受限系统用户运行，使用独立的任务目录和操作系统资源限制。

适配流程：

1. 从你已通过验证、能够在计算机上独立完成网格与求解的算例复制 `0/constant/system` 等输入。删除旧体网格 `constant/polyMesh` 和旧时间目录/结果；服务拒绝使用已有体网格，避免把新几何配给旧网格。
2. 让 snappyHexMesh 使用 `constant/triSurface/blade.stl`。平台始终输出米制 STL；不要再应用 `0.001` 缩放。基于现有背景网格正确设置 `locationInMesh`、周期面、壁面、端壁、加密区、边界层和质量约束。
3. 将需要从网页传入的**数值位置**替换为 `{{INLET_TOTAL_PRESSURE_PA}}`、`{{INLET_TOTAL_TEMPERATURE_K}}`、`{{OUTLET_STATIC_PRESSURE_PA}}`、`{{ITERATIONS}}` 等标记。不要只在注释中放置标记。保持原来经过验证的总压/总温/静压边界类型、字段名称、热力学约束和单位。所有声明参数必须在算例文件中使用。
4. 将示例描述符放入算例根目录，按实际算例修改名称、求解器、数值范围和 `geometry_bounds_m`。包络按当前几何全局坐标（单位 m）定义；它是几何尺寸检查，不能证明周期性、网格质量或可制造性。
5. 如果更换叶片会改变周期面匹配、通道交叠或网格拓扑，应先在计算端调整模板，不应简单扩大包络绕过限制。Pritchard 模板的节距由半径和叶片数计算；轮毂/机匣、转子转速及其他流道设置仍需由具体模板定义。
6. 重启桥接服务使模板重新加载。在网页“连接并检测”，选择模板并检查动态工况。提交先做低成本验证，再做网格独立性和研究工况。

本版本支持固定 allowlist 的 OpenCFD 命令与选项；不运行 Allrun、shell、任意脚本或客户端指定程序。新网格流程、单算例 MPI 并行、额外参数或输出指标需要在代码与测试中显式适配；当前已支持独立算例并行。

## 4. 使用网页

1. 在“CFD 仿真”填写 HTTPS 服务根地址和令牌，连接并检测。
2. 选择真实模板，调整由模板定义的工况。
3. 点击“提交真实仿真”。保存的参数快照不可被后续页面编辑覆盖。
4. 查看阶段、残差和日志；失败保留日志，不能下载伪造成功结果。断开网页连接不停止服务器任务，停止需点击“停止任务”。
5. 计算结束后下载 ZIP。含 `case/` 和 `run.log`；如果模板执行了 `foamToVTK -latestTime`，可用 ParaView 打开 `case/VTK/` 中的结果。

暂未集成浏览器内三维流场云图、自动总压损失或效率计算；需要你的算例测量截面、质量流量加权定义与结果格式后再适配。当前网页展示真实残差及已完成二维任务的逐单元云图；详见 [FLOW_VIEW.md](../docs/FLOW_VIEW.md)。三维结果仍需下载 VTK，不会将投影或示意图当作实际截面。

## API

所有 `/api/` 请求需要 `Authorization: Bearer <token>`，且浏览器 Origin 在允许列表内。JSON 请求上限 200 KB。

| 方法与路径 | 行为 |
|---|---|
| `GET /api/health` | 真正的环境就绪状态、版本、模板 |
| `GET /api/jobs` | 最多 100 条任务（活跃任务优先）及调度状态 |
| `GET /api/scheduler` | 并发配置、运行/排队数量与容量 |
| `POST /api/scheduler` | 使用 `{"max_parallel":2}` 调整当前进程并发数 |
| `POST /api/jobs` | 按 `aeroblade-cfd-v1` 提交参数与工况 |
| `GET /api/jobs/{id}` | 状态、工况快照、残差、日志尾部 |
| `GET /api/jobs/{id}/flow` | 已完成二维任务的实际单元多边形与速度/压力/温度场；同样需要鉴权 |
| `POST /api/jobs/{id}/cancel` | 取消排队或运行中的任务 |
| `GET /api/jobs/{id}/artifacts` | 正常结束任务的真实 ZIP |

`jobs/` 持久存储请求、模板副本、算例、日志与状态。服务重启后未完成任务标记 interrupted，需要重新提交。结果不自动清理，需由计算端管理员管理磁盘；超过 2 GB 不生成网页下载包，保留计算机上的原始算例。

## 验证范围

```bash
python3 -m unittest discover -s bridge/tests -v
```

已覆盖参数与 SI 单位转换、模板注入限制、API 鉴权/CORS/路径隔离、坏网格阻止求解、取消进程、正常结束与收敛区分。进程测试使用夹具程序模拟命令输出以验证调度逻辑，**这些单元测试不执行真实 OpenFOAM**。新增模板的真实求解与浏览器实测独立记录在 [CASCADE_VALIDATION.md](../docs/CASCADE_VALIDATION.md)。

## 官方资料

- [OpenCFD rhoSimpleFoam](https://doc.openfoam.com/2312/tools/processing/solvers/rtm/compressible/rhoSimpleFoam/)：定常可压缩湍流求解器。
- [OpenCFD snappyHexMesh](https://doc.openfoam.com/2312/tools/pre-processing/mesh/generation/snappyhexmesh/)：基于几何表面的网格生成。
- [OpenFOAM 标准求解器](https://www.openfoam.com/documentation/user-guide/a-reference/a.1-standard-solvers)：根据物理问题选择求解器。

这些文档用于接口设计参考；并不构成对用户版本、叶栅算例或边界条件的验证。

### 100% 缩放可读性

主要参数、输入框和按钮使用 14px，辅助说明至少 12px，求解日志使用 13px 等宽字体；图表刻度与深色画布标注同步放大。文字对比度提高，桌面侧栏略加宽，内容超出时在面板内部滚动。保留工作区切换和参数、连接状态。

桌面叶片设计工作区按 25% / 45% / 30% 分配设计参数输入、三维展示和截面分析宽度。平台名称位于顶栏，截面图表高度随可用空间调整。CFD 配置与监控区为 25% / 75%，监控区内残差日志与流场按 35:40 分配（比例均扣除栏间距）。

并发配置、API和实际验证见 [多算例并行计算](../docs/PARALLEL_CASES.md)。
