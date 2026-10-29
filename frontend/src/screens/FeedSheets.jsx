import { Button, CellSimple, Radio, Segmented, Switch, Typography } from '@maxhub/max-ui';
import { CategoryAccordion, CategoryItems, Sheet, toggleId } from '../components';

export const SORTS = [
  { id: 'new', title: 'Сначала новые', short: 'Новые' },
  { id: 'old', title: 'Сначала старые', short: 'Старые' },
  { id: 'soon', title: 'Ближайшие по дате', short: 'Скоро' },
  { id: 'spots', title: 'Больше свободных мест', short: 'Больше мест' },
];
const FORMATS = [
  { id: 'any', title: 'Любой' },
  { id: 'offline', title: 'Очно' },
  { id: 'online', title: 'Онлайн' },
];
export const NO_FILTER = { interests: [], fmt: null, hasSpots: false };

export function GroupSheet({ group, selected, onChange, onClose, onApply }) {
  return (
    <Sheet open={!!group} title={group?.title ?? ''} onClose={onClose}>
      {group && (
        <div className="cat sheet-cat">
          <CategoryItems group={group} selected={selected} onToggle={(id) => onChange((d) => toggleId(d, id))} />
        </div>
      )}
      <div className="row">
        <Button
          variant="secondary"
          disabled={!group || !group.items.some((i) => selected.includes(i.id))}
          onClick={() => onChange((d) => d.filter((id) => !group.items.some((i) => i.id === id)))}
        >
          Сбросить
        </Button>
        <Button onClick={onApply}>Применить</Button>
      </div>
    </Sheet>
  );
}

export function SortSheet({ open, value, onChange, onClose, onApply }) {
  return (
    <Sheet open={open} title="Сортировка" onClose={onClose}>
      <div role="radiogroup" aria-label="Сортировка">
        {SORTS.map((s) => (
          <CellSimple
            key={s.id}
            className="round-row"
            title={s.title}
            before={<Radio name="sort" checked={value === s.id} onChange={() => onChange(s.id)} />}
            onClick={() => onChange(s.id)}
          />
        ))}
      </div>
      <Button stretched size="large" onClick={onApply}>
        Применить
      </Button>
    </Sheet>
  );
}

export function FilterSheet({ open, groups, draft, onChange, openGroup, onOpenGroup, onClose, onApply }) {
  return (
    <Sheet open={open} title="Фильтр" onClose={onClose}>
      <div className="field">
        <Typography.Label variant="medium" className="muted">Категории</Typography.Label>
        <CategoryAccordion
          groups={groups}
          selected={draft.interests}
          onToggle={(id) => onChange((d) => ({ ...d, interests: toggleId(d.interests, id) }))}
          openTitle={openGroup}
          onOpenTitle={onOpenGroup}
        />
      </div>

      <div className="field">
        <Typography.Label variant="medium" className="muted">Формат</Typography.Label>
        <Segmented
          items={FORMATS}
          activeItem={draft.fmt ?? 'any'}
          onClick={(id) => onChange({ ...draft, fmt: id === 'any' ? null : id })}
        />
      </div>

      <CellSimple
        className="round-row"
        title="Только со свободными местами"
        after={<Switch checked={draft.hasSpots} onChange={(e) => onChange({ ...draft, hasSpots: e.target.checked })} />}
      />

      <div className="row">
        <Button variant="secondary" onClick={() => onChange(NO_FILTER)}>Сбросить</Button>
        <Button onClick={onApply}>Показать</Button>
      </div>
    </Sheet>
  );
}
