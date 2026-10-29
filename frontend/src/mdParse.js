export const INLINE = /\*\*([^\s*](?:.*?[^\s*])?)\*\*|\*([^\s*](?:[^*]*?[^\s*])?)\*/;

export function parseInline(text) {
  const out = [];
  let rest = text;
  for (;;) {
    const m = INLINE.exec(rest);
    if (!m) break;
    if (m.index) out.push({ t: 'text', v: rest.slice(0, m.index) });
    out.push(m[1] !== undefined ? { t: 'b', c: parseInline(m[1]) } : { t: 'i', c: parseInline(m[2]) });
    rest = rest.slice(m.index + m[0].length);
  }
  if (rest) out.push({ t: 'text', v: rest });
  return out;
}

const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBER = /^\s*\d+[.)]\s+(.*)$/;
const HEADING = /^#{1,3}\s+(.*)$/;

export function parseMarkdown(source) {
  const blocks = [];
  let para = null;
  let list = null;
  const flush = () => {
    para = list = null;
  };
  for (const raw of source.replace(/\r\n?/g, '\n').split('\n')) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      flush();
      continue;
    }
    const heading = HEADING.exec(line);
    const bullet = BULLET.exec(line);
    const number = !bullet && NUMBER.exec(line);
    if (heading) {
      flush();
      blocks.push({ type: 'h', text: heading[1] });
    } else if (bullet || number) {
      const type = bullet ? 'ul' : 'ol';
      if (!list || list.type !== type) {
        para = null;
        blocks.push((list = { type, items: [] }));
      }
      list.items.push((bullet ?? number)[1]);
    } else {
      list = null;
      if (!para) blocks.push((para = { type: 'p', lines: [] }));
      para.lines.push(line.trim());
    }
  }
  return blocks;
}

export function excerpt(source, max = 110) {
  const plain = source
    .replace(/\r\n?/g, '\n')
    .split('\n')
    .map((l) => l.replace(/^\s*(?:[-*•]|\d+[.)]|#{1,3})\s+/, ''))
    .join(' ')
    .replace(/\*+/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  if (plain.length <= max) return plain;
  const cut = plain.slice(0, max);
  const space = cut.lastIndexOf(' ');
  return (space > max - 25 ? cut.slice(0, space) : cut).replace(/[\s,.;:–-]+$/, '') + '…';
}
