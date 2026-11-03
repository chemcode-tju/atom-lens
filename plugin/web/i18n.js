/* Translate only UI presentation, never structure data, paths or input values.
 * Modules keep their original diagnostic strings; one catalogue covers both
 * JavaScript and Python errors at the presentation boundary. */
(function(root) {
  'use strict';
  const catalog = typeof module !== 'undefined' && module.exports
    ? require('./locales.json') : /*__LOCALES__*/{};
  const escape = text => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const patterns = Object.entries(catalog).filter(([key])=>/\{\d+\}/.test(key)).map(([key,value])=>{
    const keys=[];
    const parts=key.split(/(\{\d+\})/).map(part=>{
      if(/^\{\d+\}$/.test(part)){keys.push(part);return '([\\s\\S]+?)';}
      return escape(part);
    });
    return {regex:new RegExp('^'+parts.join('')+'$'),keys,value};
  });
  function translate(text, language='en', depth=0) {
    if(language!=='en'||typeof text!=='string'||depth>5||!/[\p{Script=Han}]/u.test(text))return text;
    const trimmed=text.trim();
    let translated=catalog[trimmed];
    if(translated===undefined)for(const {regex,keys,value} of patterns){
      const match=trimmed.match(regex);if(!match)continue;
      translated=value.replace(/\{\d+\}/g,key=>translate(match[keys.indexOf(key)+1],language,depth+1));break;
    }
    return translated===undefined?text:text.slice(0,text.indexOf(trimmed))+translated+text.slice(text.indexOf(trimmed)+trimmed.length);
  }
  const api={translate,catalog,language:'zh-CN'};
  if(typeof module!=='undefined'&&module.exports){module.exports=api;return;}
  root.StructureI18n=api;
  try{api.language=(localStorage.getItem('chemistry.language')||localStorage.getItem('structure-viewer.language'))==='en'?'en':'zh-CN';}catch{}
  const textStates=new WeakMap(),attributeStates=new WeakMap();
  const excluded='script,style,textarea,#filename:not([data-empty-title]),#atom-list,[data-no-i18n]';
  function textNode(node){
    if(node.parentElement?.closest(excluded))return;
    const current=node.nodeValue;
    let state=textStates.get(node);
    if(!state||current!==state.last)state={source:current,last:current};
    const value=translate(state.source,api.language);
    state.last=value;textStates.set(node,state);
    if(current!==value)node.nodeValue=value;
  }
  function element(node){
    if(node.matches(excluded))return;
    let states=attributeStates.get(node);if(!states){states={};attributeStates.set(node,states);}
    for(const attr of ['title','aria-label','placeholder']){
      if(!node.hasAttribute(attr))continue;
      const current=node.getAttribute(attr);let state=states[attr];
      if(!state||current!==state.last)state={source:current,last:current};
      const value=translate(state.source,api.language);state.last=value;states[attr]=state;
      if(current!==value)node.setAttribute(attr,value);
    }
  }
  function visit(node){
    if(node.nodeType===3){textNode(node);return;}
    if(node.nodeType!==1||node.matches(excluded))return;
    element(node);for(const child of node.childNodes)visit(child);
  }
  api.setLanguage=language=>{
    api.language=language==='en'?'en':'zh-CN';document.documentElement.lang=api.language;
    try{localStorage.setItem('structure-viewer.language',api.language);localStorage.setItem('chemistry.language',api.language);}catch{}
    visit(document.body);
    const selector=document.getElementById('language');selector.value=api.language;
    selector.options[0].textContent=api.language==='en'?'Chinese (Simplified)':'简体中文';
  };
  document.getElementById('language').onchange=event=>api.setLanguage(event.target.value);
  api.setLanguage(api.language);
  // Observe only text and accessible labels. Rendering canvases and their large
  // WebGL buffers never pass through this observer. Values (including paths)
  // are intentionally excluded. Writes below are idempotent.
  new MutationObserver(records=>{
    for(const record of records){
      if(record.type==='characterData')textNode(record.target);
      else if(record.type==='attributes')element(record.target);
      else for(const node of record.addedNodes)visit(node);
    }
  }).observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['title','aria-label','placeholder']});
})(globalThis);
