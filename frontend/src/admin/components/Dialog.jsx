import { useEffect, useRef } from 'react';

export default function Dialog({ title, text, children, confirmLabel = 'Готово', danger = false, onConfirm, onCancel }) {
  const box = useRef(null);
  const confirm = useRef(null);

  useEffect(() => {
    const previous = document.activeElement;
    (box.current?.querySelector('textarea, .chip') ?? confirm.current)?.focus();
    const onKey = (e) => e.key === 'Escape' && onCancel();
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      previous?.focus?.();
    };
  }, [onCancel]);

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onCancel()}>
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title" ref={box}>
        <h2 id="dialog-title">{title}</h2>
        {text && <p>{text}</p>}
        {children}
        <div className="dialog-actions">
          <button type="button" className="btn ghost" onClick={onCancel}>Отмена</button>
          <button type="button" className={danger ? 'btn danger' : 'btn'} ref={confirm} onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}
