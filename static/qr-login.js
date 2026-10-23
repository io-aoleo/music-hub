/* QR login runs entirely inside Hub; only the scannable image and safe status reach the browser. */
let qrLogin=null,qrGeneration=0,qrPollTimer=null,qrCountdownTimer=null;

function stopQRLogin(){
 qrGeneration++;clearTimeout(qrPollTimer);clearInterval(qrCountdownTimer);
 byId('qrLoginImage').hidden=true;byId('qrLoginImage').removeAttribute('src');byId('qrLoginResult').hidden=true;
 const previous=qrLogin;qrLogin=null;
 if(previous?.id&&!previous.finished)api('/api/qr-login/'+encodeURIComponent(previous.id)+'/cancel','POST',{}).catch(()=>{});
}
function closeQRLogin(){stopQRLogin();byId('qrLoginDialog').close()}
function qrMessage(message,state=''){byId('qrLoginState').textContent=message;byId('qrLoginState').className=state==='success'?'status-ok':state==='error'?'status-error':''}
function qrCountdown(){
 if(!qrLogin)return;
 const remaining=Math.max(0,Math.ceil((qrLogin.expires-Date.now())/1000));
 byId('qrLoginCountdown').textContent=qrLogin.finished?'':remaining?'二维码剩余有效时间 '+remaining+' 秒':'二维码已过期';
 if(!remaining&&!qrLogin.finished){qrLogin.finished=true;clearTimeout(qrPollTimer);clearInterval(qrCountdownTimer);byId('qrLoginImage').hidden=true;byId('qrLoginImage').removeAttribute('src');qrMessage('二维码已过期，请刷新后重新扫码','error')}
}
async function startNeteaseQRLogin(){
 stopQRLogin();const generation=qrGeneration;
 const dialog=byId('qrLoginDialog');if(!dialog.open)dialog.showModal();
 byId('qrLoginImage').hidden=true;byId('qrLoginImage').removeAttribute('src');byId('qrLoginCountdown').textContent='';byId('qrLoginRefresh').disabled=true;qrMessage('正在向网易云请求二维码…');
 try{
  const data=await api('/api/qr-login/netease','POST',{});
  if(generation!==qrGeneration||!dialog.open){api('/api/qr-login/'+encodeURIComponent(data.id)+'/cancel','POST',{}).catch(()=>{});return}
  qrLogin={id:data.id,expires:Date.now()+data.expires_in*1000,interval:Math.max(1500,data.poll_interval||2500),finished:false,errors:0};
  byId('qrLoginImage').src=data.qr_image;byId('qrLoginImage').hidden=false;qrMessage('请打开网易云音乐 App 扫描二维码');qrCountdown();qrCountdownTimer=setInterval(qrCountdown,1000);qrPollTimer=setTimeout(()=>pollQRLogin(generation),qrLogin.interval);
 }catch(error){if(generation===qrGeneration)qrMessage(error.message,'error')}
 finally{if(generation===qrGeneration)byId('qrLoginRefresh').disabled=false}
}
async function pollQRLogin(generation){
 const current=qrLogin;if(generation!==qrGeneration||!current||current.finished||!byId('qrLoginDialog').open)return;
 qrCountdown();if(current.finished)return;
 if(document.hidden){qrPollTimer=setTimeout(()=>pollQRLogin(generation),current.interval);return}
 try{
  const data=await api('/api/qr-login/'+encodeURIComponent(current.id)+'/check','POST',{});
  if(generation!==qrGeneration||qrLogin!==current)return;
  current.errors=0;qrMessage(data.message,data.status==='success'?'success':['failed','expired','cancelled'].includes(data.status)?'error':'');
  if(data.status==='success'){
   byId('qrLoginImage').hidden=true;byId('qrLoginImage').removeAttribute('src');byId('qrLoginResult').hidden=false;
   current.finished=true;clearInterval(qrCountdownTimer);byId('qrLoginCountdown').textContent='凭据已保存到当前设备，重启服务后仍保留。';byId('token-netease').value='';byId('clear-netease').checked=false;
   try{await refreshPlatformStatus()}catch(error){notify('登录凭据已保存，平台状态可稍后重新加载')}
   notify('网易云扫码登录成功，凭据已自动保存');return;
  }
  if(['failed','expired','cancelled'].includes(data.status)){current.finished=true;clearInterval(qrCountdownTimer);byId('qrLoginImage').hidden=true;return}
 }catch(error){
  if(generation!==qrGeneration)return;
  current.errors++;qrMessage(error.message+(current.errors<3?'，正在重试…':'，请刷新二维码重试'),'error');
  if(current.errors>=3){current.finished=true;clearInterval(qrCountdownTimer);return}
 }
 if(generation===qrGeneration&&qrLogin===current&&!current.finished)qrPollTimer=setTimeout(()=>pollQRLogin(generation),current.interval);
}
document.addEventListener('DOMContentLoaded',()=>{
 const field=byId('token-netease').parentElement;
 const actions=document.createElement('div');actions.className='qr-platform-action';
 const button=document.createElement('button');button.type='button';button.id='neteaseQRLogin';button.textContent='扫码登录网易云';button.onclick=startNeteaseQRLogin;
 const hint=document.createElement('small');hint.textContent='推荐 · 手机确认后自动保存凭据';actions.append(button,hint);field.insertBefore(actions,byId('token-netease'));
 byId('qrLoginDialog').addEventListener('close',stopQRLogin);
});
