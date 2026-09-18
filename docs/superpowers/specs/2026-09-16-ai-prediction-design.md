# AeroBlade 第一阶段 AI 气动预测详细设计

日期：2026-09-16。用户已确认技术范围：二维优先、低成本参数回归、PyTorch Geometric 消息传递网络、FNO 全流场基线及统一气动指标。本文是待实施设计，不代表模型已实现、训练或达到预测精度。

## 1. 目标与交付边界

在现有几何设计和 OpenFOAM 工作台上新增 AI 预测工作区，实现可复现的数据导出、训练、评价、模型登记和推理。三条路线回答不同问题：

| 基线 | 推理输入 | 预测输出 | 核心比较问题 |
|---|---|---|---|
| Ridge、ExtraTrees、小型 MLP | 几何参数、物理工况 | 六个标量气动指标 | 参数直接回归能达到什么效果与成本 |
| PyG MPNN | 同样的参数/工况及未求解的几何网格 | 单元中心 Ux、Uy、p、T；边界查询值；派生指标 | 网格拓扑和局部几何是否有帮助 |
| 二维 FNO | 参数生成的规则网格几何编码、工况 | 完整二维流体域 Ux、Uy、p、T；边界查询值；派生指标 | 算子路线的场重建效果、成本与分辨率敏感性 |

第一阶段限定 `pritchard-1985`、`pritchard-cascade-2d`、稳态冷态可压缩 RANS。全流场指整个二维流体计算域，不是叶片表面分布，也不是三维投影。旧几何、三维、非定常、转动功、整级效率、自动优化、GINO 和额外湍流输出不纳入本轮训练。它们保留为后续扩展方向。

## 2. 已核对的平台接入点

| 现有文件 | 现状与复用方式 |
|---|---|
| `openfoam-bridge/web/geometry.js`、`pritchard.js` | 浏览器和 Node 共用几何引擎；继续作为轮廓生成的唯一来源 |
| `openfoam-bridge/bridge/pritchard_model.py` | 参数范围检查、节距及斜置域计算；作为几何元数据来源 |
| `openfoam-bridge/bridge/core.py` | CFD 生命周期、请求快照、任务目录；扩展网格阶段复用，不把训练放入其工作线程 |
| `openfoam-bridge/bridge/flow.py` | ASCII 单层二维场展示；当前只向前端暴露速度大小，训练需另读矢量及边界场 |
| `openfoam-bridge/bridge/validate_result.py` | 现有收敛、质量守恒、网格质量审计；提取只读审计核心，保留原 CLI 写报告行为 |
| `openfoam-bridge/bridge/server.py` | Python 标准库 HTTP、鉴权、静态文件 allowlist；增加 AI 路由和公开静态文件 |
| `openfoam-bridge/web/cfd.js`、`flow-view.js` | 工作区和流场渲染接入；不能把 AI 数据伪装成 CFD 完成任务 |
| `scripts/check.sh`、`scripts/check_package.py` | 回归及发布包验证；增加 AI 无依赖测试与独立 ML 检查入口 |

当前 CFD 服务仍要求 Python 3.10+、Node.js 20+，不强制安装机器学习库。ML worker 使用独立 Python 3.10+ 虚拟环境，依赖 NumPy、SciPy、scikit-learn、PyTorch 和 PyTorch Geometric；安装验证后记录精确版本和 CPU/CUDA 构建信息。禁止先编造未经验证的版本锁。

## 3. 当前数据证据与质量分层

只读元数据盘点见 [数据盘点](../../../openfoam-bridge/docs/AI_DATA_INVENTORY.md)。本机 23 个任务中，Pritchard 二维有 10 个记录：8 个 completed、2 个 failed；8 个完成记录覆盖 3 组几何，5 个记录标为 `solver_reported`。三组几何只改变半径，其他十参数不变，收敛记录物理工况也相同。

现有数据用于解析、标签、形状匹配及小样本过拟合检查，不能据此发布跨十一参数和工况的泛化结论。任务数、独立几何数、独立几何×工况数必须分别报告。

数据记录分三种状态：

- `rejected`：维度/模型不匹配、缺场、非有限值、无效压力温度、网格失败、收敛未确认、守恒不达标、读写时间不匹配、标签定义不适用；保留拒绝原因，不填充假标签。
- `workflow`：完成、求解器明确收敛、所需残差均低于 1e-5、相对质量不平衡低于 0.001、网格门槛通过、周期/平面检查通过、场完整且有限；严格几何检查未知或有凹单元时显式记录。这一层仅学习当前数值流程。
- `engineering`：满足 workflow 并通过严格几何检查，且关联独立的网格收敛、近壁分辨率和适用工况验证记录。当前没有证据确认存在此层样本。

现有 `workflow_verified` 还包含 ZIP/VTK 是否生成，不能直接等价于 ML 样本资格。导出器分别检查物理质量和交付文件，不因缺少 ZIP 拒绝完整原始场，也不因有 ZIP 接纳不合格流场。缺审计文件时重新进行只读检查，不能默认通过。

## 4. 数据合同

### 4.1 样本及版本

新增 `openfoam-bridge/ai/`，数据与权重写入被忽略的 `openfoam-bridge/ai-data/`。

```text
ai-data/
  datasets/<dataset_id>/manifest.json
  datasets/<dataset_id>/samples/<sample_id>.npz
  datasets/<dataset_id>/split.json
  runs/<run_id>/config.json
  runs/<run_id>/status.json
  runs/<run_id>/history.jsonl
  runs/<run_id>/evaluation.json
  runs/<run_id>/model-card.json
  runs/<run_id>/weights.*
  predictions/<prediction_id>/result.json
  predictions/<prediction_id>/field.npz
```

`manifest.json` 使用 `schema=aeroblade-ai-dataset-v1`，顶层包含 accepted、rejected 两个数组和统计摘要。每条接受记录包含 sample_id、job_id、geometry_group、geometry_hash、condition_hash、mesh_hash、template_hash、field_hash、thermo_hash、source_time、质量层及相对文件路径；拒绝记录保留已知元数据和拒绝原因，不要求不存在的场哈希。condition_hash 只含物理工况，不含 iterations；重复检测同时核对模板/网格版本。dataset_id 来自排序后样本内容摘要和全部提取配置的 SHA-256，不依赖文件修改时间。

哈希包含实际冻结模板和生成几何，不能只用模板名称。只读取本任务 `case/` 的网格和快照，不从当前网页参数或最新模板反推历史样本。最新写入场必须与收敛记录对应；不同时间的 p/U/T 不得拼成一个样本。初始 `0/`、失败任务及中间迭代不构成稳态标签。

### 4.2 标准数值载荷

所有数值数组验证 shape、dtype、有限性和单位；NPZ 以 `allow_pickle=False` 加载。

| 数组/属性 | 形状或类型 | 含义 |
|---|---|---|
| `cell_ids` | int64[N] | 原始 OpenFOAM 单元编号 |
| `centers`、`volumes` | float64[N,2]、float64[N] | 米制中心和真实挤出体积 |
| `vertices`、`polygon_indices`、`polygon_offsets` | 可变长二维多边形 | 原网格几何；不规则长度用偏移数组存储 |
| `owner`、`neighbour` | int64[F]、int64[Fi] | 面关联；Fi 为内部面数量 |
| `face_centers`、`face_area_vectors` | float64[F,3] | 与 owner 外法向一致；量纲 m、m² |
| `patch_id`、`periodic_pair` | int64[F]、int64[F] | 面类型及周期配对，无配对取 -1 |
| `fields` | float32[N,4] | Ux、Uy、p、T；分别 m/s、m/s、Pa、K |
| `boundary_fields` | float32[Fb,4] | inlet/outlet/blade 的求解后实际值 |
| `boundary_phi` | float64[Fb] | 真实质量通量，仅作标签审计与参考，不能作为预测输入 |
| `parameters`、`conditions`、`thermo` | manifest 中的 JSON 对象 | 原输入、物理边界条件、物性及来源 |
| `targets`、`target_valid` | float64[6]、bool[6] | 气动标签及有效标志；严格多输出训练要求六项均有效 |

二维厚度从 `spanLow/spanHigh` 实际网格获得，不取 UI `height`。动量速度保留原始三分量用于审计；模型仅学习二维 Ux/Uy，要求 Uz 满足二维阈值。

仅支持当前 ASCII、单层 XY、常比热理想气体模板。边界解析区分显式 `value`、zeroGradient、noSlip、fixedValue 等受支持情况；缺少可恢复的求解后值时拒绝该标签并列出需要补导出的 patch/field，禁止把字典里的 `p0` 直接当作静压。

## 5. 几何与工况编码

### 5.1 参数基线

保存原十一参数并固定特征顺序。主特征使用 Cx（保留绝对尺度）、Ct/Cx、s/Cx、O/s、RLE/Cx、RTE/Cx、四个输入角度的 sin/cos；`s=2πR/N`。另附一组 raw11 回归作为特征编码对照，均由训练集拟合标准化器。

工况输入为入口总压、入口总温、出口静压及模板物性；派生 `Δp=p0_in-p_out`、压力比、参考速度、参考密度、参考 Reynolds 数。迭代上限、运行时长、收敛步数、CFD 出口速度、真实流量和真实 Mach 数不作为输入。入口几何角不当作真实来流角；当前边界没有可调入口流角，未来新增工况需另建数据版本。

参考量：`p_ref=p_out`，`T_ref=T0_in`，`rho_ref=p_ref/(Rgas*T_ref)`，`U_ref=sqrt(2*Δp/rho_ref)`；这里 U_ref 只作归一化尺度，不代替可压缩总压计算。要求 Δp>0。输出场使用 U/U_ref、(p-p_ref)/Δp、(T-T_ref)/T_ref，再由训练集统计量缩放，保存逆变换。

几何分组以实际尺度下轮廓及节距为基础，忽略 height 和二维等价的 R/N 表示差异。对归一化形状相同但尺度不同的样本再建立父形状组，主测试按父形状组隔离。浮点量化精度固定为无量纲 1e-8，并保存几何引擎版本。数据盘点中的三组仅是参数等价组计数，实施后必须补充轮廓哈希检查。

### 5.2 图网络

采用单元中心图：节点特征为归一化坐标、体积、到周期叶片的距离、边界邻接类别及全局参数/工况编码。内部面构建双向边；每条边包含物理相对位移/Cx、距离/Cx、面面积/Cx²、方向法向和边类型。

周期面按模板平移向量配对，要求中心和面积匹配；边位移使用平移后的局部距离，不使用跨整个计算域的直线距离。配对容差为 `max(1e-10 m, 1e-6*Cx)`；不满足则拒绝，不能按最近点强行连接。

不使用跨叶片 kNN 边。边界面通过其 owner、面相对位置和类型进入边界解码器；与单元共享传播后的隐向量，同时解码 p/U/T。该分支受真实边界标签监督，使质量流量和压力载荷可从预测边界计算。

MPNN 初值：隐层宽度 64，6 个残差消息传递块，SiLU，LayerNorm；整图 batch=1，AdamW，lr=1e-3，最多 200 epochs，验证集早停耐心 20。基线是稳态条件映射，不要求推理输入初始/真实流场。

### 5.3 FNO 与流场解码

当前模板具有斜置周期域。使用确定性坐标变换：

`xi=(x/Cx+2)/5`，`eta=(y+(Ct/Cx)*x)/s+1/2`。

于是入口/出口为 xi=0/1，周期边界为 eta=0/1。物理坐标和变换 Jacobian 均保留；体积损失和积分不能直接把变换坐标当物理坐标。

默认规则网格 128×64，输入含 xi、eta、x/Cx、y/Cx、周期 signed distance/Cx、流体覆盖率以及广播的几何/工况特征。SDF 由同一几何引擎生成的轮廓及相邻周期副本计算，流体为正、实体为负。

FNO 初值：4 层 spectral+pointwise 块，宽度 32，每方向 12 个低频模态，GELU；rFFT 保留复数权重并正确处理两个轴的频率。eta 为周期维；xi 扩展 padding=8，输出裁剪，不能把物理入口与出口误设为周期相邻。低分辨率输入时模态上限不得超过可用频谱。

训练标签从真实 CFD 单元多边形与规则像素的交叠面积进行投影：在 xi/eta 坐标中裁剪矩形像素，再用 Jacobian 换算物理面积，每个像素对实际流体覆盖区域加权，实体区域不填流场标签。有效覆盖率作为独立通道及损失权重。禁止散点三角剖分穿过实体后生成看似连续的标签。

回到原网格时使用保存的交叠权重从有效像素加权重建；需要查询的边界点由其同侧流体像素和几何局部编码解码，边界解码器另受 boundary_fields 监督。不能把预测场回投成零覆盖原单元的默认值。任何未覆盖单元/边界直接报告 coverage_error。

先在真实场上计算“原网格→规则网格→原网格”误差和边界查询误差，再训练模型。这是当前离散方案的重建参照，不等同于不可突破的理论下界。另报告 64×32、256×128 分辨率误差及计算成本，不因采用 FNO 就宣称分辨率无关。

FNO 推理仅需要参数生成几何；可直接显示规则网格预测。回到指定原网格评价时使用该网格的几何信息，不使用其真值。PyG 推理需要网格，因此新设计还需独立的 mesh-only 阶段；基线成本表分列几何/网格准备、前向推理和后处理。

## 6. 统一气动标签定义 v1

测量位置固定为冻结算例的 `inlet`、`outlet` patch，壁面使用 `blade` patch，坐标 x 轴向、y 周向；第一版不引入人工选择的内部测量截面。模型适用范围绑定测量位置版本。

由模板 molWeight 求 `Rgas=Ru/molWeight`（Ru 采用与 OpenFOAM 一致的 J/(kmol·K) 单位），由 Cp 求 `gamma=Cp/(Cp-Rgas)`。记录总压边界中 gamma 与此值的差异，不把固定边界字典 gamma 无说明地覆盖热物性派生值。模板外的热物性直接拒绝。

对每个测量面：`rho=p/(Rgas*T)`、`a²=gamma*Rgas*T`、`M²=|U|²/a²`，

`p0=p*(1+(gamma-1)*M²/2)^(gamma/(gamma-1))`。

实际 CFD 的边界 phi 用于检查单位为 kg/s 并核对 `rho*U·Sf` 重构误差。标签和预测都以同一套 p/U/T 重构质量通量作为指标权重；两者与 solver phi 的差异另记审计，不能拿真实 phi 给预测结果加权。

令面外法向为 Sf，入口主流权重 `w_in=-rho*U·Sf`，出口 `w_out=rho*U·Sf`。主流无回流时 `bar(q)=sum(w*q)/sum(w)`。反向流量/正向流量超过 0.001 时该样本的主指标无效；更小的反向量忽略于加权并明确记录。质量守恒使用所有面的有符号通量，不裁剪回流。

| 顺序与字段 | 定义 | 单位 |
|---|---|---|
| 0 `loss_coefficient` | `(bar(p0)_in-bar(p0)_out)/(bar(p0)_in-bar(p)_out)` | — |
| 1 `outlet_angle_deg` | `atan2(bar(Uy)_out,bar(Ux)_out)*180/pi` | deg |
| 2 `turning_angle_deg` | 出口流角减入口流角，wrap 到 [-180,180) | deg |
| 3 `mass_flow_per_span` | 出口有符号质量流量除实际网格厚度 h | kg/(s·m) |
| 4 `pressure_force_x_coefficient` | `sum_blade((p-p_ref)*Sf_x)/(h*Cx*Δp)` | — |
| 5 `pressure_force_y_coefficient` | `sum_blade((p-p_ref)*Sf_y)/(h*Cx*Δp)` | — |

blade 的 Sf 为流体域外法向，指向叶片内部，故该积分表达流体对叶片的压力作用。力系数只包含压力，不冒充包含壁面剪切的总阻力或效率。存储的积分包含所有 blade 面，检查轮廓闭合、面积法向和近零，以免参考压力引入虚假载荷。

损失分母小于 `max(1e-8*p_ref,1e-6 Pa)`、近零主流速度、非正 p/T、缺边界数据时返回结构化无效原因；不静默截断、补零或产生 NaN。损失为负时保留数值并触发质量标记，不把结果夹到零。角度误差使用周期最小角差。

## 7. 训练、数据划分与评价

### 7.1 训练协议

主比较统一使用六标签均有效且两种场表示可导出的公共样本集；参数模型可额外在更大的标量集合训练，但必须单列结果。固定几何组划分 70/15/15，seed=42，split.json 显式保存 sample_id 和 geometry_group。所有归一化器、PCA（若以后添加）和超参数选择只使用训练/验证集合。

少于 15 个独立几何组时只允许 `mode=smoke` 或显式小样本留组验证，model-card 标为 `experimental`，不发布标准测试排名。15 组只是避免极小划分的软件门槛，不代表数据充分；目标补样先达到 60 组几何×3 个工况，之后按学习曲线扩展。

表格基线：Ridge alpha∈{0.1,1,10}；ExtraTrees n_estimators=300、min_samples_leaf∈{1,2,4}、random_state=seed；MLP 隐层 [64,64]、SiLU、AdamW，与深度模型共享最多 200 epochs/早停 20 的预算。多输出目标按训练集尺度标准化；ExtraTrees 也要目标缩放，避免多输出分裂偏向大数值目标。

图网络与 FNO 主损失为等通道归一化误差：`L=L_cell+0.1*L_boundary`，单元损失按体积、边界损失按面面积加权，并对每个算例先独立归一化，防止大网格支配训练。第一轮不加 PDE 残差损失；守恒作为独立评估项。共同训练参数 seed∈{42,43,44}；smoke 模式可用 1 seed、少量 epochs，并在所有导出结果注明。

### 7.2 评价内容

- 六项指标：MAE、RMSE、有效样本数，角度采用周期误差；R² 仅对非恒定且样本足够的目标报告。近零损失不使用 MAPE。
- 场：逐通道物理单位 RMSE、参考尺度归一化 RMSE、体积加权误差；不以约 1e5 Pa 的绝对静压作为唯一归一化尺度掩盖压差误差。
- 区域：全部流体、距 blade 小于 0.02 Cx 的近壁区、尾缘下游 0～1 Cx 范围的尾迹评价区；记录每区实际体积，空区域显示不适用。
- 派生一致性：压力载荷、损失、转角、质量流量和相对质量不平衡；边界真值和预测值使用相同提取算法。
- 资源：训练墙钟、峰值内存/显存、参数量、模型大小；推理分别给出含预处理总时间与纯前向时间。GPU 计时同步并预热，记录硬件、线程和软件版本。
- 拒绝与失败率：无效几何、网格失败、数据拒绝和推理失败独立列出，不只报告成功案例。

不预设模型必然胜出。若复杂模型不优于 ExtraTrees，仍保留真实结果和代价；完成基线开发以流程正确、可复现和评价完整为准，精度结论以冻结测试集为准。

## 8. 模型登记与推理合同

`model-card.json` 包含模型种类、输入字段顺序、输出字段/单位、数据集及 split 摘要、训练配置、权重摘要、代码版本、环境版本、质量层、工况/几何范围、测试结果和实验状态。没有训练产物的模型显示“未训练”；无机器学习依赖显示“未安装训练环境”。

推理使用新参数和新工况快照。逐字段范围检查只能作为显式超范围检测，不能证明联合分布内可靠；新增最近训练样本距离作为参考，不输出未经校准的置信概率。域外结果需显示实验性警告与距离，不默默套用已验证精度。

预测结果使用 `schema=aeroblade-ai-prediction-v1`、独立 prediction_id、model_id、参数/工况快照、指标、warnings、source=ai、field_ref。CFD result 保持 source=OpenFOAM。前端修改参数后立即使旧预测失效；跨任务请求使用代次标识丢弃过期响应。CFD 对比必须同时匹配几何、工况、物性、模板及测量定义，不能只匹配任务名称。

## 9. 服务与工作区

### 9.1 进程与资源

桥接服务只负责鉴权、验证 JSON、持久状态、启动固定 worker 命令和返回产物。机器学习库仅在 worker 中导入。后台训练默认单槽、最多排队 4 个，不占用 CFD 求解槽；单训练默认超时 2 小时，可通过管理员配置修改。推理默认单槽并有限队列。停止训练终止其进程组；服务重启将运行状态恢复为 interrupted。

服务端配置 ML Python 路径和 ai-data 根目录；网页不能提交解释器路径、任意命令、任意磁盘文件或上传 pickle。模型来自本机管理员管理目录，检查路径 containment、符号链接和摘要后才在 worker 加载。PyTorch 优先 state_dict / weights_only；scikit-learn 权重仅加载本机可信训练产物。

### 9.2 API

全部沿用现有 Bearer/Origin 检查，错误以结构化 JSON 返回。

| 路由 | 请求与行为 |
|---|---|
| GET `/api/ai/capabilities` | 环境、设备、允许模型、数据/训练状态 |
| GET `/api/ai/datasets` | 数据版本及数量/拒绝原因摘要 |
| POST `/api/ai/datasets` | `{job_ids:[32位ID],quality_tier:"workflow"}`，异步导出；不接受路径 |
| GET `/api/ai/models` | 已登记模型卡片，明确 experimental/未评价状态 |
| POST `/api/ai/runs` | `{dataset_id,model_kind,mode,seed}`，服务端绑定允许配置，202 返回 run_id |
| GET `/api/ai/runs/{id}` | 状态、进度、损失历史尾部、资源及日志 |
| POST `/api/ai/runs/{id}/cancel` | 取消独立训练任务 |
| POST `/api/ai/predictions` | `{model_id,parameters,conditions,mesh_id?}`，202 返回 prediction_id |
| GET `/api/ai/predictions/{id}` | 状态、指标、警告与绑定快照 |
| GET `/api/ai/predictions/{id}/flow` | 真实预测的网格与场，保持 AI 来源标识 |
| POST `/api/ai/meshes` | `{parameters,conditions}`，只运行冻结模板的网格步骤，202 返回 mesh_id |
| GET `/api/ai/meshes/{id}` | 网格准备状态和摘要，不含场真值 |

导出、网格准备、训练、推理均异步且持久化。单次 job_ids 最多 100；模型/数据/运行 ID 为服务端生成的十六进制 ID，拒绝路径片段。沿用 200 KB 请求上限。未知模型/ID 404，输入或字段非法 400，任务状态冲突 409，队列满 429，环境不可用 503。

### 9.3 前端

新增与“叶片设计 / CFD 仿真”并列的“AI 预测”。包含数据集质量摘要、模型及适用范围、工况表单、预测操作、六项指标、场选择、误差对比以及可折叠训练任务列表。用户先编辑叶片设计再进入 AI 预测；默认复制当前参数，但提交后冻结快照。

云图提供速度大小、压力、温度及可选速度分量；预测/CFD/误差三种模式，只有严格匹配真值时启用后两种。FNO 默认显示实际预测网格；PyG 显示其未求解网格上的预测。标量模型显示“此模型仅预测性能指标”，不绘制生成的假流场。

移动端纵向排列，桌面保留可滚动配置栏。全程通过 textContent 展示模型名称和日志，禁止将模型元数据插入未转义 HTML。

## 10. 增量实施与验收

先实施数据合同/标签，再参数模型，再 PyG/FNO，最后服务/工作区。每一步独立测试，具体任务见 [实施计划](../plans/2026-09-16-ai-prediction.md)。

| 阶段 | 可验收交付 |
|---|---|
| A 数据与指标 | 只读导出、拒绝清单、唯一几何统计、六指标、真实样本数值交叉核对 |
| B 参数基线 | Ridge/ExtraTrees/MLP 可训练/保存/加载/推理，同一 split，无泄漏 |
| C 场模型 | 正确周期图、真实 PyG 前向/反传、真实 FFT 算子、投影误差报告、边界解码 |
| D 集成 | 可见环境和模型状态、异步训练/推理/取消、快照绑定、准确来源显示 |
| E 比较报告 | 统一测试集、误差/成本/失败率、权重与环境摘要；数据不足则明确 smoke 状态 |

关键数值测试使用人工可解析场验证积分；流程样本和人工场均不计入真实 CFD 数据集。真实算例检查不能以模拟求解器测试代替。

补样建议分两批：第一批 12 组几何×3 工况用于确认数据管线；第二批达到 60 组几何×3 工况用于初始学习曲线。使用固定种子 Sobol 候选点，围绕参考几何局部变化，按几何引擎组合约束筛选并记录拒绝率。半径/叶片数通过节距去冗余；保留至少 10 组完全未见几何作为冻结评估集。未收敛任务的补算和网格改进应独立记录版本，不把迭代次数当样本量。本文不自动发起新 CFD 计算或占用外部 GPU。

## 11. 资料

- [PyG 消息传递接口](https://pytorch-geometric.readthedocs.io/en/latest/notes/create_gnn.html?highlight=gcn)
- [FNO 原始论文](https://arxiv.org/abs/2010.08895)
- [GINO 原始论文，后续候选](https://arxiv.org/abs/2309.00583)
- [现有参数约定](../../../openfoam-bridge/docs/PRITCHARD.md)
- [现有场展示约定](../../../openfoam-bridge/docs/FLOW_VIEW.md)

自审：已覆盖几何/工况、数据质量、反泄漏、周期图、算子和边界解码、指标公式、进程/API/UI、成本、失败处理与验收；未为现有数据虚构精度或训练结果。
