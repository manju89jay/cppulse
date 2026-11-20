/** Actual VS Code client: public CLI contracts and retained facts only. */
import * as vscode from 'vscode';
import path from 'node:path';
import { realpath } from 'node:fs/promises';
import { readWithin, decodeText } from './files';
import { runProcess, ProcessResult } from './process';
import { StoredHealth, StoredNumber, StoredValue, storedHealth } from './stored';
import { SourceMonitor } from './watch';
import { Capabilities, ClientLimits, Generation, JsonObject, clientLimits, splitSourceLines, columnToUtf16, decodeSourceUri, parseJson, parseSarif, parseSnapshot, safeRelativePath, requireOperationPins, validateCapabilities, validatePins } from './protocol';

interface Selection { workspaceRoot?: string; store?: string; runId?: string; manifestSha256?: string }
interface Action extends Selection { request?: string; policy?: string; output?: string; format?: 'html'|'json'|'pdf' }
interface Current { limits: ClientLimits; root: string; sourceRoot: string; store: string; view?: JsonObject; health?: StoredHealth[]; sarif?: JsonObject; message: string; diagnosticCount: number; gaps: string[]; sourcePaths: Set<string>; stale: boolean }

class Row extends vscode.TreeItem {
  constructor(label: string, readonly children: Row[] = [], description?: string, command?: vscode.Command) {
    super(label, children.length ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None);
    this.description = description;
    this.tooltip = description ? `${label}\n${description}` : label;
    this.command = command;
  }
}

function retainedRow(label: string, value: StoredValue): Row {
  if (value instanceof StoredNumber) { return new Row(label, [], value.token); }
  if (value === null) { return new Row(label, [], 'unavailable (stored null)'); }
  if (Array.isArray(value)) { return new Row(label, value.map((item,index) => retainedRow(String(index + 1), item))); }
  if (typeof value === 'object') { return new Row(label, Object.entries(value).map(([key,item]) => retainedRow(key,item))); }
  return new Row(label, [], String(value));
}

function addSourcePath(paths:Set<string>,relative:string):void {
  paths.add(relative);paths.add('');
  for(let parent=path.posix.dirname(relative);parent!=='.';parent=path.posix.dirname(parent)){paths.add(parent);}
}
function sourcePaths(names:Iterable<string>):Set<string> {
  const paths=new Set<string>();for(const name of names){addSourcePath(paths,name);}return paths;
}

class Results implements vscode.TreeDataProvider<Row> {
  private emitter = new vscode.EventEmitter<Row | undefined>();
  readonly onDidChangeTreeData = this.emitter.event;
  current?: Current;
  refresh(): void { this.emitter.fire(undefined); }
  dispose(): void { this.emitter.dispose(); }
  getTreeItem(row: Row): Row { return row; }
  getChildren(row?: Row): Row[] {
    if (row) { return row.children; }
    const selected = this.current;
    if (!selected) { return [new Row('No retained run selected'), new Row('Opening a project executes no cppulse command.')]; }
    const rows = [new Row(selected.message), new Row('Problems occurrences', [], String(selected.diagnosticCount))];
    const view = selected.view;
    if (view) {
      rows.push(new Row('Run', [
        new Row('ID', [], view.run.id), new Row('Manifest SHA-256', [], view.run.manifest_sha256),
        new Row('Stored run status', [], view.run.status), new Row('Stored input verification', [], view.run.input_verification),
        new Row('Source digest', [], view.source.digest), new Row('Interpretation', [], 'Historical retained facts; source matching does not authenticate the producer.')
      ]));
      if (view.assessment) {
        const display = view.assessment.display;
        rows.push(new Row('Stored policy assessment', [
          new Row('Gate', [], display.gate), new Row('Evaluated at', [], display.generated_at),
          ...Object.entries(display.scores).map(([key,value]) => new Row(key, [], value === null ? 'unavailable' : String(value))),
          new Row('Controls', display.controls.map((control: JsonObject) => new Row(`${control.id}: ${control.status}`, [], control.reason)))
        ], display.gate));
      } else { rows.push(new Row('Policy assessment', [], 'Not assessed; no gate inferred.')); }
      rows.push(new Row('Measured maintenance health', selected.health?.length ? selected.health.map(health => new Row(health.scorerId, [
        new Row('Stored availability', [], health.availability), new Row('Full-scope health (stored)', [], health.overall ?? 'unavailable'),
        new Row('Scorer version', [], health.scorerVersion), new Row('Configuration SHA-256', [], health.configurationDigest),
        new Row('Parsed byte verification', [], health.bufferVerification),
        new Row('Assurance', [], 'Experimental maintenance description; consumer assurance is not assessed.'),
        retainedRow('Stored calculation inputs and results', health.fact),
        new Row('Original retained bytes', [], health.sha256, { command:'cppulse.openArtifact', title:'Open retained health', arguments:[health.artifactId] })
      ])) : [new Row('Unavailable; no retained maintenance-health artifact.')]));
      rows.push(new Row('Contexts', view.contexts.map((context: JsonObject) => new Row(context.id, [], `${context.provenance}; ${context.language_standard}; ${context.target}`))));
      rows.push(new Row('Evidence artifacts', view.artifacts.map((artifact: JsonObject) => new Row(artifact.id, [], `${artifact.media_type}; SHA-256 ${artifact.sha256}`, { command:'cppulse.openArtifact', title:'Open retained bytes', arguments:[artifact.id] }))));
    } else { rows.push(new Row('Imported SARIF', [], 'Historical/imported producer claims; no policy acceptance or authentication inferred.')); }
    const gaps = [...selected.gaps, ...(view?.gaps ?? []).map((gap: JsonObject) => gap.message), ...(view?.limitations ?? []), ...(view?.run?.limitations ?? [])];
    rows.push(new Row('Gaps and limitations', gaps.length ? gaps.map(value => new Row(value)) : [new Row('No additional gaps reported within this selected scope.')]));
    return rows;
  }
}

function settings(root: string): vscode.WorkspaceConfiguration { return vscode.workspace.getConfiguration('cppulse', vscode.Uri.file(root)); }
function limitsFor(root: string): ClientLimits {
  const config = settings(root);
  return clientLimits({responseLimitMiB:config.get('responseLimitMiB'),sourceLimitMiB:config.get('sourceLimitMiB'),diagnosticLimit:config.get('diagnosticLimit')});
}
function localPath(root: string, value: string): string { return path.isAbsolute(value) ? value : path.resolve(root, value); }
function pinsArguments(selection: Selection): string[] {
  const pins = validatePins(selection.runId, selection.manifestSha256);
  return pins ? ['--run-id', pins.runId, '--manifest-sha256', pins.manifestSha256] : [];
}
function severity(value: string): vscode.DiagnosticSeverity {
  return value === 'error' ? vscode.DiagnosticSeverity.Error : value === 'warning' ? vscode.DiagnosticSeverity.Warning : vscode.DiagnosticSeverity.Information;
}

export function activate(context: vscode.ExtensionContext): JsonObject {
  const diagnostics = vscode.languages.createDiagnosticCollection('cppulse');
  const output = vscode.window.createOutputChannel('cppulse commands');
  const model = new Results();
  const clock = new Generation();
  let active: AbortController | undefined;
  let pending: Current | undefined;
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 30);
  status.text = '$(pulse) cppulse: no run'; status.command = 'cppulse.readRun'; status.show();
  const evidenceText = new Map<string, string>();
  context.subscriptions.push(diagnostics, output, model, status,
    vscode.window.registerTreeDataProvider('cppulse.results', model),
    vscode.workspace.registerTextDocumentContentProvider('cppulse-evidence', { provideTextDocumentContent: uri => evidenceText.get(uri.toString()) ?? 'Retained evidence is no longer selected.' }));

  const update = (): void => {
    status.text = model.current?.stale ? '$(warning) cppulse: stale' : model.current?.view ? `$(pulse) cppulse: ${model.current.view.run.status}` : '$(pulse) cppulse: retained view';
    model.refresh();
  };
  const trusted = (): void => { if (!vscode.workspace.isTrusted) { throw new Error('Trust this workspace before executing the configured cppulse CLI. Local SARIF reading remains available.'); } };
  const rootFor = async (selection: Selection): Promise<string> => {
    if (selection.workspaceRoot) { return path.resolve(selection.workspaceRoot); }
    const folders = vscode.workspace.workspaceFolders?.filter(folder => folder.uri.scheme === 'file') ?? [];
    if (folders.length === 1) { return folders[0]!.uri.fsPath; }
    if (!folders.length) { throw new Error('Open a local filesystem workspace or select one explicitly.'); }
    const chosen = await vscode.window.showQuickPick(folders.map(folder => ({ label:folder.name, root:folder.uri.fsPath })), { placeHolder:'Select the source workspace for this retained result' });
    if (!chosen) { throw new Error('Workspace selection cancelled.'); }
    return chosen.root;
  };
  const storeFor = (root: string, selection: Selection): string => localPath(root, selection.store ?? settings(root).get<string>('storeDirectory', '.cppulse-output'));
  const invoke = async (root: string, args: string[], abort: AbortSignal): Promise<ProcessResult> => {
    trusted();
    const config = settings(root);
    const executable = config.get<string>('executable', 'cppulse');
    const prefix = config.get<string[]>('arguments', []);
    if (!Array.isArray(prefix) || prefix.some(value => typeof value !== 'string')) { throw new Error('cppulse.arguments must be an array of literal strings.'); }
    output.appendLine(`\nExecuting literal argv: ${JSON.stringify([executable,...prefix,...args])}`);
    return runProcess(executable, [...prefix,...args], { cwd:root, maxBytes:limitsFor(root).maxResponseBytes, timeoutMs:config.get<number>('timeoutSeconds',300)*1000, signal:abort, log:(channel,chunk)=>output.append(`[${channel}] ${chunk}`) });
  };
  const capabilities = async (root: string, abort: AbortSignal): Promise<Capabilities> => {
    const result = await invoke(root, ['capabilities','--format','json'], abort);
    if (result.exitCode !== 0) { throw new Error(`cppulse capabilities failed (exit ${result.exitCode}). Install a matching CLI candidate. ${result.stderr}`); }
    return validateCapabilities(parseJson(result.stdout,'Client capabilities',limitsFor(root).maxResponseBytes));
  };
  const stale = (reason: string): void => {
    clock.invalidate(); active?.abort(); diagnostics.clear();
    const selected=model.current??pending;
    if (!selected) { status.text='$(warning) cppulse: source changed during selection';return; }
    model.current=selected;selected.stale = true; selected.diagnosticCount = 0;
    selected.message = `${reason} Retained pins remain historical; refresh explicitly.`; update();
  };
  const isSelected = (uri: vscode.Uri): boolean => {
    if (uri.scheme !== 'file') { return false; }
    return [model.current,pending].some(selected=>selected && [selected.sourceRoot,selected.root].some(root=>
      selected.sourcePaths.has(path.relative(root,uri.fsPath).split(path.sep).join('/'))));
  };
  const sourceMonitor=new SourceMonitor(filename=>{
    if(filename===null||isSelected(vscode.Uri.file(filename))){stale('Selected source/input changed on disk.');}
  },error=>stale(`Selected source monitoring failed (${error.message}); current diagnostics are unavailable.`));
  context.subscriptions.push(vscode.workspace.onDidChangeTextDocument(event => {
    // A clean model can reload after its filesystem notification and after a
    // fresh source-byte check. Only dirty edits are unsaved editor changes;
    // the filesystem watcher separately invalidates actual disk changes.
    if (event.document.isDirty && isSelected(event.document.uri)) { stale('Selected source has unsaved changes.'); }
  }));
  const refreshWatchers = ():void => {
    const directories=new Set<string>();
    for(const selected of [model.current,pending]){
      if(!selected){continue;}
      directories.add(selected.sourceRoot);directories.add(selected.root);directories.add(path.dirname(selected.root));
      for(const relative of selected.sourcePaths){directories.add(path.dirname(path.join(selected.sourceRoot,relative)));}
    }
    try{sourceMonitor.update(directories);}catch(error){
      stale(`Selected source monitoring is unavailable (${String(error)}).`);throw error;
    }
  };
  context.subscriptions.push({dispose:()=>{active?.abort();sourceMonitor.close();}});

  const applyDiagnostics = async (selected: Current, generation: number): Promise<void> => {
    const byFile = new Map<string,vscode.Diagnostic[]>();
    const expected = new Map<string,string>(selected.view?.source.files.map((file:JsonObject)=>[file.path,file.sha256]) ?? []);
    const sources = new Map<string,{uri:vscode.Uri;text:string;matches:boolean}>();
    const source = async (relative: string, fallbackHash?: string): Promise<{uri:vscode.Uri;text:string;matches:boolean} | undefined> => {
      if (sources.has(relative)) { return sources.get(relative); }
      try {
        const canonical=await realpath(path.join(selected.root,...relative.split('/')));
        addSourcePath(selected.sourcePaths,safeRelativePath(path.relative(selected.sourceRoot,canonical).split(path.sep).join('/')));
        if(!sourceMonitor.hasDirectory(path.dirname(canonical))){refreshWatchers();}
        const file = await readWithin(selected.root,relative,selected.limits.maxSourceBytes);
        if(file.path!==canonical){throw new Error('Selected source alias changed during the checked read.');}
        const uri = vscode.Uri.file(file.path);
        const declared=path.resolve(selected.root,...relative.split('/'));
        if (vscode.workspace.textDocuments.some(document=>document.isDirty && document.uri.scheme==='file' &&
            (document.uri.fsPath===file.path || document.uri.fsPath===declared))) { throw new Error('unsaved editor text'); }
        const digest = expected.get(relative) ?? fallbackHash;
        const matches = typeof digest === 'string' && file.sha256 === digest;
        if (digest && !matches) { throw new Error('current bytes differ from retained source'); }
        const item = {uri,text:decodeText(file.bytes),matches}; sources.set(relative,item); return item;
      } catch (error) { selected.gaps.push(`${relative}: ${String(error)}; no current diagnostic location was accepted.`); return undefined; }
    };
    const add = (relative:string, entry:{uri:vscode.Uri;text:string;matches:boolean}, line:number, column:number|undefined, kind:string, message:string, level:string, rule:string, details:string, legacy=false):void => {
      const lines = splitSourceLines(entry.text);
      if (!Number.isSafeInteger(line) || line < 1 || line > lines.length) { selected.gaps.push(`${relative}: unavailable source line ${line}.`);return; }
      const text = lines[line-1]!;
      let start=0,end=text.length;
      if (column !== undefined && entry.matches) {
        try { start=columnToUtf16(text,column,kind);end=Math.min(text.length,start+1); } catch(error) { selected.gaps.push(`${relative}:${line}: ${String(error)}; showing line only.`); }
      }
      const note = legacy ? (entry.matches ? '[Unverified legacy observation; bytes match an imported source claim] ' : '[Unverified legacy observation; historical location, source freshness unknown] ') : column === undefined ? '[Column unavailable] ' : '';
      const diagnostic = new vscode.Diagnostic(new vscode.Range(line-1,start,line-1,end),`${note}${message}\n${details}`,severity(level));
      diagnostic.source = legacy ? 'cppulse legacy (unverified)' : 'cppulse retained'; diagnostic.code=rule;
      const key=entry.uri.toString();byFile.set(key,[...(byFile.get(key)??[]),diagnostic]);
    };
    let count=0;
    for (const run of selected.sarif?.runs ?? []) {
      const hashes = new Map<string,string>();
      for (const artifact of run.artifacts ?? []) { if(artifact.location?.uri && artifact.hashes?.['sha-256']){ hashes.set(decodeSourceUri(artifact.location.uri),artifact.hashes['sha-256']); } }
      for (const result of run.results) {
        for (const location of result.locations) {
          const physical=location.physicalLocation,relative=decodeSourceUri(physical.artifactLocation.uri);
          const entry=await source(relative,hashes.get(relative));
          if (!entry?.matches) { if(entry){selected.gaps.push(`${relative}: no matching retained source digest; typed diagnostic not mapped.`);}continue; }
          const properties=result.properties??{};
          const details=`Context: ${properties.cppulseJobContextId??'not supplied'}; occurrence: ${properties.cppulseObservationId??++count}; comparison: ${result.baselineState??'not supplied'}${result.suppressions?.length?'; stored suppression present':''}`;
          add(relative,entry,physical.region.startLine,physical.region.startColumn,run.columnKind,result.message.text,result.level,result.ruleId,details);count++;
        }
      }
      for(const invocation of run.invocations??[])for(const notification of invocation.toolExecutionNotifications??[])selected.gaps.push(notification.message.text);
    }
    // analyze's public compatibility view has legacy findings, not typed native
    // producer facts. Keep them explicitly unverified and never infer a gate.
    if (!selected.sarif?.runs.some((run:JsonObject)=>run.results.length) && selected.view?.legacy?.findings) {
      const document=parseJson(selected.view.legacy.findings.raw_json,'Retained legacy findings',selected.limits.maxResponseBytes);
      const rows=document.findings;
      if(!Array.isArray(rows)||rows.length>selected.limits.maxDiagnostics){throw new Error('Legacy finding inventory exceeds this preview or is malformed.');}
      selected.gaps.push('Legacy observations have unverified historical binding; matching file bytes alone does not establish producer verification.');
      for(const [index,result] of rows.entries()){
        const relative=safeRelativePath(result.file),entry=await source(relative);
        selected.sourcePaths.add(relative);
        if(entry){add(relative,entry,result.line,entry.matches?result.column:undefined,'utf8Bytes',String(result.message),String(result.severity),String(result.rule_id),`Legacy record ${index+1}; no producer verification or policy acceptance inferred.`,true);count++;}
      }
    }
    refreshWatchers();
    if(await realpath(selected.root)!==selected.sourceRoot){stale('Selected source root changed while reading.');}
    if (!clock.current(generation)) { return; }
    diagnostics.clear();for(const [uri,rows] of byFile){diagnostics.set(vscode.Uri.parse(uri),rows);}
    selected.diagnosticCount=[...byFile.values()].reduce((sum,rows)=>sum+rows.length,0);
    if(selected.gaps.length){selected.message+=' Scope gaps are present.';}
    model.current=selected;update();
  };

  const readSelection = async (selection:Selection,root:string,signal:AbortSignal,generation:number):Promise<Current> => {
    const store=storeFor(root,selection);
    const read=await invoke(root,['explain','--store',store,...pinsArguments(selection)],signal);
    if(read.exitCode!==0){throw new Error(`Cannot read retained run (exit ${read.exitCode}): ${read.stderr || read.stdout}`);}
    const limits=limitsFor(root),view=parseSnapshot(read.stdout,limits);
    const pins={runId:view.run.id,manifestSha256:view.run.manifest_sha256};
    const selected:Current={limits,root,sourceRoot:await realpath(root),store,view,health:storedHealth(view,limits.maxResponseBytes),message:'Historical retained run selected; no checks were rerun.',diagnosticCount:0,gaps:[],sourcePaths:sourcePaths(view.source.files.map((file:JsonObject)=>file.path)),stale:false};
    pending=selected;
    try{
      refreshWatchers();
      const exported=await invoke(root,['export-sarif','--store',store,...pinsArguments(pins)],signal);
      if(exported.exitCode!==0){throw new Error(`Cannot export the selected pinned observations (exit ${exported.exitCode}): ${exported.stderr || exported.stdout}`);}
      selected.sarif=parseSarif(exported.stdout,view,limits);
      await applyDiagnostics(selected,generation);
      if(!clock.current(generation)){throw new Error('Selected source/input changed while reading; no current diagnostic view was accepted.');}
      return selected;
    }finally{if(pending===selected){pending=undefined;}refreshWatchers();}
  };
  const action = async (title:string,handler:(root:string,signal:AbortSignal,generation:number)=>Promise<unknown>,selection:Selection={}):Promise<unknown> => {
    trusted();const root=await rootFor(selection);active?.abort();const controller=new AbortController();active=controller;const generation=clock.begin();diagnostics.clear();
    if(model.current){model.current.message=`${title} in progress; previous selection is historical.`;model.current.diagnosticCount=0;update();}
    try{
      return await vscode.window.withProgress({location:vscode.ProgressLocation.Notification,title,cancellable:true},async(_progress,token)=>{
        const cancellation=token.onCancellationRequested(()=>controller.abort());
        try{await capabilities(root,controller.signal);return await handler(root,controller.signal,generation);}finally{cancellation.dispose();}
      });
    }catch(error){if(clock.current(generation)){if(model.current){model.current.message=`${String(error)} Previous pins remain historical.`;model.current.stale=true;update();}status.text='$(warning) cppulse: action incomplete';}throw error;}
    finally{if(active===controller){active=undefined;}}
  };
  const register = (command:string,handler:(args:any)=>Promise<unknown>|unknown):void => {
    context.subscriptions.push(vscode.commands.registerCommand(command,async(args?:any)=>{
      try{return await handler(args);}catch(error){output.appendLine(String(error));void vscode.window.showErrorMessage(`cppulse: ${error instanceof Error?error.message:String(error)}`);throw error;}
    }));
  };
  const selectFile = async (provided:string|undefined,label:string):Promise<string> => {
    if(provided){return path.resolve(provided);}
    const selected=await vscode.window.showOpenDialog({canSelectMany:false,filters:{JSON:['json']},openLabel:label});
    if(!selected?.[0]){throw new Error(`${label} cancelled.`);}return selected[0].fsPath;
  };
  const summary = ():JsonObject => ({message:model.current?.message??'No run selected',runId:model.current?.view?.run.id,manifestSha256:model.current?.view?.run.manifest_sha256,storedGate:model.current?.view?.assessment?.display.gate,diagnosticCount:model.current?.diagnosticCount??0,stale:model.current?.stale??false,gaps:[...(model.current?.gaps??[])],measuredHealth:(model.current?.health??[]).map(({fact,...health})=>health)});

  register('cppulse.readRun',(selection:Selection={})=>action('Read retained cppulse run',async(root,signal,generation)=>{await readSelection(selection,root,signal,generation);return summary();},selection));
  register('cppulse.doctor',(selection:Selection={})=>action('Inspect cppulse tools',async(root,signal)=>{const result=await invoke(root,['doctor'],signal);if(result.exitCode!==0){throw new Error(`Doctor failed (exit ${result.exitCode}): ${result.stderr || result.stdout}`);}const data=parseJson(result.stdout,'Doctor');const doc=await vscode.workspace.openTextDocument({content:JSON.stringify(data,null,2),language:'json'});await vscode.window.showTextDocument(doc,{preview:true});return data;},selection));
  register('cppulse.analyze',(selection:Selection={})=>action('Analyze selected C++ workspace',async(root,signal,generation)=>{
    const store=storeFor(root,selection),args=['analyze','--repo',root,'--output',store,'--format','html'];const database=settings(root).get<string>('compilationDatabase','');if(database){args.push('--compilation-database',localPath(root,database));}
    const result=await invoke(root,args,signal);if(![0,3].includes(result.exitCode??-1)){throw new Error(`Analysis failed (exit ${result.exitCode}): ${result.stderr || result.stdout}`);}const data=parseJson(result.stdout,'Analysis result');
    await readSelection({store,...requireOperationPins(data)},root,signal,generation);return {...summary(),operationExit:result.exitCode};
  },selection));
  for(const kind of ['collect','check'] as const){register(`cppulse.${kind}`,(selection:Action={})=>action(kind==='collect'?'Collect explicit cppulse request':'Check selected cppulse policy',async(root,signal,generation)=>{
    const file=await selectFile(kind==='collect'?selection.request:selection.policy,kind==='collect'?'Select collection request':'Select policy');
    const store=storeFor(root,selection),args=[kind,'--store',store,'--workspace',root,kind==='collect'?'--request':'--policy',file];if(kind==='check'){args.push(...pinsArguments(selection));}
    const result=await invoke(root,args,signal);if(![0,1,3].includes(result.exitCode??-1)){throw new Error(`${kind} failed (exit ${result.exitCode}): ${result.stderr || result.stdout}`);}const data=parseJson(result.stdout,`${kind} result`);const selected=data.run??data.final_run;
    if(selected){await readSelection({store,...requireOperationPins(selected)},root,signal,generation);}else{throw new Error(`${kind} returned no retained run; no old positive is substituted.`);}
    return {...summary(),operationExit:result.exitCode};
  },selection));}
  register('cppulse.report',(selection:Action={})=>action('Render selected evidence report',async(root,signal)=>{
    const current=model.current;if(!current?.view){throw new Error('Select a retained run before rendering its report.');}
    const format=selection.format??'html';if(!['html','json','pdf'].includes(format)){throw new Error('Unsupported report format.');}
    let outputPath=selection.output;if(!outputPath){outputPath=(await vscode.window.showSaveDialog({defaultUri:vscode.Uri.file(path.join(root,`cppulse-report.${format}`))}))?.fsPath;}if(!outputPath){throw new Error('Report output selection cancelled.');}
    const args=['report','--input',current.store,'--evidence','--format',format,'--output',path.resolve(outputPath),...pinsArguments({runId:current.view.run.id,manifestSha256:current.view.run.manifest_sha256})];
    const result=await invoke(root,args,signal);if(result.exitCode!==0){throw new Error(`Report rendering failed (exit ${result.exitCode}): ${result.stderr || result.stdout}`);}const data=parseJson(result.stdout,'Report result');if(settings(root).get<boolean>('openReports',true)){await vscode.commands.executeCommand('vscode.open',vscode.Uri.file(path.resolve(outputPath)));}return data;
  },selection));
  register('cppulse.openSarif',async(selection:Action={})=>{
    const root=await rootFor(selection),limits=limitsFor(root),file=await selectFile(selection.request,'Open local SARIF');
    const material=await readWithin(path.dirname(file),path.basename(file),limits.maxResponseBytes);
    const sarif=parseSarif(decodeText(material.bytes),undefined,limits);active?.abort();const generation=clock.begin();const paths=new Set<string>();for(const run of sarif.runs)for(const result of run.results)for(const location of result.locations)paths.add(decodeSourceUri(location.physicalLocation.artifactLocation.uri));
    const selected:Current={limits,root,sourceRoot:await realpath(root),store:'',sarif,message:'Imported historical SARIF selected; no CLI command executed.',diagnosticCount:0,gaps:['Imported SARIF does not authenticate its producer or establish policy acceptance.'],sourcePaths:sourcePaths(paths),stale:false};
    pending=selected;
    try{refreshWatchers();await applyDiagnostics(selected,generation);if(!clock.current(generation)){throw new Error('Selected source changed while reading imported SARIF.');}return summary();}
    finally{if(pending===selected){pending=undefined;}refreshWatchers();}
  });
  register('cppulse.openArtifact',async(id:string)=>{
    const selected=model.current,artifact=selected?.view?.artifacts.find((row:JsonObject)=>row.id===id);if(!selected?.view||!artifact){throw new Error('Select one retained artifact from the active run.');}
    const material=await readWithin(path.join(selected.store,'runs',selected.view.run.id),artifact.path,selected.limits.maxSourceBytes);if(material.sha256!==artifact.sha256||material.bytes.length!==artifact.size_bytes){throw new Error('Retained artifact bytes no longer match their descriptor.');}
    const uri=vscode.Uri.from({scheme:'cppulse-evidence',path:`/${selected.view.run.id}/${encodeURIComponent(id)}`,query:artifact.sha256});let text:string;
    try{text=decodeText(material.bytes);}catch{text=`Binary retained artifact\nID: ${id}\nSHA-256: ${artifact.sha256}\nBytes: ${artifact.size_bytes}\nMedia type: ${artifact.media_type}\nNo text interpretation was invented.`;}
    evidenceText.set(uri.toString(),text);const doc=await vscode.workspace.openTextDocument(uri);await vscode.window.showTextDocument(doc,{preview:true});return {id,sha256:material.sha256,bytes:material.bytes.length};
  });
  register('cppulse.showStatus',()=>summary());
  register('cppulse.clear',()=>{clock.invalidate();active?.abort();diagnostics.clear();model.current=undefined;pending=undefined;refreshWatchers();evidenceText.clear();status.text='$(pulse) cppulse: no run';model.refresh();});
  return {getState:summary};
}

export function deactivate():void { /* Registered disposables stop the active owned process. */ }
