import { Component } from 'react';

export default class ErrorBoundary extends Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error) {
    console.error(error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <section className="login">
        <h1>Что-то пошло не так</h1>
        <p>Страница сломалась. Перезагрузите её. Если ошибка повторится, сообщите разработчику.</p>
        <button type="button" className="btn" onClick={() => window.location.reload()}>Перезагрузить</button>
      </section>
    );
  }
}
