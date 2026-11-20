const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const os=require('node:os');
const path=require('node:path');
const {SourceMonitor}=require('../dist/watch.js');

async function observe(directories,action,expected,maximum=4096){
  let monitor;
  try{
    await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('An actual source event was not observed.')),15000);
      monitor=new SourceMonitor(filename=>{if(filename===expected){clearTimeout(timer);resolve();}},error=>{clearTimeout(timer);reject(error);},maximum);
      try{monitor.update(directories);Promise.resolve().then(()=>action(monitor)).catch(error=>{clearTimeout(timer);reject(error);});}
      catch(error){clearTimeout(timer);reject(error);}
    });
  }finally{monitor?.close();}
}

test('source monitoring observes the first immediate write and atomic replacement without a readiness delay',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'cppulse-watch-ready-'));
  try{
    const source=path.join(root,"it's 😀.cpp");await fs.writeFile(source,'int x;\n');
    await observe([root,root],()=>fs.appendFile(source,'// immediate\n'),source);
    const replacement=path.join(root,'replacement');await fs.writeFile(replacement,'int y;\n');
    await observe([root],()=>fs.rename(replacement,source),source);
  }finally{await fs.rm(root,{recursive:true,force:true});}
});

test('source monitoring rejects excessive scope while retaining an existing subscription',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'cppulse-watch-bound-'));
  try{
    const source=path.join(root,'one.cpp');await fs.writeFile(source,'int x;\n');
    await observe([root],async monitor=>{
      assert.throws(()=>monitor.update([root,path.join(root,'other')]),/limit/);
      await fs.appendFile(source,'// still monitored\n');
    },source,1);
    for(const maximum of [0,-1,Infinity,1.5,65537]){assert.throws(()=>new SourceMonitor(()=>{},()=>{},maximum),/limit/);}
  }finally{await fs.rm(root,{recursive:true,force:true});}
});

test('an existing ancestor observes creation of a previously missing source directory',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'cppulse-watch-missing-'));
  try{
    const missing=path.join(root,'missing');
    await observe([root,missing],()=>fs.mkdir(missing),missing);
  }finally{await fs.rm(root,{recursive:true,force:true});}
});

test('reselecting a replaced source directory watches its new inode before the first write',async()=>{
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'cppulse-watch-replaced-directory-'));
  try{
    const selected=path.join(root,'selected');await fs.mkdir(selected);
    const source=path.join(selected,'one.cpp');await fs.writeFile(source,'int old_value;\n');
    await observe([root,selected],async monitor=>{
      await fs.rename(selected,path.join(root,'old-selected'));await fs.mkdir(selected);
      await fs.writeFile(source,'int new_value;\n');
      monitor.update([root,selected]);
      await fs.appendFile(source,'// first immediate write after reselect\n');
    },source);
  }finally{await fs.rm(root,{recursive:true,force:true});}
});
