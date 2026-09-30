export function composeMessage(text,attachments=[],capability='') {
  let result=text.trim();
  if(capability)result+=`\n\n请着重协助：${capability}。`;
  for(const file of attachments)result+=`\n\n--- 附件：${file.name} ---\n${file.content}\n--- 附件结束 ---`;
  if(result.length>12000)throw Error('正文和附件合计最多 12000 字符，请缩短内容或移除附件。');
  return result;
}

export function prepareMarkdown(content) {
  const formulas=[];
  const text=content.replace(/(```[\s\S]*?```|`[^`\n]*`)|(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$(?!\s)[^$`\n]+?\$)/g,(match,code,math)=>{
    if(code)return code;
    const display=math.startsWith('$$')||math.startsWith('\\[');
    const source=math.slice(display||math.startsWith('\\(')?2:1,display||math.startsWith('\\(')?-2:-1);
    const index=formulas.push({source,display})-1;
    return `<span data-formula="${index}"></span>`;
  });
  return {text,formulas};
}

export function renderRichContent(content) {
  const node=document.createElement('div');node.className='initial-rich';
  if(!globalThis.marked||!globalThis.DOMPurify){node.textContent=content;return node;}
  const {text,formulas}=prepareMarkdown(content);
  node.innerHTML=DOMPurify.sanitize(marked.parse(text,{breaks:true,gfm:true}),{
    ALLOWED_TAGS:['p','br','strong','em','del','h1','h2','h3','h4','h5','h6','ul','ol','li','blockquote','pre','code','table','thead','tbody','tr','th','td','a','hr','span'],
    ALLOWED_ATTR:['href','title','class','data-formula','start'],ALLOW_DATA_ATTR:false,
  });
  for(const placeholder of node.querySelectorAll('[data-formula]')){
    const formula=formulas[Number(placeholder.dataset.formula)];if(!formula)continue;
    if(globalThis.katex){try{placeholder.innerHTML=katex.renderToString(formula.source,{displayMode:formula.display,output:'mathml',throwOnError:false,trust:false,strict:'ignore'});}catch{placeholder.textContent=formula.source;}}
    else placeholder.textContent=formula.source;
    if(formula.display)placeholder.className='initial-math-display';
  }
  for(const link of node.querySelectorAll('a')){link.rel='noopener noreferrer';link.target='_blank';}
  for(const table of node.querySelectorAll('table')){const wrap=document.createElement('div');wrap.className='initial-table-wrap';table.before(wrap);wrap.append(table);}
  for(const pre of node.querySelectorAll('pre')){
    const copy=document.createElement('button');copy.type='button';copy.className='initial-copy';copy.textContent='复制代码';
    copy.onclick=async()=>{try{await navigator.clipboard.writeText(pre.querySelector('code')?.textContent||'');copy.textContent='已复制';}catch{copy.textContent='复制失败';}setTimeout(()=>copy.textContent='复制代码',1800);};pre.append(copy);
  }
  return node;
}
