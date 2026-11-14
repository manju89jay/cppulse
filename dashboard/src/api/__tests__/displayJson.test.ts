import { expect, it } from "vitest";
import { displayJson } from "../displayJson";

it("preserves exact retained numeric tokens and strings without arithmetic", () => {
  const value = displayJson('{"line":9007199254740993,"decimal":1.0000000000000001,"exponent":-1e+09,"text":"line123 \\\" quoted","values":[0,true,null]}');
  expect(value).toEqual({line:"9007199254740993",decimal:"1.0000000000000001",exponent:"-1e+09",text:'line123 " quoted',values:["0",true,null]});
});

it("does not accept malformed JSON as a display document", () => {
  expect(() => displayJson('{"line":01}')).toThrow();
  expect(() => displayJson('{"line":-}')).toThrow();
});
