import { fmtClock } from '../format';

export default function TopBar({ updated, onRefresh, onLogout }) {
  return (
    <header className="top">
      <div className="top-in">
        <div className="brand">Модерация<small>Кто со мной?</small></div>
        <div className="grow" />
        {updated && <span className="updated">Обновлено {fmtClock(updated)}</span>}
        <button type="button" className="btn ghost small" onClick={onRefresh}>Обновить</button>
        <button type="button" className="btn ghost small" onClick={onLogout}>Выйти</button>
      </div>
    </header>
  );
}
