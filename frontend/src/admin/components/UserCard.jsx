import { fmtDate } from '../format';

export default function UserCard({ item: u, actions, ask, busy }) {
  return (
    <article className={u.banned ? 'card hid' : 'card'}>
      <div className="row">
        {u.banned && <span className="tag red">{u.ban_until ? `Заблокирован до ${fmtDate(u.ban_until)}` : 'Заблокирован'}</span>}
        <span className="tag">id {u.id}</span>
        {u.reports > 0 && <span className="tag warn">жалоб на автора: {u.reports}</span>}
      </div>
      <div className="title">{u.name || 'Без имени'}</div>
      <div className="meta">
        {u.username && <span>@{u.username}</span>}
        <span>приглашений: {u.invitations}</span>
      </div>
      {u.banned && u.ban_reason && <div className="why">Причина блокировки: {u.ban_reason}</div>}
      <div className="actions">
        <button type="button" className="btn ghost" onClick={() => ask.profile(u)}>Профиль</button>
        {u.banned ? (
          <button type="button" className="btn ok" disabled={busy} onClick={() => actions.unban(u.id)}>Разблокировать</button>
        ) : (
          <button type="button" className="btn danger" disabled={busy} onClick={() => ask.ban(u)}>Заблокировать</button>
        )}
      </div>
    </article>
  );
}
