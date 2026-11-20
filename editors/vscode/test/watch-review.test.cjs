/** Independent actual-filesystem controls for retained source subscriptions. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const os=require('node:os');
const {SourceMonitor}=require('../dist/watch.js');

function tracked(maximum=4096){
 const events=[],errors=[],waiting=new Set();
 const monitor=new SourceMonitor(filename=>{events.push(filename);for(const waiter of waiting){if(waiter.expected===filename){clearTimeout(waiter.timer);waiting.delete(waiter);waiter.resolve();}}},error=>{errors.push(error);for(const waiter of waiting){clearTimeout(waiter.timer);waiter.reject(error);}waiting.clear();},maximum);
 return {monitor,events,errors,async mutate(expected,operation){
  let waiter;const received=new Promise((resolve,reject)=>{waiter={expected,resolve,reject,timer:setTimeout(()=>{waiting.delete(waiter);reject(new Error('Actual source-monitor event missing: '+String(expected)));},10000)};waiting.add(waiter);});
  try{await operation();await received;}catch(error){clearTimeout(waiter.timer);waiting.delete(waiter);throw error;}
 },close(){monitor.close();for(const waiter of waiting){clearTimeout(waiter.timer);}waiting.clear();}};
}
async function fixture(body){const root=await fs.mkdtemp(path.join(os.tmpdir(),'cppulse-watch-review-'));try{await body(root);}finally{await fs.rm(root,{recursive:true,force:true});}}

test('one persistent subscription observes immediate writes before and after atomic source replacement',async()=>fixture(async root=>{
 const source=path.join(root,"it's 😀.cpp"),replacement=path.join(root,'replacement.cpp');await fs.writeFile(source,'int x;\n');
 const state=tracked();try{
  state.monitor.update([root,root]);
  for(let iteration=0;iteration<12;iteration++)await state.mutate(source,()=>fs.appendFile(source,'// immediate '+iteration+'\n'));
  await fs.writeFile(replacement,'int replacement;\n');
  await state.mutate(source,()=>fs.rename(replacement,source));
  await state.mutate(source,()=>fs.appendFile(source,'// replacement still tracked\n'));
  assert.equal(state.errors.length,0);
 }finally{state.close();}
}));

test('declared alias parent and pre-resolved canonical target parent observe distinct mutations',async()=>fixture(async root=>{
 const declared=path.join(root,'declared'),actual=path.join(root,'actual');await fs.mkdir(declared);await fs.mkdir(actual);
 const target=path.join(actual,'target.cpp'),alias=path.join(declared,'alias.cpp');await fs.writeFile(target,'int x;\n');await fs.symlink('../actual/target.cpp',alias);
 const canonical=await fs.realpath(alias),state=tracked();try{
  state.monitor.update([path.dirname(alias),path.dirname(canonical)]);
  await state.mutate(canonical,()=>fs.appendFile(target,'// changed actual target\n'));
  await state.mutate(alias,()=>fs.unlink(alias));
  await state.mutate(alias,()=>fs.symlink('../actual/target.cpp',alias));
  assert.equal(state.errors.length,0);
 }finally{state.close();}
}));

test('root-parent subscription observes an immediate selected-directory rename',async()=>fixture(async root=>{
 const selected=path.join(root,'selected'),renamed=path.join(root,'renamed');await fs.mkdir(selected);
 const state=tracked();try{state.monitor.update([root,selected]);await state.mutate(selected,()=>fs.rename(selected,renamed));}finally{state.close();}
}));

test('failed partial registration and rejected limits preserve prior subscriptions',async()=>fixture(async root=>{
 const old=path.join(root,'old'),added=path.join(root,'added'),denied=path.join(root,'denied');for(const directory of [old,added,denied])await fs.mkdir(directory);
 const source=path.join(old,'source.cpp');await fs.writeFile(source,'int x;\n');const state=tracked(3);
 try{
  state.monitor.update([old]);await fs.chmod(denied,0);
  assert.throws(()=>state.monitor.update([old,added,denied]),/EACCES|permission/i);
  await state.mutate(source,()=>fs.appendFile(source,'// old subscription survived registration failure\n'));
  assert.throws(()=>state.monitor.update([old,added,denied,root]),/limit/);
  await state.mutate(source,()=>fs.appendFile(source,'// old subscription survived limit failure\n'));
  for(const maximum of [NaN,Infinity,-1,0,1.2,65537])assert.throws(()=>tracked(maximum));
 }finally{await fs.chmod(denied,0o700);state.close();}
}));

test('closed subscriptions receive no event from a later real write observed by a control',async()=>fixture(async root=>{
 const source=path.join(root,'source.cpp');await fs.writeFile(source,'int x;\n');const old=tracked(),control=tracked();
 try{old.monitor.update([root]);old.monitor.close();control.monitor.update([root]);await control.mutate(source,()=>fs.appendFile(source,'// after close\n'));assert.equal(old.events.length,0);}finally{old.close();control.close();}
}));

test('Linux invalid-UTF8 directory entry names invalidate conservatively', {skip:process.platform!=='linux'},async()=>fixture(async root=>{
 const invalid=Buffer.concat([Buffer.from(root+path.sep),Buffer.from([0xff]),Buffer.from('.cpp')]);const state=tracked();
 try{state.monitor.update([root]);await state.mutate(null,()=>fs.writeFile(invalid,'int x;\n'));assert.equal(state.errors.length,0);}finally{state.close();}
}));

test('updating an unchanged directory path rebinds a replaced directory inode',async()=>fixture(async root=>{
 const selected=path.join(root,'selected'),archived=path.join(root,'archived');await fs.mkdir(selected);
 const source=path.join(selected,'source.cpp');await fs.writeFile(source,'int original;\n');const state=tracked();
 try{
  state.monitor.update([root,selected]);
  await fs.rename(selected,archived);await fs.mkdir(selected);await fs.writeFile(source,'int replacement;\n');
  state.monitor.update([root,selected]);
  await state.mutate(source,()=>fs.appendFile(source,'// new inode still monitored\n'));
 }finally{state.close();}
}));
