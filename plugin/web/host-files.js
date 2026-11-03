/* File-like access only to a resource selected by Codex or explicitly opened by path. */
const StructureHostFiles = (() => {
  async function call(args) {
    const reply = await request('tools/call', {name:'structure_import', arguments:args}, 180000);
    if (reply.isError || !reply.structuredContent) throw Error(reply.content?.find(item=>item.text)?.text || '结构读取失败');
    return reply.structuredContent;
  }
  async function open(ref) {
    const binding = ref.token ? {token:ref.token} : {};
    const meta = await call({...binding,action:'stat'});
    if (!meta.supported) return null;
    const read = args => call({...binding,version:meta.version,...args});
    const file = {
      name:ref.name, size:meta.size,
      topology(){return read({action:"topology"});},
      async xyzSource(){
        const batch=async args=>{
          const reply=await request('tools/call',{name:'read_trajectory_frames',arguments:{...binding,version:meta.version,...args}});
          if(reply.isError)throw Error(reply.content?.[0]?.text || 'XYZ read failed');
          return reply.structuredContent;
        };
        return new StructureTrajectory.HostSource(batch,await batch({offset:0,frameLimit:1}));
      },
      convert(options){return read({action:"convert",...options});},
      slice(start=0,end=meta.size) {
        end=Math.min(end,meta.size);
        const bytes=async()=>{
          const output=new Uint8Array(end-start);
          for(let pos=start;pos<end;pos+=1048576) {
            const length=Math.min(1048576,end-pos);
            const part=await read({action:'range',offset:pos,length});
            output.set(Uint8Array.from(atob(part.data),c=>c.charCodeAt(0)),pos-start);
          }
          return output.buffer;
        };
        return {arrayBuffer:bytes, text:async()=>new TextDecoder().decode(await bytes())};
      },
      text(){return this.slice().text();},
      async openMD(format) {
        const batch=args=>read({action:'frames',format,offset:args.offset,indexOnly:!!args.indexOnly});
        const first=await batch({offset:0});
        const source=new StructureTrajectory.HostSource(batch,{...first,version:meta.version});
        let seed=first.text;
        const fetchFrame=source.read.bind(source);
        source.raw=async index=>index===0 && seed!==null ? seed : fetchFrame(index);
        source.format=format;
        source.read=async index=>{
          const text=await source.raw(index);
          seed=null;
          return format==='gromacs'?StructureMD.parseGro(text):StructureMD.parseDump(text,source.metadata);
        };
        return source;
      }
    };
    return file;
  }
  return {open,call};
})();
