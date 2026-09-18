import {reference, specs} from './pritchard.js';
import {validate, analyze} from './geometry.js';

export const PARAMETER_FIELDS = specs.flatMap(group => group[2]);
export const ASSISTANT_ENDPOINT = '/api/design-assistant/chat';
const string = (value, label, limit = 12000) => {
  if (typeof value !== 'string' || !value.trim() || value.length > limit) throw Error(`${label}格式错误`);
  return value;
};
const strings = (value, label) => {
  if (!Array.isArray(value) || value.length > 40) throw Error(`${label}格式错误`);
  return value.map(item => string(item, label, 2000));
};

export function validateProposal(raw) {
  if (raw?.schema !== 'aeroblade-initial-proposal-v1') throw Error('初设方案协议不匹配');
  if (raw.units?.length !== 'mm' || raw.units?.angle !== 'deg') throw Error('方案单位必须为 mm / deg');
  if (raw.parameters?.model !== 'pritchard-1985') throw Error('方案必须使用 Pritchard 1985 模型');
  const parameters = validate(raw.parameters);
  analyze(parameters); // Field ranges alone do not guarantee a feasible profile.
  const sources = Object.fromEntries(PARAMETER_FIELDS.map(([key]) => [key, string(raw.sources?.[key], `${key} 参数来源`, 2000)]));
  const assumptions = strings(raw.assumptions, '假设'), missing = strings(raw.missing, '待补条件'), warnings = strings(raw.warnings, '待验证项');
  if (missing.length) throw Error('方案仍有待补条件，请通过对话补充后重新生成');
  if (!Array.isArray(raw.aerodynamic) || raw.aerodynamic.length > 30) throw Error('气动参数格式错误');
  const aerodynamic = raw.aerodynamic.map(item => {
    if (typeof item?.value !== 'number' || !Number.isFinite(item.value)) throw Error('气动参数必须为有限数值');
    return {label:string(item.label,'气动参数名称',120), value:item.value,
      unit:typeof item.unit === 'string' && item.unit.length <= 40 ? item.unit : string(null,'气动单位'),
      source:string(item.source,'气动参数来源',2000)};
  });
  return {schema:raw.schema, units:{length:'mm',angle:'deg'}, parameters, sources, aerodynamic, assumptions, missing, warnings};
}

export function validateReply(raw) {
  if (raw?.schema && raw.schema !== 'aeroblade-assistant-reply-v1') throw Error('助手响应协议不匹配');
  return {message:string(raw?.message,'助手回复'), proposal:raw.proposal == null ? null : validateProposal(raw.proposal)};
}

export function demoReply(message) {
  if (message !== '载入参考方案') return {
    message:'已记录这条设计要求。当前是参考演示，不会根据自由文本执行大模型推理或平均线求解。\n\n实际初设需要明确：流量与功率目标、转速、入口总温/总压、出口压力或压比、工质，以及转/静子和流路尺寸约束。接入模型后，总师智能体将在这里追问并整理这些信息。\n\n你可以继续补充要求，切换到已配置的模型服务，或点击“载入参考方案”体验参数确认与设计交接。', proposal:null,
  };
  return {message:'已载入 Pritchard 图19参考截面，用于演示参数审阅与设计交接。它不是根据当前需求推导的初设，也未计算气动性能。长度采用项目统一的毫米尺度。', proposal:{
    schema:'aeroblade-initial-proposal-v1', units:{length:'mm',angle:'deg'}, parameters:{...reference},
    sources:Object.fromEntries(PARAMETER_FIELDS.map(([key]) => [key,key === 'throat' ? '参考规则：O = (2πR/N) cos(βout) − 2RTE' : 'Pritchard 1985 图19 · 项目参考预设'])),
    aerodynamic:[], assumptions:['示例长度单位按 25.4 mm 换算，不代表真实发动机尺寸。','角度为轴向有符号几何角；出口采用负角分支，进口楔角为半角。','60 mm 展宽仅用于等截面直线拉伸展示，不属于11参数。'],
    missing:[], warnings:['尚未匹配总体性能要求，也未执行平均线计算。','需进一步检查气动性能、工况适配和网格质量。'],
  }};
}

export async function requestAssistant({provider, messages, signal, fetchImpl = globalThis.fetch}) {
  if (!['general','domain'].includes(provider)) throw Error('请选择通用或航发领域模型');
  const response = await fetchImpl(ASSISTANT_ENDPOINT, {
    method:'POST', signal, credentials:'same-origin', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({schema:'aeroblade-assistant-request-v1',provider,messages,
      geometryModel:'pritchard-1985',units:{length:'mm',angle:'deg'},parameterContract:PARAMETER_FIELDS.map(([key,label,min,max,,unit])=>({key,label,min,max,unit})),
      angleConvention:'signed-from-axial; negative-outlet; inlet-half-wedge',extrusion:{key:'height',min:30,max:160,unit:'mm',partOfElevenParameters:false}}),
  });
  if (!response.ok) {
    if ([404,405,501,503].includes(response.status)) throw Error('大模型 API 尚未接入或服务暂不可用；可重试，或切换“参考演示”');
    if ([401,403].includes(response.status)) throw Error('模型服务鉴权失败，请由服务端配置访问凭据');
    throw Error(`模型服务请求失败（HTTP ${response.status}），请稍后重试`);
  }
  let raw;
  try { raw = await response.json(); } catch { throw Error('模型服务未返回有效 JSON'); }
  if (raw?.schema !== 'aeroblade-assistant-reply-v1') throw Error('助手响应协议不匹配');
  return validateReply(raw);
}
