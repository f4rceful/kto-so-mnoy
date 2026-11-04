import { useState } from 'react';
import Dialog from './Dialog';
import ReasonField from './ReasonField';

const PRESETS = ['Нарушение правил', 'Оскорбления', 'Спам или реклама', 'Опасное содержание'];
export const BAN_TERMS = [
  [1, '1 день'],
  [7, '7 дней'],
  [30, '30 дней'],
  [null, 'Навсегда'],
];

export default function BanDialog({ author, onConfirm, onCancel }) {
  const [reason, setReason] = useState('');
  const [days, setDays] = useState(null);
  return (
    <Dialog
      title="Заблокировать пользователя?"
      text={`${author.name || 'Пользователь'} (id ${author.id}) потеряет доступ к сервису, его приглашения будут скрыты, а он получит сообщение с причиной. После окончания срока или при разблокировке эти приглашения вернутся в ленту.`}
      confirmLabel="Заблокировать"
      danger
      onConfirm={() => onConfirm(reason.trim(), days)}
      onCancel={onCancel}
    >
      <div className="chips" role="group" aria-label="Срок блокировки">
        {BAN_TERMS.map(([value, label]) => (
          <button key={label} type="button" className="chip" aria-pressed={days === value} onClick={() => setDays(value)}>{label}</button>
        ))}
      </div>
      <ReasonField presets={PRESETS} value={reason} onChange={setReason} placeholder="Причина (её увидит пользователь)" />
    </Dialog>
  );
}
