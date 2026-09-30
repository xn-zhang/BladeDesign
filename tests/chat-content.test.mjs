import test from 'node:test';
import assert from 'node:assert/strict';
import {composeMessage, prepareMarkdown} from '../aeroblade/web/chat-content.js';

test('attachments and selected capability are included in the actual model message',()=>{
  const result=composeMessage('设计叶片',[{name:'工况.csv',content:'流量,2'}],'需求梳理');
  assert.match(result,/设计叶片/);assert.match(result,/工况.csv/);assert.match(result,/流量,2/);assert.match(result,/需求梳理/);
  assert.equal(composeMessage('  普通问题  '),'普通问题');
  assert.throws(()=>composeMessage('x',[{name:'a.txt',content:'x'.repeat(12000)}]),/12000/);
});
test('math is extracted while code and monetary amounts remain readable',()=>{
  const result=prepareMarkdown('公式 $x^2$ 和 \\[\\eta = 0.9\\]，金额 $20。`$code$`\n```js\nconst x = "$code$";\n```');
  assert.equal(result.formulas.length,2);assert.equal(result.formulas[0].source,'x^2');
  assert.equal(result.formulas[1].display,true);assert.match(result.text,/`\$code\$`/);assert.match(result.text,/金额 \$20/);
});
