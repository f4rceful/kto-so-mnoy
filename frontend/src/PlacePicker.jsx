import { useEffect, useState } from 'react';
import { Button, CellSimple, Input } from '@maxhub/max-ui';
import { Empty, Loading } from './components';
import { clean } from './profile';

const SEARCH_DELAY = 250;

const membersText = (members) => {
  if (members === undefined) return undefined;
  return members ? `Уже в приложении: ${members}` : 'Пока никого';
};

export default function PlacePicker({ load, value, onChange, placeholder, maxLength, emptyHint, autoFocus, allowAdd = true }) {
  const [query, setQuery] = useState('');
  const [items, setItems] = useState(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (value) return undefined;
    let cancelled = false;
    setFailed(false);
    const timer = setTimeout(
      () =>
        load(clean(query)).then(
          (list) => !cancelled && setItems(list),
          () => !cancelled && setFailed(true),
        ),
      query ? SEARCH_DELAY : 0,
    );
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, load, value, attempt]);

  if (value) {
    return (
      <CellSimple
        surface="island"
        title={value.name}
        subtitle={value.id ? membersText(value.members) : 'Добавлено вами'}
        after={
          <Button type="button" size="small" variant="secondary" onClick={() => onChange(null)}>
            Изменить
          </Button>
        }
      />
    );
  }

  const typed = clean(query);
  const canAdd = allowAdd && typed.length >= 2 && !items?.some((i) => i.name.toLowerCase() === typed.toLowerCase());

  return (
    <>
      <Input size="large" autoFocus={autoFocus} placeholder={placeholder} maxLength={maxLength} value={query} onChange={(e) => setQuery(e.target.value)} />
      {failed ? (
        <Empty>
          Не удалось загрузить список.
          <div style={{ marginTop: 12 }}>
            <Button type="button" size="small" variant="secondary" onClick={() => setAttempt((n) => n + 1)}>
              Повторить
            </Button>
          </div>
        </Empty>
      ) : items === null ? (
        <Loading />
      ) : (
        <>
          {items.length > 0 && (
            <div className="cell-stack">
              {items.map((item) => (
                <CellSimple
                  key={item.id}
                  surface="island"
                  title={item.name}
                  subtitle={membersText(item.members)}
                  onClick={() => onChange({ id: item.id, name: item.name, members: item.members })}
                />
              ))}
            </div>
          )}
          {canAdd && (
            <CellSimple surface="island" title={`Добавить «${typed}»`} subtitle="Нет в списке — впишите своё название" onClick={() => onChange({ id: null, name: typed })} />
          )}
          {!items.length && !typed && <Empty>{emptyHint}</Empty>}
        </>
      )}
    </>
  );
}
