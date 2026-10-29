import { useState } from 'react';
import { fmtDate } from '../format';

const LONG_TEXT = 160;
const isLong = (text) => text.length > LONG_TEXT || text.split('\n').length > 3;

function groupReasons(reports) {
  const count = new Map();
  for (const r of reports) count.set(r.reason, (count.get(r.reason) || 0) + 1);
  return [...count];
}

function Description({ text }) {
  const [expanded, setExpanded] = useState(false);
  const long = isLong(text);
  return (
    <>
      <p className={long && !expanded ? 'desc clamp' : 'desc'}>{text}</p>
      {long && (
        <button type="button" className="link" onClick={() => setExpanded(!expanded)}>
          {expanded ? 'Свернуть' : 'Показать полностью'}
        </button>
      )}
    </>
  );
}

function ReportList({ reports }) {
  return (
    <details>
      <summary>Что написали в жалобах ({reports.length})</summary>
      {reports.map((r, n) => (
        <div className="rep" key={n}>
          <b>{r.reason}</b>
          <time>{fmtDate(r.at)}</time>
          {r.text && <div>{r.text}</div>}
        </div>
      ))}
    </details>
  );
}

export default function InvitationCard({ item: inv, actions, ask }) {
  const author = inv.author;
  const reported = inv.reports.length > 0;
  const classes = ['card', reported && !inv.hidden && 'reported', inv.hidden && 'hid'].filter(Boolean).join(' ');

  return (
    <article className={classes}>
      <div className="row">
        <span className="tag">№{inv.id}</span>
        {inv.hidden && <span className="tag dark">Скрыто</span>}
        {inv.status === 'closed' && <span className="tag">Набор закрыт</span>}
        {reported && <span className="tag red">Жалоб: {inv.reports.length}</span>}
        {groupReasons(inv.reports).map(([reason, n]) => (
          <span key={reason} className="tag warn">{n > 1 ? `${reason} ×${n}` : reason}</span>
        ))}
      </div>

      <div className="title">{inv.title}</div>
      {inv.description && <Description text={inv.description} />}

      <div className="meta">
        <span>
          Автор: <b>{author.name || '—'}</b>
          {author.username ? ` @${author.username}` : ''} · id {author.id}
        </span>
        {author.banned && <span className="tag red">автор заблокирован</span>}
        <span>его приглашений: {author.invitations}</span>
        {inv.school && <span>Школа: {inv.school}</span>}
        <span>Создано: {fmtDate(inv.created_at)}</span>
        <span>Откликов: {inv.responses}</span>
      </div>

      {inv.hidden && inv.hidden_reason && <div className="why">Причина скрытия: {inv.hidden_reason}</div>}

      {reported && <ReportList reports={inv.reports} />}

      <div className="actions">
        {inv.hidden ? (
          <button type="button" className="btn ok" onClick={() => actions.restore(inv)}>Вернуть в ленту</button>
        ) : (
          <button type="button" className="btn danger" onClick={() => ask.hide(inv)}>Скрыть</button>
        )}
        {reported && (
          <button type="button" className="btn ghost" onClick={() => actions.dismiss(inv)}>Жалобы необоснованны</button>
        )}
        {author.banned ? (
          <button type="button" className="btn ghost" onClick={() => actions.unban(author.id)}>Разблокировать автора</button>
        ) : (
          <button type="button" className="btn ghost" onClick={() => ask.ban(author)}>Заблокировать автора</button>
        )}
      </div>
    </article>
  );
}
