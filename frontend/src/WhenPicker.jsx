import { useMemo, useState } from 'react';
import { Button, Input, Segmented, Typography } from '@maxhub/max-ui';
import HScroll from './HScroll';
import { NOTE_MAX, WEEK_LABELS, addDays, dayStrip, formatWhen, toISO, whenFields } from './when';

const MODES = [
  { id: 'date', title: 'Дата' },
  { id: 'weekly', title: 'Каждую неделю' },
  { id: 'later', title: 'Позже' },
];
const TIMES = ['15:00', '16:00', '17:00', '18:00'];
const NOTES = ['После уроков', 'На большой перемене', 'После школы'];
const HINTS = {
  date: 'Выберите день и, если знаете, время.',
  weekly: 'Для встреч, которые повторяются: тренировки, кружки, игры.',
  later: 'Дату назначите потом — договоритесь с откликнувшимися в чате.',
};

export default function WhenPicker({ value, onChange }) {
  const [now] = useState(() => new Date());
  const days = useMemo(() => dayStrip(now), [now]);
  const set = (patch) => onChange({ ...value, ...patch });
  const today = toISO(now);
  const showTime = (value.mode === 'date' && value.date) || (value.mode === 'weekly' && value.weekday !== null);
  const preview = formatWhen(whenFields(value), { now, fallback: 'Договоримся в чате' });

  return (
    <>
      <Segmented items={MODES} activeItem={value.mode} onClick={(mode) => set({ mode })} />
      <Typography.Body variant="small" className="muted">{HINTS[value.mode]}</Typography.Body>

      {value.mode === 'date' && (
        <div className="field">
          <Typography.Label variant="medium" className="muted">День</Typography.Label>
          <HScroll>
            {days.map((d) => (
              <button
                key={d.iso}
                type="button"
                className={['day-tile', value.date === d.iso && 'on', d.weekend && 'weekend'].filter(Boolean).join(' ')}
                aria-pressed={value.date === d.iso}
                onClick={() => set({ date: value.date === d.iso ? '' : d.iso, time: value.date === d.iso ? '' : value.time })}
              >
                <span>{d.top}</span>
                <b>{d.day}</b>
                <span>{d.month}</span>
              </button>
            ))}
          </HScroll>
          <Input
            size="large"
            type="date"
            min={today}
            max={addDays(today, 365)}
            value={value.date}
            aria-label="Другая дата"
            onChange={(e) => set({ date: e.target.value })}
          />
        </div>
      )}

      {value.mode === 'weekly' && (
        <div className="field">
          <Typography.Label variant="medium" className="muted">День недели</Typography.Label>
          <div className="week-row">
            {WEEK_LABELS.map((label, i) => (
              <button key={label} type="button" className={value.weekday === i ? 'week-btn on' : 'week-btn'} aria-pressed={value.weekday === i} onClick={() => set({ weekday: value.weekday === i ? null : i })}>
                {label}
              </button>
            ))}
          </div>
        </div>
      )}

      {showTime && (
        <div className="field">
          <Typography.Label variant="medium" className="muted">Во сколько (необязательно)</Typography.Label>
          <div className="chips">
            {TIMES.map((t) => (
              <Button key={t} type="button" size="medium" variant={value.time === t ? 'primary' : 'secondary'} onClick={() => set({ time: value.time === t ? '' : t })}>
                {t}
              </Button>
            ))}
          </div>
          <Input size="large" type="time" value={value.time} aria-label="Своё время" onChange={(e) => set({ time: e.target.value })} />
        </div>
      )}

      {(value.mode === 'later' || showTime || (value.mode === 'date' && value.date)) && (
        <div className="field">
          <Typography.Label variant="medium" className="muted">{value.mode === 'later' ? 'Пояснение (необязательно)' : 'Уточнение (необязательно)'}</Typography.Label>
          <div className="chips">
            {NOTES.map((n) => (
              <Button key={n} type="button" size="small" variant={value.note === n ? 'primary' : 'secondary'} onClick={() => set({ note: value.note === n ? '' : n })}>
                {n}
              </Button>
            ))}
          </div>
          <Input
            size="large"
            value={value.note}
            maxLength={NOTE_MAX}
            placeholder={value.mode === 'later' ? 'Например, договоримся в чате' : 'Например, у входа в школу'}
            onChange={(e) => set({ note: e.target.value })}
          />
        </div>
      )}

      <div className="when-preview">
        <span>Так увидят другие</span>
        <b>{preview}</b>
      </div>
    </>
  );
}
