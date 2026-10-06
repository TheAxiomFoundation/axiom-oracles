import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const old = [
  'maintained independently of Axiom',
  'Axiom never grades its own work',
  'Independent engine',
  'disagreeing with independent engines points at the encoding',
];
function contents(dir) {
  return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>{
    const p=path.join(dir,e.name);
    if (e.isDirectory() && e.name !== 'data') return contents(p);
    return e.isFile() && /\.(js|html|txt)$/.test(e.name) ? [p] : [];
  });
}
const source = ['OraclesV2.jsx','Households.jsx'].map(f=>fs.readFileSync('dashboard/src/components/'+f,'utf8')).join('\n');
const files = contents('dashboard/out');
const bundle = files.map(f=>fs.readFileSync(f,'utf8')).join('\n');
for (const s of old) { assert(!source.includes(s)); assert(!bundle.includes(s)); }
console.log(`Source old strings: 4 passed, 0 failed; exported old strings: 4 passed, 0 failed (${files.length} files).`);
