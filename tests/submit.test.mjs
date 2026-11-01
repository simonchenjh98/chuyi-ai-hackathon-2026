import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('../submit.js',import.meta.url),'utf8').replace(/\nrender\(\);\s*$/,'');
function app(){
  const elements=new Map(),events={};
  const get=id=>{if(!elements.has(id))elements.set(id,{innerHTML:'',textContent:'',checked:false,disabled:false,classList:{toggle(){},add(){},remove(){}}});return elements.get(id);};
  const context=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[]},location:{hostname:'example.test',href:'https://example.test/chuyi/submit.html',hash:'#admin'},window:{addEventListener:(name,fn)=>events[name]=fn},URL,Blob,AbortController,Date,setTimeout,clearTimeout,console});
  vm.runInContext(source,context);return {context,elements,get,events,run:code=>vm.runInContext(code,context)};
}
test('untrusted links only become HTTP(S) hyperlinks; text is escaped',()=>{
  const a=app();assert.equal(a.run("safeUrl('javascript:alert(1)')"),'');assert.equal(a.run("safeUrl('data:text/html,test')"),'');
  assert.equal(a.run("safeUrl('https://example.com/game?a=1')"),'https://example.com/game?a=1');
  assert.equal(a.run("esc('<img src=x onerror=alert(1)>')"),'&lt;img src=x onerror=alert(1)&gt;');
});
test('admin filters preserve team-number order and accept files or demo links as submissions',()=>{
  const a=app();a.run(`adminTeams=[{id:'a',number:1,name:'第一队',submitted:false,files:[]},{id:'b',number:2,name:'第二队',submission:{title:'游戏',demoUrl:'https://example.com'},files:[]},{id:'c',number:12,name:'第三队',files:[{id:'f'}]}];statusFilter='submitted';`);
  assert.equal(a.run("shownTeams().map(t=>t.number).join(',')"),'2,12');
  a.run("search='02'");assert.equal(a.run("shownTeams().map(t=>t.number).join(',')"),'2');
  a.run("search='游戏'");assert.equal(a.run("shownTeams()[0].id"),'b');
});
test('admin output escapes team, project, filename and rejects executable links',()=>{
  const a=app();a.run(`adminTeams=[{id:'t',number:1,name:'<img src=x onerror=alert(1)>',submitted:true,submission:{title:'<script>x</script>',demoUrl:'javascript:alert(1)'},files:[{id:'f',name:'<svg onload=alert(1)>.pdf',kind:'ppt',size:100}]}];renderAdminRows();`);
  const html=a.get('admin-rows').innerHTML;
  assert.ok(!html.includes('<img src=x'));assert.ok(!html.includes('<script>x'));assert.ok(!html.includes('href="javascript:'));
  assert.match(html,/&lt;img/);assert.match(html,/&lt;svg/);assert.match(html,/data-admin-download="f"/);
});
test('selection survives refresh while pending and deleted teams leave selection',()=>{
  const a=app();a.run(`adminTeams=[{id:'a',number:1,name:'A',submitted:true,files:[]},{id:'b',number:2,name:'B',submitted:false,files:[]}];selected=new Set(['a','b','deleted']);renderAdminRows();`);
  assert.equal(a.run("[...selected].join(',')"),'a');assert.equal(a.get('selected-count').textContent,'已选择 1 组');
  assert.equal(a.get('select-all').checked,true);assert.equal(a.get('batch-download').disabled,false);
  a.run('pending=true;updateSelection()');assert.equal(a.get('batch-download').disabled,true);
});
test('HTML complies with site CSP and file pickers accept requested formats',()=>{
  assert.ok(!/style=/.test(source));assert.ok(!/<[^>]*\sonclick=/.test(source));
  assert.match(source,/accept="\.ppt,\.pptx,\.pdf"/);assert.match(source,/accept="\.html,\.htm,\.zip"/);
  assert.match(source,/X-File-Name/);assert.match(source,/encodeURIComponent\(file.name\)/);
});
test('students enter from any device using only team ID; teacher login keeps its code',()=>{
  const a=app();a.run("teams=[{id:'t1',number:1,name:'第一队',submitted:false}];renderStudent();");
  const html=a.get('main').innerHTML;
  assert.match(html,/name="teamId"/);assert.ok(!html.includes('name="receipt"'));
  assert.ok(!html.includes('name="code"'));assert.ok(!html.includes('活动提交码'));
  const studentFlow=source.slice(source.indexOf('function renderStudent()'),source.indexOf('function showTeamDetail()'));
  assert.match(studentFlow,/data:\{teamId:id\}/);
  assert.ok(!studentFlow.includes('elements.code'));assert.ok(!studentFlow.includes('receipt'));assert.ok(!html.includes('原浏览器'));assert.ok(!source.includes('backup-receipt'));
  a.run('renderAdminLogin()');assert.match(a.get('main').innerHTML,/组织方邀请码/);assert.match(a.get('main').innerHTML,/name="code"/);
});
