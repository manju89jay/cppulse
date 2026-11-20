/** Read retained numeric lexemes without rounding or calculating a score. */
import { createHash } from 'node:crypto';
import { JsonObject, MAX_RESPONSE_BYTES } from './protocol';

export class StoredNumber { constructor(readonly token: string) {} }
export type StoredValue = null | boolean | string | StoredNumber | StoredValue[] | { [key: string]: StoredValue };

/** A finite JSON reader: number tokens stay tokens, duplicate keys are errors. */
export function parseStoredJson(text: string, maxBytes = MAX_RESPONSE_BYTES): StoredValue {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1 || maxBytes > 64 * 1024 * 1024) {
    throw new Error('Stored fact byte limit must be a positive finite integer of at most 64 MiB.');
  }
  if (Buffer.byteLength(text, 'utf8') > maxBytes) { throw new Error('Stored fact exceeds the response limit.'); }
  let position = 0;
  const numberPattern = /-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/y;
  const fail = (): never => { throw new Error('Malformed or excessively nested retained JSON.'); };
  const whitespace = (): void => { while (/[\t\n\r ]/.test(text[position] ?? '') && position < text.length) { position++; } };
  const string = (): string => {
    const start = position++;
    while (position < text.length) {
      const character = text[position++];
      if (character === '\\') { position++; }
      else if (character === '"') {
        try { return JSON.parse(text.slice(start, position)); } catch { return fail(); }
      }
    }
    return fail();
  };
  const value = (depth: number): StoredValue => {
    if (depth > 64) { return fail(); }
    whitespace();
    const character = text[position];
    if (character === '"') { return string(); }
    if (character === '{' || character === '[') {
      position++;
      const array = character === '[';
      const result: StoredValue[] | { [key: string]: StoredValue } = array ? [] : Object.create(null);
      const end = array ? ']' : '}';
      whitespace();
      if (text[position] === end) { position++; return result; }
      while (position < text.length) {
        whitespace();
        if (array) { (result as StoredValue[]).push(value(depth + 1)); }
        else {
          if (text[position] !== '"') { return fail(); }
          const key = string();
          if (Object.prototype.hasOwnProperty.call(result, key)) { throw new Error('Duplicate retained JSON key.'); }
          whitespace();
          if (text[position++] !== ':') { return fail(); }
          (result as { [key: string]: StoredValue })[key] = value(depth + 1);
        }
        whitespace();
        const separator = text[position++];
        if (separator === end) { return result; }
        if (separator !== ',') { return fail(); }
      }
      return fail();
    }
    for (const [literal, decoded] of [['true', true], ['false', false], ['null', null]] as const) {
      if (text.startsWith(literal, position)) { position += literal.length; return decoded; }
    }
    numberPattern.lastIndex = position;
    const number = numberPattern.exec(text);
    if (!number) { return fail(); }
    position += number[0].length;
    return new StoredNumber(number[0]);
  };
  const result = value(0);
  whitespace();
  if (position !== text.length) { return fail(); }
  return result;
}

function record(value: StoredValue | undefined): { [key: string]: StoredValue } {
  if (value === null || typeof value !== 'object' || Array.isArray(value) || value instanceof StoredNumber) {
    throw new Error('Malformed retained maintenance-health object.');
  }
  return value;
}

/** Compare a decimal JSON lexeme with 0..100 without binary-float rounding. */
function scoreInRange(token: string): boolean {
  const match = /^(-?)([0-9]+)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?$/.exec(token);
  if (!match) { return false; }
  const digits = (match[2]! + (match[3] ?? '')).replace(/^0+/, '');
  if (!digits) { return true; } // Positive and negative decimal zero are zero.
  if (match[1] === '-') { return false; }
  const exponentText = match[4] ?? '0';
  const exponentDigits = exponentText.replace(/^[+-]?0*/, '');
  // Beyond this magnitude the exponent dominates every possible mantissa
  // in the bounded input. Clamp before converting, avoiding huge integers.
  const exponent = exponentDigits.length > 8 ? (exponentText.startsWith('-') ? -token.length - 3 : token.length + 3) : Number(exponentText);
  const order = digits.length - (match[3]?.length ?? 0) + exponent;
  if (order < 3) { return true; }
  if (order > 3) { return false; }
  return /^10*$/.test(digits); // At decimal order three, only exactly 100 fits.
}

export interface StoredHealth {
  artifactId: string;
  sha256: string;
  scorerId: string;
  scorerVersion: string;
  configurationDigest: string;
  bufferVerification: string;
  availability: string;
  overall: string | null;
  fact: { [key: string]: StoredValue };
}

/** Accept only an exact, pinned wrapper from a checked snapshot view. */
export function storedHealth(view: JsonObject, maxBytes = MAX_RESPONSE_BYTES): StoredHealth[] {
  return view.facts.filter((wrapper: JsonObject) => wrapper.kind === 'maintenance_health').map((wrapper: JsonObject) => {
    const descriptor = view.artifacts.find((artifact: JsonObject) => artifact.id === wrapper.artifact_id);
    if (!descriptor || descriptor.contract?.kind !== 'maintenance_health' || descriptor.contract?.version !== '2.0.0' || descriptor.sha256 !== wrapper.sha256 ||
        descriptor.size_bytes !== wrapper.size_bytes || typeof wrapper.raw_json !== 'string' ||
        Buffer.byteLength(wrapper.raw_json, 'utf8') !== wrapper.size_bytes ||
        createHash('sha256').update(wrapper.raw_json).digest('hex') !== wrapper.sha256) {
      throw new Error('Retained maintenance-health bytes do not match their descriptor.');
    }
    const fact = record(parseStoredJson(wrapper.raw_json, maxBytes));
    const scorer = record(fact.scorer), aggregate = record(fact.aggregate);
    const legacy = scorer.id === 'analyzed-kloc-context-v3' && scorer.version === '3.0.0' && !('requires_buffer_coherence' in scorer);
    const current = scorer.id === 'analyzed-kloc-context-v4' && scorer.version === '4.0.0' && scorer.requires_buffer_coherence === true;
    if (fact.version !== '2.0.0' || typeof fact.id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(fact.id) || wrapper.id !== fact.id ||
        fact.source_digest !== view.source.digest || fact.consumer_assurance !== 'not_assessed' || (!legacy && !current) ||
        scorer.loc_metric !== 'physical_loc' || scorer.metric_version !== 'cppulse-metrics-1' ||
        typeof scorer.configuration_digest !== 'string' || !/^[a-f0-9]{64}$/.test(scorer.configuration_digest) ||
        !Array.isArray(fact.contexts) || !['scored','partial','no_data'].includes(aggregate.availability as string) ||
        !(aggregate.overall === null || (aggregate.overall instanceof StoredNumber && scoreInRange(aggregate.overall.token)))) {
      throw new Error('Unsupported or inconsistent retained maintenance-health identity.');
    }
    return {
      artifactId: wrapper.artifact_id, sha256: wrapper.sha256, scorerId: scorer.id as string,
      scorerVersion: scorer.version as string, configurationDigest: scorer.configuration_digest,
      bufferVerification: legacy ? 'Legacy v3: parsed source and header byte verification was not required.' :
        'v4 requires verified parsed source and header bytes; inferred-parse opt-in does not waive this requirement.',
      availability: aggregate.availability, overall: aggregate.overall === null ? null : aggregate.overall.token, fact
    };
  });
}
