const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const Module = require('node:module');
const path = require('node:path');
const file = path.resolve(__dirname, '../lib/candles.ts');
const compiled = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2017 } });
const loaded = new Module(file);
loaded._compile(compiled.outputText, file);
const { aggregateCandles } = loaded.exports;
const points = [
  { receivedAt: 2900, price: 101 },
  { receivedAt: 1000, price: 100 },
  { receivedAt: 2100, price: 98 },
  { receivedAt: 3000, price: 104, fundamental: 103 },
  { receivedAt: 2500, price: NaN },
];
const snapshot = JSON.stringify(points);
assert.deepEqual(aggregateCandles(points, 1000), [
  { time: 1000, open: 100, high: 100, low: 100, close: 100, fundamental: undefined },
  { time: 2000, open: 98, high: 101, low: 98, close: 101, fundamental: undefined },
  { time: 3000, open: 104, high: 104, low: 104, close: 104, fundamental: 103 },
]);
assert.equal(JSON.stringify(points), snapshot);
assert.deepEqual(aggregateCandles([], 1000), []);
assert.throws(() => aggregateCandles(points, 0), RangeError);
assert.equal(aggregateCandles(points, 5000)[0].close, 104);
console.log('Candle aggregation: passed (boundaries, order, OHLC, missing values, immutability)');
