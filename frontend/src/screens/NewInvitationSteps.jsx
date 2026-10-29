import { Button, CellSimple, IconButton, Typography } from '@maxhub/max-ui';
import HScroll from '../HScroll';
import { excerpt } from '../mdParse';
import { formatWhen } from '../when';
import { FORMAT, interestName } from '../components';

export const MAX_PEOPLE = 30;
const PRESETS = [2, 3, 5, 10];
const FORMATS = [
  { id: 'offline', title: 'Очно', hint: 'Встречаемся вживую' },
  { id: 'online', title: 'Онлайн', hint: 'Общаемся и играем в сети' },
];

export function CategoryStep({ groups, group, onGroup, interests, interest, onChange }) {
  return (
    <>
      <HScroll>
        {groups.map((g) => (
          <button key={g.title} type="button" className={g.title === group?.title ? 'gtab on' : 'gtab'} onClick={() => onGroup(g.title)}>
            {g.title}
          </button>
        ))}
      </HScroll>
      <div className="chips">
        {group?.items.map((i) => (
          <Button key={i.id} type="button" size="medium" variant={interest === i.id ? 'primary' : 'secondary'} onClick={() => onChange(i.id)}>
            {i.name}
          </Button>
        ))}
      </div>
      {interest && <Typography.Body variant="small" className="muted">Выбрано: {interestName(interests, interest)}</Typography.Body>}
    </>
  );
}

export function DetailsStep({ fmt, onFmt, people, onPeople, minPeople, accepted }) {
  return (
    <>
      <div className="choice-grid" role="radiogroup" aria-label="Формат">
        {FORMATS.map((f) => (
          <button key={f.id} type="button" role="radio" aria-checked={fmt === f.id} className={fmt === f.id ? 'choice on' : 'choice'} onClick={() => onFmt(f.id)}>
            <b>{f.title}</b>
            <span>{f.hint}</span>
          </button>
        ))}
      </div>
      <div className="field ni-people">
        <Typography.Body variant="medium-strong">Сколько человек нужно</Typography.Body>
        <Typography.Body variant="small" className="muted">
          Вас в это число не включаем.{accepted ? ` Уже принято ${accepted}, меньше поставить нельзя.` : ''}
        </Typography.Body>
        <div className="stepper">
          <IconButton type="button" variant="secondary" size="medium" aria-label="Меньше" disabled={people <= minPeople} onClick={() => onPeople(people - 1)}>
            <span className="stepper-sign">−</span>
          </IconButton>
          <span className="stepper-n" aria-live="polite">{people}</span>
          <IconButton type="button" variant="secondary" size="medium" aria-label="Больше" disabled={people >= MAX_PEOPLE} onClick={() => onPeople(people + 1)}>
            <span className="stepper-sign">+</span>
          </IconButton>
        </div>
        <div className="chips ni-presets">
          {PRESETS.map((n) => (
            <Button key={n} type="button" size="small" disabled={n < minPeople} variant={people === n ? 'primary' : 'secondary'} onClick={() => onPeople(n)}>
              {n}
            </Button>
          ))}
        </div>
      </div>
    </>
  );
}

export function SummaryStep({ me, interests, payload, description, accepted, onEdit }) {
  const { interest, title, fmt, max_participants: people } = payload;
  const rows = [
    ['Что', title, 'what'],
    ['Описание', description.trim() ? excerpt(description, 80) : 'Нет', 'about'],
    ['Категория', interest && interestName(interests, interest), 'category'],
    ['Когда', formatWhen(payload, { fallback: 'Договоримся в чате' }), 'when'],
    ['Формат', FORMAT[fmt], 'details'],
    ['Нужно человек', String(people), 'details'],
  ];
  return (
    <>
      <CellSimple
        surface="island"
        overline={interest ? interestName(interests, interest) : 'Категория'}
        title={title || 'Ваше приглашение'}
        subtitle={[formatWhen(payload), FORMAT[fmt], me?.display_name].filter(Boolean).join(' · ')}
        after={<Typography.Label variant="medium-strong">{accepted}/{people}</Typography.Label>}
      />
      <hr className="divider" />
      <div className="cell-stack">
        {rows.map(([label, value, target]) => (
          <CellSimple key={label} surface="island" overline={label} title={value || '—'} showChevron onClick={() => onEdit(target)} />
        ))}
      </div>
    </>
  );
}
