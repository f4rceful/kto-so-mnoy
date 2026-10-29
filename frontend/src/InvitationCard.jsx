import { Empty, FORMAT, interestName } from './components';
import { CalendarIcon } from './icons';
import { formatWhen, isPast } from './when';
import { excerpt } from './mdParse';
import { plural } from './plural';

const GROUP_COLORS = {
  Спорт: '#f59e0b',
  Игры: '#8b5cf6',
  'Музыка и творчество': '#ec4899',
  'Учёба и наука': '#3b82f6',
  'Проекты и дела': '#10b981',
  'Отдых и общение': '#06b6d4',
};
const FALLBACK_COLOR = '#6b7cff';
const AVATAR_COLORS = ['#3b82f6', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#ec4899'];

export const colorOf = (interests, id) => GROUP_COLORS[interests.find((i) => i.id === id)?.group] ?? FALLBACK_COLOR;

const avatarColor = (name) => AVATAR_COLORS[[...name].reduce((sum, ch) => sum + ch.codePointAt(0), 0) % AVATAR_COLORS.length];

export function NameAvatar({ name, size = 26 }) {
  return (
    <span className="ava" style={{ width: size, height: size, fontSize: Math.round(size * 0.46), background: avatarColor(name) }} aria-hidden="true">
      {[...name][0]?.toUpperCase()}
    </span>
  );
}

export function spotsText(left) {
  if (left <= 0) return 'Мест нет';
  return `Осталось ${left} ${plural(left, ['место', 'места', 'мест'])}`;
}

export const pendingCount = (inv) => (inv.responses ?? []).filter((r) => r.status === 'pending').length;

export const filledPercent = (inv) => Math.min(100, Math.round((inv.accepted / inv.max_participants) * 100));

export const Chip = ({ kind, children }) => <span className={`inv-chip ${kind}`}>{children}</span>;

function chips(inv) {
  const list = [];
  const pending = inv.is_mine && inv.status === 'open' ? pendingCount(inv) : 0;
  if (inv.hidden) list.push(['alert', 'Скрыто']);
  else if (inv.status === 'closed') list.push(['neutral', 'Закрыто']);
  else if (isPast(inv)) list.push(['neutral', 'Прошло']);
  if (pending) list.push(['alert', `Ждут ответа: ${pending}`]);
  if (inv.my_response === 'accepted') list.push(['good', 'Вы участвуете']);
  else if (inv.my_response === 'pending') list.push(['warn', 'Вы откликнулись']);
  else if (inv.my_response === 'declined') list.push(['neutral', 'Отклонено']);
  if (inv.is_mine && !pending) list.push(['mine', 'Моё']);
  return list.slice(0, 2);
}

export default function InvitationCard({ inv, interests, onOpen }) {
  const left = inv.max_participants - inv.accepted;
  const inactive = inv.status === 'closed' || isPast(inv) || inv.hidden;
  const when = formatWhen(inv);
  const text = inv.description ? excerpt(inv.description) : '';
  const place = inv.my_school ? '' : inv.school;
  const share = filledPercent(inv);

  return (
    <button
      type="button"
      className={inactive ? 'inv-card inactive' : 'inv-card'}
      style={{ '--c': colorOf(interests, inv.interest) }}
      onClick={() => onOpen(inv.id)}
    >
      <div className="inv-top">
        <span className="inv-cat">{interestName(interests, inv.interest)}</span>
        <span className="inv-chips">
          {chips(inv).map(([kind, label]) => (
            <Chip key={label} kind={kind}>{label}</Chip>
          ))}
        </span>
      </div>

      <span className="inv-title">{inv.title}</span>
      {text && <span className="inv-desc">{text}</span>}

      <span className="inv-meta">
        {when && (
          <span className="inv-when">
            <CalendarIcon />
            {when}
          </span>
        )}
        <span>{FORMAT[inv.fmt]}</span>
        {place && <span>{place}</span>}
      </span>

      <span className="inv-bottom">
        <span className="inv-author">
          <NameAvatar name={inv.author} />
          <span className="inv-name">{inv.author}</span>
        </span>
        <span className="inv-spots">
          <span className={left <= 0 ? 'inv-left full' : 'inv-left'}>{inactive ? `${inv.accepted} из ${inv.max_participants}` : spotsText(left)}</span>
          <span className="inv-bar" role="presentation"><i style={{ width: `${share}%` }} /></span>
        </span>
      </span>
    </button>
  );
}

const LabeledDivider = ({ children }) => (
  <div className="labeled-divider" role="separator">
    <span>{children}</span>
    <i />
  </div>
);

export function InvitationList({ items, interests, onOpen, emptyText, split = true }) {
  if (!items.length) return <Empty>{emptyText}</Empty>;
  const past = split ? items.filter((inv) => isPast(inv)) : [];
  const upcoming = split ? items.filter((inv) => !isPast(inv)) : items;
  const card = (inv) => <InvitationCard key={inv.id} inv={inv} interests={interests} onOpen={onOpen} />;
  return (
    <div className="inv-list">
      {upcoming.map(card)}
      {past.length > 0 && <LabeledDivider>Прошедшие</LabeledDivider>}
      {past.map(card)}
    </div>
  );
}
