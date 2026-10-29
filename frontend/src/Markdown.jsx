import { Fragment } from 'react';
import { parseInline, parseMarkdown } from './mdParse';

const inline = (nodes) =>
  nodes.map((n, i) => {
    if (n.t === 'text') return <Fragment key={i}>{n.v}</Fragment>;
    return n.t === 'b' ? <strong key={i}>{inline(n.c)}</strong> : <em key={i}>{inline(n.c)}</em>;
  });

export default function Markdown({ text }) {
  const blocks = parseMarkdown(text);
  if (!blocks.length) return null;
  return (
    <div className="md">
      {blocks.map((b, i) => {
        if (b.type === 'h') return <div className="md-h" key={i}>{inline(parseInline(b.text))}</div>;
        if (b.type === 'p') {
          return (
            <p key={i}>
              {b.lines.map((line, j) => (
                <Fragment key={j}>
                  {j > 0 && <br />}
                  {inline(parseInline(line))}
                </Fragment>
              ))}
            </p>
          );
        }
        const List = b.type;
        return (
          <List key={i}>
            {b.items.map((item, j) => (
              <li key={j}>{inline(parseInline(item))}</li>
            ))}
          </List>
        );
      })}
    </div>
  );
}
