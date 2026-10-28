/* Offline, frame-by-frame export through the plugin's FFmpeg encoder. */
async function mediaCall(arguments_) {
  const response=await request('tools/call',{name:'structure_media_export',arguments:arguments_},660000);
  if(response.isError||!response.structuredContent)throw Error(response.content?.find(c=>c.text)?.text||'导出失败');
  return response.structuredContent;
}
async function uploadMedia(id,bytes,cancelled=()=>false){
  const size=65536;
  for(let offset=0,chunk=0;offset<bytes.length;offset+=size,chunk++){
    if(cancelled())throw Error('已取消导出');
    const data=btoa(String.fromCharCode(...bytes.subarray(offset,offset+size)));
    await mediaCall({action:'append',id,chunk,data,last:offset+size>=bytes.length});
  }
}
async function exportContext(prefix){
  const response=await request('tools/call',{name:'snapshot_context',arguments:fileRef?.token?{token:fileRef.token}:{}});
  if(response.isError||!response.structuredContent)throw Error('无法读取保存位置');
  const host=response.structuredContent,option=$(prefix+'-destination').querySelector('[value="server"]');
  option.hidden=host.nativePicker||pickedFile;option.textContent='服务器 · '+host.host;
  $(prefix+'-destination').value=host.nativePicker||pickedFile?'local':'server';
  $(prefix+'-directory').value=pickedFile?'':host.directory;
  $(prefix+'-directory-row').hidden=$(prefix+'-destination').value!=='server';return host;
}
async function saveMedia(id,host,prefix){
  const local=$(prefix+'-destination').value==='local',output=$(prefix+'-result');
  const saved=await mediaCall({action:'save',id,destination:local?(host.nativePicker?'native':'helper'):'server',
    directory:$(prefix+'-directory').value.trim(),...(fileRef?.token?{token:fileRef.token}:{})});
  if(!local||host.nativePicker){
    if(!saved.cancelled&&!saved.path)throw Error('宿主未确认保存结果');
    output.textContent=saved.cancelled?'已取消保存':'已保存：'+saved.path;return;
  }
  output.textContent='请在 Mac 系统窗口选择保存位置…';
  for(let attempt=0;attempt<330;attempt++){
    await new Promise(resolve=>setTimeout(resolve,2000));
    const reply=await request('tools/call',{name:'snapshot_save_status',arguments:{id:saved.id}});
    if(reply.isError)throw Error('无法确认保存状态');
    const state=reply.structuredContent?.status;
    if(state==='saved'||state==='cancelled'){output.textContent=state==='saved'?'已保存到本地 Mac':'已取消保存';return;}
    if(['error','disconnected','expired'].includes(state))throw Error('Mac 保存失败或助手已断开，请检查保存助手');
  }
  throw Error('等待 Mac 保存结果超时，请检查系统窗口');
}
let animationHost=null,animationBusy=false,animationCancelled=false;
$('animation-export').onclick=async()=>{
  if(!doc||!views)return;
  stop();$('animation-start').value=1;$('animation-end').value=doc.count;
  $('animation-rate').value=playback.fps;$('animation-stride').value=playback.step;
  $('animation-name').value=$('filename').textContent.replace(/\.[^.]+$/,'').replace(/[^\p{L}\p{N}_ .()\-]/gu,'_')+'-trajectory';
  $('animation-result').textContent='';$('animation-dialog').showModal();
  try{animationHost=await exportContext('animation');}catch(error){$('animation-result').textContent=error.message;}
};
$('animation-destination').onchange=()=>{$('animation-directory-row').hidden=$('animation-destination').value!=='server';};
$('animation-close').onclick=()=>{if(animationBusy){animationCancelled=true;$('animation-result').textContent='正在取消…';}else $('animation-dialog').close();};
$('animation-dialog').addEventListener('cancel',event=>{if(animationBusy){event.preventDefault();animationCancelled=true;}});
$('animation-save').onclick=async()=>{
  if(animationBusy||!animationHost)return;
  const start=Number($('animation-start').value)-1,end=Number($('animation-end').value)-1,stride=Number($('animation-stride').value);
  const fps=Number($('animation-rate').value),speed=Number($('animation-speed').value);
  if(![start,end,stride].every(Number.isInteger)||start<0||end>=doc.count||end<start||stride<1||!(fps>0)){$('animation-result').textContent='请填写有效的已加载帧范围、帧率和间隔';return;}
  const format=$('animation-format').value,name=$('animation-name').value+'.'+format;
  const rate=fps*speed/stride;
  // GIF stores centiseconds. Quantize explicitly instead of silently speeding up at >100 FPS.
  const encodedRate=format==='gif'?100/Math.max(1,Math.round(100/rate)):rate;
  const exportDoc=doc,generation=readGeneration;
  let job;const original=frameIndex,savedSelection=selection.slice(),savedDisplay=displayState;
  const cameras=views.panes.map(p=>p.viewer.getView());
  animationBusy=true;animationCancelled=false;$('animation-save').disabled=true;$('animation-fields').disabled=true;$('animation-close').textContent='取消导出';
  try{
    job=await mediaCall({action:'begin',kind:'animation',name,fps:encodedRate});
    let count=0,total=Math.floor((end-start)/stride)+1;
    const reference=doc.frame(drift?.reference||0);
    for(let index=start;index<=end;index+=stride){
      if(animationCancelled)throw Error('已取消导出');
      if(doc!==exportDoc||readGeneration!==generation)throw Error('结构文件在导出期间改变，请重新导出');
      if(drift&&StructureSelection.remap(reference,doc.frame(index),drift.indices).length!==drift.indices.length)throw Error(`第 ${index+1} 帧无法对应质心校正原子`);
      // Do not run go(): exports must not remap or mutate interactive selection/style state.
      frameIndex=index;render(false,true);
      views.panes.forEach((p,i)=>p.viewer.setView(cameras[i]));
      const image=await StructureSnapshot.capture(views,{dpi:96,crop:false,transparent:false,format:'png'});
      await uploadMedia(job.id,image.bytes,()=>animationCancelled);
      $('animation-result').textContent=`渲染 ${++count} / ${total}`;
      await new Promise(resolve=>setTimeout(resolve,0));
    }
    if(animationCancelled)throw Error('已取消导出');
    let result=await mediaCall({action:'finish',id:job.id});
    while(result.state==='encoding'){
      if(animationCancelled)throw Error('已取消导出');
      $('animation-result').textContent='正在编码动画…';await new Promise(resolve=>setTimeout(resolve,500));
      result=await mediaCall({action:'status',id:job.id});
    }
    if(result.state!=='ready')throw Error(result.error||'编码失败');
    $('animation-close').disabled=true;
    await saveMedia(job.id,animationHost,'animation');
  }catch(error){$('animation-result').textContent=error.message;}
  finally{
    if(job)await mediaCall({action:'cancel',id:job.id}).catch(()=>{});
    if(doc===exportDoc){frameIndex=original;selection=savedSelection;displayState=savedDisplay;render();views.panes.forEach((p,i)=>p.viewer.setView(cameras[i]));}
    animationBusy=false;$('animation-save').disabled=false;$('animation-fields').disabled=false;$('animation-close').disabled=false;$('animation-close').textContent='关闭';
  }
};
