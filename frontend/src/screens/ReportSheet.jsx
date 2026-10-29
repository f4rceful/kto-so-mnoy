import { useState } from 'react';
import { Button, CellSimple, Input, Radio, Typography } from '@maxhub/max-ui';
import { api } from '../api';
import { useLoad } from '../hooks';
import { Loading, Sheet } from '../components';

const REPORT_TEXT_MAX = 300;

export default function ReportSheet({ onClose, onSend, busy }) {
  const reasons = useLoad(() => api.reportReasons(), []);
  const [reason, setReason] = useState(null);
  const [text, setText] = useState('');
  return (
    <Sheet title="Пожаловаться" onClose={onClose}>
      <Typography.Body variant="small" className="muted">
        Выберите, что не так. Автор не узнает, кто пожаловался. Если жалоб будет несколько, приглашение скроется до проверки.
      </Typography.Body>
      {reasons.loading && !reasons.data ? (
        <Loading />
      ) : (
        <div role="radiogroup" aria-label="Причина жалобы">
          {(reasons.data ?? []).map((r) => (
            <CellSimple
              key={r.id}
              className="round-row"
              title={r.name}
              before={<Radio name="reason" checked={reason === r.id} onChange={() => setReason(r.id)} />}
              onClick={() => setReason(r.id)}
            />
          ))}
        </div>
      )}
      <Input value={text} maxLength={REPORT_TEXT_MAX} placeholder="Пояснение (необязательно)" onChange={(e) => setText(e.target.value)} />
      <div className="row">
        <Button variant="secondary" onClick={onClose}>Отмена</Button>
        <Button disabled={!reason || busy} loading={busy} onClick={() => onSend({ reason, text: text.trim() })}>Отправить</Button>
      </div>
    </Sheet>
  );
}
