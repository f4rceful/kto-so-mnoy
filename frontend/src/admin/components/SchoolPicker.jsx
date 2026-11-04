import { useEffect, useState } from 'react';
import { AuthError, adminApi } from '../api';

const MIN_QUERY = 2;

export default function SchoolPicker({ onPick, onAuthError }) {
  const [query, setQuery] = useState('');
  const [state, setState] = useState({ items: [], error: '' });

  useEffect(() => {
    const text = query.trim();
    if (text.length < MIN_QUERY) {
      setState({ items: [], error: '' });
      return undefined;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      adminApi.schools(text).then(
        (data) => !cancelled && setState({ items: data.items, error: '' }),
        (e) => {
          if (cancelled) return;
          if (e instanceof AuthError) onAuthError(e.message);
          else setState({ items: [], error: e.message });
        },
      );
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, onAuthError]);

  const searched = query.trim().length >= MIN_QUERY;
  return (
    <div className="picker">
      <input className="input" type="search" value={query} placeholder="Найти другую школу по названию…" aria-label="Поиск школы" onChange={(e) => setQuery(e.target.value)} />
      {state.error && <div className="err" role="alert">{state.error}</div>}
      {searched && !state.error && !state.items.length && <div className="note">Ничего не найдено.</div>}
      {state.items.length > 0 && (
        <ul className="results">
          {state.items.map((s) => (
            <li key={s.id}>
              <button type="button" onClick={() => { onPick(s); setQuery(''); }}>
                <b>{s.name}</b>
                <span>{s.city}, {s.region} · учеников: {s.members}{s.custom ? ' · добавлена пользователем' : ''}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
