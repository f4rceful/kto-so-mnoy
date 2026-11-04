export const SERIES = [
  { key: 'invitations', label: 'Новые приглашения', color: 'var(--series-1)' },
  { key: 'responses', label: 'Отклики', color: 'var(--series-2)' },
  { key: 'accepted', label: 'Принятые отклики', color: 'var(--series-3)' },
];

export const sumOf = (days, key) => days.reduce((total, d) => total + d[key], 0);

const niceStep = (raw) => {
  const power = 10 ** Math.floor(Math.log10(raw));
  const f = raw / power;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * power;
};

export function yScale(max) {
  if (max <= 0) return { top: 1, ticks: [0, 1] };
  const step = Math.max(1, niceStep(max / 2));
  const top = step * Math.ceil(max / step);
  const ticks = [];
  for (let v = 0; v <= top; v += step) ticks.push(v);
  return { top, ticks };
}
