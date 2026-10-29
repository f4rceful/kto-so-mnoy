import { useState } from 'react';
import Dialog from './Dialog';

const PRESETS = ['Нарушение правил', 'Спам или реклама', 'Оскорбления', 'Личные данные', 'Опасное содержание'];

export default function HideDialog({ item, onConfirm, onCancel }) {
  const [reason, setReason] = useState('');
  return (
    <Dialog
      title="Скрыть приглашение?"
      text={`«${item.title}» пропадёт из ленты, автор получит сообщение с причиной.`}
      confirmLabel="Скрыть"
      danger
      onConfirm={() => onConfirm(reason.trim())}
      onCancel={onCancel}
    >
      <div className="chips">
        {PRESETS.map((p) => (
          <button key={p} type="button" className="chip" aria-pressed={reason === p} onClick={() => setReason(p)}>{p}</button>
        ))}
      </div>
      <textarea value={reason} maxLength={200} placeholder="Причина (её увидит автор)" aria-label="Причина" onChange={(e) => setReason(e.target.value)} />
    </Dialog>
  );
}
