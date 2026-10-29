import { useState } from 'react';
import { BottomSheet, Button, IconButton, Typography } from '@maxhub/max-ui';
import { api, openContact } from './api';
import { AcceptIcon, DeclineIcon } from './icons';
import { Chip, NameAvatar, pendingCount } from './InvitationCard';
import { formatAgo } from './when';

const STATUS = {
  pending: ['warn', 'Ждёт ответа'],
  accepted: ['good', 'Принят'],
  declined: ['neutral', 'Отклонён'],
};
const RANK = { pending: 0, accepted: 1, declined: 2 };

const StatusChip = ({ status }) => <Chip kind={STATUS[status][0]}>{STATUS[status][1]}</Chip>;

const sortResponses = (list) =>
  [...list].sort((a, b) => RANK[a.status] - RANK[b.status] || new Date(a.created_at) - new Date(b.created_at));

const classText = (r) => (r.grade ? `${r.grade} класс` : '');
const subline = (r) => [classText(r), r.school, formatAgo(r.created_at)].filter(Boolean).join(' · ');

export default function Responses({ inv, isOpen, full, busy, act }) {
  const [openId, setOpenId] = useState(null);
  const [showDeclined, setShowDeclined] = useState(false);

  const list = sortResponses(inv.responses ?? []);
  const live = list.filter((r) => r.status !== 'declined');
  const declined = list.filter((r) => r.status === 'declined');
  const waiting = pendingCount(inv);
  const picked = list.find((r) => r.id === openId);

  const accept = (r) => {
    setOpenId(null);
    act(() => api.accept(r.id), 'Отклик принят');
  };
  const decline = (r) => {
    setOpenId(null);
    act(() => api.decline(r.id));
  };

  const row = (r) => (
    <div className="d-resp" key={r.id}>
      <button type="button" className="d-resp-main" onClick={() => setOpenId(r.id)} aria-label={`Профиль: ${r.user}`}>
        <NameAvatar name={r.user} size={40} />
        <span className="d-resp-text">
          <b>{r.user}</b>
          <span className="d-resp-sub">{subline(r)}</span>
        </span>
      </button>
      {r.status === 'pending' && isOpen ? (
        <span className="d-resp-actions">
          <IconButton type="button" size="small" variant="primary" aria-label="Принять" disabled={busy || full} onClick={() => accept(r)}>
            <AcceptIcon />
          </IconButton>
          <IconButton type="button" size="small" variant="secondary" aria-label="Отклонить" disabled={busy} onClick={() => decline(r)}>
            <DeclineIcon />
          </IconButton>
        </span>
      ) : (
        <StatusChip status={r.status} />
      )}
    </div>
  );

  return (
    <div className="field">
      <div className="between">
        <Typography.Label variant="medium" className="muted">Отклики · {list.length}</Typography.Label>
        {waiting > 0 && <Chip kind="alert">Ждут ответа: {waiting}</Chip>}
      </div>

      {list.length ? (
        <div className="resp-list">
          {live.map(row)}
          {declined.length > 0 && (
            <>
              <button type="button" className="d-link resp-toggle" onClick={() => setShowDeclined((v) => !v)}>
                {showDeclined ? 'Скрыть отклонённых' : `Отклонённые · ${declined.length}`}
              </button>
              {showDeclined && declined.map(row)}
            </>
          )}
        </div>
      ) : (
        <div className="d-empty">
          <Typography.Body variant="medium" className="muted">Пока никто не откликнулся. Поделитесь приглашением с друзьями — кнопка внизу.</Typography.Body>
        </div>
      )}

      <BottomSheet open={!!picked} title="Профиль" onClose={() => setOpenId(null)} innerClassNames={{ sheet: 'sheet-narrow' }}>
        {picked && (
          <div className="sheet-body">
            <div className="resp-head">
              <NameAvatar name={picked.user} size={56} />
              <span className="resp-head-text">
                <b>{picked.user}</b>
                <span className="d-hint">{[classText(picked), picked.school].filter(Boolean).join(' · ') || 'Класс и школа не указаны'}</span>
              </span>
              <span className="resp-head-status">
                <StatusChip status={picked.status} />
              </span>
            </div>
            {picked.same_school && (
              <div className="resp-badges">
                <Chip kind="good">Из вашей школы</Chip>
              </div>
            )}
            {picked.created_at && <span className="d-hint">Откликнулся(ась) {formatAgo(picked.created_at)}</span>}

            {picked.stats && (
              <div className="stat-row">
                <div className="stat"><b>{picked.stats.created}</b><span>предложил</span></div>
                <div className="stat"><b>{picked.stats.joined}</b><span>участвует</span></div>
                <div className="stat"><b>{picked.stats.gathered}</b><span>собрал</span></div>
              </div>
            )}

            {picked.status === 'pending' && isOpen && (
              <div className="row">
                <Button disabled={busy || full} onClick={() => accept(picked)}>{full ? 'Мест нет' : 'Принять'}</Button>
                <Button variant="secondary" disabled={busy} onClick={() => decline(picked)}>Отклонить</Button>
              </div>
            )}
            {picked.status === 'accepted' && (
              <Button stretched variant="secondary" disabled={!picked.contact} onClick={() => openContact(picked.contact)}>
                {picked.contact ? 'Написать в MAX' : 'Нет username в MAX'}
              </Button>
            )}
          </div>
        )}
      </BottomSheet>
    </div>
  );
}
