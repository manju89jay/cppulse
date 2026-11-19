const test = require('node:test');
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { parseStoredJson, StoredNumber, storedHealth } = require('../dist/stored.js');

test('retained JSON preserves numeric lexemes, quoted escapes and object keys exactly', () => {
  const raw = '{"overall":45.454545454545454545,"count":9007199254740993,"nested":[-0,1.2300e-007,null,true,"1.234", "a\\\"b\\\\c"],"__proto__":{"safe":true}}';
  const parsed = parseStoredJson(raw);
  assert.ok(parsed.overall instanceof StoredNumber);
  assert.equal(parsed.overall.token,'45.454545454545454545');
  assert.equal(parsed.count.token,'9007199254740993');
  assert.equal(parsed.nested[0].token,'-0');
  assert.equal(parsed.nested[1].token,'1.2300e-007');
  assert.deepEqual(parsed.nested.slice(2),[null,true,'1.234','a"b\\c']);
  assert.equal(Object.getPrototypeOf(parsed),null);
  assert.equal(parsed.__proto__.safe,true);
});

test('retained JSON refuses duplicates, malformed syntax, excess depth and byte overflow', () => {
  for (const raw of ['{"x":1,"x":2}', '{"x":1,"\\u0078":2}', '[01]', '[1,]', '{"x":true false}',
    '{"x":NaN}', '{"x":Infinity}', '[1.]', '[.1]', '[1e]', 'true false', '"bad\nstring"',
    '['.repeat(66)+'0'+']'.repeat(66)]) {
    assert.throws(()=>parseStoredJson(raw), /JSON|nested/i, raw);
  }
  assert.throws(()=>parseStoredJson('"é"',3),/limit/);
});

const sourceDigest = 'a'.repeat(64);
const raw = () => '{"version":"2.0.0","id":"retained-health","consumer_assurance":"not_assessed","source_digest":"'+sourceDigest+'","scorer":{"id":"analyzed-kloc-context-v4","version":"4.0.0","loc_metric":"physical_loc","metric_version":"cppulse-metrics-1","configuration_digest":"'+'b'.repeat(64)+'","requires_buffer_coherence":true},"aggregate":{"availability":"scored","overall":45.454545454545454545},"contexts":[]}';
const view = (text=raw()) => {
  const sha256=createHash('sha256').update(text).digest('hex'),size_bytes=Buffer.byteLength(text);
  return {source:{digest:sourceDigest},artifacts:[{id:'health',contract:{kind:'maintenance_health',version:'2.0.0'},sha256,size_bytes}],
    facts:[{kind:'maintenance_health',artifact_id:'health',id:'retained-health',sha256,size_bytes,raw_json:text}]};
};

test('health projection carries original identity and exact tokens without recalculation', () => {
  const [health]=storedHealth(view());
  assert.equal(health.overall,'45.454545454545454545');
  assert.equal(health.scorerId,'analyzed-kloc-context-v4');
  assert.match(health.bufferVerification,/opt-in does not waive/);
  assert.equal(health.fact.aggregate.overall.token,health.overall);
  const legacy=raw().replace('context-v4','context-v3').replace('4.0.0','3.0.0').replace(',"requires_buffer_coherence":true','');
  assert.match(storedHealth(view(legacy))[0].bufferVerification,/Legacy v3.*not required/);
  assert.equal(storedHealth(view(raw().replace('45.454545454545454545','null')))[0].overall,null);
});

test('health projection refuses changed bytes, descriptor kind and unsupported scorer identities', () => {
  const changed=view();changed.facts[0].raw_json+=' ';
  assert.throws(()=>storedHealth(changed),/descriptor/);
  const kind=view();kind.artifacts[0].contract.kind='source';
  assert.throws(()=>storedHealth(kind),/descriptor/);
  for (const text of [raw().replace('context-v4','context-v99'),raw().replace('"4.0.0"','"3.0.0"'),
    raw().replace('"requires_buffer_coherence":true','"requires_buffer_coherence":false'),
    raw().replace(sourceDigest,'c'.repeat(64)),raw().replace('45.454545454545454545','"45"')]) {
    assert.throws(()=>storedHealth(view(text)),/identity/);
  }
});
