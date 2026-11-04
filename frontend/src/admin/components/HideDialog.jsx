import { useState } from 'react';
import Dialog from './Dialog';
import ReasonField from './ReasonField';

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
      <ReasonField presets={PRESETS} value={reason} onChange={setReason} placeholder="Причина (её увидит автор)" />
    </Dialog>
  );
}
