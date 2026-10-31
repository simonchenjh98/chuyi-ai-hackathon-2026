import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

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
const cfg = {minJudges:5, resultsPublished:true, scoringOpen:true};
const team = (n, extra = {}) => ({id:`T${n}`,number:n,name:`TEAM-${n}`,project:'project',judgeCount:5,score:80,rank:n,audienceVotes:0,...extra});

test('board presents rank order, then waiting teams, preserving a zero score', () => {
  const html = renderer()({teams:[team(1,{rank:null,score:null}),team(3,{rank:2,score:0}),team(2,{rank:1,score:90})],config:cfg});
  assert.ok(html.indexOf('TEAM-2') < html.indexOf('TEAM-3'));
  assert.ok(html.indexOf('TEAM-3') < html.indexOf('TEAM-1'));
  assert.match(html,/0\.00/);
  assert.match(html,/等待评审/);
});

test('public team text cannot inject HTML or disclose unprovided judge data', () => {
  const html = renderer()({teams:[team(1,{name:'<img src=x onerror=alert(1)>',project:'<script>secret</script>'})],config:cfg});
  assert.ok(!html.includes('<img src=x'));
  assert.ok(!html.includes('<script>secret'));
  assert.match(html,/&lt;img/);
});

test('screen mode rotates eight teams and leaves full metrics intact', () => {
  const data = {teams:Array.from({length:10},(_,i)=>team(i+1)),config:cfg};
  const first = renderer(true)(data);
  const second = renderer(true,13000)(data);
  assert.match(first,/第 1 \/ 2 屏/);
  assert.ok(first.includes('TEAM-8'));
  assert.ok(!first.includes('TEAM-9'));
  assert.match(second,/第 2 \/ 2 屏/);
  assert.ok(second.includes('TEAM-9'));
  assert.ok(!second.includes('TEAM-1<'));
  assert.match(second,/>10<\/strong>/);
});

test('unpublished scores and an empty event have explicit states', () => {
  const html = renderer()({teams:[team(1,{score:null,rank:null})],config:{...cfg,resultsPublished:false}});
  assert.match(html,/暂未发布/);
  assert.match(renderer()({teams:[],config:cfg}),/本届队伍尚未录入/);
});

const awards = [
  ['creativity', '最佳创意奖'], ['technology', '最佳技术实现奖'],
  ['potential', '最具应用潜力奖'], ['care', '最具社会关怀奖'],
].map(([id, name], i) => ({id, name, score:91.1+i, leaders:[`T${i+1}`], winner:null, winnerConfirmed:false, tied:false}));
function finalData() {
  return {
    config:{...cfg, finalResultsPublished:true, finalMinJudges:3, finalScoringOpen:false},
    finalists:Array.from({length:4}, (_, i) => team(i+1, {project:`PROJECT-${i+1}`, finalJudgeCount:3, finalScores:[91.1+i, 92.2+i, 93.3+i, 94.4+i]})),
    awards:awards.map(a=>({...a, leaders:[...a.leaders]})),
  };
}
const cards = html => [...html.matchAll(/<article class="surface award-card">([\s\S]*?)<\/article>/g)].map(m=>m[1]);

test('final board presents four independent award scores and candidates', () => {
  const html = renderer(false, 0, 'final')(finalData());
  const rendered = cards(html);
  assert.equal(rendered.length, 4);
  awards.forEach((award, i) => {
    assert.ok(rendered[i].includes(`<h2>${award.name}</h2>`));
    assert.ok(rendered[i].includes(`<strong class="award-winner">TEAM-${i+1}</strong>`));
    assert.ok(rendered[i].includes(`${award.score.toFixed(2)}<small> / 100</small>`));
    assert.match(rendered[i], /当前最高分候选/);
  });
  assert.match(html, /四个方向分别评选/);
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

function browserHarness({hash='#admin', confirm=()=>false, fetch}={}) {
  const nodes = new Map(), listeners = new Map(), requests = [];
  const fields = {activeStage:'roadshow', finalistCount:'6', minJudges:'3', finalMinJudges:'3'};
  function element(id) {
    if(nodes.has(id)) return nodes.get(id);
    const controls = new Map();
    const node = {
      innerHTML:'', textContent:'', disabled:false, isConnected:true,
      classList:{contains:()=>false, add(){}, remove(){}, toggle(){}},
      elements:new Proxy({}, {get:(_, key)=>{
        if(!controls.has(key)) controls.set(key, {value:fields[key]||'', checked:false});
        return controls.get(key);
      }}),
      querySelector:selector=>element(`${id}/${selector}`), querySelectorAll:()=>[],
      addEventListener(){}, setAttribute(){}, removeAttribute(){},
    };
    nodes.set(id,node);
    return node;
  }
  const data = {
    teams:[], judges:[], awards:[], finalists:[], myScores:[], dimensions:[],
    qualification:{confirmed:false, ready:false},
    config:{activeStage:'roadshow', finalistCount:6, minJudges:3, finalMinJudges:3},
  };
  const context = vm.createContext({
    document:{getElementById:element, querySelectorAll:()=>[], body:{classList:{contains:()=>false, remove(){}, toggle(){}}}},
    location:{href:`https://example.test/chuyi/platform.html${hash}`, hash},
    window:{addEventListener:(name,handler)=>listeners.set(name,handler)},
    URL, Date, setTimeout:()=>0, clearTimeout(){}, confirm,
    fetch:async(url,options)=>{
      requests.push({path:url.pathname, options});
      const result = fetch ? await fetch(url,options) : data;
      return {ok:true, json:async()=>result};
    },
  });
  vm.runInContext(eventSource,context);
  return {context, nodes, requests, element, run:code=>vm.runInContext(code,context), dispatch:name=>listeners.get(name)?.()};
}

test('shared judge login only offers identities from the current stage', () => {
  const h=browserHarness({hash:'#judge-final'});
  const accounts="[{id:'R1',name:'路演一',judgeStage:'roadshow'},{id:'F1',name:'决赛一',judgeStage:'final'},{id:'F2',name:'决赛二',judgeStage:'final'}]";
  assert.equal(h.run(`JSON.stringify(selectableAccounts('judge',${accounts},'final').map(a=>a.id))`),'["F1","F2"]');
  assert.equal(h.run(`JSON.stringify(selectableAccounts('judge',${accounts},'roadshow').map(a=>a.id))`),'["R1"]');
  assert.equal(h.run(`selectableAccounts('admin',${accounts},'final').length`),3);
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
  const adminData={teams:[],judges:[],awards:[],finalists:[],qualification:{confirmed:false,ready:false},config:{activeStage:'roadshow',finalistCount:6,minJudges:3,finalMinJudges:3}};
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
  h.run("route='judge-roadshow';root.innerHTML='EXISTING JUDGE DATA';");
  await h.run('refreshJudgeIfCurrent(3)');
  assert.equal(h.element('platform-main').innerHTML,'EXISTING JUDGE DATA');
  assert.match(h.element('platform-toast').textContent,/刷新失败：OFFLINE/);
});
