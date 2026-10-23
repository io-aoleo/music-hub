/* Native Music Hub interaction layer. Task scheduling remains in index.html. */
const byId=id=>document.getElementById(id);
const platforms={netease:'网易云音乐',qq:'QQ 音乐',kuwo:'酷我音乐',kugou:'酷狗音乐',migu:'咪咕音乐'};
let musicSource='netease',searchResults=[],searchVersion=0,directoryPath='/music',csrfToken='';
let searchContext=null,searchLoading=false;
const selection=new Map();
const nativeFetch=window.fetch.bind(window);
const authReady=nativeFetch('/api/auth/status').then(r=>r.json()).then(state=>{csrfToken=state.csrf||'';return state});
window.fetch=async function(input,options={}){
 const method=(options.method||'GET').toUpperCase();
 const headers=new Headers(options.headers||{});
 if(!['GET','HEAD','OPTIONS'].includes(method)){await authReady;headers.set('X-CSRF-Token',csrfToken)}
 const response=await nativeFetch(input,{...options,headers});
 if(response.status===401)location.assign('/login');
 if(response.status===428)location.assign('/setup');
 return response;
};
function safeText(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function api(url,method='GET',body){
 const response=await fetch(url,{method,...(body===undefined?{}:{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})});
 const data=await response.json();if(!response.ok||data.ok===false)throw Error(data.msg||'请求失败，请稍后重试');return data;
}
function notify(message){byId('toast').textContent=message;clearTimeout(notify.timer);notify.timer=setTimeout(()=>byId('toast').textContent='',5000)}
function switchView(view){document.querySelectorAll('.feature-panel').forEach(p=>p.hidden=p.id!=='view-'+view);document.querySelectorAll('[data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view===view));if(view==='settings')loadPreferences();if(view==='downloads')loadDownloads()}
function songKey(song){return song.source+':'+song.id}
function updateSelection(){
 byId('selectionCount').textContent='已选 '+selection.size+' 首';byId('batchDownload').disabled=!selection.size;
 byId('selectPage').checked=searchResults.length>0&&searchResults.every(s=>selection.has(songKey(s)));
 byId('selectPage').indeterminate=searchResults.some(s=>selection.has(songKey(s)))&&!byId('selectPage').checked;
 document.querySelectorAll('.song-choice').forEach(input=>input.checked=selection.has(input.dataset.songKey));
}
function selectSearchPage(checked){for(const song of searchResults){if(checked){if(selection.size>=200&&!selection.has(songKey(song))){notify('每次最多选择 200 首');break}selection.set(songKey(song),song)}else selection.delete(songKey(song))}updateSelection()}
function clearSelection(){selection.clear();updateSelection()}
function renderSearchPage(data){
  searchResults=data.songs||[];byId('searchCount').textContent=data.total==null?' · 本页 '+searchResults.length+' 首':' · 共 '+data.total+' 首';const list=byId('searchResults');list.replaceChildren();list.className=searchResults.length?'':'empty';if(!searchResults.length)list.textContent=data.page>1?'这一页没有结果，可返回上一页':'未找到歌曲，请更换关键词或音乐来源';
  searchResults.forEach((song,index)=>{
   const row=document.createElement('div');row.className='track';
   const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.className='song-choice';checkbox.dataset.songKey=songKey(song);checkbox.setAttribute('aria-label','选择 '+song.name);
   checkbox.onchange=()=>{if(checkbox.checked){if(selection.size>=200){checkbox.checked=false;notify('每次最多选择 200 首');return}selection.set(songKey(song),song)}else selection.delete(songKey(song));updateSelection()};row.appendChild(checkbox);
   const content=document.createElement('div');content.style.display='contents';content.innerHTML='<small>'+String((data.page-1)*data.page_size+index+1).padStart(2,'0')+'</small><div class="track-title">'+safeText(song.name)+'</div><div class="artist">'+safeText(song.artist)+'</div><div class="album sub">'+safeText(song.album)+'</div>';row.appendChild(content);
   const button=document.createElement('button');button.textContent='↓ 下载';button.onclick=()=>downloadSong(song,button);row.appendChild(button);list.appendChild(row);
  });updateSelection();renderSearchPagination();
}
function renderSearchPagination(){
 const data=searchContext;byId('searchPagination').hidden=!data;
 byId('searchPrevious').disabled=searchLoading||!data||data.page<=1;
 byId('searchNext').disabled=searchLoading||!data||!data.has_more;
 byId('searchGoButton').disabled=searchLoading||!data;byId('searchPageSize').disabled=searchLoading;
 if(data){byId('searchPageInfo').textContent='第 '+data.page+(data.total_pages?' / '+data.total_pages:'')+' 页';byId('searchGoPage').max=data.total_pages||1000;byId('searchGoPage').value=data.page}
}
function goSearchPage(){const value=Number(byId('searchGoPage').value),max=searchContext?.total_pages||1000;if(!Number.isInteger(value)||value<1||value>max){notify('请输入 1～'+max+' 之间的页码');return}searchSongs(value)}
async function searchSongs(page=null){
 const navigation=Number.isInteger(page);if(navigation&&!searchContext)return;
 const query=navigation?searchContext.query:byId('searchQuery').value.trim();if(!query)return;
 const source=navigation?searchContext.source:musicSource,size=Number(byId('searchPageSize').value)||20;
 page=navigation?page:1;switchView('discover');const version=++searchVersion;
 searchLoading=true;byId('searchButton').disabled=true;byId('searchState').textContent='正在搜索 '+platforms[source]+' · 第 '+page+' 页…';renderSearchPagination();
 if(!searchContext){byId('searchResults').className='empty';byId('searchResults').textContent='正在寻找喜欢的旋律…'}
 try{
  const data=await api('/api/search?'+new URLSearchParams({q:query,source,page,page_size:size}));if(version!==searchVersion)return;
  searchContext={...data,query,source};renderSearchPage(searchContext);byId('searchState').textContent='';if(navigation)byId('searchResults').scrollIntoView({behavior:'smooth',block:'start'});
 }catch(error){if(version===searchVersion){if(!searchContext)byId('searchResults').textContent=error.message;byId('searchState').textContent=error.message+(searchContext?' · 仍显示上次成功加载的结果':'')}}
 finally{if(version===searchVersion){searchLoading=false;byId('searchButton').disabled=false;renderSearchPagination()}}
}
async function downloadSong(song,button){button.disabled=true;try{const data=await api('/api/downloads','POST',song);button.textContent='查看下载';button.onclick=()=>switchView('downloads');notify(data.added?'已加入下载「'+song.name+'」':'歌曲已在队列中，可到下载中心查看')}catch(error){notify(error.message)}finally{button.disabled=false}}
async function downloadSelected(){
 const songs=[...selection.values()];if(!songs.length)return;byId('batchDownload').disabled=true;
 try{const data=await api('/api/downloads','POST',{songs});for(const song of songs)selection.delete(songKey(song));updateSelection();notify('已添加 '+data.added+' 首，跳过 '+data.duplicates+' 首队列中的重复歌曲');switchView('downloads')}
 catch(error){notify(error.message);updateSelection()}
}
async function downloadAction(id,action){try{await api('/api/downloads/'+encodeURIComponent(id)+'/'+action,'POST',{});await loadDownloads()}catch(error){notify(error.message)}}
async function loadDownloads(){
 try{
  const data=await api('/api/downloads');const counts=data.counts||{};const total=Object.values(counts).reduce((a,b)=>a+b,0);const finished=(counts.done||0)+(counts.error||0)+(counts.interrupted||0)+(counts.cancelled||0);
  byId('downloadSummary').innerHTML=[['已完成',counts.done||0],['下载中',counts.running||0],['等待中',counts.queued||0],['失败 / 中断',(counts.error||0)+(counts.interrupted||0)]].map(([label,value])=>'<div class="card queue-count"><b>'+Number(value)+'</b>'+label+'</div>').join('');
  byId('queueProgress').textContent=total?'已处理 '+finished+' / '+total+' 首 · 已取消 '+(counts.cancelled||0)+' 首':'选择喜欢的歌曲，开始建立音乐库';byId('queueProgressBar').style.width=(total?Math.round(finished/total*100):0)+'%';
  const filter=byId('downloadFilter').value;const jobs=(data.downloads||[]).filter(j=>filter==='all'||filter==='active'&&['queued','running'].includes(j.status)||filter==='done'&&j.status==='done'||filter==='error'&&['error','interrupted'].includes(j.status));
  const list=byId('downloadList');list.replaceChildren();list.className=jobs.length?'':'empty';if(!jobs.length)list.textContent=filter==='all'?'暂无下载，去发现音乐勾选喜欢的歌曲':'此分类暂无记录';
  for(const job of jobs){
   const row=document.createElement('div');row.className='track download-track';row.innerHTML='<small>'+(job.status==='running'?'◷':job.status==='done'?'✓':job.status==='queued'?'…':'!')+'</small><div class="track-title">'+safeText(job.song.name)+'</div><div class="artist">'+safeText(job.song.artist)+'</div><div class="queue-message '+(job.status==='done'?'status-ok':['error','interrupted'].includes(job.status)?'status-error':'')+'">'+safeText(job.message)+'</div>';
   const action=document.createElement('div');if(['error','interrupted','cancelled'].includes(job.status)){const b=document.createElement('button');b.className='secondary';b.textContent='重试';b.onclick=()=>downloadAction(job.id,'retry');action.appendChild(b)}else if(job.status==='queued'){const b=document.createElement('button');b.className='secondary';b.textContent='取消';b.onclick=()=>downloadAction(job.id,'cancel');action.appendChild(b)}row.appendChild(action);list.appendChild(row);
  }
 }catch(error){byId('downloadList').textContent=error.message}
}
function showMapping(mapping){byId('mappingInfo').textContent='宿主机 '+mapping.host+' → 容器 '+mapping.container}
function updatePlatformStatus(tokens){Object.keys(platforms).forEach(k=>byId('token-status-'+k).textContent=tokens[k]?'已配置 · 留空保留':'尚未配置')}
async function refreshPlatformStatus(){const data=await api('/api/preferences');updatePlatformStatus(data.tokens)}
async function checkStorage(){
 const state=byId('storageStatus');state.textContent='正在检查目录和写入权限…';state.className='';
 try{const data=await api('/api/storage?'+new URLSearchParams({path:byId('downloadDir').value||'/music'}));showMapping(data.mapping);state.textContent=data.writable?'目录可写 · 运行用户 UID '+data.uid:data.error;state.className=data.writable?'status-ok':'status-error'}catch(error){state.textContent=error.message;state.className='status-error'}
}
async function loadPreferences(){
 byId('settingsState').textContent='正在读取设置…';
 try{const data=await api('/api/preferences');if(document.activeElement!==byId('downloadDir'))byId('downloadDir').value=data.downloadDir;showMapping(data.mapping);updatePlatformStatus(data.tokens);byId('settingsState').textContent='';await checkStorage()}catch(error){byId('settingsState').textContent=error.message}
}
async function savePreferences(){
 byId('savePreferencesButton').disabled=true;byId('settingsState').textContent='正在保存…';const tokens={};Object.keys(platforms).forEach(k=>{if(byId('clear-'+k).checked)tokens[k]='';else if(byId('token-'+k).value.trim())tokens[k]=byId('token-'+k).value.trim()});
 try{await api('/api/preferences','POST',{downloadDir:byId('downloadDir').value.trim(),tokens});Object.keys(platforms).forEach(k=>{byId('token-'+k).value='';byId('clear-'+k).checked=false});await loadPreferences();byId('settingsState').textContent='设置已保存';notify('下载路径和平台凭据已保存')}
 catch(error){byId('settingsState').textContent=error.message}finally{byId('savePreferencesButton').disabled=false}
}
async function openDirectoryPicker(){byId('storageDialog').showModal();await browseDirectory(byId('downloadDir').value||'/music')}
async function browseDirectory(path){
 byId('directoryState').textContent='正在读取目录…';byId('chooseDirectory').disabled=true;
 try{const data=await api('/api/storage?'+new URLSearchParams({path}));directoryPath=path;byId('directoryPath').textContent=path;byId('directoryList').replaceChildren();for(const child of data.directories){const b=document.createElement('button');b.className='directory-entry';b.textContent='▸　'+child.name;b.onclick=()=>browseDirectory(child.path);byId('directoryList').appendChild(b)}byId('directoryState').textContent=data.writable?(data.directories.length?'此目录可写':'此目录可写，暂无子目录'):data.error;byId('chooseDirectory').disabled=!data.writable}
 catch(error){byId('directoryState').textContent=error.message}
}
function browseParent(){if(directoryPath!=='/music')browseDirectory(directoryPath.slice(0,directoryPath.lastIndexOf('/'))||'/music')}
async function createDirectory(){const name=byId('newDirectoryName').value.trim();if(!name||name.includes('/')||name.includes('\\')||name==='.'||name==='..'){notify('请输入不含斜杠的子目录名称');return}try{const path=directoryPath+'/'+name;await api('/api/storage','POST',{path});byId('newDirectoryName').value='';await browseDirectory(path)}catch(error){byId('directoryState').textContent=error.message}}
function chooseDirectory(){byId('downloadDir').value=directoryPath;byId('storageDialog').close();checkStorage();notify('已选择目录，点击「保存设置」后生效')}
async function logout(){try{await api('/api/auth/logout','POST',{});location.assign('/login')}catch(error){notify(error.message)}}
document.addEventListener('DOMContentLoaded',async()=>{
 for(const [source,title] of Object.entries(platforms)){
  const button=document.createElement('button');button.textContent=title;button.type='button';button.className=source===musicSource?'active':'';button.onclick=()=>{musicSource=source;document.querySelectorAll('#sourceTabs button').forEach(x=>x.classList.toggle('active',x===button));if(byId('searchQuery').value.trim())searchSongs()};byId('sourceTabs').appendChild(button);
  const field=document.createElement('div');field.className='field';field.innerHTML='<label for="token-'+source+'">'+title+'</label><input type="password" autocomplete="new-password" id="token-'+source+'" placeholder="输入平台 Token 或完整 Cookie"><small id="token-status-'+source+'">尚未加载</small><label style="font-weight:400;margin-top:8px"><input style="width:auto" type="checkbox" id="clear-'+source+'"> 清除此平台凭据</label>';byId('tokenFields').appendChild(field);
 }
 try{const state=await authReady;if(state.username)byId('accountName').textContent=state.username;if(state.change_required){location.assign('/setup');return}if(new URLSearchParams(location.search).has('welcome')){byId('welcomeHint').textContent='账号设置完成。请确认下方目录映射与写入权限；平台 Token / Cookie 可按需配置。';switchView('settings');history.replaceState(null,'','/')}}catch(error){notify('账号状态读取失败，请刷新页面')}
 setInterval(()=>{if(!byId('view-downloads').hidden)loadDownloads()},2500);
});
