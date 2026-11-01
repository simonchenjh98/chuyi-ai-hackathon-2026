import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';

const completeSource = fs.readFileSync(new URL('../platform.js', import.meta.url), 'utf8');
const source = completeSource.split("window.addEventListener('beforeunload'")[0];
const eventSource = completeSource.slice(0, completeSource.lastIndexOf("(async()=>{try{session=await api('session')"));
function renderer(screen = false, elapsed = 0, stage = 'roadshow') {
  const context = vm.createContext({
    document: {getElementById: () => ({}), body: {classList: {contains: () => screen}}},
    location: {href: 'https://example.test/chuyi/platform.html#board'}, URL,
    Date, setTimeout, clearTimeout,
  });
  vm.runInContext(source + `\nscreenStarted = Date.now() - ${elapsed}; boardStage = ${JSON.stringify(stage)}; globalThis.render = boardMarkup;`, context);
  return data => context.render(data);
}
const cfg = {minJudges:1, resultsPublished:true, scoringOpen:true};
const team = (n, extra = {}) => ({id:`T${n}`,number:n,name:`TEAM-${n}`,project:'project',judgeCount:5,score:80,rank:n,audienceVotes:0,...extra});

test('board presents rank order, then waiting teams, preserving a zero score', () => {
  const html = renderer()({teams:[team(1,{rank:null,score:null}),team(3,{rank:2,score:0}),team(2,{rank:1,score:90})],config:cfg});
  assert.ok(html.indexOf('TEAM-2') < html.indexOf('TEAM-3'));
  assert.ok(html.indexOf('TEAM-3') < html.indexOf('TEAM-1'));
  assert.match(html,/0\.00/);
  assert.match(html,/等待评审/);
});

test('roadshow board explains unlimited judges and shows one submitted score as effective', () => {
  const html = renderer()({teams:[team(1,{judgeCount:1,score:80,rank:1})],config:cfg});
  assert.match(html,/路演评委人数不限/);
  assert.match(html,/1 位评委正式提交即生成有效均分/);
  assert.match(html,/<td>1 位<\/td>/);
  assert.match(html,/80\.00/);
});

test('public team text cannot inject HTML or disclose unprovided judge data', () => {
  const html = renderer()({teams:[team(1,{name:'<img src=x onerror=alert(1)>',project:'<script>secret</script>'})],config:cfg});
  assert.ok(!html.includes('<img src=x'));
  assert.ok(!html.includes('<script>secret'));
  assert.match(html,/&lt;img/);
});

test('roadshow screen shows all 23 teams continuously at every refresh', () => {
  const data = {teams:Array.from({length:23},(_,i)=>team(i+1)),config:cfg};
  for(const elapsed of [0,13000,37000]){
    const html = renderer(true,elapsed)(data);
    assert.equal((html.match(/class="team-number"/g)||[]).length,23);
    for(let n=1;n<=23;n++)assert.ok(html.includes(`TEAM-${n}<`));
    assert.ok(html.indexOf('TEAM-1<')<html.indexOf('TEAM-23<'));
    assert.match(html,/全部 23 支队伍 · 上下滚动查看/);
    assert.doesNotMatch(html,/第 \d+ \/ \d+ 屏|轮播/);
  }
});

test('unpublished scores and an empty event have explicit states', () => {
  const html = renderer()({teams:[team(1,{score:null,rank:null})],config:{...cfg,resultsPublished:false}});
  assert.match(html,/暂未发布/);
  assert.match(renderer()({teams:[],config:cfg}),/本届队伍尚未录入/);
});

const awards = [
  ['creativity', '最佳创意奖'], ['technology', '最佳技术实现奖'],
  ['potential', '最具应用潜力奖'], ['care', '最具社会关怀奖'],
].map(([id, name], i) => ({id, name, max:150, score:150-i*5, leaders:[`T${i+1}`], winner:null, winnerConfirmed:false, tied:false, ready:true}));
function finalData() {
  const totals=[[150,100,100,100],[110,145,110,110],[120,120,140,120],[125,125,125,135]];
  return {
    config:{...cfg, finalResultsPublished:true, finalMinJudges:6, finalJudgeLimit:6, finalScoringOpen:false},
    finalists:totals.map((scores,i)=>team(i+1,{project:`PROJECT-${i+1}`,finalJudgeCount:6,finalReady:true,finalTotals:scores,finalTotal:scores.reduce((a,b)=>a+b,0),finalScores:scores.map(n=>n/6)})),
    awards:awards.map(a=>({...a, leaders:[...a.leaders]})),
    mvp:{id:'mvp',name:'全场MVP',score:510,max:600,leaders:['T4'],winner:null,winnerConfirmed:false,tied:false,ready:true},
  };
}
const cards = html => [...html.matchAll(/<article class="surface award-card">([\s\S]*?)<\/article>/g)].map(m=>m[1]);

test('final board presents four summed awards out of 150 and a separate MVP out of 600', () => {
  const html = renderer(false, 0, 'final')(finalData());
  const rendered = cards(html);
  assert.equal(rendered.length, 4);
  awards.forEach((award, i) => {
    assert.ok(rendered[i].includes(`<h2>${award.name}</h2>`));
    assert.ok(rendered[i].includes(`<strong class="award-winner">TEAM-${i+1}</strong>`));
    assert.ok(rendered[i].includes(`${award.score.toFixed(2)}<small> / 150</small>`));
    assert.match(rendered[i], /当前最高分候选/);
  });
  assert.match(html, /全场MVP/);
  assert.match(html, /510\.00<small> \/ 600<\/small>/);
  assert.match(html, /单项满分 150 分/);
  assert.match(html, /MVP 总分 \/ 600/);
  assert.match(html, /6 \/ 6 位 · 已完成/);
  assert.match(html, /<td>150\.00<\/td>/);
  assert.ok(!html.includes('<td>25.00</td>')); // The board must not reuse the retained per-judge mean.
  assert.ok(!html.includes('路演总分'));
  assert.ok(!html.includes('获奖已确认'));
});

test('tied final leaders remain candidates until the organizer confirms a winner', () => {
  const data = finalData();
  data.awards[0] = {...data.awards[0], leaders:['T1','T2'], tied:true};
  const [card] = cards(renderer(false, 0, 'final')(data));
  assert.match(card, /最高分并列 · 待裁定/);
  assert.match(card, /<strong class="award-winner">TEAM-1 \/ TEAM-2<\/strong>/);
  assert.match(card, /当前最高分候选/);
  assert.ok(!card.includes('获奖已确认'));
});

test('confirmed final award shows the chosen winner and project rather than all tied leaders', () => {
  const data = finalData();
  data.awards[0] = {...data.awards[0], leaders:['T1','T2'], tied:true, winner:'T2', winnerConfirmed:true};
  const [card] = cards(renderer(false, 0, 'final')(data));
  assert.match(card, /获奖已确认/);
  assert.match(card, /<strong class="award-winner">TEAM-2<\/strong>/);
  assert.match(card, /PROJECT-2/);
  assert.ok(!card.includes('TEAM-1'));
  assert.ok(!card.includes('当前最高分候选'));
});

test('one final submission shows interim sums and progress rather than waiting for six means', () => {
  const data=finalData();
  data.finalists=data.finalists.slice(0,1).map(t=>({...t,finalJudgeCount:1,finalReady:false,finalTotals:[0,21,22,23],finalTotal:66,finalScores:[null,null,null,null]}));
  data.awards=data.awards.map((a,i)=>({...a,score:[0,21,22,23][i],leaders:['T1'],ready:false}));
  data.mvp={...data.mvp,score:66,leaders:['T1'],ready:false};
  const html=renderer(false,0,'final')(data);
  assert.match(html,/66\.00<small> \/ 600<\/small>/);
  assert.match(html,/0\.00<small> \/ 150<\/small>/);
  assert.match(html,/1 \/ 6 位 · 未完成/);
  assert.match(html,/阶段累计 · 尚未定稿/);
  assert.match(html,/待其余评委提交/);
  assert.ok(!html.includes('获奖已确认'));
});

test('final screen rotates compact awards and the complete finalist table every twelve seconds', () => {
  const data=finalData();
  data.finalists=Array.from({length:8},(_,i)=>({...data.finalists[i%4],id:`T${i+1}`,number:i+1,name:`TEAM-${i+1}`}));
  const awardsPage=renderer(true,0,'final')(data),tablePage=renderer(true,13000,'final')(data);
  assert.match(awardsPage,/第 1 \/ 2 屏/);
  assert.match(awardsPage,/全场MVP/);
  assert.equal(cards(awardsPage).length,4);
  assert.ok(!awardsPage.includes('final-table'));
  assert.match(tablePage,/第 2 \/ 2 屏/);
  assert.match(tablePage,/final-table/);
  assert.match(tablePage,/TEAM-8/);
  assert.equal(cards(tablePage).length,0);
  assert.ok(!awardsPage.includes('class="metrics"'));
  assert.ok(!tablePage.includes('class="info-banner"'));
});

test('hidden final results never fall back to retained per-judge means', () => {
  const data=finalData();data.config.finalResultsPublished=false;
  data.finalists=data.finalists.map(t=>({...t,finalTotals:[null,null,null,null],finalTotal:null}));
  data.awards=data.awards.map(a=>({...a,score:null,leaders:[],winner:null,winnerConfirmed:false,ready:false}));
  data.mvp={...data.mvp,score:null,leaders:[],winner:null,winnerConfirmed:false,ready:false};
  const html=renderer(false,0,'final')(data);
  assert.match(html,/决赛成绩暂未发布/);
  assert.match(html,/—<small> \/ 600<\/small>/);
  assert.ok(!html.includes('510.00'));
  assert.ok(!html.includes('<td>25.00</td>'));
});

function browserHarness({hash='#admin', confirm=()=>false, fetch}={}) {
  const nodes = new Map(), listeners = new Map(), requests = [], timers=new Map();let timerId=0;
  const fields = {activeStage:'roadshow', finalistCount:'6', minJudges:'1', finalMinJudges:'6'};
  function element(id) {
    if(nodes.has(id)) return nodes.get(id);
    const controls = new Map();
    const node = {
      innerHTML:'', textContent:'', disabled:false, isConnected:true, hidden:id==='identity-field',reportValidity:()=>true,
      classList:{contains:()=>false, add(){}, remove(){}, toggle(){}},
      elements:new Proxy({}, {get:(_, key)=>{
        if(!controls.has(key)) controls.set(key, {value:fields[key]||'', checked:false});
        return controls.get(key);
      }}),
      querySelector:selector=>element(`${id}/${selector}`), querySelectorAll:()=>node.formControls||[],
      addEventListener(){}, setAttribute(){}, removeAttribute(){},
      scrollIntoView(options){node.scrolledIntoView=options;},focus(options){node.focused=options||true;},
    };
    nodes.set(id,node);
    return node;
  }
  const data = {
    teams:[], judges:[], awards:[], finalists:[], myScores:[], dimensions:[],
    qualification:{confirmed:false, ready:false},
    config:{activeStage:'roadshow', finalistCount:6, minJudges:1, finalMinJudges:6},
  };
  const storage=()=>{const entries=new Map();return {getItem:key=>entries.get(key)||null,setItem:(key,value)=>entries.set(key,String(value))};};
  const localStorage=storage(),sessionStorage=storage();
  const context = vm.createContext({
    document:{getElementById:element, querySelectorAll:selector=>selector==='[data-team]'?[...element('team-picker').innerHTML.matchAll(/data-team="([^"]+)"/g)].map(([,id])=>{const button=element(`team:${id}`);button.dataset={team:id};return button;}):[], body:{classList:{contains:()=>false, remove(){}, toggle(){}}}},
    location:{href:`https://example.test/chuyi/platform.html${hash}`, hash},
    window:{addEventListener:(name,handler)=>listeners.set(name,handler),localStorage,sessionStorage,scrollX:0,scrollY:0,scrollTo(x,y){this.scrollX=x;this.scrollY=y;}},
    URL, Date, AbortController,crypto:webcrypto,setTimeout:(callback,delay)=>{timers.set(++timerId,{callback,delay});return timerId;},clearTimeout:id=>timers.delete(id),confirm,
    fetch:async(url,options)=>{
      requests.push({path:url.pathname, options});
      const result = fetch ? await fetch(url,options) : data;
      return {ok:true, json:async()=>result};
    },
  });
  vm.runInContext(eventSource,context);
  return {context,nodes,requests,element,timers,localStorage,sessionStorage,run:code=>vm.runInContext(code,context),dispatch:(name,event={})=>listeners.get(name)?.(event),fireTimer:delay=>{const entry=[...timers].find(([,timer])=>timer.delay===delay);assert.ok(entry,`Expected a ${delay}ms timer`);timers.delete(entry[0]);return entry[1].callback();}};
}

test('shared judge login only offers identities from the current stage', () => {
  const h=browserHarness({hash:'#judge-final'});
  const accounts="[{id:'R1',name:'路演一',judgeStage:'roadshow'},{id:'F1',name:'决赛一',judgeStage:'final'},{id:'F2',name:'决赛二',judgeStage:'final'}]";
  assert.equal(h.run(`JSON.stringify(selectableAccounts('judge',${accounts},'final').map(a=>a.id))`),'["F1","F2"]');
  assert.equal(h.run(`JSON.stringify(selectableAccounts('judge',${accounts},'roadshow').map(a=>a.id))`),'["R1"]');
  assert.equal(h.run(`selectableAccounts('admin',${accounts},'final').length`),3);
});

test('shared final login selects a final identity and opens the matching judge workbench', async () => {
  const logins=[];
  const h=browserHarness({hash:'#judge-final',fetch:async(url,options)=>{
    if(url.pathname.endsWith('/api/login')){
      const body=JSON.parse(options.body);logins.push(body);
      return body.accountId?{ok:true}:{selectAccount:true,accounts:[{id:'R1',name:'ROADSHOW ONLY',judgeStage:'roadshow'},{id:'F1',name:'FINAL JUDGE',judgeStage:'final'}]};
    }
    if(url.pathname.endsWith('/api/session'))return {role:'judge',name:'FINAL JUDGE',judgeStage:'final'};
    return {teams:[],myScores:[],dimensions:[],scoringOpen:true,name:'FINAL JUDGE'};
  }});
  await h.run('renderRoute()');
  const form=h.element('login-form');form.elements.code.value='000000';
  await form.onsubmit({preventDefault(){}});
  assert.equal(h.element('identity-field').hidden,false);
  assert.ok(form.elements.accountId.innerHTML.includes('FINAL JUDGE'));
  assert.ok(!form.elements.accountId.innerHTML.includes('ROADSHOW ONLY'));
  form.elements.accountId.value='F1';
  await form.onsubmit({preventDefault(){}});
  assert.deepEqual(logins,[{role:'judge',code:'000000',judgeStage:'final'},{role:'judge',code:'000000',judgeStage:'final',accountId:'F1'}]);
  assert.equal(h.run('session.judgeStage'),'final');
  assert.equal(h.run('route'),'judge-final');
  assert.match(h.element('platform-main').innerHTML,/决赛评委工作台/);
  assert.ok(h.requests.some(r=>r.path.endsWith('/api/judge/final')));
  assert.ok(!h.requests.some(r=>r.path.endsWith('/api/judge/roadshow')));
});

test('a roadshow identity opens final login directly without an exit-identity blocker', async () => {
  const h=browserHarness({hash:'#judge-final'});
  h.run("session={role:'judge',judgeStage:'roadshow'};");
  await h.run('renderRoute()');
  assert.match(h.element('platform-main').innerHTML,/决赛评委登录/);
  assert.ok(!h.element('platform-main').innerHTML.includes('退出并切换身份'));
  assert.equal(h.requests.length,0);
});

test('roadshow code logs in directly with a persistent device identity and no selection step', async () => {
  const logins=[];
  const h=browserHarness({hash:'#judge-roadshow',fetch:async(url,options)=>{
    if(url.pathname.endsWith('/api/login')){logins.push(JSON.parse(options.body));return {ok:true};}
    if(url.pathname.endsWith('/api/session'))return {role:'judge',name:'本机路演评委',judgeStage:'roadshow'};
    return {teams:[],myScores:[],dimensions:[],scoringOpen:false,roadshowOpensAt:1793509200000};
  }});
  await h.run('renderRoute()');
  const form=h.element('login-form');form.elements.code.value='000000';
  await form.onsubmit({preventDefault(){}});
  assert.equal(logins.length,1);
  assert.equal(logins[0].judgeStage,'roadshow');
  assert.match(logins[0].deviceToken,/^[a-f0-9]{64}$/);
  assert.ok(!('accountId' in logins[0]));
  assert.equal(h.element('identity-field').hidden,true);
  assert.match(h.element('platform-main').innerHTML,/路演评委工作台/);
  assert.match(h.element('platform-main').innerHTML,/13:00/);
  assert.equal(h.run('roadshowDeviceToken()'),logins[0].deviceToken);
  const other=browserHarness({hash:'#judge-roadshow'});
  assert.notEqual(other.run('roadshowDeviceToken()'),logins[0].deviceToken);
});

test('roadshow identity falls back to session storage and never uses a shared default when storage fails', async () => {
  const h=browserHarness({hash:'#judge-roadshow'});
  h.run("window.localStorage={getItem(){throw new Error('blocked')},setItem(){throw new Error('blocked')}};");
  const token=h.run('roadshowDeviceToken()');
  assert.equal(token,h.sessionStorage.getItem('chuyi-roadshow-device-v1'));
  assert.equal(h.run('roadshowDeviceToken()'),token);
  h.run('window.localStorage=null;window.sessionStorage=null;');
  await h.run('renderRoute()');
  h.element('login-form').elements.code.value='000000';
  await h.element('login-form').onsubmit({preventDefault(){}});
  assert.equal(h.requests.length,0);
  assert.match(h.element('login-form/.form-error').textContent,/无法保存本机评委身份/);
});

test('all 23 final team tags show completion and clicking a team opens its four score inputs', async () => {
  const data={teams:Array.from({length:23},(_,i)=>team(i+1,{project:'项目待定'})),myScores:[{teamId:'T1',status:'submitted',scores:[25,25,25,25]},{teamId:'T2',status:'draft',scores:[20,20,20,20]}],dimensions:awards.map(a=>({id:a.id,name:a.name,max:25})),scoringOpen:true};
  const h=browserHarness({hash:'#judge-final',fetch:async()=>data});
  h.run("session={role:'judge',judgeStage:'final'};");await h.run('renderRoute()');
  const tags=h.element('team-picker').innerHTML;
  assert.equal((tags.match(/data-team=/g)||[]).length,23);
  assert.match(tags,/data-team="T1" data-score-status="submitted"/);
  assert.match(tags,/已评分 ✓/);
  assert.match(tags,/<strong>TEAM-23<\/strong>/);
  assert.ok(!tags.includes('<strong>项目待定</strong>'));
  assert.ok(h.element('platform-main').innerHTML.indexOf('id="team-picker"')<h.element('platform-main').innerHTML.indexOf('id="judge-editor"'));
  h.element('team:T23').onclick();
  assert.equal(h.run('selectedTeam'),'T23');
  assert.match(h.element('judge-editor').innerHTML,/<h2>TEAM-23<\/h2>/);
  assert.equal((h.element('judge-editor').innerHTML.match(/max="25"/g)||[]).length,8);
  assert.equal(h.element('judge-editor').scrolledIntoView.block,'start');
  assert.equal(h.element('score-0').focused.preventScroll,true);
  h.element('score-form').oninput();h.element('team:T2').onclick();
  assert.equal(h.run('selectedTeam'),'T23'); // Canceling the dirty switch keeps the current team.
});

test('scheduled opening updates controls in place every second without replacing unsaved scores', async () => {
  let calls=0;
  const data={teams:[team(1)],myScores:[],dimensions:[{id:'problem',name:'问题价值',max:20}],scoringOpen:false,roadshowOpensAt:1793509200000,roadshowAutoOpenDone:false};
  const h=browserHarness({hash:'#judge-roadshow',fetch:async(url)=>{
    if(url.pathname.endsWith('/api/judge/status')){calls++;if(calls===1)throw new Error('OFFLINE');return {stage:'roadshow',scoringOpen:true,roadshowOpensAt:1793509200000,roadshowAutoOpenDone:true};}
    return data;
  }});
  h.run("session={role:'judge',judgeStage:'roadshow'};");await h.run('renderRoute()');
  const form=h.element('score-form');form.elements.score0.value='12.3';form.oninput();
  const input={tagName:'INPUT',disabled:true};form.formControls=[input];
  const editor=h.element('judge-editor').innerHTML;
  await h.fireTimer(1000);
  assert.match(h.element('workbench-status').textContent,/连接中断/);
  assert.equal(form.elements.score0.value,'12.3');
  await h.fireTimer(1000);
  assert.equal(h.run('judgeData.scoringOpen'),true);
  assert.equal(input.disabled,false);
  assert.match(h.element('judge-availability').textContent,/路演评分开放中/);
  assert.equal(h.element('judge-editor').innerHTML,editor);
  assert.equal(form.elements.score0.value,'12.3');
  assert.equal(h.run('editorDirty'),true);
  assert.equal(h.requests.filter(r=>r.path.endsWith('/api/judge/roadshow')).length,1);
});

test('a late judge status response cannot update a different route', async () => {
  let finish;const h=browserHarness({fetch:async()=>new Promise(resolve=>{finish=()=>resolve({stage:'roadshow',scoringOpen:true});})});
  h.run("route='judge-roadshow';judgeStage='roadshow';routeVersion=1;judgeData={scoringOpen:false};startJudgeStatusPolling(1,'roadshow');");
  const pending=h.fireTimer(1000);
  h.run("route='admin';routeVersion=2;root.innerHTML='ADMIN PAGE';");
  finish();await pending;
  assert.equal(h.run('judgeData.scoringOpen'),false);
  assert.equal(h.element('platform-main').innerHTML,'ADMIN PAGE');
  assert.ok(![...h.timers.values()].some(t=>t.delay===1000));
});

test('organizer saves independent toggles and an explicitly Shanghai scheduled opening', async () => {
  let settings;
  const data={teams:[],judges:[],awards:[],finalists:[],qualification:{confirmed:false,ready:false},config:{roadshowOpensAt:1793509200000,scoringOpen:false,finalScoringOpen:true,finalIndependent:true,finalistCount:6,minJudges:1,finalMinJudges:6}};
  const h=browserHarness({fetch:async(url,options)=>{if(url.pathname.endsWith('/api/admin/settings')){settings=JSON.parse(options.body);return {ok:true};}return data;}});
  assert.equal(h.run('scheduleInput(1793509200000)'),'2026-11-01T13:00');
  assert.equal(h.run("scheduleEpoch('2026-11-01T13:00')"),1793509200000);
  assert.equal(h.run("scheduleEpoch('')"),null);
  assert.throws(()=>h.run("scheduleEpoch('not a date')"),/有效的北京时间/);
  h.run("session={role:'admin'};");await h.run('renderRoute()');
  assert.ok(!h.element('platform-main').innerHTML.includes('name="activeStage"'));
  data.qualification.confirmed=true;await h.run('renderAdmin(routeVersion)');
  const roadshowToggle=h.element('platform-main').innerHTML.match(/<input[^>]*name="scoringOpen"[^>]*>/)[0];
  assert.ok(!roadshowToggle.includes('disabled')); // Old reference lists cannot disable the independent switch.
  const form=h.element('settings-form');form.elements.roadshowOpensAt.value='2026-11-01T13:00';form.elements.finalScoringOpen.checked=true;
  await form.onsubmit({preventDefault(){}});
  assert.equal(settings.roadshowOpensAt,1793509200000);
  assert.equal(settings.scoringOpen,false);
  assert.equal(settings.finalScoringOpen,true);
  assert.equal(settings.finalIndependent,true);
  assert.ok(!('activeStage' in settings));
});

test('final screen paginates all 23 teams as eight, eight and seven after the awards screen', () => {
  const data=finalData();data.finalists=Array.from({length:23},(_,i)=>team(i+1,{finalTotal:null,finalTotals:[null,null,null,null],finalJudgeCount:0,finalReady:false}));
  const pages=[13000,25000,37000].map(elapsed=>renderer(true,elapsed,'final')(data));
  pages.forEach((html,i)=>{assert.match(html,new RegExp(`第 ${i+2} / 4 屏`));const body=html.match(/<tbody>([\s\S]*?)<\/tbody>/)[1];assert.equal((body.match(/<tr>/g)||[]).length,i===2?7:8);});
  assert.match(pages[0],/TEAM-1<\/strong>/);assert.ok(!pages[0].includes('TEAM-9</strong>'));
  assert.match(pages[1],/TEAM-9<\/strong>/);assert.match(pages[2],/TEAM-23<\/strong>/);
});

test('unscored teams do not keep completed award candidates pending and screen ties stay compact', () => {
  const data=finalData();data.finalists.push(...Array.from({length:19},(_,i)=>team(i+5,{finalJudgeCount:0,finalReady:false,finalTotal:null,finalTotals:[null,null,null,null]})));
  let html=renderer(false,0,'final')(data);
  assert.match(cards(html)[0],/等待组织方确认/);
  assert.ok(!cards(html)[0].includes('尚未定稿'));
  const ids=data.finalists.map(t=>t.id);data.awards[0]={...data.awards[0],leaders:ids,tied:true};
  html=renderer(true,0,'final')(data);
  assert.match(cards(html)[0],/等 23 队并列/);
  assert.ok(!cards(html)[0].includes('TEAM-23'));
  assert.match(cards(renderer(false,0,'final')(data))[0],/TEAM-23/);
});

test('score notifications request an immediate board refresh without overlapping an active read', async () => {
  let calls=0,finish;const data=finalData();
  const h=browserHarness({hash:'#board-final',fetch:async()=>{calls++;if(calls===1)return new Promise(resolve=>{finish=()=>resolve(data);});return data;}});
  h.run("route='board-final';boardStage='final';routeVersion=1;");
  const reading=h.run('renderBoard(1)');
  h.dispatch('storage',{key:'chuyi-score-updated'});
  assert.equal(calls,1);
  finish();await reading;
  await h.fireTimer(0);
  assert.equal(calls,2);
  assert.ok([...h.timers.values()].some(t=>t.delay===1000));
});

test('organizer can confirm MVP and four awards only after complete judging and closure', () => {
  const h=browserHarness(),data=finalData();
  let html=h.run(`awardAdminMarkup(${JSON.stringify(data)})`);
  assert.equal((html.match(/data-award-form=/g)||[]).length,5);
  assert.match(html,/data-award-form="mvp"/);
  assert.match(html,/510\.00 \/ 600 分/);
  assert.match(html,/150\.00 \/ 150 分/);
  assert.ok(!html.includes('type="submit" disabled'));
  data.config.finalScoringOpen=true;
  data.mvp.ready=false;data.awards.forEach(a=>a.ready=false);
  html=h.run(`awardAdminMarkup(${JSON.stringify(data)})`);
  assert.equal((html.match(/type="submit" disabled/g)||[]).length,5);
});

function mountFinalEditor(h,values=[25,25,25,25]) {
  const form=h.element('score-form');values.forEach((value,i)=>{form.elements[`score${i}`].value=String(value);});
  const data={teams:[team(1),team(2)],myScores:[{teamId:'T1',scores:values,status:'draft',feedback:''}],dimensions:awards.map(a=>({id:a.id,name:a.name,max:25})),scoringOpen:true};
  h.run(`session={role:'judge',judgeStage:'final'};route='judge-final';judgeStage='final';routeVersion=1;judgeData=${JSON.stringify(data)};selectedTeam='T1';renderJudgeEditor();`);
  return form;
}

test('final judge scores each dimension out of 25 and submits a personal total out of 100', async () => {
  let submitted;
  const h=browserHarness({hash:'#judge-final',fetch:async(url,options)=>{
    if(url.pathname.endsWith('/api/score')){submitted=JSON.parse(options.body);return {ok:true};}
    throw new Error('RELOAD OFFLINE');
  }});
  const form=mountFinalEditor(h);
  assert.equal((h.element('judge-editor').innerHTML.match(/max="25"/g)||[]).length,8);
  assert.match(h.element('score-total').innerHTML,/100\.0 <small>\/ 100<\/small>/);
  form.elements.score0.value='25.1';form.reportValidity=()=>false;
  await form.onsubmit({preventDefault(){}});
  assert.equal(h.requests.length,0);
  form.elements.score0.value='25';form.reportValidity=()=>true;form.oninput();
  await form.onsubmit({preventDefault(){}});
  assert.deepEqual(submitted.scores,[25,25,25,25]);
  assert.equal(submitted.stage,'final');
  assert.equal(submitted.teamId,'T1');
  assert.equal(h.run('editorDirty'),false);
  assert.equal(form.elements.score0.value,'25');
  assert.match(h.element('platform-toast').textContent,/刷新失败：RELOAD OFFLINE/);
});

test('edits entered during a slow score submission survive its successful completion', async () => {
  let finish,start;const started=new Promise(resolve=>{start=resolve;});
  const h=browserHarness({hash:'#judge-final',fetch:async(url)=>{
    assert.ok(url.pathname.endsWith('/api/score'));
    start();return new Promise(resolve=>{finish=()=>resolve({ok:true});});
  }});
  const form=mountFinalEditor(h,[20,20,20,20]);form.oninput();
  const saving=form.onsubmit({preventDefault(){}});await started;
  form.elements.score0.value='23';form.oninput();
  await h.element('save-draft').onclick({currentTarget:h.element('save-draft')});
  assert.equal(h.requests.length,1); // A second action cannot overtake the pending submission.
  finish();await saving;
  assert.equal(form.elements.score0.value,'23');
  assert.equal(h.run('editorDirty'),true);
  assert.equal(h.run('scoreSavePending'),false);
  assert.match(h.element('platform-toast').textContent,/你之后的修改尚未保存/);
  assert.equal(h.requests.length,1); // No refresh can replace the newer local values.
});

test('edits entered while a manual reload is pending cannot be replaced by its older response', async () => {
  let finish,start;const started=new Promise(resolve=>{start=resolve;});
  const h=browserHarness({hash:'#judge-final',fetch:async()=>{
    start();return new Promise(resolve=>{finish=()=>resolve({teams:[],myScores:[],dimensions:[],scoringOpen:true});});
  }});
  const form=mountFinalEditor(h,[20,20,20,20]);form.oninput();
  const reloading=h.run('refreshJudgeIfCurrent(1,true)');await started;
  form.elements.score0.value='24';form.oninput();
  finish();await reloading;
  assert.equal(form.elements.score0.value,'24');
  assert.equal(h.run('editorDirty'),true);
  assert.equal(h.run('judgeData.teams.length'),2);
});

test('GET and POST requests time out and uncertain writes are not automatically retried', async () => {
  const h=browserHarness({fetch:async(_url,options)=>new Promise((_resolve,reject)=>{
    options.signal.addEventListener('abort',()=>reject(Object.assign(new Error('Aborted'),{name:'AbortError'})));
  })});
  const reading=h.run("api('board')");h.fireTimer(15000);
  await assert.rejects(reading,/连接超时/);
  const saving=h.run("api('score',{stage:'final'})");h.fireTimer(15000);
  await assert.rejects(saving,/操作可能已送达/);
  assert.equal(h.requests.length,2);
  assert.equal(h.timers.size,0);
});

test('roadshow refresh keeps the current page and table scroll position', () => {
  const h=browserHarness({hash:'#board-roadshow'}),content=h.element('board-content');
  let table={scrollLeft:45,scrollTop:70},markup='';
  content.querySelector=()=>table;
  Object.defineProperty(content,'innerHTML',{get:()=>markup,set:value=>{
    markup=value;table={scrollLeft:0,scrollTop:0};h.context.window.scrollTo(0,0);
  }});
  h.context.window.scrollTo(0,1200);
  h.run("boardStage='roadshow';updateBoardContent({teams:[],config:{}})");
  assert.equal(h.context.window.scrollY,1200);
  assert.equal(table.scrollLeft,45);
  assert.equal(table.scrollTop,70);
});

test('board polling waits for each request, preserves stale data, then recovers automatically', async () => {
  let calls=0,finish;const data=finalData();
  const h=browserHarness({hash:'#board-final',fetch:async()=>{
    calls++;
    if(calls===1)return new Promise(resolve=>{finish=()=>resolve(data);});
    if(calls===2)throw new Error('OFFLINE');
    return {...data,mvp:{...data.mvp,score:520}};
  }});
  h.run("route='board-final';boardStage='final';routeVersion=1;");
  const initial=h.run('renderBoard(1)');
  assert.equal(calls,1);
  assert.ok(![...h.timers.values()].some(t=>t.delay===1000));
  finish();await initial;
  const original=h.element('board-content').innerHTML;
  await h.fireTimer(1000);
  assert.equal(h.element('board-content').innerHTML,original);
  assert.match(h.element('live-status').textContent,/显示上次数据，正在重试/);
  await h.fireTimer(1000);
  assert.match(h.element('board-content').innerHTML,/520\.00/);
  assert.match(h.element('live-status').innerHTML,/已连接/);
  assert.equal(calls,3);
});

test('canceling dirty hash navigation preserves the current scores and restores the route', async () => {
  let confirmations=0;
  const h=browserHarness({hash:'#judge-roadshow', confirm:()=>{confirmations++;return false;}});
  h.run("session={role:'judge',judgeStage:'roadshow'};route='judge-roadshow';routeVersion=7;selectedTeam='T7';editorDirty=true;root.innerHTML='UNSAVED SCORE EDITOR';");
  h.context.location.hash='#board-final';
  h.dispatch('hashchange');
  assert.equal(confirmations,1);
  assert.equal(h.context.location.hash,'#judge-roadshow');
  assert.equal(h.run('editorDirty'),true);
  assert.equal(h.run('selectedTeam'),'T7');
  assert.equal(h.run('routeVersion'),7);
  assert.equal(h.element('platform-main').innerHTML,'UNSAVED SCORE EDITOR');
  h.dispatch('hashchange'); // The browser dispatches a second event for the restored hash.
  assert.equal(h.run('restoringHash'),false);
  assert.equal(h.run('editorDirty'),true);
  assert.equal(h.requests.length,0);
});

test('a settings save that completes after navigation cannot replace the new board page', async () => {
  let finishPost, startPost;
  const postStarted=new Promise(resolve=>{startPost=resolve;});
  const adminData={teams:[],judges:[],awards:[],finalists:[],qualification:{confirmed:false,ready:false},config:{activeStage:'roadshow',finalistCount:6,minJudges:1,finalMinJudges:6}};
  const h=browserHarness({fetch:async(url)=>{
    if(url.pathname.endsWith('/api/admin/settings')){
      startPost();
      return new Promise(resolve=>{finishPost=()=>resolve({ok:true});});
    }
    return adminData;
  }});
  h.run("session={role:'admin'};");
  await h.run('renderRoute()');
  const saving=h.element('settings-form').onsubmit({preventDefault(){}});
  await postStarted;
  h.context.location.hash='#board-roadshow';
  await h.run('renderRoute()');
  const board=h.element('platform-main').innerHTML;
  assert.match(board,/路演实时看板/);
  finishPost();
  await saving;
  assert.equal(h.run('route'),'board-roadshow');
  assert.equal(h.element('platform-main').innerHTML,board);
  assert.equal(h.requests.filter(r=>r.path.endsWith('/api/admin')).length,1);
});

test('skip-to-content hash leaves the current workbench and unsaved edits intact', () => {
  let confirmations=0;
  const h=browserHarness({hash:'#judge-roadshow',confirm:()=>{confirmations++;return false;}});
  h.run("route='judge-roadshow';routeVersion=4;editorDirty=true;root.innerHTML='SCORE EDITOR';");
  h.context.location.hash='#platform-main';
  h.dispatch('hashchange');
  assert.equal(h.run('route'),'judge-roadshow');
  assert.equal(h.run('routeVersion'),4);
  assert.equal(h.run('editorDirty'),true);
  assert.equal(h.element('platform-main').innerHTML,'SCORE EDITOR');
  assert.equal(confirmations,0);
  assert.equal(h.requests.length,0);
});

test('returning from the skip target to the same route does not rebuild a dirty editor', () => {
  let confirmations=0;
  const h=browserHarness({hash:'#judge-roadshow',confirm:()=>{confirmations++;return false;}});
  h.run("route='judge-roadshow';routeVersion=5;selectedTeam='T8';editorDirty=true;root.innerHTML='UNSAVED TEAM-8 SCORES';");
  h.context.location.hash='#platform-main';
  h.dispatch('hashchange');
  h.context.location.hash='#judge-roadshow'; // Browser Back or the current-stage navigation link.
  h.dispatch('hashchange');
  assert.equal(h.run('route'),'judge-roadshow');
  assert.equal(h.run('routeVersion'),5);
  assert.equal(h.run('selectedTeam'),'T8');
  assert.equal(h.run('editorDirty'),true);
  assert.equal(h.element('platform-main').innerHTML,'UNSAVED TEAM-8 SCORES');
  assert.equal(confirmations,0);
  assert.equal(h.requests.length,0);
});

test('failed manual refresh preserves existing data and reports the connection failure', async () => {
  const h=browserHarness({fetch:async()=>{throw new Error('OFFLINE');}});
  h.run("route='admin';routeVersion=3;root.innerHTML='EXISTING ADMIN DATA';");
  await h.run('refreshAdminIfCurrent(3)');
  assert.equal(h.element('platform-main').innerHTML,'EXISTING ADMIN DATA');
  assert.match(h.element('platform-toast').textContent,/刷新失败：OFFLINE/);
  h.run("route='judge-roadshow';editorDirty=true;root.innerHTML='EXISTING JUDGE DATA';");
  await h.run('refreshJudgeIfCurrent(3,true)');
  assert.equal(h.element('platform-main').innerHTML,'EXISTING JUDGE DATA');
  assert.equal(h.run('editorDirty'),true);
  assert.match(h.element('platform-toast').textContent,/刷新失败：OFFLINE/);
});
