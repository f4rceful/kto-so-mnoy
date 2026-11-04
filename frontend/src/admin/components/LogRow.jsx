import { fmtDate } from '../format';

const ACTIONS = {
  hide: ['Скрыто', 'dark'],
  restore: ['Возвращено в ленту', ''],
  dismiss: ['Жалобы закрыты', ''],
  ban: ['Заблокирован', 'red'],
  unban: ['Разблокирован', ''],
  edit_user: ['Изменён профиль', ''],
  edit_inv: ['Изменено приглашение', ''],
  rename_school: ['Школа переименована', ''],
};

const target = (item) => {
  if (item.target_type === 'invitation') return `«${item.target_label || 'Приглашение'}» №${item.target_id}`;
  if (item.target_type === 'school') return `Школа «${item.target_label}» (id ${item.target_id})`;
  return `${item.target_label || 'Пользователь'} (id ${item.target_id})`;
};

export default function LogRow({ item }) {
  const [label, tone] = ACTIONS[item.action] ?? [item.action, ''];
  return (
    <article className="log-row">
      <div className="row">
        <span className={tone ? `tag ${tone}` : 'tag'}>{label}</span>
        <time className="log-time" dateTime={item.at}>{fmtDate(item.at)}</time>
      </div>
      <div className="log-target">{target(item)}</div>
      {item.detail && <div className="why">{item.detail}</div>}
      {item.source && <div className="log-src">источник: {item.source}</div>}
    </article>
  );
}
