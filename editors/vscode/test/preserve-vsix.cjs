/** Keep generated preview artifacts before packaging a newer local version. */
const fs = require('node:fs/promises');
const path = require('node:path');
const { createHash } = require('node:crypto');

async function preserveVsix(root) {
  const artifacts=path.join(root,'artifacts');
  await fs.mkdir(artifacts,{recursive:true});
  const source=path.join(artifacts,'cppulse-0.2.0-preview.vsix');
  let stat;
  try{stat=await fs.lstat(source);}catch(error){if(error.code==='ENOENT'){return;}throw error;}
  if(!stat.isFile()){throw new Error('Existing preview VSIX must be a regular file before packaging.');}
  const bytes=await fs.readFile(source);
  const digest=createHash('sha256').update(bytes).digest('hex');
  const history=path.join(artifacts,'history');
  await fs.mkdir(history,{recursive:true});
  const destination=path.join(history,`${digest}.vsix`);
  try{await fs.writeFile(destination,bytes,{flag:'wx'});}catch(error){
    if(error.code!=='EEXIST'){throw error;}
    if(!(await fs.readFile(destination)).equals(bytes)){throw new Error('Preserved VSIX bytes do not match their digest.');}
  }
  return {path:destination,sha256:digest,size_bytes:bytes.length};
}

module.exports={preserveVsix};
if(require.main===module){preserveVsix(path.resolve(__dirname,'..')).catch(error=>{console.error(error);process.exitCode=1;});}
