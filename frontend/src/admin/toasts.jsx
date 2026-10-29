import { createContext, useCallback, useContext, useState } from 'react';

const ToastContext = createContext(() => {});
const SHOW_MS = 3200;
let nextId = 1;

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const toast = useCallback((text, kind = 'ok') => {
    const id = nextId++;
    setItems((list) => [...list, { id, text, kind }]);
    setTimeout(() => setItems((list) => list.filter((t) => t.id !== id)), SHOW_MS);
  }, []);
  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={t.kind === 'bad' ? 'toast bad' : 'toast'}>{t.text}</div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
