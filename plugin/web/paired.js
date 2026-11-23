/* Pair explicit metadata with the current trajectory. FrameStore owns the decoded-frame cache. */
const StructurePaired = (() => {
  async function storeFor(source, note) {
    const store = new StructureTrajectory.FrameStore('preview.extxyz',source);
    await store.get(0);
    return {store,note};
  }

  async function cellTable(file) {
    const lines=new StructureTrajectory.ByteLines(file), table=new Map();
    let scale=1;
    for(let row;(row=await lines.next());) {
      const text=row.text.trim();
      if(!text)continue;
      if(text.startsWith('#')){
        const units=text.match(/\bAx\s*\[([^\]]+)\]/i)?.[1]?.toLowerCase();
        if(units && !['angstrom','bohr','a.u.'].includes(units))throw Error('Unsupported CELL length unit: '+units);
        if(units)scale=units==='angstrom'?1:0.529177210903;
        continue;
      }
      const values=text.split(/\s+/).map(s=>Number(s.replace(/[dD]/,'e')));
      const step=values[0], lattice=values.slice(2,11).map(v=>v*scale);
      if(values.length<11 || !values.every(Number.isFinite) || !Number.isSafeInteger(step))throw Error('Invalid CP2K CELL row');
      if(table.has(step))throw Error('Duplicate CP2K CELL step: '+step);
      table.set(step,lattice);
    }
    return table;
  }

  async function cp2k(file, cell) {
    if(file.xyzSource && cell.cellBinding)return storeFor(await file.xyzSource(cell.cellBinding),'CP2K XYZ + CELL');
    const table=await cellTable(cell);
    const source=file.xyzSource ? await file.xyzSource() : new StructureTrajectory.LocalSource(file,file.name);
    if(!file.xyzSource)await source.initialize();
    const raw=source.read.bind(source);
    source.read=async index=>{
      const text=await raw(index), first=text.indexOf('\n'), end=text.indexOf('\n',first+1);
      const header=text.slice(first+1,end).trim();
      const match=header.match(/(?:^|[,\s])i\s*=\s*(-?\d+)\b/i);
      if(!match)throw Error('Missing CP2K XYZ step (i = ...) at frame '+(index+1));
      const step=Number(match[1]), lattice=table.get(step);
      if(!lattice)throw Error('No CELL row for CP2K XYZ step '+step);
      return text.slice(0,first+1)+'Lattice="'+lattice.join(' ')+'" pbc="T T T" step='+step+' '+header+text.slice(end);
    };
    return storeFor(source,'CP2K XYZ + CELL');
  }

  async function topology(file, includes) {
    if(file.topology && !includes.length)return file.topology();
    const files=[];
    for(const item of [file,...includes]){
      const data=new Uint8Array(await item.slice(0,item.size).arrayBuffer());
      let binary='';
      for(let i=0;i<data.length;i+=32768)binary+=String.fromCharCode(...data.subarray(i,i+32768));
      files.push({name:item.name,data:btoa(binary)});
    }
    return StructureHostFiles.call({action:'topology',files});
  }

  function element(atom) {
    const symbol=(atom.number>0 && StructureParser.elements[atom.number]) || StructureLammps.massElement(atom.mass);
    if(!symbol || symbol==='X')throw Error('Cannot resolve topology element for '+(atom.name||atom.mass));
    return symbol;
  }

  async function gro(file, atoms) {
    const fmt='gromacs';
    const source=file.openMD ? await file.openMD(fmt) : new StructureMD.MDSource(file,fmt);
    if(!file.openMD)await source.advance(1);
    source.read=async index=>StructureMD.parseGro(await source.raw(index),atoms);
    return storeFor(source,'GRO + TOP');
  }

  // Standard big-endian XDR TRR (GMX_trn_file). Headers index coordinate
  // frames without transferring velocity/force arrays or later coordinates.
  class TrrSource {
    constructor(file, topology){
      this.pbc=topology.pbc;this.file=file;this.atoms=topology.atoms;this.symbols=topology.atoms.map(element);this.frames=[];this.offset=0;this.complete=false;
      this.block=null;
    }
    get count(){return this.frames.length;}
    async header(){
      const pos=this.offset;
      if(!this.block || pos+92>this.block.start+this.block.bytes.byteLength){
        const bytes=await this.file.slice(pos,Math.min(this.file.size,pos+65536)).arrayBuffer();
        this.block={start:pos,bytes};
      }
      const view=new DataView(this.block.bytes,pos-this.block.start);
      if(this.file.frozen && view.byteLength<84){this.complete=true;this.offset=this.file.size;return;}
      if(view.byteLength<84 || view.getInt32(0)!==1993 || view.getInt32(4)!==13 || view.getInt32(8)!==12 ||
         String.fromCharCode(...new Uint8Array(view.buffer,view.byteOffset+12,12))!=='GMX_trn_file')throw Error('Invalid TRR header at byte '+pos);
      const sizes=Array.from({length:10},(_,i)=>view.getInt32(24+i*4));
      const n=view.getInt32(64), step=view.getInt32(68);
      if(n!==this.symbols.length || !n)throw Error('TRR/TPR atom count mismatch: '+n+' / '+this.symbols.length);
      const [ir,e,box,vir,pres,top,sym,x,v,f]=sizes;
      const width=box?box/9:(x||v||f)/(n*3);
      if(![4,8].includes(width) || sizes.some(s=>s<0) || ir||e||top||sym ||
         [box,vir,pres].some(s=>s && s!==9*width) || [x,v,f].some(s=>s && s!==n*3*width))throw Error('Unsupported TRR block layout');
      const start=pos+76+2*width;
      this.offset=start+sizes.reduce((a,b)=>a+b,0);
      if(this.offset>this.file.size){if(this.file.frozen){this.complete=true;this.offset=this.file.size;return;}throw Error('Truncated TRR frame at step '+step);}
      this.complete=this.offset===this.file.size;
      if(x)this.frames.push({step,width,start,box,coords:start+box+vir+pres,n});
    }
    async advance(limit=256){
      if(this.file.trrIndex){
        const result=await this.file.trrIndex(this.offset,limit);
        if(result.nextOffset<=this.offset&&!result.eof)throw Error('Invalid TRR index progress');
        for(const frame of result.frames){
          if(frame.n!==this.symbols.length)throw Error('TRR/TPR atom count mismatch: '+frame.n+' / '+this.symbols.length);
          this.frames.push(frame);
        }
        this.offset=result.nextOffset;this.complete=result.eof;
        return;
      }
      for(let i=0;i<limit&&!this.complete;i++)await this.header();
    }
    async read(index){
      const {step,width,start,box,coords,n}=this.frames[index];
      const data=new DataView(await this.file.slice(start,coords+n*3*width).arrayBuffer());
      const number=offset=>{
        const value=(width===4?data.getFloat32(offset):data.getFloat64(offset))*10;
        if(!Number.isFinite(value))throw Error('Non-finite TRR coordinate or cell');
        return value;
      };
      const lattice=Array.from({length:box/width},(_,i)=>number(i*width));
      if(this.pbc.some(Boolean) && !lattice.some(x=>x!==0))throw Error('Periodic TRR frame is missing its cell');
      const atoms=this.atoms.map((atom,i)=>({...atom,id:i+1,elem:this.symbols[i],position:[0,1,2].map(j=>number(coords-start+(3*i+j)*width))}));
      return StructureParser.serializeFrame(atoms,lattice.length?[lattice.slice(0,3),lattice.slice(3,6),lattice.slice(6,9)]:null,this.pbc,{source_format:'GROMACS TRR + TPR',step});
    }
  }

  async function open(primary, companions) {
    const file=primary.file, bySuffix=suffix=>companions.filter(f=>f.name.toLowerCase().endsWith(suffix));
    if(/\.xyz$/i.test(file.name) && bySuffix('.cell').length){
      if(companions.length!==1)throw Error('Select one XYZ and one CP2K CELL');
      return cp2k(file,companions[0]);
    }
    if(primary.format==='gromacs' && companions.length){
      const tops=bySuffix('.top'),includes=bySuffix('.itp');
      if(tops.length!==1 || companions.length!==1+includes.length)throw Error('Select one GRO, one TOP, and its local ITP includes');
      const {atoms}=await topology(tops[0],includes);
      return gro(file,atoms.map(a=>({...a,symbol:element(a)})));
    }
    if(primary.format==='trr'){
      if(companions.length!==1 || !bySuffix('.tpr').length)throw Error('Select one TRR and its matching TPR');
      const source=new TrrSource(file,await topology(companions[0],[]));
      while(!source.complete&&!source.count)await source.advance(1);
      if(!source.count)throw Error('No coordinate frames in TRR');
      return storeFor(source,'TRR + TPR');
    }
    if(primary.format==='xtc'){
      let symbols,particleMetadata,pbc=null,note='XTC + TPR';
      if(companions.length===1&&bySuffix('.tpr').length){
        const meta=await topology(companions[0],[]);symbols=meta.atoms.map(element);pbc=meta.pbc;particleMetadata=meta.atoms;
      }else if(bySuffix('.gro').length===1&&companions.every(f=>/\.(gro|top|itp)$/i.test(f.name))&&bySuffix('.top').length<=1&&(!bySuffix('.itp').length||bySuffix('.top').length)){
        const companion=bySuffix('.gro')[0];
        const groSource=companion.openMD?await companion.openMD('gromacs'):new StructureMD.MDSource(companion,'gromacs');
        if(!companion.openMD)await groSource.advance(1);
        const atoms=bySuffix('.top').length?(await topology(bySuffix('.top')[0],bySuffix('.itp'))).atoms:null;
        const text=StructureMD.parseGro(await groSource.raw(0),atoms?.map(atom=>({...atom,symbol:element(atom)})));
        particleMetadata=new StructureParser.StructureDocument('preview.extxyz',text).frame(0).atoms;
        symbols=particleMetadata.map(atom=>atom.elem);
        note=atoms?'XTC + GRO + TOP':'XTC + GRO · 元素按 GRO 原子名识别';
      }else throw Error('请选择 XTC 和对应的 TPR 或 GRO；GRO 可额外搭配 TOP。');
      const source=new StructureXtc.Source(file,symbols,pbc,particleMetadata);
      await source.advance(1);
      if(!source.count)throw Error('No complete coordinate frames in XTC');
      return storeFor(source,note);
    }
    return null;
  }
  return {open};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=StructurePaired;
