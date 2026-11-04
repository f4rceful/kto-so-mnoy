export default function LoadError({ message, onRetry, onLogout }) {
  return (
    <section className="login">
      <h1>Не удалось загрузить</h1>
      <p>{message}</p>
      <button type="button" className="btn" onClick={onRetry}>Повторить</button>
      <button type="button" className="btn ghost wide" onClick={onLogout}>Выйти</button>
    </section>
  );
}
