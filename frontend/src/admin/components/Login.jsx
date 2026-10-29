import { useState } from 'react';

export default function Login({ error, onSubmit }) {
  const [key, setKey] = useState('');
  const [hint, setHint] = useState('');
  const submit = (e) => {
    e.preventDefault();
    const value = key.trim();
    setKey('');
    if (!value) {
      setHint('Введите ключ модератора');
      return;
    }
    setHint('');
    onSubmit(value);
  };
  return (
    <section className="login">
      <h1>Модерация</h1>
      <p>Введите ключ модератора (<code>ADMIN_KEY</code> из настроек сервера).</p>
      <form onSubmit={submit}>
        <input type="password" autoFocus autoComplete="off" placeholder="Ключ" aria-label="Ключ модератора" value={key} onChange={(e) => setKey(e.target.value)} />
        <button type="submit" className="btn">Войти</button>
      </form>
      <div className="err" role="alert">{hint || error}</div>
    </section>
  );
}
