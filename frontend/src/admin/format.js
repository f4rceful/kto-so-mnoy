const MONTHS = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
const pad = (n) => String(n).padStart(2, '0');

export const fmtClock = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;

export function fmtDate(iso, now = new Date()) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const year = d.getFullYear() === now.getFullYear() ? '' : ` ${d.getFullYear()}`;
  return `${d.getDate()} ${MONTHS[d.getMonth()]}${year}, ${fmtClock(d)}`;
}

export function fmtDay(iso) {
  const [, month, day] = iso.split('-').map(Number);
  return `${day} ${MONTHS[month - 1]}`;
}

const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

export function fmtDayLong(iso) {
  const [year, month, day] = iso.split('-').map(Number);
  return `${WEEKDAYS[new Date(year, month - 1, day).getDay()]}, ${day} ${MONTHS[month - 1]}`;
}
