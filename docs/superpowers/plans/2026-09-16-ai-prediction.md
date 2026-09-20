# AeroBlade AI Prediction Implementation Plan

> 2026-09-21 更新：标量数据/回归/API/UI与自动优化由 [分阶段实施计划](2026-09-21-evaluation-optimization.md) 接管，实际落地在 `aeroblade/evaluation` 和“评估与优化”工作区。本文的 PyG / FNO、正式 benchmark 和流场预测仍待实施；原任务条目不等价于本次精简后的实现。当前仅3组独立几何，执行实验性 smoke。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execute locally in sequence; no delegation is required.

**Goal:** 在现有工作台完成参数回归、PyG 图网络和 FNO 全流场三条可训练、可评价、可推理的二维气动预测路线。

**Architecture:** 只读 CFD 导出器产生版本化样本；独立 ML worker 负责训练和推理，标准库桥接服务提供鉴权、任务状态及静态工作区。所有路线共用几何/工况特征、几何分组划分与六项指标定义。

**Tech Stack:** 现有 Python 3.10+、Node.js 20+ 与原生 JavaScript；独立 ML 环境使用 NumPy、SciPy、scikit-learn、PyTorch、PyTorch Geometric。精确版本在安装和实际导入测试后保存，不修改 CFD 环境依赖。

**Spec:** [2026-09-16-ai-prediction-design.md](../specs/2026-09-16-ai-prediction-design.md)

## Global Constraints

- 第一阶段限定 `pritchard-1985`、`pritchard-cascade-2d`、稳态冷态可压缩 RANS。
- 当前 CFD 服务仍要求 Python 3.10+、Node.js 20+，不强制安装机器学习库。
- 所有归一化器、PCA（若以后添加）和超参数选择只使用训练/验证集合。
- 迭代上限、运行时长、收敛步数、CFD 出口速度、真实流量和真实 Mach 数不作为输入。
- 数据与权重写入被忽略的 `aeroblade/ai-data/`。
- 人工场和流程夹具不计入真实 CFD 数据集。
- 本计划任务尚未执行；当前已完成详细设计和只读数据盘点。

## 执行前检查

- [ ] 读取设计第 3 节和 `aeroblade/docs/AI_DATA_INVENTORY.md`，确认当前只有三个二维 Pritchard 参数几何组，不启动正式 benchmark。
- [ ] 检查工作区及 Git 状态；本次盘点时仓库没有首个提交、原有源码均未跟踪。不要把全部源码当作本功能新文件提交。工作区隔离或提交只包含本任务明确生成的文件，记录基准状态。
- [ ] 确认 Linux/WSL Python 与 Node 路径，运行现有回归；不安装依赖到现有 CFD Python。

```bash
cd aeroblade
python3 -m unittest discover -s bridge/tests -v
node --test ../tests/*.test.mjs
```

## 文件职责与接口总表

| 新建文件 | 职责 |
|---|---|
| `ai/contracts.py` | Schema 版本、字段顺序、类型与输入检查 |
| `ai/foam.py` | ASCII 网格、体积、边界和完整场导出 |
| `ai/quality.py` | 只读质量分层和拒绝原因 |
| `ai/metrics.py` | 热物性、边界质量权重、六项气动指标 |
| `ai/dataset.py` | manifest、哈希、原子导出和读取 |
| `ai/features.py` | 物理输入特征、归一化和几何组 |
| `ai/splits.py` | 冻结几何组划分、泄漏检查 |
| `ai/models/tabular.py` | Ridge/ExtraTrees/MLP 的训练与恢复 |
| `ai/graph.py`、`ai/models/mpnn.py` | 周期图和 PyG 编码传播解码 |
| `ai/grid.py`、`ai/models/fno.py` | 面积投影、规则网格编码、谱算子和边界解码 |
| `ai/train.py`、`ai/evaluate.py` | 共享训练协议与独立评价 |
| `ai/registry.py`、`ai/predict.py` | 可信模型登记和快照推理 |
| `ai/cli.py` | 固定命令行入口；测试与独立运行共用 |
| `bridge/ai_service.py` | 不导入 ML 库的异步任务管理 |
| `web/workspaces.js`、`web/ai.js`、`web/ai.css` | 三工作区切换与预测 UI |
| `ai/tests/` | 数值、模型、数据协议测试 |

表内路径相对 `aeroblade/`。AI 包的 `__init__.py` 和 `models/__init__.py` 不进行 eager ML 导入。桥接服务测试放在原 `bridge/tests/`。具体协议均由设计文档定义。

## Task 1 — 只读网格/场导出与质量分层

**Files:** Create `ai/{__init__,contracts,foam,quality,dataset}.py`、`ai/tests/{__init__,fixtures,test_dataset}.py`；Modify `bridge/validate_result.py`（拆出只读核心而保留原 CLI 行为）、`.gitignore`（相对仓库根目录）。

**Interfaces:**

```python
read_case(case_dir: Path, time: str) -> dict
audit_job(job_dir: Path) -> dict
export_dataset(jobs_root: Path, job_ids: list[str], output_root: Path,
               quality_tier: str = 'workflow') -> dict
load_sample(dataset_dir: Path, sample_id: str) -> dict
```

read_case 返回设计第 4.2 节全部数组以及 thermo/patch 元数据；audit_job 返回 tier、reasons、source_time、checks。export_dataset 返回 manifest，rejected 样本只写原因、不创建带假值的 NPZ。

- [ ] 先写质量分层测试；修改“缺少审计视为通过”“End 视为收敛”应使其失败。人工夹具从现有 `bridge/tests/test_flow.py` 起步，新建包含真实内部面、inlet/outlet/blade/empty/cyclic patch 的完整二维网格夹具；不能沿用只含 empty 面的展示夹具测试流量。

```python
def test_finished_without_convergence_is_rejected():
    from ai.quality import classify
    result = classify({'completed': True, 'solver_end': True,
                       'solver_reported_convergence': False})
    assert result['tier'] == 'rejected'
    assert 'solver_reported_convergence' in result['reasons']
```

- [ ] 运行缺失接口测试并确认失败原因；定义 `classify(checks: dict) -> dict` 后按设计补全必需检查集合，unknown 不等于 true。

```bash
python -m pytest ai/tests/test_dataset.py -q
```

- [ ] 写读写实现时复用 `flow.py` 已有 ASCII 校验思路，但在 AI 包内保留明确读取体积、面和边界的模块；面法向由顶点顺序及 owner 中心核对，单元几何使用有向体积计算，拒绝零体积和负体积。

```python
manifest = export_dataset(jobs_root, selected_ids, output_root)
assert manifest['schema'] == 'aeroblade-ai-dataset-v1'
assert all(row['source_time'] != '0' for row in manifest['accepted'])
```

- [ ] 增加失败任务、缺 T、非有限压力、运动压力单位、三维、错位场长度、跨目录路径、旧模板混入和读取前后源文件摘要不变测试。生成临时目录然后原子 rename；失败不得留下可加载的半份数据集。
- [ ] 只读导出当前任务，生成 accepted/rejected 和重复候选报告；保留旧 audit CLI 的输出字段与退出码，运行 `bridge/tests/test_result.py`。

**验收：** 能准确列出 10 个 Pritchard 二维任务的逐条原因，不能把 8 个完成记录标成 8 个独立有效样本。报告现有场是否能恢复全部边界标签；不能恢复时明确列出补导出字段。

## Task 2 — 可解析测试场与六项指标

**Files:** Create `ai/metrics.py`、`ai/tests/test_metrics.py`；Modify `ai/dataset.py`（targets 及版本）；在 `ai/tests/fixtures.py` 增加面数据夹具。

**Interfaces:**

```python
derive_thermo(mol_weight: float, cp: float) -> dict
total_pressure(p, temperature, velocity, thermo) -> array
compute_metrics(boundaries: dict, span_m: float, chord_m: float,
                conditions: dict, thermo: dict) -> dict
```

compute_metrics 返回 `values`（六字段）、`valid`、`reasons`、`diagnostics`。boundaries 每个 patch 提供 p/T/U/Sf；仅 diagnostics 可使用真实 phi 核对误差。

- [ ] 先用数值可解析的直通流验证总压损失为 0、角度为 0、展宽归一化正确。下面是测试夹具的完整简单形式（没有 blade 时两个压力力系数应为无效，不影响本例其他断言）。

```python
def straight_boundaries(span):
    import numpy as np
    return {name: {'p': np.array([100000.]), 'T': np.array([300.]),
                   'U': np.array([[20., 0., 0.]]),
                   'Sf': np.array([[sign * span, 0., 0.]])}
            for name, sign in [('inlet', -1.), ('outlet', 1.)]}

def test_uniform_straight_flow():
    from ai.metrics import compute_metrics
    thermo = {'Rgas': 287., 'Cp': 1004.5, 'gamma': 1.4}
    r = compute_metrics(straight_boundaries(.01), .01, 1.,
                        {'inletTotalPressure': 100300.,
                         'inletTotalTemperature': 300.,
                         'outletStaticPressure': 100000.}, thermo)
    assert abs(r['values']['loss_coefficient']) < 1e-12
    assert abs(r['values']['outlet_angle_deg']) < 1e-12
    assert abs(r['values']['mass_flow_per_span'] - 100000/287/300*20) < 1e-10
```

- [ ] 运行 `python -m pytest ai/tests/test_metrics.py -q`，在实现前确认缺失特征导致失败。
- [ ] 按设计第 6 节写向量化公式；正负法向显式固定，不使用 abs(phi) 掩盖回流。闭合矩形叶片上常压力产生零合力；单侧增压产生预期符号的力。增加非均匀流的质量加权和面积加权不相等测试。

```python
speed_squared = (velocity * velocity).sum(axis=-1)
mach_squared = speed_squared / (thermo['gamma'] * thermo['Rgas'] * temperature)
p0 = p * (1 + (thermo['gamma'] - 1) * mach_squared / 2) ** (
    thermo['gamma'] / (thermo['gamma'] - 1))
```

- [ ] 增加近零分母、负温度、179°/-179° 周期角误差、回流超阈值、二维厚度翻倍但单位展宽流量不变、真实 phi 改动不影响预测指标等测试。
- [ ] 对一个真实完整场使用独立 OpenFOAM 后处理输出核对 patch 流量/压力积分；未具备命令环境时输出可复跑命令及“未完成独立 CFD 核对”，不写通过。

**验收：** 人工解析测试通过；真实数据每个标签可追溯到测量 patch、时间和热物性版本。

## Task 3 — 几何分组、特征与参数基线

**Files:** Create `ai/features.py`、`ai/splits.py`、`ai/models/{__init__,tabular}.py`、`ai/tests/test_tabular.py`、`ai/requirements.txt`。

**Interfaces:**

```python
encode_parameters(parameters: dict, conditions: dict, thermo: dict) -> dict
geometry_group(parameters: dict, contour: array) -> str
make_split(rows: list[dict], seed: int = 42, mode: str = 'benchmark') -> dict
fit_tabular(kind: str, x_train, y_train, x_valid, y_valid, seed: int) -> dict
predict_tabular(bundle: dict, features: array) -> array
```

encode_parameters 返回 names、values；feature 顺序写入模型卡。fit_tabular 返回 estimator、x_scaler、y_scaler、config；只接受 ridge/extratrees/mlp。

- [ ] 写等价几何和反泄漏测试。父形状组不能跨集合；针对同一几何改变工况仍留在同一集合。

```python
def test_small_dataset_cannot_claim_benchmark():
    import pytest
    from ai.splits import make_split
    rows = [{'sample_id': str(i), 'geometry_group': str(i)} for i in range(3)]
    with pytest.raises(ValueError, match='15'):
        make_split(rows, mode='benchmark')
```

- [ ] 在独立虚拟环境安装依赖，验证 PyTorch/PyG 导入与设备，记录版本；运行 `python -m pytest ai/tests/test_tabular.py -q` 看到预期失败。
- [ ] 实现按组排序后确定种子置乱划分，冻结 ID；拟合只接受训练与验证参数，不允许 test 输入进入 fit 接口。smoke 使用显式小样本协议并写入 experimental。

```python
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.preprocessing import StandardScaler
y_scaler = StandardScaler().fit(y_train)
estimator = ExtraTreesRegressor(n_estimators=300, min_samples_leaf=2,
                               random_state=seed, n_jobs=1)
estimator.fit(x_train, y_scaler.transform(y_train))
predicted = y_scaler.inverse_transform(estimator.predict(x_valid))
```

- [ ] 按设计超参数网格增加 Ridge 与 MLP，测试恢复后预测一致、多输出 shape、恒定训练特征、非法值和目标单位逆变换。MLP 使用真实 PyTorch，不用 sklearn MLP 冒充所设计网络。
- [ ] 现有三组几何仅执行 smoke；输出每条预测、实际标签和实验标识，不报告正式三模型排名。

**验收：** 三种参数模型训练/恢复可用，预处理器保存完整，无测试集泄漏。

## Task 4 — 周期网格图和 PyG 稳态模型

**Files:** Create `ai/graph.py`、`ai/models/mpnn.py`、`ai/tests/test_graph.py`。

**Interfaces:**

```python
build_graph(sample: dict) -> torch_geometric.data.Data
# Data: x, pos, edge_index, edge_attr, volume, boundary_owner,
# boundary_features, boundary_area, global_features; y 只在训练时附加
MPNN(node_dim: int, edge_dim: int, global_dim: int, width: int = 64,
     depth: int = 6)
# forward(data) -> {'cells': Tensor[N,4], 'boundary': Tensor[Fb,4]}
```

- [ ] 先写两单元内部面双向边测试和两个周期面的位移修正测试；构造叶片两侧相近但不相邻单元，验证不出现穿实体边。

```python
def test_periodic_displacement_is_local(periodic_sample):
    from ai.graph import build_graph
    graph = build_graph(periodic_sample)
    periodic = graph.edge_attr[:, -1] == 1
    assert periodic.any()
    assert graph.edge_attr[periodic, :2].norm(dim=1).max() < .1
```

periodic_sample 由 `ai/tests/fixtures.py` 构造：域高为 1，单元中心 eta=.02/.98，周期平移为 1，配对局部距离为 .04；fixture 使用原始面连接和 patch 标识。

- [ ] 运行 `python -m pytest ai/tests/test_graph.py -q` 确认失败，再实现周期配对和图特征。
- [ ] 基于 PyG MessagePassing 实现 `message=MLP([h_i,h_j,e_ij,g])`，aggregate=sum，节点残差更新；边界解码拼接 owner 隐特征和面特征。体积权重按算例归一化。

```python
output = model(graph)
loss = ((output['cells'] - graph.y).square().mean(dim=-1)
        * graph.volume / graph.volume.sum()).sum()
loss.backward()
assert any(p.grad is not None and p.grad.abs().sum() > 0 for p in model.parameters())
```

- [ ] 测试节点重编号等变、两个图 batch 不混边、CPU 真前向/反传、未知几何分支拒绝、缺失周期配对失败。
- [ ] 在 1～2 个已接受真实样本上验证可降低训练损失，记录这是过拟合链路检查。推理输入删除全部 y、boundary_phi 和真实 fields 后仍可运行。

**验收：** 真正使用 PyG 图传播，无真值输入，具有四场和边界输出。

## Task 5 — 面积投影、FNO 与边界解码

**Files:** Create `ai/grid.py`、`ai/models/fno.py`、`ai/tests/test_fno.py`。

**Interfaces:**

```python
build_grid(parameters: dict, contour: array, shape: tuple = (128, 64)) -> dict
project_to_grid(sample: dict, grid: dict) -> dict
restore_cells(grid_fields, projection: dict) -> array
FNO2d(input_channels: int, width: int = 32, modes: int = 12, depth: int = 4)
# forward(channels, boundary_queries) -> {'grid': Tensor[B,4,H,W],
#                                      'boundary': Tensor[Fb,4]}
```

projection 保存 sparse overlap、cell_volume、fluid_coverage 和边界同侧查询映射。无法覆盖时返回 coverage_error，不补成零流场。

- [ ] 写固体隔断两侧值差异测试以及常值场的投影/回投守恒测试。人工矩形交叠可直接解析，避免用同一个投影实现计算 expected。

```python
def test_constant_field_survives_projection(two_cell_sample, matching_grid):
    import numpy as np
    from ai.grid import project_to_grid, restore_cells
    sample = dict(two_cell_sample)
    sample['fields'] = np.full((2, 4), 3.0)
    projection = project_to_grid(sample, matching_grid)
    restored = restore_cells(projection['fields'], projection)
    np.testing.assert_allclose(restored, sample['fields'], atol=1e-6)
```

two_cell_sample 为两个相邻单位方形，matching_grid 为覆盖同域的 4×2 格；两者在 `fixtures.py` 中使用字面坐标定义。

- [ ] 运行 `python -m pytest ai/tests/test_fno.py -q` 确认失败，实现多边形与网格矩形的裁剪交叠、周期 SDF 和坐标变换，不使用穿实体的散点插值。
- [ ] 实现双侧 Fourier 模态权重及点卷积分支，沿 xi padding/crop；eta 保持周期。输出正确 shape 并能反向传播到复数谱权重。

```python
spectrum = torch.fft.rfft2(features)
filtered = torch.zeros_like(spectrum)
filtered[:, :, :mx, :my] = torch.einsum(
    'bixy,ioxy->boxy', spectrum[:, :, :mx, :my], weight_positive)
filtered[:, :, -mx:, :my] = torch.einsum(
    'bixy,ioxy->boxy', spectrum[:, :, -mx:, :my], weight_negative)
spatial = torch.fft.irfft2(filtered, s=features.shape[-2:])
```

谱块输入/输出隐通道均 width，上式用于相同通道数；mx 必须限制在不重叠的正负频率带内。

- [ ] 写正弦场频率保留/抑制测试、两个分辨率输出 shape 测试、改变实体填充值不改变有效标签/损失测试、边界查询梯度测试。
- [ ] 输出现有场的 64×32、128×64、256×128 往返重建误差；在真实样本上执行 CPU/GPU smoke 并保存有限输出。若窄通道没有有效覆盖，失败并提示提高分辨率。

**验收：** 确有 Fourier 运算和可训练谱权重；几何输入不依赖 CFD 场；可查询边界和计算统一指标。

## Task 6 — 共享训练、评价、登记与 CLI

**Files:** Create `ai/{train,evaluate,registry,predict,cli}.py`、`ai/tests/test_lifecycle.py`。

**Interfaces:**

```python
train_run(dataset_dir: Path, run_dir: Path, config: dict) -> dict
evaluate_run(run_dir: Path, dataset_dir: Path, split_name: str) -> dict
register_model(run_dir: Path) -> dict
predict_model(model_dir: Path, request: dict, mesh: dict | None = None) -> dict
```

- [ ] 编写恢复推理一致性、模型摘要篡改、输入字段顺序错误、未训练模型和 dataset/split 不匹配测试。

```python
def test_scalar_prediction_has_no_fabricated_flow(trained_scalar, valid_request):
    from ai.predict import predict_model
    result = predict_model(trained_scalar, valid_request)
    assert result['schema'] == 'aeroblade-ai-prediction-v1'
    assert result['source'] == 'ai'
    assert result['field_ref'] is None
```

trained_scalar fixture 用 Task 3 的实现拟合 20 条确定性人工数据，明确 fixture 类型不允许进入真实数据集；valid_request 使用现有参考参数与合法工况。

- [ ] 运行 `python -m pytest ai/tests/test_lifecycle.py -q` 确认失败；实现设计第 7 节的训练/验证/早停，best checkpoint 仅由验证损失决定。

```python
if validation_loss < best_loss:
    best_loss = validation_loss
    torch.save({'state_dict': model.state_dict(), 'config': config}, checkpoint)
```

- [ ] 六指标逐条计算，流场使用体积/区域误差；无有效目标的 R² 输出 null 和原因。记录真实耗时、硬件和环境，GPU 计时使用 synchronize，smoke 报告不命名 benchmark。
- [ ] 完成以下 CLI 并记录 --help 与错误退出码。dataset_id/run_id 使用真实命令返回值，不在文档写虚构成功结果。

```bash
python -m ai.cli audit --jobs ./jobs --output ./ai-data/inventory.json
python -m ai.cli export --jobs ./jobs --output ./ai-data/datasets --quality workflow
python -m ai.cli train --dataset ./ai-data/datasets/$DATASET_ID --model extratrees --mode smoke
python -m ai.cli train --dataset ./ai-data/datasets/$DATASET_ID --model mpnn --mode smoke
python -m ai.cli train --dataset ./ai-data/datasets/$DATASET_ID --model fno --mode smoke
python -m ai.cli evaluate --run ./ai-data/runs/$RUN_ID
```

**验收：** 真实三路线产物可追溯，模型加载无需接触测试真值，无未声明的精度和加速数字。

## Task 7 — 异步桥接 API 与 mesh-only

**Files:** Create `bridge/ai_service.py`、`bridge/tests/test_ai_service.py`；Modify `bridge/server.py`、`bridge/core.py`、`bridge/tests/test_server.py`。

**Interfaces:**

```python
AIService(root: Path, python: Path | None, jobs_root: Path, templates_root: Path)
# capabilities(), datasets(), models(), submit(kind: str, request: dict),
# detail(kind: str, id: str), cancel(kind: str, id: str), shutdown()
```

- [ ] 先写无 ML 环境可启动原服务、未鉴权 401、路径注入 400/404、未知 ID 404、不可用环境 503 和队列满 429 测试。

```python
def test_missing_worker_is_explicit(tmp_path):
    from ai_service import AIService
    service = AIService(tmp_path/'ai', None, tmp_path/'jobs', tmp_path/'templates')
    assert service.capabilities()['ready'] is False
    assert service.capabilities()['reason'] == 'ml_environment_unavailable'
```

- [ ] 运行 `python -m unittest discover -s bridge/tests -p 'test_ai*.py' -v`；实现固定 argv `python -m ai.cli worker --request <服务端生成路径>`。客户端配置字段必须为设计 allowlist；不能传任意超参数字典再拼命令。
- [ ] 持久化 queued/running/completed/failed/cancelled/interrupted；原子写状态。训练单槽/等待上限 4，推理单槽；取消训练不得取消 CFD。

```python
request_path = (run_dir / 'request.json').resolve()
request_path.relative_to(service_root.resolve())
argv = [str(worker_python), '-m', 'ai.cli', 'worker', '--request', str(request_path)]
```

- [ ] core.py 中显式增加只执行网格的目标，仍使用冻结的受信任模板 pipeline，停止在 checkMesh 通过后，状态类型为 mesh 而非 completed CFD。mesh_id 绑定参数、模板、几何和网格摘要。测试 pipeline 没有启动求解器、也不携带真实场。
- [ ] 加入重启恢复、独立取消、timeout、无效 artifact、源目录符号链接、两个并发任务隔离测试；新路由不绕过既有鉴权和请求体上限。

**验收：** 所有路由符合设计表，CFD 回归通过；用户无需安装 ML 即可继续原平台操作。

## Task 8 — AI 工作区、发布与完整验收

**Files:** Create `web/{workspaces,ai}.js`、`web/ai.css`、`ai/README.md`、`scripts/check-ai.sh`（仓库根）；Modify `web/{app,cfd,flow-view}.js`、`web/workspace.css`、`bridge/server.py` 静态 allowlist、`bridge/package.py`、`scripts/check_package.py`、`README.md`。

**Interfaces:**

```javascript
// workspaces.js
export function createWorkspaces(tabsElement) // returns {register, activate}
// register({id, button, panel, onActivate}); activate(id)
// ai.js
export function initAI({getDesign, api, workspaces})
// flow-view.js: preserve existing initFlowView API; add independent
export function renderField(container, payload) // returns {clear, destroy}
```

共享连接对象留在页面内存，经闭包向 CFD 与 AI 注入 api 函数；禁止将令牌写入 DOM dataset/localStorage。旧 initCFD 调用保持兼容，工作区切换代码单独抽取后覆盖两旧页回归。

- [ ] 先写状态测试：参数改变使旧预测失效、迟到响应不覆盖新请求、断开清空展示、标量模型不显示云图、未匹配 CFD 禁止误差图。

```javascript
const submittedRevision = revision;
const result = await api('/ai/predictions/' + id);
if (submittedRevision !== revision) return;
statusElement.textContent = result.status;
```

以延迟 HTTP 响应测试该行为，不只断言上面代码字面存在。

- [ ] 实现六指标、模型/质量/适用范围、异步状态、预测/CFD/误差选择；未知和未训练状态真实显示。脚本新增必须加入静态 allowlist；动态文字统一 textContent。
- [ ] 修改发布包目录 allowlist 纳入 ai 源码与依赖说明，并允许 requirements.txt 后缀；不包含 ai-data、权重、虚拟环境、令牌和运行记录。标准包可无 ML 运行；check-ai.sh 专门验证已安装 ML 环境。
- [ ] 执行完整检查与浏览器检查（桌面、390 px、键盘切换、模型切换、取消、断线、恢复、迟到响应）；独立记录实际截图/控制台和检查结果。

```bash
bash scripts/check.sh
bash scripts/check-ai.sh
```

- [ ] 在 README 写清数据规模、smoke 与 benchmark 区别、首次安装、导出、训练、预测及模型目录；追加实际执行报告，逐项列完成/未完成及证据。

**验收：** 可见 UI 操作与后端真实结果一致；没有模型时保持可解释空状态，不展示随机或预置预测。

## 计划自审与交付规则

| 设计要求 | 承接任务 |
|---|---|
| 数据合同/质量/来源 | 1 |
| 热物性/六指标/边界权重 | 2 |
| 几何编码/分组/参数模型 | 3 |
| 周期图/矢量解码 | 4 |
| FNO/投影/全场与边界解码 | 5 |
| 训练/评价/模型卡/推理 | 6 |
| 异步执行/网格准备/API | 7 |
| 工作区/回归/发布 | 8 |

阶段验收记录必须区分：代码测试通过、真实数据链路通过、泛化评价完成、工程精度验证完成。三个几何组只能支持前两项的部分验证。数据不足时完整交付可运行工具和补样方案，不补造训练样本或模型成绩。

文档自审已完成；执行任务 checkbox 均保持未勾选。用户确认的是技术方案，当前文件提供可审阅的实现细节；实际代码开发以本计划为入口。
