/* AI workspace shell. All model, data and compute actions are intentionally inactive. */
const icons = {
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/>',
  nodes: '<circle cx="5" cy="6" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="12" cy="18" r="2"/><path d="M7 6h10M6 8l5 8M18 8l-5 8"/>',
  wave: '<path d="M2 12c4-12 6-12 10 0s6 12 10 0M2 18h20"/>',
  data: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
  chart: '<path d="M4 3v17h17M8 14l4-5 4 3 5-7"/>',
  field: '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M9 3v18M15 3v18M3 9h18M3 15h18"/>',
  arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]}</svg>`;
const routes = {
  parameters: {
    name: '参数直接预测', subtitle: '低成本标量基线', icon: 'layers', engine: 'ExtraTrees · Ridge · MLP',
    stages: [['几何编码', '11 参数与无量纲特征'], ['输入表示', '参数向量 + 物理工况'], ['回归模型', 'ExtraTrees / Ridge / MLP'], ['指标输出', '六项气动性能指标']],
    hint: '参数与工况直接映射到气动指标，用于建立低成本精度参照。',
    output: '六项气动性能指标',
  },
  graph: {
    name: '图网络预测', subtitle: '非结构网格基线', icon: 'nodes', engine: 'PyTorch Geometric · MPNN',
    stages: [['几何编码', '单元位置与边界特征'], ['图构建', '网格邻接 + 周期配对'], ['消息传递', 'PyG · MPNN'], ['流场解码', '单元 / 边界场 → 指标']],
    hint: '以真实网格拓扑组织几何信息，预测流场，再提取气动指标。',
    output: '全流场 + 气动性能指标',
  },
  operator: {
    name: '神经算子预测', subtitle: '全流场算子基线', icon: 'wave', engine: 'Fourier Neural Operator · FNO',
    stages: [['几何编码', '距离场与流体掩码'], ['规则网格', '几何映射 + 工况通道'], ['神经算子', '二维 FNO'], ['流场解码', '全域 / 边界场 → 指标']],
    hint: '在规则网格上学习几何与工况到完整二维流场的映射。',
    output: '全流场 + 气动性能指标',
  },
};
const metrics = [
  ['总压损失系数', 'Yₚ', '无量纲'],
  ['出口流角', 'β₂', 'deg'],
  ['流动转折角', 'Δβ', 'deg'],
  ['单位展宽质量流量', 'ṁ / h', 'kg/(s·m)'],
  ['轴向压力载荷系数', 'Cₚ,x', '无量纲'],
  ['周向压力载荷系数', 'Cₚ,y', '无量纲'],
];

export function initAIWorkspace() {
  const host = document.createElement('section');
  host.id = 'ai-panel';
  host.hidden = true;
  host.setAttribute('aria-label', 'AI 气动预测工作区');
  host.innerHTML = `
    <div class="ai-heading">
      <div><div class="ai-title-line"><h2>AI 气动预测</h2><span class="ai-preview-badge">界面预览</span></div><p>从几何参数到气动指标，建立三条可比较的预测基线。</p></div>
      <div class="ai-heading-actions"><span class="ai-scope">二维 Pritchard 叶栅</span><button disabled>导入模型</button></div>
    </div>
    <div class="ai-layout">
      <aside class="ai-config" aria-label="数据与模型配置">
        <div class="ai-config-scroll">
          <section class="ai-card ai-input-card">
            <div class="ai-card-heading"><h3>${icon('data')}数据与输入</h3><span class="ai-state">待接入</span></div>
            <label for="ai-dataset">训练数据集</label><select id="ai-dataset" disabled><option>尚未接入数据集</option></select>
            <div class="ai-input-summary"><span>有效样本 <b>—</b></span><span>独立几何 <b>—</b></span></div>
            <div class="ai-input-source"><span>几何来源</span><strong>叶片设计工作区</strong></div>
            <div class="ai-tags"><span>11 参数</span><span>物理工况</span><span>CFD 标签</span></div>
            <details class="ai-details"><summary>数据准备与质量检查</summary><p>预留几何去重、收敛筛选、场数据检查与训练 / 验证 / 测试集划分。</p><button disabled>管理数据集</button></details>
          </section>
          <section class="ai-card ai-model-card">
            <div class="ai-card-heading"><h3>${icon('layers')}模型路线</h3><span class="ai-count">03</span></div>
            <div class="ai-model-options" role="group" aria-label="选择模型路线">
              ${Object.entries(routes).map(([key, route]) => `<button class="ai-model-option" data-ai-route="${key}" aria-pressed="${key === 'parameters'}"><span class="ai-model-icon">${icon(route.icon)}</span><span><strong>${route.name}</strong><small>${route.subtitle}</small></span><span class="ai-radio" aria-hidden="true"></span></button>`).join('')}
            </div>
            <label for="ai-checkpoint">模型版本</label><select id="ai-checkpoint" disabled><option>尚无已训练模型</option></select>
          </section>
          <section class="ai-card ai-condition-card">
            <div class="ai-card-heading"><h3>预测工况</h3><span class="ai-state">待接入</span></div>
            <div class="ai-condition-row"><label for="ai-inlet-pressure">入口总压</label><div><input id="ai-inlet-pressure" placeholder="—" disabled><span>Pa</span></div></div>
            <div class="ai-condition-row"><label for="ai-inlet-temperature">入口总温</label><div><input id="ai-inlet-temperature" placeholder="—" disabled><span>K</span></div></div>
            <div class="ai-condition-row"><label for="ai-outlet-pressure">出口静压</label><div><input id="ai-outlet-pressure" placeholder="—" disabled><span>Pa</span></div></div>
          </section>
        </div>
        <div class="ai-config-actions"><button class="primary" disabled>${icon('arrow')}开始预测</button><p>数据、训练与推理功能待接入</p></div>
      </aside>
      <div class="ai-main">
        <section class="ai-card ai-pipeline-card" aria-label="预测流程">
          <div class="ai-card-heading"><h3>建模流程</h3><span class="ai-route-label" id="ai-route-label"></span></div>
          <ol class="ai-pipeline" id="ai-pipeline"></ol><p class="ai-route-hint" id="ai-route-hint"></p>
        </section>
        <section class="ai-card ai-results-card">
          <div class="ai-card-heading"><h3>${icon('field')}流场与结果预览</h3><span class="ai-state">等待预测</span></div>
          <div class="ai-result-toolbar"><div class="ai-result-tabs" role="group" aria-label="结果展示模式"><button data-ai-view="field" aria-pressed="true">预测流场</button><button data-ai-view="reference" aria-pressed="false">CFD 对照</button><button data-ai-view="error" aria-pressed="false">误差分布</button></div><label class="ai-field-label" for="ai-field">物理量<select id="ai-field" disabled><option>速度大小</option><option>静压</option><option>温度</option></select></label></div>
          <div class="ai-field-placeholder"><div class="ai-domain-mark" aria-hidden="true">${icon('field')}</div><strong id="ai-field-title"></strong><p id="ai-field-description"></p><span class="ai-empty-tag">预览区域 · 暂无场数据</span></div>
          <div class="ai-field-footer"><span id="ai-output-type"></span><span>结果来源 <b>—</b></span></div>
        </section>
        <section class="ai-card ai-comparison-card">
          <div class="ai-card-heading"><h3>基线对比</h3><span class="ai-table-caption">统一数据划分 · 同一指标口径</span></div>
          <div class="ai-table-scroll"><table><caption class="ai-sr-only">三条预测基线的评价结果，尚未接入评价数据</caption><thead><tr><th scope="col">模型路线</th><th scope="col">指标误差</th><th scope="col">流场误差</th><th scope="col">推理耗时</th><th scope="col">状态</th></tr></thead><tbody><tr><th scope="row">参数直接预测</th><td>—</td><td>不适用</td><td>—</td><td><span class="ai-state">未评估</span></td></tr><tr><th scope="row">PyG 图网络</th><td>—</td><td>—</td><td>—</td><td><span class="ai-state">未评估</span></td></tr><tr><th scope="row">FNO 神经算子</th><td>—</td><td>—</td><td>—</td><td><span class="ai-state">未评估</span></td></tr></tbody></table></div>
        </section>
      </div>
      <aside class="ai-insights" aria-label="气动指标与训练状态">
        <section class="ai-card ai-metrics-card">
          <div class="ai-card-heading"><h3>${icon('chart')}AI 气动性能指标</h3><span class="ai-count">06</span></div>
          <div class="ai-metric-grid">${metrics.map(([label, symbol, unit]) => `<div class="ai-metric"><span>${label}</span><div><strong aria-label="暂无预测值">—</strong><small>${symbol}</small></div><em>${unit}</em></div>`).join('')}</div>
          <p class="ai-metrics-note">接入模型后展示预测值与 CFD 对比结果。</p>
        </section>
        <section class="ai-card ai-training-card">
          <div class="ai-card-heading"><h3>训练与验证</h3><span class="ai-state">未开始</span></div>
          <div class="ai-training-empty">${icon('chart')}<strong>尚无训练记录</strong><p>训练损失、验证误差与运行日志将在此展示。</p></div>
          <details class="ai-details"><summary>训练配置</summary><div class="ai-training-fields"><label for="ai-epochs">训练轮数</label><input id="ai-epochs" placeholder="待配置" disabled><label for="ai-device">计算设备</label><select id="ai-device" disabled><option>待接入训练环境</option></select></div></details>
          <div class="ai-training-actions"><button disabled>新建训练</button><button disabled>查看日志</button></div>
        </section>
      </aside>
    </div>`;
  document.querySelector('footer').before(host);
  let selectedRoute = 'parameters', selectedView = 'field';
  const find = selector => host.querySelector(selector);
  function renderEmptyState() {
    let title, description;
    if (selectedView === 'reference') {
      title = '尚未关联 CFD 参考结果';
      description = '此区域预留与预测几何、工况一致的 CFD 流场对照。';
    } else if (selectedView === 'error') {
      title = '尚无可比较的预测结果';
      description = '完成预测并关联参考结果后，在此查看流场误差分布。';
    } else if (selectedRoute === 'parameters') {
      title = '当前路线直接预测气动指标';
      description = '标量结果预留在右侧。选择图网络或神经算子，可查看全流场模块布局。';
    } else {
      title = '全流场预测将在此展示';
      description = '预留速度、压力、温度云图与网格查看；当前尚未接入模型推理。';
    }
    find('#ai-field-title').textContent = title;
    find('#ai-field-description').textContent = description;
  }
  function selectRoute(key) {
    selectedRoute = key;
    const route = routes[key];
    host.querySelectorAll('[data-ai-route]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.aiRoute === key)));
    find('#ai-route-label').textContent = route.engine;
    find('#ai-route-hint').textContent = route.hint;
    find('#ai-output-type').textContent = route.output;
    const pipeline = find('#ai-pipeline');
    pipeline.replaceChildren(...route.stages.map(([name, detail], index) => {
      const item = document.createElement('li');
      const number = document.createElement('span');number.className = 'ai-step-number';number.textContent = String(index + 1).padStart(2, '0');
      const label = document.createElement('strong');label.textContent = name;
      const text = document.createElement('small');text.textContent = detail;
      item.append(number, label, text);return item;
    }));
    renderEmptyState();
  }
  host.querySelectorAll('[data-ai-route]').forEach(button => { button.onclick = () => selectRoute(button.dataset.aiRoute); });
  host.querySelectorAll('[data-ai-view]').forEach(button => { button.onclick = () => {
    selectedView = button.dataset.aiView;
    host.querySelectorAll('[data-ai-view]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    renderEmptyState();
  }; });
  selectRoute(selectedRoute);
  return host;
}
