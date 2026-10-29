import { INLINE } from './mdParse';

const BULLET = /^\s*[-*•]\s+/;
const NUMBER = /^\s*\d+[.)]\s+/;
const LIST_PREFIX = /^\s*(?:[-*•]|\d+[.)])\s+/;
const HEADING = /^#{1,3}\s+/;
const isWordChar = (ch) => /[\p{L}\p{N}_]/u.test(ch);

const lineStart = (v, i) => (i === 0 ? 0 : v.lastIndexOf('\n', i - 1) + 1);
const lineEnd = (v, i) => {
  const n = v.indexOf('\n', i);
  return n === -1 ? v.length : n;
};
const fits = (r, max) => (r && r.value.length <= max ? r : null);

const selectedLines = (value, start, end) => {
  const last = end > start && value[end - 1] === '\n' ? end - 1 : end;
  return [lineStart(value, start), lineEnd(value, last)];
};

const withoutMarks = (text, spans, base = 0) => {
  const drop = new Set();
  for (const sp of spans) {
    for (let i = 0; i < sp.mark; i++) {
      drop.add(sp.start + i - base);
      drop.add(sp.end - 1 - i - base);
    }
  }
  return text.split('').filter((_, i) => !drop.has(i)).join('');
};

function findSpans(text, base = 0, out = []) {
  let from = 0;
  for (;;) {
    const m = INLINE.exec(text.slice(from));
    if (!m) break;
    const bold = m[1] !== undefined;
    const mark = bold ? 2 : 1;
    const start = base + from + m.index;
    out.push({ kind: bold ? 'bold' : 'italic', mark, start, end: start + m[0].length });
    findSpans(bold ? m[1] : m[2], start + mark, out);
    from += m.index + m[0].length;
  }
  return out;
}

function enclosing(kind, value, s, e) {
  const ls = lineStart(value, s);
  return findSpans(value.slice(ls, lineEnd(value, s)), ls)
    .filter((sp) => sp.kind === kind && sp.start <= s && e <= sp.end)
    .sort((a, b) => a.end - a.start - (b.end - b.start))[0];
}

export function formatState({ value, start, end }) {
  const ls = lineStart(value, start);
  const lines = value.slice(ls, lineEnd(value, end)).split('\n').filter((l) => l.trim());
  const state = {
    bold: false,
    italic: false,
    ul: lines.length > 0 && lines.every((l) => BULLET.test(l)),
    ol: lines.length > 0 && lines.every((l) => NUMBER.test(l)),
    heading: lines.some((l) => HEADING.test(l)),
  };
  if (!value.slice(start, end).includes('\n')) {
    state.bold = !!enclosing('bold', value, start, end);
    state.italic = !!enclosing('italic', value, start, end);
  }
  return state;
}

function wrapPart(part, mark) {
  if (!part.trim()) return part;
  return part.match(/^\s*/)[0] + mark + part.trim() + mark + part.match(/\s*$/)[0];
}

function inlineOne(kind, value, s, e, force) {
  const mark = kind === 'bold' ? '**' : '*';
  const m = mark.length;
  let a = s;
  let b = e;
  while (a < b && /\s/.test(value[a])) a++;
  while (b > a && /\s/.test(value[b - 1])) b--;
  const collapsed = a === b;
  if (collapsed) a = b = s;

  const inside = enclosing(kind, value, a, b);
  if (inside) {
    if (force === 'on') return { value, start: s, end: e };
    const cs = inside.start + m;
    const ce = inside.end - m;
    const from = collapsed ? cs : Math.max(a, cs);
    const to = collapsed ? ce : Math.min(b, ce);
    const left = wrapPart(value.slice(cs, from), mark);
    const right = wrapPart(value.slice(to, ce), mark);
    const mid = value.slice(from, to);
    const start = inside.start + left.length;
    return { value: value.slice(0, inside.start) + left + mid + right + value.slice(inside.end), start, end: start + mid.length };
  }
  if (force === 'off') return { value, start: s, end: e };

  if (collapsed) {
    const ls = lineStart(value, s);
    const le = lineEnd(value, s);
    while (a > ls && isWordChar(value[a - 1])) a--;
    while (b < le && isWordChar(value[b])) b++;
    if (a === b) {
      const placeholder = 'текст';
      return { value: value.slice(0, s) + mark + placeholder + mark + value.slice(s), start: s + m, end: s + m + placeholder.length };
    }
  }

  const ls = lineStart(value, a);
  const spans = findSpans(value.slice(ls, lineEnd(value, a)), ls).filter((sp) => sp.kind === kind);
  for (let hit; (hit = spans.find((sp) => sp.start < b && sp.end > a && (sp.start < a || sp.end > b))); ) {
    a = Math.min(a, hit.start);
    b = Math.max(b, hit.end);
  }
  const inner = withoutMarks(value.slice(a, b), spans.filter((sp) => sp.start >= a && sp.end <= b), a);
  return { value: value.slice(0, a) + mark + inner + mark + value.slice(b), start: a + m, end: a + m + inner.length };
}

export function toggleInline(kind, { value, start, end }, max = Infinity) {
  if (!value.slice(start, end).includes('\n')) return fits(inlineOne(kind, value, start, end), max);

  const segs = [];
  for (let p = start; p <= end; ) {
    const le = lineEnd(value, p);
    const seg = [p, Math.min(le, end)];
    if (value.slice(seg[0], seg[1]).trim()) segs.push(seg);
    p = le + 1;
  }
  if (!segs.length) return null;
  const allOn = segs.every(([s, e]) => enclosing(kind, value, s, e));
  let text = value;
  for (const [s, e] of [...segs].reverse()) text = inlineOne(kind, text, s, e, allOn ? 'off' : 'on').value;
  return fits({ value: text, start, end: Math.max(start, end + text.length - value.length) }, max);
}

export function toggleList(kind, { value, start, end }, max = Infinity) {
  const [ls, le] = selectedLines(value, start, end);
  const lines = value.slice(ls, le).split('\n');
  const re = kind === 'ul' ? BULLET : NUMBER;
  const filled = lines.filter((l) => l.trim());
  const allOn = filled.length > 0 && filled.every((l) => re.test(l));
  let n = 0;
  const text = lines
    .map((l) => {
      if (!l.trim()) return l;
      const bare = l.replace(LIST_PREFIX, '').replace(HEADING, '');
      if (allOn) return bare;
      return kind === 'ul' ? `- ${bare}` : `${++n}. ${bare}`;
    })
    .join('\n');
  const value2 = value.slice(0, ls) + text + value.slice(le);
  const collapsed = start === end;
  return fits({ value: value2, start: collapsed ? ls + text.length : ls, end: ls + text.length }, max);
}

export function clearFormatting({ value, start, end }) {
  const [ls, le] = selectedLines(value, start, end);
  const text = value
    .slice(ls, le)
    .split('\n')
    .map((l) => {
      const line = l.replace(LIST_PREFIX, '').replace(HEADING, '');
      return withoutMarks(line, findSpans(line));
    })
    .join('\n');
  return { value: value.slice(0, ls) + text + value.slice(le), start: ls, end: ls + text.length };
}

export function continueList({ value, start, end }) {
  if (start !== end) return null;
  const ls = lineStart(value, start);
  const le = lineEnd(value, start);
  const line = value.slice(ls, le);
  const bullet = /^(\s*)[-*•]\s+/.exec(line);
  const number = bullet ? null : /^(\s*)(\d+)([.)])\s+/.exec(line);
  const m = bullet ?? number;
  if (!m || start < ls + m[0].length) return null;
  if (!line.slice(m[0].length).trim()) {
    return { value: value.slice(0, ls) + value.slice(le), start: ls, end: ls };
  }
  const prefix = bullet ? `${m[1]}- ` : `${m[1]}${Number(m[2]) + 1}${m[3]} `;
  const before = value.slice(0, start).replace(/[ \t]+$/, '');
  const pos = before.length + 1 + prefix.length;
  return { value: before + '\n' + prefix + value.slice(start).replace(/^[ \t]+/, ''), start: pos, end: pos };
}

export function createHistory(limit = 100, window = 1000) {
  const past = [];
  let future = [];
  let lastKind = null;
  let lastAt = 0;
  return {
    record(before, kind, now = Date.now()) {
      const merge = kind === 'type' && lastKind === 'type' && now - lastAt < window;
      lastKind = kind;
      lastAt = now;
      future = [];
      if (merge) return;
      past.push(before);
      if (past.length > limit) past.shift();
    },
    undo(current) {
      if (!past.length) return null;
      future.push(current);
      lastKind = null;
      return past.pop();
    },
    redo(current) {
      if (!future.length) return null;
      past.push(current);
      lastKind = null;
      return future.pop();
    },
    get canUndo() {
      return past.length > 0;
    },
    get canRedo() {
      return future.length > 0;
    },
  };
}
