import { useEffect, useRef } from 'react';

export default function Modal({ title, onClose, wide = false, children }) {
  const box = useRef(null);

  useEffect(() => {
    const previous = document.activeElement;
    box.current?.focus();
    const onKey = (e) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      previous?.focus?.();
    };
  }, [onClose]);

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={wide ? 'dialog wide' : 'dialog'} role="dialog" aria-modal="true" aria-labelledby="modal-title" tabIndex={-1} ref={box}>
        <div className="modal-head">
          <h2 id="modal-title">{title}</h2>
          <button type="button" className="btn ghost small" onClick={onClose}>Закрыть</button>
        </div>
        {children}
      </div>
    </div>
  );
}
