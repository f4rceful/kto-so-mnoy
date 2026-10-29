export default function StatsBar({ stats: s }) {
  const tiles = [
    [s.reports, 'жалоб ждут решения', s.reports ? 'attn' : ''],
    [s.hidden, 'скрыто', s.hidden ? 'warn' : ''],
    [s.banned, 'заблокировано', ''],
    [s.invitations, 'приглашений', ''],
    [s.users, 'пользователей', ''],
  ];
  return (
    <div className="stats">
      {tiles.map(([value, label, tone]) => (
        <div key={label} className={`stat ${tone}`}>
          <b>{value}</b>
          <span>{label}</span>
        </div>
      ))}
    </div>
  );
}
