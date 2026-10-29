export default function UserCard({ item: u, actions }) {
  return (
    <article className="card hid">
      <div className="row">
        <span className="tag red">Заблокирован</span>
        <span className="tag">id {u.id}</span>
      </div>
      <div className="title">{u.name || 'Без имени'}</div>
      <div className="meta">
        {u.username && <span>@{u.username}</span>}
        <span>приглашений: {u.invitations}</span>
      </div>
      <div className="actions">
        <button type="button" className="btn ok" onClick={() => actions.unban(u.id)}>Разблокировать</button>
      </div>
    </article>
  );
}
