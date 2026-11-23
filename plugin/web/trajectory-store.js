/* A growing byte index plus a bounded LRU of decoded frames. No all-frame text. */
(function(root) {
  'use strict';
  const pause=(ms=0)=>new Promise(resolve=>setTimeout(resolve,ms));
  class FrameStore {
    constructor(name,source,{maxFrames=16,maxBytes=64*1024*1024}={}) {
      this.name=name;this.source=source;this.maxFrames=maxFrames;this.maxBytes=maxBytes;
      this.cache=new Map();this.pending=new Map();this.bytes=0;this.disposed=false;
      this.active=true;this.playing=false;this.playhead=0;this.prefetchTask=null;
      this.prefetchTargets=[];
      this.vaspPreview=/^(POSCAR|CONTCAR|XDATCAR)$/i.test(name)||/\.vasp$/i.test(name);
      this.xyz=!this.vaspPreview;
    }
    get count(){return this.source.count;}
    get complete(){return this.source.complete;}
    put(index,text,decode=true) {
      const frame=decode?new StructureParser.StructureDocument(this.vaspPreview?'POSCAR':'preview.extxyz',text).frame(0):null;
      const atomCount=frame?frame.atoms.length:this.vaspPreview?text.split(/\r?\n/,7)[6].trim().split(/\s+/).reduce((sum,n)=>sum+Number(n),0):Number(text.slice(0,text.indexOf('\n')).trim());
      // Conservative accounting, not a JavaScript heap measurement. One oversized
      // frame is allowed so the cache budget never becomes a file-size limit.
      const bytes=text.length*2+atomCount*512+1024,record={frame,text,bytes};
      if(this.cache.has(index))this.bytes-=this.cache.get(index).bytes;
      this.cache.delete(index);this.cache.set(index,record);this.bytes+=bytes;
      while(this.cache.size>1&&(this.cache.size>this.maxFrames||this.bytes>this.maxBytes)) {
        const oldest=this.cache.keys().next().value;this.bytes-=this.cache.get(oldest).bytes;this.cache.delete(oldest);
      }
      return record;
    }
    async get(index) {
      if(this.disposed)throw Error('结构文件已关闭');
      if(!Number.isInteger(index)||index<0||index>=this.count)throw Error('帧尚未索引或超出范围');
      if(this.cache.has(index)) {const record=this.cache.get(index);this.cache.delete(index);this.cache.set(index,record);if(!record.frame)record.frame=new StructureParser.StructureDocument(this.vaspPreview?'POSCAR':'preview.extxyz',record.text).frame(0);return record;}
      if(this.prefetchTask&&this.prefetchTargets.includes(index)){
        await this.prefetchTask;
        if(this.disposed)throw Error('结构文件已关闭');
        if(this.cache.has(index))return this.get(index);
      }
      if(!this.pending.has(index)) {
        const task=this.source.read(index).then(text=>{if(this.disposed)throw Error('结构文件已关闭');return this.put(index,text);}).finally(()=>this.pending.delete(index));
        this.pending.set(index,task);
      }
      return this.pending.get(index);
    }
    setActive(active){this.active=active;}
    setPlayback(index,playing){this.playhead=index;this.playing=playing;}
    prefetch(index,step=1) {
      if(this.disposed||!this.active||this.prefetchTask||this.pending.size||this.maxFrames<2)return;
      const largest=Math.max(1024,...[...this.cache.values()].map(record=>record.bytes));
      // Retain room for the displayed frame. A large structure never turns
      // read-ahead into an unbounded trajectory download.
      const capacity=Math.min(8,this.maxFrames-1,Math.floor(this.maxBytes/largest)-1);
      const targets=[];
      for(let i=index+step;i<this.count&&targets.length<capacity;i+=step)targets.push(i);
      const first=targets.find(i=>!this.cache.has(i));
      if(first===undefined)return;
      // Refill at a low watermark, rather than sending one new SSH request
      // after every displayed frame when most of the window is already cached.
      if(targets.indexOf(first)>=Math.min(3,capacity))return;
      const batch=this.source.readMany&&step===1;
      this.prefetchTargets=batch?targets.slice(targets.indexOf(first)):[first];
      this.prefetchTask=(async()=>{
        const texts=batch?await this.source.readMany(first,this.prefetchTargets.length):[await this.source.read(first)];
        for(let i=0;i<texts.length;i++){
          if(this.disposed)return;
          // Keep raw neighbors; decode only the frame actually displayed.
          this.put(first+i,texts[i],false);
        }
      })().catch(()=>{/* A foreground read reports errors; speculation does not stop playback. */}).finally(()=>{
        this.prefetchTask=null;this.prefetchTargets=[];
      });
      return this.prefetchTask;
    }
    async scan(onProgress) {
      let nextBackgroundBatch=0;
      while(!this.disposed&&!this.complete) {
        await pause();if(this.disposed)return;
        if(!this.active||(this.playing&&!this.concurrentIndex&&this.count>this.playhead+64&&performance.now()<nextBackgroundBatch)){
          await pause(40);continue;
        }
        // Legacy hosts serialize everything. The desktop worker can index while
        // a foreground frame is in flight, without holding up playback.
        if(!this.concurrentIndex){
          if(this.pending.size){await Promise.allSettled([...this.pending.values()]);continue;}
          if(this.prefetchTask){await this.prefetchTask;continue;}
        }
        await this.source.advance(this.playing?(this.concurrentIndex?64:16):4096);
        nextBackgroundBatch=performance.now()+250;
        if(!this.disposed)onProgress();
      }
    }
    dispose(){this.disposed=true;this.cache.clear();this.bytes=0;this.source.dispose?.();}
  }
  class HostSource {
    constructor(call,batch) {
      this.call=call;this.version=batch.version;this.offsets=[];this.offset=0;this.count=0;this.complete=false;
      this.accept(batch);
    }
    accept(batch) {
      if(!Array.isArray(batch.offsets)||!Number.isSafeInteger(batch.nextOffset)||batch.nextOffset<this.offset||(!batch.eof&&batch.nextOffset===this.offset))throw Error('分段读取返回无效数据');
      if(batch.headerOffsets){this.headerOffsets ||= [];this.headerOffsets.push(...batch.headerOffsets);}
      this.offsets.push(...batch.offsets);this.offset=batch.nextOffset;this.complete=batch.eof;
      this.binary=Number.isSafeInteger(batch.totalFrames);
      this.count=this.binary?batch.totalFrames:this.offsets.length;
      if(this.binary)this.complete=true;
    }
    async read(index){const batch=await this.call({offset:this.binary?index:this.offsets[index],frameLimit:1,version:this.version,...(this.headerOffsets?{headerOffset:this.headerOffsets[index]}:{})});return batch.text;}
    async advance(limit=4096){this.accept(await this.call({offset:this.offset,frameLimit:limit,indexOnly:true,version:this.version,...(this.headerOffsets?{headerOffset:this.headerOffsets.at(-1)||0}:{})}));}
  }
  // The scanner retains at most one 64 KiB chunk; offsets refer to UTF-8 bytes,
  // not JS characters, including CRLF and multibyte comments.
  class ByteLines {
    constructor(file){this.file=file;this.offset=0;this.buffer=new Uint8Array();this.cursor=0;this.decoder=new TextDecoder();}
    async skipRows(count, checkBlank=true) {
      // Index coordinates as bytes. Decode only requested frames.
      let nonblank=false;
      rows: while(count>0) {
        if(this.cursor===this.buffer.length) {
          if(this.offset>=this.file.size)throw Error('轨迹末尾存在不完整帧');
          this.buffer=new Uint8Array(await this.file.slice(this.offset,this.offset+65536).arrayBuffer());this.cursor=0;
        }
        const end=this.buffer.indexOf(10,this.cursor);
        const stop=end<0?this.buffer.length:end;
        if(checkBlank && !nonblank) {
          for(let i=this.cursor;i<stop;i++){
            const byte=this.buffer[i];
            if(byte>=128){
              // Preserve Unicode whitespace handling without decoding ordinary coordinates.
              if(!(await this.next()).text.trim())throw Error('轨迹末尾存在不完整帧');
              count--;continue rows;
            }
            if(byte!==32 && (byte<9 || byte>13)){nonblank=true;break;}
          }
        }
        const next=stop+(end>=0?1:0);
        this.offset+=next-this.cursor;this.cursor=next;
        if(end>=0 || this.offset===this.file.size) {
          if(checkBlank && !nonblank)throw Error('轨迹末尾存在不完整帧');
          nonblank=false;count--;
        }
      }
    }
    async next() {
      const start=this.offset,parts=[];
      while(true) {
        if(this.cursor===this.buffer.length) {
          if(this.offset>=this.file.size)break;
          this.buffer=new Uint8Array(await this.file.slice(this.offset,this.offset+65536).arrayBuffer());this.cursor=0;
        }
        const end=this.buffer.indexOf(10,this.cursor),stop=end<0?this.buffer.length:end+1;
        parts.push(this.decoder.decode(this.buffer.subarray(this.cursor,stop),{stream:true}));
        this.offset+=stop-this.cursor;this.cursor=stop;
        if(end>=0)break;
      }
      parts.push(this.decoder.decode());
      if(start===this.offset)return null;
      return {start,end:this.offset,text:parts.join('').replace(/\r?\n$/,'')};
    }
  }
  class LocalSource {
    constructor(file,name) {
      this.file=file;this.name=name;this.lines=new ByteLines(file);this.offsets=[];this.ends=[];this.count=0;this.complete=false;
      this.vasp=/^(POSCAR|CONTCAR|XDATCAR)$/i.test(name)||/\.vasp$/i.test(name);this.header='';this.frameHeaders=[];
    }
    async required(){const row=await this.lines.next();if(!row)throw Error('轨迹末尾存在不完整帧');return row;}
    async initialize() {
      if(/\.traj$/i.test(this.name)) {this.binary=await ASETrajectory.open(this.file);this.count=this.binary.count;this.complete=true;return;}
      if(this.vasp) await this.readHeader(await this.required());
      await this.advance(1);
    }
    async readHeader(first) {
        const rows=[first.text];for(let i=1;i<7;i++)rows.push((await this.required()).text);
        const counts=rows[6].trim().split(/\s+/).map(Number);this.atomCount=counts.reduce((a,b)=>a+b,0);
        if(counts.some(n=>!Number.isSafeInteger(n)||n<0)||this.atomCount<1)throw Error('VASP 元素计数无效');
        this.mode=await this.required();if(/^s/i.test(this.mode.text.trim())){rows.push(this.mode.text);this.mode=await this.required();}
        this.trajectory=/^XDATCAR$/i.test(this.name)||/configuration/i.test(this.mode.text);
        this.header=rows.join('\n')+'\n';
    }
    async advance(limit=4096) {
      const initial=this.lines.offset,started=performance.now();
      for(let i=0;i<limit&&!this.complete;i++) {
        let row=this.mode||await this.lines.next();this.mode=null;
        while(row&&!row.text.trim())row=await this.lines.next();
        if(!row){this.complete=true;break;}
        if(this.vasp && this.trajectory && this.count && !/^(direct|cartesian)(?:\s+configuration\s*=.*)?$/i.test(row.text.trim())) {
          await this.readHeader(row);
          row=this.mode;this.mode=null;
        }
        const start=row.start;
        let count=this.atomCount;
        if(this.vasp) {if(!/^[dck]/i.test(row.text.trim()))throw Error('无法识别 VASP 坐标模式');}
        else {
          if(!/^\s*\d+\s*$/.test(row.text))throw Error('轨迹原子数无效');
          count=Number(row.text);if(!Number.isSafeInteger(count)||count<1||count>1000000)throw Error('原子数必须在 1–1000000 范围内');
          await this.required();
        }
        await this.lines.skipRows(count);
        if(this.vasp)this.frameHeaders.push(this.header);
        this.offsets.push(start);this.ends.push(this.lines.offset);this.count++;
        this.complete=this.lines.offset>=this.file.size||(this.vasp&&!this.trajectory);
        if(this.lines.offset-initial>=1048576||performance.now()-started>=8)break;
      }
    }
    async read(index) {
      if(this.binary)return this.binary.frameText(index);
      return (this.frameHeaders[index] || '')+await this.file.slice(this.offsets[index],this.ends[index]).text();
    }
  }
  async function local(file,name=file.name,options) {const source=new LocalSource(file,name);await source.initialize();const store=new FrameStore(name,source,options);await store.get(0);return store;}
  function host(name,call,batch,options) {
    const source=new HostSource(call,batch),store=new FrameStore(name,source,options);
    // Only the direct XYZ/VASP/ASE route batches raw frames. Paired-file sources
    // override read() to attach cell/topology data and keep that transformation.
    source.readMany=async(index,limit)=>{
      const result=await call({offset:source.binary?index:source.offsets[index],frameLimit:limit,version:source.version,...(source.headerOffsets?{headerOffset:source.headerOffsets[index]}:{})});
      let parsed;
      if(store.vaspPreview){parsed=new StructureParser.ProgressiveVASPDocument(name);parsed.append(result.text);}
      else parsed=new StructureParser.StructureDocument('preview.extxyz',result.text);
      return Array.from({length:Math.min(limit,parsed.count)},(_,i)=>parsed.frameText(i)+(store.vaspPreview?'':parsed.newline));
    };
    store.put(0,batch.text);return store;
  }
  const api={FrameStore,HostSource,LocalSource,ByteLines,local,host};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.StructureTrajectory=api;
})(typeof window!=='undefined'?window:globalThis);
