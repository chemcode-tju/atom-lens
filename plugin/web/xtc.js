/* Progressive XTC indexing; transfer/decompress only one requested frame. */
const StructureXtc = (() => {
  function header(bytes, offset=0) {
    const view=new DataView(bytes);
    if(view.byteLength<56)throw Error('Truncated XTC header');
    if(view.getInt32(0)!==1995)throw Error('Unsupported XTC magic at byte '+offset);
    const n=view.getInt32(4),step=view.getInt32(8),time=view.getFloat32(12);
    if(n<1||n>1000000||view.getInt32(52)!==n)throw Error('Invalid XTC atom count (limit 1,000,000)');
    if(!Number.isFinite(time))throw Error('Invalid XTC time');
    let length=56+12*n;
    if(n>9){
      if(view.byteLength<92)throw Error('Truncated XTC compressed header');
      const size=view.getInt32(88);
      if(size<=0||size>n*32)throw Error('Invalid XTC compressed length');
      length=92+Math.ceil(size/4)*4;
    }
    return {offset,end:offset+length,n,step,time};
  }
  class Source {
    constructor(file,symbols,pbc=null,atoms=null){
      this.file=file;this.symbols=symbols;this.atoms=atoms;this.pbc=pbc;this.frames=[];this.offset=0;this.complete=false;
    }
    get count(){return this.frames.length;}
    accept(frame){
      if(frame.n!==this.symbols.length)throw Error('XTC/topology atom count mismatch: '+frame.n+' / '+this.symbols.length);
      this.frames.push(frame);
    }
    async advance(limit=256){
      if(this.complete)return;
      if(this.file.xtcIndex){
        const result=await this.file.xtcIndex(this.offset,limit);
        if(result.nextOffset<=this.offset&&!result.eof)throw Error('Invalid XTC index progress');
        result.frames.forEach(frame=>this.accept(frame));
        this.offset=result.nextOffset;this.complete=result.eof;return;
      }
      for(let i=0;i<limit&&!this.complete;i++){
        try {
          const frame=header(await this.file.slice(this.offset,Math.min(this.file.size,this.offset+92)).arrayBuffer(),this.offset);
          if(frame.end>this.file.size)throw Error('Truncated XTC frame');
          this.accept(frame);this.offset=frame.end;this.complete=this.offset===this.file.size;
        }catch(error){
          if(this.file.frozen&&/^Truncated XTC/.test(error.message)){this.offset=this.file.size;this.complete=true;return;}
          throw error;
        }
      }
    }
    async read(index){
      const frame=this.frames[index];
      const bytes=await this.file.slice(frame.offset,frame.end).arrayBuffer();
      const check=header(bytes,frame.offset);
      if(check.end!==frame.end||check.n!==frame.n||check.step!==frame.step)throw Error('XTC frame changed; reopen trajectory');
      const result=await StructureXtcDecoder.decode(new Uint8Array(bytes));
      if(result.frames.length!==1)throw Error('Invalid XTC frame');
      const coordinates=result.frames[0],lattice=Array.from(result.boxes[0]);
      const pbc=this.pbc || [0,1,2].map(()=>lattice.some(x=>x!==0));
      if(lattice.some(x=>!Number.isFinite(x))||pbc.some(Boolean)&&!lattice.some(x=>x!==0))throw Error('Invalid XTC cell');
      const atoms=[];
      for(let i=0;i<frame.n;i++){
        const x=coordinates.x[i],y=coordinates.y[i],z=coordinates.z[i];
        if(!Number.isFinite(x)||!Number.isFinite(y)||!Number.isFinite(z))throw Error('Invalid XTC coordinate');
        atoms.push({...this.atoms?.[i],elem:this.symbols[i],id:i+1,position:[x,y,z]});
      }
      return StructureParser.serializeFrame(atoms,[lattice.slice(0,3),lattice.slice(3,6),lattice.slice(6,9)],pbc,{source_format:'GROMACS XTC',step:frame.step,time:frame.time});
    }
  }
  return {Source,header};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=StructureXtc;
