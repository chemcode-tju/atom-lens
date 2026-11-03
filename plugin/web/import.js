/* Browser file routing. Companion files are metadata only, never executable inputs. */
(function(root) {
  'use strict';
  function localName(name, format = 'auto') {
    if (format === 'extxyz') return 'preview.extxyz';
    if (format === 'vasp') return 'POSCAR';
    if (format === 'vasp-xdatcar') return 'XDATCAR';
    if (format !== 'auto') return null;
    if (/^XDATCAR(?:[._-].*)?$/i.test(name)) return 'XDATCAR';
    if (/^(POSCAR|CONTCAR)(?:[._-].*)?$|\.vasp$/i.test(name)) return 'POSCAR';
    if (/\.(xyz|extxyz|traj)$/i.test(name)) return name;
    return null;
  }
  async function classify(file) {
    const prefix=await file.slice(0,8192).text();
    if (/^ITEM: (?:TIMESTEP|UNITS|TIME)/m.test(prefix)) return 'lammps-dump-text';
    if (/^data[._-]|\.(data|lmp)$/i.test(file.name) && /\d+\s+atom types\b/m.test(prefix)) return 'lammps-data';
    if (/^\s*\d+\s+atoms\s*$/m.test(prefix) && /^\s*\d+\s+atom types\s*$/m.test(prefix)) return 'lammps-data';
    if (localName(file.name)) return 'local';
    if (/\.gro$/i.test(file.name)) return 'gromacs';
    if (/\.pdb$/i.test(file.name)) return 'proteindatabank';
    if (/\.cif$/i.test(file.name)) return 'cif';
    return 'companion';
  }
  async function companionsText(files) {
    if (files.reduce((size,file)=>size+file.size,0)>32*1024*1024) throw Error('配套 data/输入/日志合计超过 32 MiB，请选择较小的元数据文件。轨迹不受此限制。');
    return Promise.all(files.map(async file=>({name:file.name,text:await file.text()})));
  }
  async function open(input, {format = 'auto'} = {}) {
    const files=input && typeof input.slice==='function' && typeof input.name==='string' ? [input] : Array.from(input||[]);
    if(!files.length || files.length>32)throw Error('请选择 1–32 个结构及配套文件');
    const entries=await Promise.all(files.map(async file=>({file,format:await classify(file)})));
    if(format!=='auto') {
      if(files.length===1)entries[0].format=format;
      else if(!entries.some(entry=>entry.format===format))entries[0].format=format;
    }
    const dumps=entries.filter(entry=>entry.format==='lammps-dump-text');
    const candidates=entries.filter(entry=>entry.format!=='companion' && !(dumps.length && entry.format==='lammps-data'));
    if(candidates.length!==1)throw Error('请每次选择一条轨迹（或一个结构），可同时选择它的 LAMMPS data、输入文件和日志；不自动拼接多条轨迹。');
    const primary=candidates[0],file=primary.file;
    const selectedFormat=files.length===1 && format!=='auto'?format:primary.format;
    const other=files.filter(item=>item!==file);
    if(other.length && !selectedFormat.startsWith('lammps'))throw Error('配套文件联合读取目前用于 LAMMPS；其他格式请一次选择一个结构文件。');
    const name=localName(file.name,selectedFormat==='local'?'auto':selectedFormat);
    if(name)return {name:file.name,store:await StructureTrajectory.local(file,name),note:'本地浏览器读取 · 坐标单位 Å · 未上传文件'};
    const companions=await companionsText(other);
    if(['gromacs','lammps-dump-text'].includes(selectedFormat))return {name:file.name,...await StructureMD.open(file,selectedFormat,companions)};
    if(file.size>32*1024*1024)throw Error('单个 data/PDB/CIF 转换上传上限为 32 MiB；GRO、dump、XYZ、VASP、ASE .traj 可本地逐帧读取。');
    let metadata=null,typeMap='',primaryText;
    if(selectedFormat==='lammps-data') {
      primaryText=await file.text();
      const all=[...companions,{name:file.name,text:primaryText}];
      const initial=StructureLammps.resolve(all);
      if(!initial.typeCount || initial.typeCount>1180)throw Error('data 的 atom types 数量无效或过多');
      const types=Array.from({length:initial.typeCount},(_,i)=>String(i+1));
      metadata=StructureLammps.resolve(all,types);
      typeMap=types.map(type=>metadata.mapping[type]).join(' ');
    }
    const atomStyle=['bond','angle'].includes(metadata?.atomStyle)?'molecular':metadata?.atomStyle||'auto';
    const options={format:selectedFormat,elements:typeMap.trim()?typeMap.split(' '):[],
      units:metadata?.units||'metal',atomStyle};
    const result=file.convert ? await file.convert(options) : await StructureHostFiles.call({
      action:'convert',...options,text:primaryText ?? await file.text()});
    let blob=new Blob([result.text]);
    let note='当前服务转换 · 坐标单位 Å · 未发送给模型';
    if(metadata) {
      if(metadata.pbc)blob=new Blob([(await blob.text()).replace(/pbc="[TF ]+"/g,`pbc="${metadata.pbc.map(value=>value?'T':'F').join(' ')}"`)]);
      note+=` · 自动识别 ${typeMap} · ${metadata.pbc?'使用配套文件的边界条件':'data 未包含边界条件，按三维周期显示'}`;
      if(metadata.warnings.length)note+=' · '+metadata.warnings.join('；');
    }
    return {name:file.name,store:await StructureTrajectory.local(blob,'converted.extxyz'),note};
  }
  const api={localName,open,classify};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.StructureImport=api;
})(typeof window!=='undefined'?window:globalThis);
