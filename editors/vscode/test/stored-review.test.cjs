/** Independent protocol counterexamples retained from the Cloud review. */
const test=require('node:test');
const assert=require('node:assert/strict');
const {createHash}=require('node:crypto');
const {storedHealth,parseStoredJson,StoredNumber}=require('../dist/stored.js');
const rawBase={version:'2.0.0',id:'retained-health',required_context_ids:[],optional_context_ids:[],limitations:[],consumer_assurance:'not_assessed',source_digest:'a'.repeat(64),scorer:{id:'analyzed-kloc-context-v4',version:'4.0.0',loc_metric:'physical_loc',metric_version:'cppulse-metrics-1',profile:'default',allow_inferred_parse:false,required_rule_ids:['CPP-CX-001'],required_rule_versions:{'CPP-CX-001':'1'},categories:[{category:'complexity',weight:3,density_cap:5}],configuration_digest:'b'.repeat(64),requires_buffer_coherence:true},aggregate:{availability:'scored',overall:100,by_category:{complexity:100},worst_context_id:null,incomplete_required_context_ids:[],limitations:[]},contexts:[]};
function view(raw=JSON.stringify(rawBase),version='2.0.0') {const sha256=createHash('sha256').update(raw).digest('hex'),size_bytes=Buffer.byteLength(raw);return {source:{digest:rawBase.source_digest},artifacts:[{id:'health',contract:{kind:'maintenance_health',version},sha256,size_bytes}],facts:[{kind:'maintenance_health',id:'retained-health',artifact_id:'health',sha256,size_bytes,raw_json:raw}]};}
function changed(mutator){let fact=structuredClone(rawBase);mutator(fact);return view(JSON.stringify(fact));}
test('new health presentation rejects unsupported descriptor versions even with matching bytes',()=>{
 for(const version of ['99.0.0','1.0.0',null])assert.throws(()=>storedHealth(view(undefined,version)));
 const missing=view();delete missing.artifacts[0].contract.version;assert.throws(()=>storedHealth(missing));
});
test('new health presentation rejects invented availability and assurance states',()=>{
 for(const availability of ['certified','passed','',true,0,null])assert.throws(()=>storedHealth(changed(f=>{f.aggregate.availability=availability;})));
 for(const consumer_assurance of ['certified','assessed','',true,null])assert.throws(()=>storedHealth(changed(f=>{f.consumer_assurance=consumer_assurance;})));
});
test('new health presentation rejects impossible health scores but preserves accepted exact tokens',()=>{
 for(const overall of [-1,100.0001,101,-1e100])assert.throws(()=>storedHealth(changed(f=>{f.aggregate.overall=overall;})));
 for(const token of ['1e999','-1e999'])assert.throws(()=>storedHealth(view(JSON.stringify(rawBase).replace('"overall":100','"overall":'+token))));
 for(const token of ['0','-0','1e2','45.454545454545454545','99.999999999999999999999']) {
  assert.equal(storedHealth(view(JSON.stringify(rawBase).replace('"overall":100','"overall":'+token)))[0].overall,token);
 }
});
test('stored JSON parser refuses invalid caller limits',()=>{
 for(const limit of [NaN,Infinity,-Infinity,0,-1,1.5,64*1024*1024+1])assert.throws(()=>parseStoredJson('0',limit));
});
test('stored JSON parser keeps escaped keys/strings, deep values and all valid numeric spellings',()=>{
 const strings=['x','\\" braces{}[] numbers01','line\nfeed\rtab\t','emoji 😀','\u0000','"\\/'];
 const numeric=['0','-0','123','-9007199254740993','1.2300','-0.000001','1e+999','1E-009','3.1415926535897932384626'];
 for(let iteration=0;iteration<300;iteration++) {
  const string=strings[iteration%strings.length],token=numeric[iteration%numeric.length];
  const raw='{'+JSON.stringify(string)+':['+token+','+JSON.stringify(string)+',true,false,null,{"nested":'+token+'}]}';
  const parsed=parseStoredJson(raw),array=parsed[string];
  assert.equal(array[0].token,token);assert.ok(array[0] instanceof StoredNumber);
  assert.equal(array[1],string);assert.equal(array[5].nested.token,token);
 }
 assert.equal(parseStoredJson('['.repeat(64)+'1'+']'.repeat(64))[0][0][0][0][0] instanceof Array,true);
 assert.throws(()=>parseStoredJson('['.repeat(65)+'1'+']'.repeat(65)));
 const many=parseStoredJson('['+Array.from({length:30000},(_,i)=>String(i)).join(',')+']');
 assert.equal(many.length,30000);assert.equal(many.at(-1).token,'29999');
});
test('stored JSON parser rejects escaped duplicate keys and malformed boundary tokens',()=>{
 for(const raw of ['{"a":1,"\\u0061":2}','{"a":1,"a":2}','[truex]','[null0]','{"x":00}','[1e+]','[1.e2]','{"\\q":0}','["\\uZZZZ"]','["\\"]','["raw\nnewline"]','{"x":1,}','[,0]','{"x" 1}','{"x":}', '0.0.0'])assert.throws(()=>parseStoredJson(raw),undefined,raw);
});
test('stored health does not relabel historical v3 coherence and refuses mixed versions',()=>{
 let legacy=structuredClone(rawBase);legacy.scorer.id='analyzed-kloc-context-v3';legacy.scorer.version='3.0.0';delete legacy.scorer.requires_buffer_coherence;
 assert.match(storedHealth(view(JSON.stringify(legacy)))[0].bufferVerification,/Legacy v3/);
 legacy.scorer.requires_buffer_coherence=true;assert.throws(()=>storedHealth(view(JSON.stringify(legacy))));
 for(const mutate of [f=>f.scorer.version='3.0.0',f=>delete f.scorer.requires_buffer_coherence,f=>f.source_digest='c'.repeat(64)])assert.throws(()=>storedHealth(changed(mutate)));
 const bad=view();bad.facts[0].raw_json+=' ';assert.throws(()=>storedHealth(bad));
});

test('stored health rejects mismatched fact identity and unsupported metric methods',()=>{
 for(const mutate of [f=>f.id='other-health',f=>delete f.id,f=>f.scorer.loc_metric='severity_proxy',f=>f.scorer.metric_version='unknown'])assert.throws(()=>storedHealth(changed(mutate)));
});

test('health token bounds are exact even beyond binary64 precision and exponent range',()=>{
 for(const token of ['100.00000000000000000001','-1e-999','1.00000000000000000000001e2','100.'+'0'.repeat(5000)+'1','1e'+'9'.repeat(1000)])assert.throws(()=>storedHealth(view(JSON.stringify(rawBase).replace('"overall":100','"overall":'+token))));
 for(const token of ['0e'+'9'.repeat(1000),'-0e-999','1e-999','1e-'+'9'.repeat(1000),'100.'+'0'.repeat(5000),'1.00e2'])assert.equal(storedHealth(view(JSON.stringify(rawBase).replace('"overall":100','"overall":'+token)))[0].overall,token);
});

test('health fact IDs follow common fact IDs rather than the shorter run-ID syntax',()=>{
 for(const id of ['health-'+'a'.repeat(64),'a'.repeat(128),'health:clang19.fixture-1_v4']){
  const fact=structuredClone(rawBase);fact.id=id;const selected=view(JSON.stringify(fact));selected.facts[0].id=id;
  assert.equal(storedHealth(selected)[0].artifactId,'health');
 }
 for(const id of ['a'.repeat(129),'_bad','.bad','../bad','bad/slash']){
  const fact=structuredClone(rawBase);fact.id=id;const selected=view(JSON.stringify(fact));selected.facts[0].id=id;
  assert.throws(()=>storedHealth(selected));
 }
});
