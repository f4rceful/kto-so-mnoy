import { brotliCompressSync, constants, gunzipSync, brotliDecompressSync, gzipSync } from 'node:zlib';
import { readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const DIST = fileURLToPath(new URL('../dist/', import.meta.url));
const EXTENSIONS = new Set(['.js', '.css', '.svg', '.json', '.html']);
const MIN_SIZE = 1024;

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* walk(path);
    else yield path;
  }
}

const kb = (n) => `${(n / 1024).toFixed(1)} KB`;
let written = 0;
let saved = 0;

for (const file of walk(DIST)) {
  if (!EXTENSIONS.has(extname(file)) || statSync(file).size < MIN_SIZE) continue;
  const source = readFileSync(file);
  const variants = [
    ['.br', brotliCompressSync(source, { params: { [constants.BROTLI_PARAM_QUALITY]: 11, [constants.BROTLI_PARAM_SIZE_HINT]: source.length } }), brotliDecompressSync],
    ['.gz', gzipSync(source, { level: 9 }), gunzipSync],
  ];
  for (const [suffix, packed, unpack] of variants) {
    if (packed.length >= source.length) continue;
    if (!unpack(packed).equals(source)) throw new Error(`${file}${suffix} не совпадает с исходным файлом`);
    writeFileSync(file + suffix, packed);
    written += 1;
    if (suffix === '.br') saved += source.length - packed.length;
  }
}

console.log(`precompress: ${written} файлов, brotli экономит ${kb(saved)}`);
