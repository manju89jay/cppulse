/** Synchronous subscription to finite, nonrecursive retained-source directories. */
import { watch, FSWatcher, statSync } from 'node:fs';
import path from 'node:path';

export class SourceMonitor {
  private watchers = new Map<string,FSWatcher>();
  private identities = new Map<string,{dev:bigint;ino:bigint}>();
  constructor(private changed:(filename:string|null)=>void, private failed:(error:Error)=>void, private maximum=4096) {
    if(!Number.isSafeInteger(maximum)||maximum<1||maximum>65536){throw new Error('Source watch limit must be a finite positive integer.');}
  }
  hasDirectory(directory:string):boolean {
    if(!this.watchers.has(directory)){return false;}
    try{
      const current=statSync(directory,{bigint:true}),recorded=this.identities.get(directory);
      return current.isDirectory()&&recorded?.dev===current.dev&&recorded.ino===current.ino;
    }catch{return false;}
  }
  update(directories:Iterable<string>):void {
    const desired=new Set(directories);
    if(desired.size>this.maximum){throw new Error(`Source monitoring exceeds the ${this.maximum}-directory preview limit.`);}
    const added=new Map<string,FSWatcher>();
    const identities=new Map<string,{dev:bigint;ino:bigint}>();
    try{
      for(const directory of desired){
        if(this.hasDirectory(directory)){continue;}
        this.watchers.get(directory)?.close();this.watchers.delete(directory);this.identities.delete(directory);
        let watcher:FSWatcher|undefined;
        try{
          const before=statSync(directory,{bigint:true});
          if(!before.isDirectory()){throw new Error('Selected source monitor requires a directory.');}
          // Nonrecursive fs.watch registers before returning. Watching selected
          // parent directories survives file replacement and avoids walking an
          // entire repository or waiting for VS Code's async watcher service.
          watcher=watch(directory,{persistent:false,encoding:'buffer'},(_event,filename)=>{
            if(!watcher||this.watchers.get(directory)!==watcher){return;}
            if(filename===null){this.changed(null);return;}
            let decoded:string;
            try{decoded=new TextDecoder('utf-8',{fatal:true}).decode(filename);}
            catch{this.changed(null);return;}
            this.changed(path.join(directory,decoded));
          });
          const after=statSync(directory,{bigint:true});
          if(!after.isDirectory()||before.dev!==after.dev||before.ino!==after.ino){throw new Error('Source directory changed while monitoring was being registered.');}
          identities.set(directory,{dev:before.dev,ino:before.ino});
        }catch(error){
          watcher?.close();
          const code=(error as NodeJS.ErrnoException).code;
          // An existing ancestor is watched too. A missing source directory
          // cannot supply a current diagnostic; its later creation invalidates
          // that explicitly incomplete selection through the ancestor watch.
          if(code==='ENOENT'||code==='ENOTDIR'){continue;}
          throw error;
        }
        watcher.on('error',error=>{
          if(this.watchers.get(directory)!==watcher){return;}
          this.watchers.delete(directory);this.identities.delete(directory);watcher.close();this.failed(error);
        });
        added.set(directory,watcher);
      }
    }catch(error){for(const watcher of added.values()){watcher.close();}throw error;}
    for(const [directory,watcher] of this.watchers){if(!desired.has(directory)){watcher.close();this.watchers.delete(directory);this.identities.delete(directory);}}
    for(const [directory,watcher] of added){this.watchers.set(directory,watcher);this.identities.set(directory,identities.get(directory)!);}
  }
  close():void {for(const watcher of this.watchers.values()){watcher.close();}this.watchers.clear();this.identities.clear();}
}
