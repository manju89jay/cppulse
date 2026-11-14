const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { createHash } = require('node:crypto');
const path = require('node:path');
const protocol = require('../dist/protocol.js');

const capabilities = JSON.parse(readFileSync(path.join(__dirname, '../contracts/client-capabilities.fixture.json'), 'utf8'));
const sha = value => createHash('sha256').update(value).digest('hex');
const fixture = JSON.parse(readFileSync(path.join(__dirname, '../contracts/snapshot-view.fixture.json'), 'utf8'));
const manifest = fixture.run_manifest_json;
const view = () => structuredClone(fixture);
const sarif = () => ({version:'2.1.0',runs:[{columnKind:'unicodeCodePoints',tool:{driver:{name:'cppulse',version:'0.2.0.dev2'}},results:[],properties:{cppulseOwningRunId:view().run.id,cppulseInputRunId:view().run.id,cppulseInputManifestSha256:sha(manifest),cppulseSourceDigest:view().source.digest}}]});

test('accepts only compatible explicit backend capabilities', () => {
  assert.equal(protocol.validateCapabilities(capabilities).tool_version,'0.2.0.dev2');
  for (const changed of [{contract_version:'99.0.0'},{snapshot_view_versions:['9.0.0']},{sarif_column_kinds:[]},{execution_on_open:true},{commands:['doctor']}]) {
    assert.throws(()=>protocol.validateCapabilities({...capabilities,...changed}));
  }
});

test('requires paired exact pins and rejects unsafe identifiers', () => {
  assert.deepEqual(protocol.validatePins(undefined,undefined),undefined);
  assert.deepEqual(protocol.validatePins('run-1','b'.repeat(64)),{runId:'run-1',manifestSha256:'b'.repeat(64)});
  for(const pins of [['run-1',undefined],[undefined,'b'.repeat(64)],['../run','b'.repeat(64)],['run','bad']]) assert.throws(()=>protocol.validatePins(...pins));
});

test('checks snapshot manifest/source integrity without rounding display tokens', () => {
  const checked=protocol.parseSnapshot(JSON.stringify(view()));
  assert.equal(checked.assessment.display.controls[0].weight,'9007199254740993.0');
  for(const change of [{version:'9.0.0'},{run_manifest_json:manifest+' '},{run:{...view().run,source_digest:'c'.repeat(64)}}]) assert.throws(()=>protocol.parseSnapshot(JSON.stringify({...view(),...change})));
  assert.throws(()=>protocol.parseSnapshot(' '.repeat(protocol.MAX_RESPONSE_BYTES+1)));
});

test('pins SARIF to the exact selected owning run, manifest and source', () => {
  assert.equal(protocol.parseSarif(JSON.stringify(sarif()),view()).runs.length,1);
  for(const field of ['cppulseOwningRunId','cppulseInputManifestSha256','cppulseSourceDigest']) {
    const altered=sarif();altered.runs[0].properties[field]='wrong';assert.throws(()=>protocol.parseSarif(JSON.stringify(altered),view()));
  }
  const altered=sarif();altered.runs[0].columnKind='bytes';assert.throws(()=>protocol.parseSarif(JSON.stringify(altered),view()));
});

test('retains same basenames, spaces, apostrophes and encoded UTF-8 source identities', () => {
  assert.equal(protocol.decodeSourceUri('one/same.cpp'),'one/same.cpp');
  assert.equal(protocol.decodeSourceUri('two/same.cpp'),'two/same.cpp');
  assert.equal(protocol.decodeSourceUri('dir%20with%20spaces/it%27s.cpp'),"dir with spaces/it's.cpp");
  assert.equal(protocol.decodeSourceUri('src/%C3%A9.cpp'),'src/é.cpp');
  for(const value of ['../secret','%2e%2e/secret','/absolute','file:///tmp/a','https://example/a','C:/a','dir\\a','a//b','a/%00b','bad%ZZ']) assert.throws(()=>protocol.decodeSourceUri(value));
});

test('maps code points and native byte columns to UTF-16 without splitting UTF-8', () => {
  const line='// é 😀 int value = 1;';
  const prefix='// é 😀 ';
  const codepointColumn=Array.from(prefix).length+1;
  const byteColumn=Buffer.byteLength(prefix,'utf8')+1;
  assert.equal(protocol.columnToUtf16(line,codepointColumn,'unicodeCodePoints'),prefix.length);
  assert.equal(protocol.columnToUtf16(line,byteColumn,'utf8Bytes'),prefix.length);
  assert.equal(protocol.columnToUtf16(line,prefix.length+1,'utf16CodeUnits'),prefix.length);
  assert.throws(()=>protocol.columnToUtf16(line,byteColumn-2,'utf8Bytes'));
  for(const bad of [0,-1,1.2,999]) assert.throws(()=>protocol.columnToUtf16(line,bad,'unicodeCodePoints'));
});

test('generation prevents delayed old results from replacing newer selections', () => {
  const clock=new protocol.Generation();const old=clock.begin();const current=clock.begin();assert.equal(clock.current(old),false);assert.equal(clock.current(current),true);clock.invalidate();assert.equal(clock.current(current),false);
});

test('operation results require their own complete pins before any follow-up read', () => {
  assert.deepEqual(protocol.requireOperationPins({run_id:'operation-1',manifest_sha256:'b'.repeat(64)}),{runId:'operation-1',manifestSha256:'b'.repeat(64)});
  for(const result of [{},{run_id:'operation-1'},{manifest_sha256:'b'.repeat(64)},{run_id:'../bad',manifest_sha256:'b'.repeat(64)}]) {
    assert.throws(()=>protocol.requireOperationPins(result),/run|pins|Select/);
  }
});

test('finite diagnostic limits count every SARIF location, including repeated locations', () => {
  const document=sarif();
  document.runs[0].results=[{ruleId:'CPP-CX-001',level:'warning',message:{text:'multi-location observation'},
    locations:Array.from({length:protocol.MAX_DIAGNOSTICS+1},()=>({physicalLocation:{artifactLocation:{uri:'one/same.cpp'},region:{startLine:1}}}))}];
  assert.throws(()=>protocol.parseSarif(JSON.stringify(document)),/occurrences/);
});

test('configured client limits are finite and overflow remains an explicit error', () => {
  const limits=protocol.clientLimits({responseLimitMiB:2,sourceLimitMiB:3,diagnosticLimit:1});
  assert.equal(limits.maxResponseBytes,2*1024*1024); assert.equal(limits.maxSourceBytes,3*1024*1024);
  assert.equal(limits.maxDiagnostics,1);
  for(const config of [{responseLimitMiB:0},{sourceLimitMiB:Infinity},{diagnosticLimit:1.5},{diagnosticLimit:100001}]) assert.throws(()=>protocol.clientLimits(config),/limit/i);
  assert.throws(()=>protocol.parseJson('{}','sample',1),/limit/);
  const document=sarif();document.runs[0].results=[{ruleId:'CPP-CX-001',level:'warning',message:{text:'two locations'},
    locations:Array.from({length:2},()=>({physicalLocation:{artifactLocation:{uri:'one/same.cpp'},region:{startLine:1}}}))}];
  assert.throws(()=>protocol.parseSarif(JSON.stringify(document),undefined,limits),/occurrences/);
});
