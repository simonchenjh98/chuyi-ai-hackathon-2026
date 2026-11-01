'use strict';
if (location.hostname.endsWith('.github.io')) location.replace('https://8.141.114.201/chuyi/submit.html' + location.hash);
const root = document.getElementById('main');
const base = new URL('./', location.href);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = t => String(t.number).padStart(2, '0');
const label = t => `${number(t)} · ${t.name}`;
const bytes = n => n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.ceil(n / 1024))} KB`;
const dateText = n => n ? new Date(n).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai',hour12:false}) : '—';
let teams = [], mine = null, token = '', studentTeamId = '', routeId = 0, pending = false, dirty = false;
let adminTeams = [], selected = new Set(), search = '', statusFilter = 'all', fileKind = 'all', refreshTimer, toastTimer;
let acceptedHash = location.hash, restoringHash = false;
function toast(message) { const el=document.getElementById('toast');el.textContent=message;el.classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('visible'),5000); }
function savedToken(id) { try { return localStorage.getItem(`chuyi-submission-${id}`) || ''; } catch { return ''; } }
function keepToken(id,value) { try { localStorage.setItem(`chuyi-submission-${id}`,value);return localStorage.getItem(`chuyi-submission-${id}`)===value; } catch { return false; } }
function safeUrl(url) { try { const u=new URL(url);return ['https:','http:'].includes(u.protocol) ? u.href : ''; } catch { return ''; } }
async function request(path, options={}) {
  const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),options.timeout||25000);
  const headers={...options.headers};if(options.student&&token)headers.Authorization=`Bearer ${token}`;
  if(options.data!==undefined)headers['Content-Type']='application/json';
  try {
    const res=await fetch(new URL(`api/${path}`,base), {method:options.method||(options.data!==undefined?'POST':'GET'),credentials:'same-origin',cache:'no-store',headers,body:options.data!==undefined?JSON.stringify(options.data):undefined,signal:controller.signal});
    if(!res.ok){let body;try{body=await res.json();}catch{}const e=new Error(body?.error||`请求未成功（${res.status}），请重试。`);e.status=res.status;throw e;}
    return options.blob ? res.blob() : res.json();
  } catch(e) { if(e.name==='AbortError')throw new Error('连接超时，请重试；提交操作请先刷新核对是否已保存。');throw e; }
  finally { clearTimeout(timer); }
}
function heading(admin=false) { return `<div class="intro"><div><span class="kicker">${admin?'TEACHER DESK / 老师工作台':'PROJECT DELIVERY / 作品交付'}</span><h1>${admin?'按队伍，一次收齐。':'把你们的想法，交上来。'}</h1><p>${admin?'队号顺序查看全部作品；多选几个组，PPT 和网页一次打包。':'选择自己的队伍，提交 PPT 或演示／游戏网页。任何设备选择本组，即可继续修改。'}</p></div><span class="pill"><span class="dot"></span>${admin?'作品集中管理':'按报名队号提交 · 云端保存'}</span></div>`; }
function errorState(error) { root.innerHTML=`${heading(location.hash==='#admin')}<section class="card empty"><h2>暂时无法连接作品平台</h2><p>${esc(error.message)}</p><button class="btn" id="retry">重新连接 ↗</button></section>`;document.getElementById('retry').onclick=render; }
function setPending(value) { pending=value;root.querySelectorAll('button,input,textarea,select').forEach(el=>{if(!el.dataset.keepEnabled)el.disabled=value;}); }
function downloadBlob(blob,name) { const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000); }
async function fileDownload(file,student=false,button=null) { if(!file){toast('附件列表已变化，请刷新后重试。');return;}if(button)button.disabled=true;try { const blob=await request(`submissions/files/${encodeURIComponent(file.id)}`,{student,blob:true,timeout:180000});downloadBlob(blob,file.name); } catch(e){toast(e.message);}finally{if(button?.isConnected)button.disabled=false;} }
async function render() {
  const version=++routeId;clearTimeout(refreshTimer);dirty=false;
  const admin=location.hash==='#admin';document.getElementById('admin-nav').classList.toggle('active',admin);document.getElementById('student-nav').classList.toggle('active',!admin);
  root.innerHTML='<div class="loading">正在连接作品平台…</div>';
  try { if(admin){await loadAdmin(version);}else{const data=await request('submissions/teams');if(version!==routeId)return;teams=[...(data.teams||[])].sort((a,b)=>a.number-b.number);renderStudent();} }catch(e){if(version===routeId)errorState(e);}
}
function renderStudent() {
  root.innerHTML=heading()+`<div class="layout"><aside class="card side"><h2 class="step"><span class="step-num">01</span>选择你的队伍</h2><form id="team-login"><label class="field">报名队号 · 队伍名称<select name="teamId" id="team-select" required><option value="">请选择自己的队伍</option>${teams.map(t=>`<option value="${esc(t.id)}" ${t.id===studentTeamId?'selected':''}>${esc(label(t))}${t.submitted?' · 已交':''}</option>`).join('')}</select></label><p class="error" role="alert" id="login-error"></p><button class="btn full" type="submit">进入本组提交 ↗</button></form><div class="team-detail" id="team-detail"></div><ul class="checklist"><li>按报名队号选择，别选错组</li><li>PPT、演示／游戏网页，至少交一项</li><li>最多 6 个附件，不限制单文件大小</li></ul></aside><div id="editor"><section class="card empty"><span class="kicker">YOUR NEXT BIG IDEA</span><h2 class="section-gap">作品准备好了，就从这里提交。</h2><p>先在左侧选择自己的队伍并进入。<br>可交 PPT、PDF、HTML、网页 ZIP，或在线演示链接。</p></section><div class="note warm"><strong>想让老师完整下载网页？</strong><br>请上传单个 HTML 文件，或把网页和图片、脚本等素材一起打成 ZIP。只填在线链接时，下载包将保存链接与说明，不能保证离线运行。</div></div></div>`;
  const select=document.getElementById('team-select');select.onchange=showTeamDetail;showTeamDetail();
  document.getElementById('team-login').onsubmit=async e=>{
    e.preventDefault();if(pending)return;const form=e.currentTarget, id=form.elements.teamId.value;
    if(dirty&&!confirm('当前作品信息尚未确认提交，确定重新进入或切换队伍吗？'))return;
    document.getElementById('login-error').textContent='';setPending(true);
    try {
      const result=await request('submissions/login',{data:{teamId:id}});
      token=result.token;if(!token)throw new Error('登录凭证缺失，请重试。');studentTeamId=id;
      keepToken(id,token);mine=result.team?result:await request('submissions/mine',{student:true});
      dirty=false;renderEditor();showTeamDetail();
    }catch(error){document.getElementById('login-error').textContent=error.message;}finally{setPending(false);}
  };
  if(token&&mine&&studentTeamId){renderEditor();}
}
function showTeamDetail() {
  const t=teams.find(t=>t.id===document.getElementById('team-select')?.value),el=document.getElementById('team-detail');
  if(!el)return;el.innerHTML=t?`<span class="kicker">TEAM ${number(t)}</span><strong>${esc(t.name)}</strong><p>${esc(t.project||'作品名称待补充')}</p><span class="chip ${t.submitted?'':'pending'}">${t.submitted?'已有作品提交':'等待本组提交'}</span>`:'<p>所有队伍按报名编号排列。</p>';
}
function renderEditor() {
  const el=document.getElementById('editor');if(!el||!mine)return;
  const t=mine.team||teams.find(t=>t.id===studentTeamId),s=mine.submission||{},files=mine.files||[];
  el.innerHTML=`<section class="card"><div class="actions editor-heading"><h2 class="step editor-title"><span class="step-num">02</span>第 ${number(t)} 队 · ${esc(t.name)}</h2></div><div id="saved-banner">${s.updatedAt&&(s.title||files.length||s.demoUrl)?`<div class="success-banner"><strong>本组信息已保存 ✓</strong>最近保存：${dateText(s.updatedAt)}（北京时间）。${files.length||s.demoUrl?'作品已在云端，可继续更新。':'请继续上传附件或填写演示链接。'}</div>`:''}</div><form id="submission-form"><label class="field">作品名称 <span aria-hidden="true">*</span><input name="title" required maxlength="140" placeholder="给你们的作品起个名字" value="${esc(s.title||t.project||'')}"></label><label class="field">一句话介绍<textarea name="summary" maxlength="2000" rows="3" placeholder="你们做了什么？解决了什么问题？">${esc(s.summary||'')}</textarea></label><label class="field">演示／游戏网页链接<input name="demoUrl" type="url" maxlength="2000" placeholder="https://…" value="${esc(s.demoUrl||'')}"><small>有在线网页时填写；也可以直接上传下方的 HTML 或 ZIP 文件。</small></label><h3>上传作品附件</h3><div class="upload-grid"><label class="upload-box"><span class="upload-icon" aria-hidden="true">↥</span><b>PPT / 展示文稿</b><small>PPT、PPTX 或 PDF<br>不限制单文件大小</small><input id="ppt-upload" type="file" accept=".ppt,.pptx,.pdf" multiple aria-label="选择 PPT 或 PDF 文件"></label><label class="upload-box"><span class="upload-icon" aria-hidden="true">⌘</span><b>演示 / 游戏网页</b><small>HTML、HTM 或 ZIP<br>多文件网页请整体打包 ZIP</small><input id="web-upload" type="file" accept=".html,.htm,.zip" multiple aria-label="选择 HTML 或网页 ZIP"></label></div><p class="small">选中文件后自动上传。已上传文件与本组绑定，老师可直接下载。</p><div id="upload-progress" class="progress-wrap" role="status" hidden><span id="upload-status"></span><progress id="upload-bar" max="100" value="0"></progress></div><div id="files-list"></div><p class="error" id="save-error" role="alert"></p><div class="submit-footer"><span class="small">PPT、网页文件或在线链接，至少提交一项。<br>最后请点击“确认提交作品”，保存作品名称和介绍。</span><button class="btn" type="submit">确认提交作品 ↗</button></div></form></section><div class="note warm"><strong>网页下载说明</strong><br>上传单个 HTML 或包含素材的 ZIP，老师就能完整下载原文件。仅填写在线链接时，下载包会附网页链接说明；第三方在线网页不会自动抓取为离线游戏。</div>`;
  renderFiles();
  const form=document.getElementById('submission-form');form.addEventListener('input',()=>{dirty=true;});
  form.onsubmit=saveSubmission;
  document.getElementById('ppt-upload').onchange=e=>uploadFiles([...e.target.files],'ppt',e.target);
  document.getElementById('web-upload').onchange=e=>uploadFiles([...e.target.files],'web',e.target);
}
function renderFiles() {
  const el=document.getElementById('files-list');if(!el)return;const files=mine.files||[];
  el.innerHTML=files.length?`<div class="section-gap"><h3>已上传 ${files.length} / 6 个文件</h3>${files.map(f=>`<div class="file-row"><span class="file-kind">${f.kind==='ppt'?'PPT':'WEB'}</span><span class="file-label"><strong>${esc(f.name)}</strong><small>${bytes(f.size)} · 已上传</small></span><button class="btn secondary sm" type="button" data-file-download="${esc(f.id)}">下载</button><button class="btn danger sm" type="button" data-file-delete="${esc(f.id)}">删除</button></div>`).join('')}</div>`:'<p class="small section-gap">还没有上传附件；也可以只提交上方的在线演示链接。</p>';
  el.querySelectorAll('[data-file-download]').forEach(b=>b.onclick=()=>fileDownload(files.find(f=>f.id===b.dataset.fileDownload),true,b));
  el.querySelectorAll('[data-file-delete]').forEach(b=>b.onclick=async()=>{
    if(pending)return;const f=files.find(f=>f.id===b.dataset.fileDelete);if(!confirm(`删除本组附件“${f.name}”？`))return;
    setPending(true);try{await request(`submissions/files/${encodeURIComponent(f.id)}`,{method:'DELETE',student:true});mine.files=files.filter(x=>x.id!==f.id);renderFiles();toast('附件已删除。');}catch(e){toast(e.message);}finally{setPending(false);}
  });
}
function uploadOne(file,kind,index,total) {
  return new Promise((resolve,reject)=>{
    const xhr=new XMLHttpRequest();xhr.open('POST',new URL(`api/submissions/upload/${kind}`,base));xhr.timeout=0;xhr.withCredentials=true;xhr.setRequestHeader('Authorization',`Bearer ${token}`);xhr.setRequestHeader('X-File-Name',encodeURIComponent(file.name));xhr.setRequestHeader('Content-Type','application/octet-stream');
    const status=document.getElementById('upload-status'),bar=document.getElementById('upload-bar');
    status.textContent=`正在上传 ${index} / ${total}：${file.name}`;bar.value=0;
    xhr.upload.onprogress=e=>{if(e.lengthComputable){bar.value=Math.round(e.loaded/e.total*100);status.textContent=`${index} / ${total} · ${file.name} · ${bar.value}%${bar.value===100?' · 云端保存中…':''}`;}};
    xhr.onload=()=>{let result;try{result=JSON.parse(xhr.responseText);}catch{}if(xhr.status>=200&&xhr.status<300)resolve(result);else reject(new Error(result?.error||`上传失败（${xhr.status}），请重新选择文件重试。`));};
    xhr.onerror=()=>reject(new Error('上传连接中断，请重新连接后核对文件列表，再选择未完成的文件重试。'));
    xhr.ontimeout=()=>reject(new Error('上传超时，请重新连接后核对文件列表，再重试未完成的文件。'));xhr.send(file);
  });
}
async function uploadFiles(files,kind,input) {
  if(!files.length||pending)return;const error=document.getElementById('save-error');error.textContent='';
  const allowed=kind==='ppt'?/\.(ppt|pptx|pdf)$/i:/\.(html?|zip)$/i;
  if((mine.files||[]).length+files.length>6){error.textContent='每组最多 6 个附件，请减少文件数量，或先删除旧文件。';input.value='';return;}
  for(const f of files){if(!allowed.test(f.name)){error.textContent='文件格式不支持，请按上传区域选择 PPT/PDF 或 HTML/ZIP。';input.value='';return;}if(f.size===0){error.textContent=`“${f.name}”是空文件，请检查后重试。`;input.value='';return;}}
  setPending(true);const progress=document.getElementById('upload-progress');progress.hidden=false;
  try { for(let i=0;i<files.length;i++){await uploadOne(files[i],kind,i+1,files.length);const fresh=await request('submissions/mine',{student:true});mine={...mine,...fresh};renderFiles();}toast(`${files.length} 个文件已上传，请确认作品信息并点击提交。`); }
  catch(e){error.textContent=e.message;try{mine=await request('submissions/mine',{student:true});renderFiles();}catch{}}
  finally{progress.hidden=true;input.value='';setPending(false);}
}
async function saveSubmission(event) {
  event.preventDefault();if(pending)return;const form=event.currentTarget,error=document.getElementById('save-error');error.textContent='';
  const data={title:form.elements.title.value.trim(),summary:form.elements.summary.value.trim(),demoUrl:form.elements.demoUrl.value.trim()};
  if(!data.title){error.textContent='请填写作品名称。';return;}
  if(data.demoUrl&&!safeUrl(data.demoUrl)){error.textContent='网页链接请使用完整的 http:// 或 https:// 地址。';return;}
  if(!(mine.files||[]).length&&!data.demoUrl){error.textContent='请上传 PPT / 网页文件，或填写在线演示链接，至少提交一项。';return;}
  setPending(true);
  try {
    await request('submissions/save',{data,student:true});mine=await request('submissions/mine',{student:true});dirty=false;
    const t=teams.find(t=>t.id===studentTeamId);if(t)t.submitted=true;
    document.getElementById('saved-banner').innerHTML=`<div class="success-banner"><strong>作品提交成功 ✓</strong>第 ${number(mine.team)} 队 · ${esc(mine.team.name)}<br>保存于 ${dateText(mine.submission?.updatedAt||Date.now())}（北京时间）。老师已能查看并下载。</div>`;
    showTeamDetail();toast('作品已提交，老师可以查看和下载了。');document.getElementById('saved-banner').scrollIntoView({behavior:'smooth',block:'center'});
  }catch(e){error.textContent=e.message;}finally{setPending(false);}
}
async function loadAdmin(version) {
  try { const data=await request('submissions/admin');if(version!==routeId)return;adminTeams=[...(data.teams||[])].sort((a,b)=>a.number-b.number);renderAdmin();scheduleAdminRefresh(); }
  catch(e){if(version!==routeId)return;if(e.status===401||e.status===403)renderAdminLogin();else throw e;}
}
function renderAdminLogin() {
  root.innerHTML=heading(true)+`<section class="card admin-login"><h2>老师／组织方登录</h2><p>使用组织方邀请码进入，查看所有队伍作品并批量下载。</p><form id="admin-login"><label class="field">组织方邀请码<input name="code" type="password" inputmode="numeric" required maxlength="160" autocomplete="off" placeholder="请输入组织方邀请码"></label><p class="error" role="alert"></p><button class="btn full" type="submit">进入作品后台 ↗</button></form><p><a class="text-link" href="platform.html#admin">返回原组织方平台 ↗</a></p></section>`;
  document.getElementById('admin-login').onsubmit=async e=>{
    e.preventDefault();const form=e.currentTarget,button=form.querySelector('button'),err=form.querySelector('.error');err.textContent='';button.disabled=true;
    try{let data=await request('login',{data:{role:'admin',code:form.elements.code.value.trim()}});if(data.selectAccount&&data.accounts?.length){data=await request('login',{data:{role:'admin',code:form.elements.code.value.trim(),accountId:data.accounts[0].id}});}await loadAdmin(routeId);}catch(error){err.textContent=error.message;}finally{if(button.isConnected)button.disabled=false;}
  };
}
function renderAdmin() {
  root.innerHTML=heading(true)+`<div class="stats" id="admin-stats"></div><div class="toolbar"><div class="filters"><input id="search" type="search" placeholder="搜索队号、队名、作品" aria-label="搜索队伍或作品" value="${esc(search)}"><select id="status-filter" aria-label="按提交状态筛选"><option value="all">全部队伍</option><option value="submitted">已提交</option><option value="pending">未提交</option></select></div><div class="actions"><button class="btn secondary sm" id="refresh-admin">刷新列表 ↻</button><button class="btn secondary sm" id="logout-admin">退出后台</button></div></div><div class="batch"><strong id="selected-count">已选择 0 组</strong><select id="download-kind" aria-label="选择打包内容"><option value="all">PPT + 网页（全部）</option><option value="ppt">仅 PPT / PDF</option><option value="web">仅演示 / 游戏网页</option></select><button class="btn" id="batch-download" disabled>一键下载所选组 ↓</button><button class="btn secondary sm" id="clear-selection">取消选择</button></div><div class="note">作品按队号顺序排列。勾选多组后，下载包会按“队号_队名”分文件夹保存。网页原文件会保留；只有在线链接的组会附链接说明。</div><div class="table-scroll"><table><thead><tr><th><input id="select-all" type="checkbox" aria-label="全选当前显示的已提交队伍"></th><th>队伍</th><th>提交状态</th><th>作品 / 演示链接</th><th>附件下载</th><th>管理</th></tr></thead><tbody id="admin-rows"></tbody></table></div><div class="table-foot"><span id="list-count"></span><span id="updated-at"></span></div><p class="error" id="admin-error" role="alert"></p>`;
  document.getElementById('status-filter').value=statusFilter;document.getElementById('download-kind').value=fileKind;
  document.getElementById('search').oninput=e=>{search=e.target.value;renderAdminRows();};
  document.getElementById('status-filter').onchange=e=>{statusFilter=e.target.value;renderAdminRows();};
  document.getElementById('download-kind').onchange=e=>{fileKind=e.target.value;};
  document.getElementById('refresh-admin').onclick=refreshAdmin;
  document.getElementById('logout-admin').onclick=async()=>{try{await request('logout',{data:{}});clearTimeout(refreshTimer);renderAdminLogin();}catch(e){toast(e.message);}};
  document.getElementById('select-all').onchange=e=>{shownTeams().filter(t=>isSubmitted(t)).forEach(t=>e.target.checked?selected.add(t.id):selected.delete(t.id));renderAdminRows();};
  document.getElementById('clear-selection').onclick=()=>{selected.clear();renderAdminRows();};
  document.getElementById('batch-download').onclick=batchDownload;
  renderAdminRows();
}
function isSubmitted(t){return Boolean(t.submitted||(t.files||[]).length||t.submission?.demoUrl);}
function shownTeams(){const q=search.toLocaleLowerCase().trim();return adminTeams.filter(t=>(statusFilter==='all'||isSubmitted(t)===(statusFilter==='submitted'))&&(!q||`${t.number} ${number(t)} ${t.name} ${t.project||''} ${t.submission?.title||''}`.toLocaleLowerCase().includes(q)));}
function renderAdminRows() {
  if(!document.getElementById('admin-rows'))return;const shown=shownTeams(),valid=new Set(adminTeams.filter(isSubmitted).map(t=>t.id));selected=new Set([...selected].filter(id=>valid.has(id)));
  const count=adminTeams.filter(isSubmitted).length,totalFiles=adminTeams.reduce((n,t)=>n+(t.files||[]).length,0);
  document.getElementById('admin-stats').innerHTML=`<div class="stat"><b>${count} <span class="stat-denominator">/ ${adminTeams.length}</span></b><span>队伍已提交作品</span></div><div class="stat"><b>${totalFiles}</b><span>个附件可下载</span></div><div class="stat"><b>${adminTeams.length-count}</b><span>队伍等待提交</span></div>`;
  document.getElementById('admin-rows').innerHTML=shown.length?shown.map(t=>{
    const s=t.submission||{},url=safeUrl(s.demoUrl),files=t.files||[],submitted=isSubmitted(t);
    return `<tr class="${selected.has(t.id)?'selected':''}"><td><input type="checkbox" data-team-check="${esc(t.id)}" aria-label="选择第${number(t)}队 ${esc(t.name)}" ${selected.has(t.id)?'checked':''} ${submitted?'':'disabled'}></td><td><span class="team-num">TEAM ${number(t)}</span><strong class="team-title">${esc(t.name)}</strong></td><td><span class="chip ${submitted?'':'pending'}">${submitted?'已提交':'待提交'}</span><small class="small">${s.updatedAt?dateText(s.updatedAt):''}</small></td><td><strong class="project-title">${esc(s.title||t.project||'尚未填写')}</strong>${s.summary?`<small class="small">${esc(s.summary.length>100?s.summary.slice(0,100)+'…':s.summary)}</small>`:''}${url?`<a class="text-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">打开演示／游戏网页 ↗</a>`:''}</td><td><div class="file-links">${files.map(f=>`<button class="text-link" data-admin-download="${esc(f.id)}">${f.kind==='ppt'?'PPT':'WEB'} · ${esc(f.name)} <span class="small inline-meta">${bytes(f.size)}</span></button>`).join('')||'<span class="small">'+(url?'仅在线链接；打包时附链接说明':'暂无附件')+'</span>'}</div></td><td><button class="btn secondary sm" data-reset-team="${esc(t.id)}" title="保留作品，注销本组现有登录凭证">注销本组登录</button></td></tr>`;
  }).join(''):'<tr><td colspan="6"><div class="empty">没有匹配的队伍，试试调整搜索或筛选。</div></td></tr>';
  document.querySelectorAll('[data-team-check]').forEach(el=>el.onchange=()=>{el.checked?selected.add(el.dataset.teamCheck):selected.delete(el.dataset.teamCheck);el.closest('tr').classList.toggle('selected',el.checked);updateSelection();});
  document.querySelectorAll('[data-admin-download]').forEach(button=>button.onclick=()=>{const file=adminTeams.flatMap(t=>t.files||[]).find(f=>f.id===button.dataset.adminDownload);fileDownload(file,false,button);});
  document.querySelectorAll('[data-reset-team]').forEach(button=>button.onclick=()=>resetTeam(button.dataset.resetTeam,button));
  document.getElementById('list-count').textContent=`显示 ${shown.length} / ${adminTeams.length} 支队伍 · 按队号排序`;
  document.getElementById('updated-at').textContent=`最近同步 ${new Date().toLocaleTimeString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})} · 每 10 秒刷新`;
  updateSelection();
}
function updateSelection() {
  const enabled=shownTeams().filter(isSubmitted),all=document.getElementById('select-all');
  if(!all)return;all.checked=enabled.length>0&&enabled.every(t=>selected.has(t.id));all.indeterminate=enabled.some(t=>selected.has(t.id))&&!all.checked;all.disabled=enabled.length===0;
  document.getElementById('selected-count').textContent=`已选择 ${selected.size} 组`;
  document.getElementById('batch-download').disabled=!selected.size||pending;
}
async function batchDownload() {
  if(pending||!selected.size)return;const button=document.getElementById('batch-download'),error=document.getElementById('admin-error');error.textContent='';pending=true;button.disabled=true;const old=button.textContent;button.textContent='正在打包，请稍候…';
  try{const teamIds=adminTeams.filter(t=>selected.has(t.id)).map(t=>t.id);const blob=await request('submissions/download',{data:{teamIds,kind:fileKind},blob:true,timeout:300000});downloadBlob(blob,`初一黑客松_${teamIds.length}组_${fileKind==='ppt'?'PPT':fileKind==='web'?'网页':'全部作品'}_${new Date().toLocaleDateString('sv-SE',{timeZone:'Asia/Shanghai'})}.zip`);toast('作品包已生成，浏览器已开始下载。');}
  catch(e){error.textContent=e.message;}finally{pending=false;if(button.isConnected){button.textContent=old;updateSelection();}}
}
async function resetTeam(id,button) {
  const t=adminTeams.find(t=>t.id===id);if(!confirm(`注销第${number(t)}队“${t.name}”的现有登录？作品会保留，各设备重新选择本组即可继续修改。`))return;
  button.disabled=true;try{await request('submissions/admin/reset',{data:{teamId:id}});toast('本组现有登录已注销，重新选择队伍即可进入。');}catch(e){toast(e.message);}finally{if(button.isConnected)button.disabled=false;}
}
async function refreshAdmin() {
  if(pending)return;const version=routeId,button=document.getElementById('refresh-admin');if(button)button.disabled=true;
  try{const data=await request('submissions/admin');if(version!==routeId)return;adminTeams=[...(data.teams||[])].sort((a,b)=>a.number-b.number);renderAdminRows();document.getElementById('admin-error').textContent='';}
  catch(e){if(version===routeId){if(e.status===401||e.status===403){clearTimeout(refreshTimer);renderAdminLogin();}else{const el=document.getElementById('admin-error');if(el)el.textContent=`同步暂时中断：${e.message} 保留当前列表与选择，可稍后刷新。`;}}}
  finally{if(button?.isConnected)button.disabled=false;}
}
function scheduleAdminRefresh(){clearTimeout(refreshTimer);const version=routeId;refreshTimer=setTimeout(async()=>{if(version!==routeId||location.hash!=='#admin')return;await refreshAdmin();if(document.getElementById('admin-rows'))scheduleAdminRefresh();},10000);}
window.addEventListener('beforeunload',event=>{if(pending||dirty){event.preventDefault();event.returnValue='';}});
window.addEventListener('hashchange',()=>{
  if(restoringHash){restoringHash=false;return;}
  if(pending||(dirty&&!confirm('作品信息尚未确认提交，确定离开吗？'))){
    if(pending)toast('操作正在进行，请完成后再切换页面。');
    restoringHash=true;location.hash=acceptedHash;return;
  }
  acceptedHash=location.hash;render();
});
render();
