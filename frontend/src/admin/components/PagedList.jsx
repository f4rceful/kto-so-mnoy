import { useEffect, useState } from 'react';
import { usePaged } from '../usePaged';
import Empty from './Empty';

export default function PagedList({ section, query, filter, version, onAuthError, actions, ask, busy }) {
  const [debounced, setDebounced] = useState(query);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query), 300);
    return () => clearTimeout(timer);
  }, [query]);

  const search = debounced.trim();
  const params = { ...(search ? { q: search } : {}), ...(filter ? { banned: filter } : {}) };
  const list = usePaged(section.load, params, { version, onAuthError });
  const Card = section.Card;

  if (list.loading && !list.items.length) return <div className="empty">Загрузка…</div>;
  if (list.error && !list.items.length) {
    return (
      <Empty
        title="Не удалось загрузить"
        hint={<><br />{list.error}<br /><button type="button" className="btn ghost small" onClick={list.reload}>Повторить</button></>}
      />
    );
  }
  if (!list.items.length) {
    return search || filter ? <Empty title="Ничего не найдено" hint="Попробуйте другой запрос." /> : <Empty {...section.empty} />;
  }
  return (
    <>
      {(search || filter) && <div className="found">Найдено: {list.total}</div>}
      {list.items.map((item) => (
        <Card key={`${section.id}-${item.id}`} item={item} actions={actions} ask={ask} busy={busy} />
      ))}
      {list.items.length < list.total && (
        <div className="more">
          <button type="button" className="btn ghost" disabled={list.loadingMore} onClick={list.loadMore}>
            {list.loadingMore ? 'Загрузка…' : `Показать ещё (${list.total - list.items.length})`}
          </button>
        </div>
      )}
      {list.error && <div className="err" role="alert">{list.error}</div>}
    </>
  );
}
