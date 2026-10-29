const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
const MONTHS = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
export const WEEK_LABELS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const REPEAT = ['Каждый понедельник', 'Каждый вторник', 'Каждую среду', 'Каждый четверг', 'Каждую пятницу', 'Каждую субботу', 'Каждое воскресенье'];
export const NOTE_MAX = 50;

const pad = (n) => String(n).padStart(2, '0');
export const toISO = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const fromISO = (iso) => {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d);
};
export const addDays = (iso, n) => {
  const d = fromISO(iso);
  d.setDate(d.getDate() + n);
  return toISO(d);
};
const daysBetween = (a, b) => Math.round((fromISO(b) - fromISO(a)) / 86400000);
const clock = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;

export function dayStrip(now = new Date(), count = 14) {
  const today = toISO(now);
  return Array.from({ length: count }, (_, i) => {
    const iso = addDays(today, i);
    const d = fromISO(iso);
    return {
      iso,
      top: i === 0 ? 'Сегодня' : i === 1 ? 'Завтра' : WEEKDAYS[d.getDay()],
      day: d.getDate(),
      month: MONTHS[d.getMonth()],
      weekend: d.getDay() === 0 || d.getDay() === 6,
    };
  });
}

function formatDate(iso, now = new Date()) {
  const diff = daysBetween(toISO(now), iso);
  if (diff === 0) return 'Сегодня';
  if (diff === 1) return 'Завтра';
  if (diff === -1) return 'Вчера';
  const d = fromISO(iso);
  const base = `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS[d.getMonth()]}`;
  return d.getFullYear() === now.getFullYear() ? base : `${base} ${d.getFullYear()}`;
}

export function formatWhen({ when_date: date, when_time: time, when: note }, { now = new Date(), fallback = '' } = {}) {
  if (date) {
    const head = [formatDate(date, now), time].filter(Boolean).join(', ');
    return note ? `${head} · ${note}` : head;
  }
  return note || fallback;
}

export function formatEdited(iso, now = new Date()) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const diff = daysBetween(toISO(now), toISO(d));
  let day = `${d.getDate()} ${MONTHS[d.getMonth()]}`;
  if (diff === 0) day = 'сегодня';
  else if (diff === -1) day = 'вчера';
  else if (d.getFullYear() !== now.getFullYear()) day += ` ${d.getFullYear()}`;
  return `Изменено ${day} в ${clock(d)}`;
}

export function formatAgo(iso, now = new Date()) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const minutes = Math.floor((now - d) / 60000);
  if (minutes < 1) return 'только что';
  if (minutes < 60) return `${minutes} мин назад`;
  if (minutes < 60 * 24) return `${Math.floor(minutes / 60)} ч назад`;
  const time = clock(d);
  if (daysBetween(toISO(now), toISO(d)) === -1) return `вчера в ${time}`;
  const year = d.getFullYear() !== now.getFullYear() ? ` ${d.getFullYear()}` : '';
  return `${d.getDate()} ${MONTHS[d.getMonth()]}${year} в ${time}`;
}

export const isPast = ({ when_date: date }, now = new Date()) => !!date && daysBetween(toISO(now), date) < 0;

export const EMPTY_WHEN = { mode: 'date', date: '', time: '', weekday: null, note: '' };

export function whenFields(w) {
  const note = w.note.trim();
  if (w.mode === 'date' && w.date) return { when_date: w.date, when_time: w.time, when: note };
  if (w.mode === 'weekly' && w.weekday !== null) {
    return { when_date: null, when_time: '', when: REPEAT[w.weekday] + (w.time ? ` в ${w.time}` : '') + (note ? `, ${note}` : '') };
  }
  return { when_date: null, when_time: '', when: note };
}

export const whenValid = (w) => w.mode !== 'weekly' || w.weekday !== null;
export const whenEmpty = (w) => {
  const f = whenFields(w);
  return !f.when && !f.when_date;
};

const REPEAT_RE = new RegExp(`^(${REPEAT.join('|')})(?: в (\\d{2}:\\d{2}))?(?:, (.*))?$`);

export function whenStateFrom({ when_date: date, when_time: time, when: note }) {
  if (date) return { mode: 'date', date, time: time || '', weekday: null, note: note || '' };
  const repeat = REPEAT_RE.exec(note || '');
  if (repeat) return { mode: 'weekly', date: '', time: repeat[2] || '', weekday: REPEAT.indexOf(repeat[1]), note: repeat[3] || '' };
  return { ...EMPTY_WHEN, mode: note ? 'later' : 'date', note: note || '' };
}
