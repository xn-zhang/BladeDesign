# CFD 数据、参数回归与自动优化

平台将 **AI 预测** 与 **评估与优化** 作为两个独立的一级工作区。AI 预测是模型开发与推理中心，包含代理模型推理、数据与训练、大模型与模型路线三个页签；评估与优化包含性能评估和自动优化。两个工作区共享几何、物理工况、所选代理模型和任务状态。

AI 页面直接提供代理模型开发、模型卡、推理指标，以及通用/航发领域大模型的配置和总师智能体入口。大模型对话复用初始设计工作区；PyG / FNO 流场代理明确标注待开发。

## 启动与部署

HTTP bridge 本身使用 Python 标准库；数值计算由独立子进程运行。建议在计算机或 Linux 求解服务器创建独立环境：

```bash
python3 -m venv .venv-evaluation
.venv-evaluation/bin/python -m pip install -r aeroblade/evaluation/requirements.txt
# 使用 MLP 时另行安装适合机器的 PyTorch：
.venv-evaluation/bin/python -m pip install torch
export AEROBLADE_EVALUATION_PYTHON="$PWD/.venv-evaluation/bin/python"
python3 aeroblade/bridge/server.py --port 8791
```

Windows 的环境解释器为 `.venv-evaluation\Scripts\python.exe`。本次本地验收创建的环境通过 `--system-site-packages` 复用已有数值库；部署环境按上面的 requirements 独立安装。模型卡记录实际 Python / NumPy / sklearn / torch 版本。

缺少 OpenFOAM 时，可使用 `--model-only` 启动数据扫描、训练与预测；这时 CFD 评估和自动优化不可启动。完整服务须在已安装相应 OpenFOAM、模板并通过 `/api/health` 检查的 Linux 求解环境运行。

路径参数：

- `--jobs`：真实 CFD 任务目录，默认 `aeroblade/jobs`。
- `--evaluation-dir` 或 `AEROBLADE_EVALUATION_DIR`：数据集、模型卡、计算任务与结果，默认 `aeroblade/ai-data`。
- `AEROBLADE_EVALUATION_PYTHON`：指定数值 worker 解释器；未配置时优先找项目 `.venv-evaluation`，否则使用 bridge 解释器。

Vercel 承载静态页面，并将 `/api/*` 同源转发到长期运行的 Python bridge。OpenFOAM、训练进程和持久存储均在该后端机器上，不能在 Vercel 静态托管内执行。使用现有平台账号登录，不需要在工作区填写额外令牌。评估目录不在静态文件允许列表内，也不进入发布 ZIP。

## 页面操作

1. 打开独立的“AI 预测”工作区，点击“连接 / 刷新”，登录平台账号。
2. 在“数据与训练”点击“扫描已有任务”。查看质量通过、拒收原因、独立几何和去重记录。
3. 选择数据版本及 Ridge / ExtraTrees / MLP，点击“训练并保存模型”。模型卡显示分组样本数量及验证 / 测试 MAE。
4. 在“代理模型推理”选择模型、输入工况并运行 AI 预测。点击“性能对比 / 优化”进入独立评估工作区，提交 CFD、载入已有合格 CFD，或输入任务 ID 重新检查并提取指标。AI 和 CFD 任务独立运行。
5. “载入模型参考设计与工况”可回到训练参考输入。编辑几何或工况会将已有评估标记为历史快照；比较差值要求几何、工况、模板、热物性和指标版本相同。
6. 在“自动优化”选择 1–6 个设计变量、包含基准值的边界、1–2 个目标、可选约束、CFD 预算。代理模式使用 AI 预测工作区所选模型，小样本模型需要勾选实验性筛选。
7. 启动后，查看 CFD 质量通过的候选、主目标历史和 Pareto 集；候选详情可对比基准轮廓并载入叶片设计。导出任务 JSON 包括冻结输入、预测、CFD 证据、失败原因。

## 数据合同和适用范围

只支持 `pritchard-cascade-2d` 的静止、冷态、单层 XY 叶栅。压力为 Pa，温度为 K，速度为 m/s，phi 为 kg/s；使用常比热、常黏度理想气体。通过实际 empty 平面间距获得展宽，与界面显示的拉伸高度无关。

网格读取保留 owner / neighbour 和有向面矢量，检查正体积、闭合、周期平移面的一一匹配；不通过猜测边界值恢复数据。入口和出口的已写出静压值用于指标，`p0` 边界条件参数不能代替求解后的静压。常用的 zeroGradient、noSlip 边界可按显式规则恢复。

六项指标：

| 指标 | 定义 |
|---|---|
| 总压损失系数 | `(质量加权入口总压 − 质量加权出口总压) / (质量加权入口总压 − 质量加权出口静压)` |
| 出口流角 | `atan2(质量加权 Uy, 质量加权 Ux)`，轴向有符号角 |
| 流动转折角 | 出口角减入口角，归约到 `[-180°,180°)` |
| 单位展宽质量流量 | 出口净质量流量 / 实际网格展宽 |
| 轴向、周向压力载荷系数 | 叶片壁面 `Σ(p−p_ref) Sf` 的 x / y 分量，除以实际展宽 × 轴向弦长 × 入口总压与出口静压差 |

总压由每个边界面的静压、温度、速度及实际热物性推导。权重使用 `rho U·Sf`，并与已写出 phi 独立核对。叶片边界矢量为流体外法向，即指向叶片；载荷不包含黏性剪切。

workflow 门槛包含：任务完成、求解器显式收敛、所需初始残差小于 `1e-5`、日志与重构质量不平衡小于 `0.1%`、有限正压正温、平面速度、网格门槛、周期几何 / 通量配对、边界回流比例和 phi 重构误差。求解迭代与场时间必须一致，读取前后源文件摘要必须稳定。job / request 中的输入快照必须相同。

严格几何检查失败或未知会单独保留，不等同于工程级通过。当前数据没有工程级标签：尚缺网格独立性和试验验证。旧任务、不收敛任务、其他模板进入拒收报告，不用推测值填补。

数据集保留 source hash、网格 / 模板 / 热物性摘要、原始边界数组及训练去重标记。相同几何、工况、模板和热物性仅取一个训练样本。按归一化叶型及节距比例建立几何组，重复几何不会同时进入训练和验证 / 测试集。

## 回归与优化行为

输入为几何比值、四个角度的 sin/cos、物理工况、气体属性和参考 Reynolds 数；迭代次数、CFD 输出、时间信息不作为预测输入。归一化、角度展开中心仅从训练集求得。超参数在验证集选择，测试集不参与训练或调参。至少需要 3 组几何；不足 15 组仅为实验性 smoke，独立测试集留空。输出角度误差按圆周最短差计算。

模型使用可校验的 JSON 数组保存，不接受上传 pickle。记录特征顺序、来源摘要、划分 ID、代码版本、模型权重摘要和每指标 MAE / RMSE。外推提示由训练特征范围和标准化最近距离给出，不是校准置信区间。输入在范围内也不意味着预测准确。

优化是有预算的 DOE 加局部细化搜索。基准首先提交 CFD；后续候选在真实几何引擎校验后才可提交。基准必须通过质量门槛，并固定模板、热物性、工况和指标版本；后续不同上下文的CFD不参与排序。代理模式先与已完成的基准核对上下文，再排序范围内候选并做CFD复核；旧模板模型会停止搜索，超过训练范围的候选保留记录并跳过代理筛选。已通过 CFD 的可行候选用于细化后续采样中心。最优与 Pareto 只使用 CFD 质量通过并满足约束的候选，不使用 AI 值冒充求解结果。算法提供可追溯的搜索过程，不保证全局最优。

每次优化预算 2–30 次，最多一个优化任务同时运行。评估进程池 2 个槽位，最多 4 个未结束任务；CFD 使用已有 manager 的并行队列。暂停等待当前 CFD 和指标提取完成，之后不提交新任务；取消只停止该任务拥有的 worker / CFD。切换页面不停止服务器任务。服务重启将未完成评估标记 interrupted，不盲目重交 CFD；已保存结果仍可读取。

## API

所有 `/api/evaluation/*` 路由需要现有平台会话；写操作校验 CSRF，跨域使用既有 origin 规则。兼容已有受控服务 Bearer 鉴权。

| 方法与路径 | 内容 |
|---|---|
| GET `capabilities` | CFD 就绪状态、算法、任务和预算限制 |
| GET `datasets` / `models` / `tasks` | 已保存的数据、模型卡、任务 |
| POST `dataset` | `{}`，扫描服务器 jobs 目录 |
| POST `train` | `{dataset_id, algorithm, seed}` |
| POST `predict` | `{model_id, parameters, conditions}` |
| POST `analyze` | `{job_id}`，检查已有 CFD 并提取指标 |
| POST `evaluate` | `{parameters, conditions}`，提交 CFD 并自动检查与提取 |
| POST `optimize` | `{parameters, conditions, mode, bounds, budget, seed, objectives, constraints, model_id?, allow_experimental?}` |
| GET `tasks/<id>` | 持久任务、冻结请求及结果 |
| POST `tasks/<id>/pause` / `resume` / `cancel` | `{}` |

conditions 包含 `inletTotalPressure`, `inletTotalTemperature`, `outletStaticPressure`，真实 CFD 另需 `iterations`。优化 objectives 示例：`[{"metric":"loss_coefficient","direction":"min"}]`；constraints 示例：`[{"metric":"mass_flow_per_span","op":">=","value":0.17}]`。

## 本次验收边界

现有 23 个任务中 5 个通过 workflow 门槛，去重后 3 个独立几何。三种回归算法均用真实数据执行训练和预测。自动优化的软件调度由显式标记的受控夹具验证；当前 Windows 未提供可用 OpenFOAM 环境，因此本次没有新增真实 CFD 优化结论。测试夹具不进入真实数据目录或模型训练。

已知轻微状态边界：数值计算已经结束、最终状态尚未写入的极短窗口中点击取消，最后可能显示“完成”。结果仍完整保留；该显示语义改进列入后续事项。
