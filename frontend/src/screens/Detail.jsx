import { useEffect, useRef, useState } from 'react';
import { Button, IconButton, Typography } from '@maxhub/max-ui';
import { api, openContact } from '../api';
import { useLoad, useNotify, useShare } from '../hooks';
import Markdown from '../Markdown';
import Responses from '../Responses';
import ReportSheet from './ReportSheet';
import { Chip, NameAvatar, colorOf, filledPercent, spotsText } from '../InvitationCard';
import { CalendarIcon, EyeOffIcon, FlagIcon, GlobeIcon, PencilIcon, PinIcon, SchoolIcon, ShareIcon, UsersIcon } from '../icons';
import { formatEdited, formatWhen, isPast } from '../when';
import { ConfirmSheet, ErrorState, FORMAT, Loading, interestName } from '../components';

const Fact = ({ icon, label, wide, children }) => (
  <div className={wide ? 'd-fact wide' : 'd-fact'}>
    <span className="d-fact-label">{icon}{label}</span>
    {children}
  </div>
);

function StatusNotes({ inv, isOpen, past }) {
  return (
    <>
      {inv.is_mine && inv.hidden && (
        <div className="d-state warn">
          <Typography.Body variant="medium-strong">Приглашение скрыто модерацией</Typography.Body>
          <Typography.Body variant="small">
            Другие его не видят{inv.hidden_reason ? `: ${inv.hidden_reason.toLowerCase()}` : ''}. Если это ошибка, мы разберёмся. Вы можете исправить приглашение.
          </Typography.Body>
        </div>
      )}
      {!inv.is_mine && inv.my_response === 'accepted' && (
        <div className="d-state good">
          <Typography.Body variant="medium-strong">Вас приняли!</Typography.Body>
          <Typography.Body variant="small">Договоритесь о деталях с автором ({inv.author}) в MAX.</Typography.Body>
          {inv.author_contact ? (
            <Button stretched variant="primary" onClick={() => openContact(inv.author_contact)}>Написать автору</Button>
          ) : (
            <Typography.Body variant="small" className="muted">
              Автор не указал username в MAX, поэтому мы не можем показать ссылку на его профиль. Найдите его в школьном чате или подождите сообщения от автора.
            </Typography.Body>
          )}
        </div>
      )}
      {!inv.is_mine && inv.my_response === 'pending' && (
        <div className="d-state warn">
          <Typography.Body variant="medium-strong">Отклик отправлен</Typography.Body>
          <Typography.Body variant="small">Автор получил уведомление и скоро ответит. Мы напишем вам в чат.</Typography.Body>
        </div>
      )}
      {!inv.is_mine && inv.my_response === 'declined' && (
        <div className="d-state">
          <Typography.Body variant="medium-strong">В этот раз не получилось</Typography.Body>
          <Typography.Body variant="small" className="muted">Автор не смог вас принять. В ленте много других приглашений.</Typography.Body>
        </div>
      )}
      {inv.is_mine && isOpen && past && (
        <div className="d-state">
          <Typography.Body variant="small">Дата уже прошла. Если набор вам больше не нужен, закройте его.</Typography.Body>
        </div>
      )}
    </>
  );
}

const RESPONSE_LABEL = { pending: 'Отклик отправлен', accepted: 'Вы участвуете', declined: 'Отклик отклонён' };

function MainAction({ inv, isOpen, full, busy, onClose, onRespond }) {
  if (inv.is_mine) {
    return isOpen ? (
      <Button stretched size="large" variant="destructive" disabled={busy} onClick={onClose}>
        Закрыть набор
      </Button>
    ) : (
      <Button stretched size="large" variant="secondary" disabled>Набор закрыт</Button>
    );
  }
  if (inv.my_response) {
    return (
      <Button stretched size="large" variant="secondary" disabled>
        {RESPONSE_LABEL[inv.my_response]}
      </Button>
    );
  }
  return (
    <Button stretched size="large" loading={busy} disabled={!isOpen || full} onClick={onRespond}>
      {!isOpen ? 'Набор закрыт' : full ? 'Мест нет' : 'Откликнуться'}
    </Button>
  );
}

export default function Detail({ id, interests, onChanged, onEdit, onBack }) {
  const { data, loading, error, reload } = useLoad(() => api.detail(id), [id]);
  const [busy, setBusy] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [sheet, setSheet] = useState(null);
  const notify = useNotify();
  const share = useShare();
  const last = useRef(null);
  if (data) last.current = data;
  const inv = data ?? last.current;
  useEffect(() => {
    if (error && last.current) notify(error);
  }, [error, notify]);

  if (loading && !inv) return <Loading />;
  if (error && !inv) return <div className="page"><ErrorState error={error} onRetry={reload} /></div>;

  const act = async (action, doneText) => {
    setBusy(true);
    try {
      await action();
      if (doneText) notify(doneText);
      reload();
      onChanged();
      return true;
    } catch (e) {
      notify(e);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const shareInvite = () => share(`Присоединяйся: «${inv.title}» — в «Кто со мной?»`, inv.link);

  const sendReport = (body) =>
    act(() => api.report(inv.id, body), 'Спасибо, жалоба отправлена').then((ok) => ok && setSheet(null));
  const blockAuthor = () =>
    act(async () => {
      await api.blockAuthor(inv.id);
      onBack?.();
    }, 'Автор скрыт: его приглашений вы больше не увидите');

  const isOpen = inv.status === 'open';
  const past = isPast(inv);
  const left = inv.max_participants - inv.accepted;
  const full = left <= 0;
  const when = formatWhen(inv, { fallback: 'Договоримся в чате' });

  return (
    <>
      <div className="page detail" style={{ '--c': colorOf(interests, inv.interest) }}>
        <div className="d-hero">
          <div className="inv-top">
            <span className="inv-cat">{interestName(interests, inv.interest)}</span>
            <span className="inv-chips">
              {!isOpen ? <Chip kind="neutral">Набор закрыт</Chip> : past ? <Chip kind="neutral">Прошло</Chip> : full ? <Chip kind="neutral">Мест нет</Chip> : <Chip kind="good">Идёт набор</Chip>}
              {inv.hidden && <Chip kind="alert">Скрыто</Chip>}
              {inv.is_mine && <Chip kind="mine">Ваше</Chip>}
            </span>
          </div>
          <h1 className="d-title">{inv.title}</h1>
          {inv.description && (
            <div className="d-desc">
              <Markdown text={inv.description} />
            </div>
          )}
          {inv.edited_at && (
            <span className="d-edited" title="Автор менял это приглашение">
              <PencilIcon />
              {formatEdited(inv.edited_at)}
            </span>
          )}
          {inv.is_mine && isOpen && onEdit && (
            <Button size="small" variant="secondary" onClick={onEdit}>
              Редактировать
            </Button>
          )}
        </div>

        <StatusNotes inv={inv} isOpen={isOpen} past={past} />

        <div className="d-facts">
          <Fact wide icon={<CalendarIcon />} label="Когда">
            <b>{when}</b>
          </Fact>
          <Fact icon={inv.fmt === 'online' ? <GlobeIcon /> : <PinIcon />} label="Формат">
            <b>{FORMAT[inv.fmt]}</b>
          </Fact>
          <Fact icon={<SchoolIcon />} label="Школа">
            <b>{inv.school || '—'}</b>
          </Fact>
          <Fact wide icon={<UsersIcon />} label="Участники">
            <b>{inv.accepted} из {inv.max_participants}</b>
            <span className="inv-bar" role="presentation"><i style={{ width: `${filledPercent(inv)}%` }} /></span>
            <span className="d-hint">{isOpen && !past ? spotsText(left) : 'Набор завершён'}</span>
          </Fact>
        </div>

        {!inv.is_mine && (
          <div className="d-author">
            <NameAvatar name={inv.author} size={44} />
            <span>
              <b>{inv.author}</b>
              <span className="d-hint">Автор{inv.my_school ? ' · из вашей школы' : inv.school ? ` · ${inv.school}` : ''}</span>
            </span>
          </div>
        )}

        {inv.is_mine && <Responses inv={inv} isOpen={isOpen} full={full} busy={busy} act={act} />}

        {!inv.is_mine && (
          <div className="d-safety">
            <button type="button" className="safe-btn" disabled={inv.reported} onClick={() => setSheet('report')}>
              <span className="safe-ico red"><FlagIcon /></span>
              {inv.reported ? 'Жалоба отправлена' : 'Пожаловаться'}
            </button>
            <button type="button" className="safe-btn" onClick={() => setSheet('block')}>
              <span className="safe-ico orange"><EyeOffIcon /></span>
              Скрыть автора
            </button>
          </div>
        )}
      </div>

      <div className="bottom-bar bar-row">
        {inv.link && (
          <IconButton type="button" variant="secondary" size="large" aria-label="Поделиться приглашением" onClick={shareInvite}>
            <ShareIcon />
          </IconButton>
        )}
        <MainAction inv={inv} isOpen={isOpen} full={full} busy={busy} onClose={() => setConfirmClose(true)} onRespond={() => act(() => api.respond(inv.id), 'Отклик отправлен')} />
      </div>

      {sheet === 'report' && <ReportSheet busy={busy} onClose={() => setSheet(null)} onSend={sendReport} />}
      <ConfirmSheet
        open={sheet === 'block'}
        title="Скрыть автора?"
        text={`Вы больше не увидите приглашения ${inv.author}, а он не сможет откликаться на ваши. Передумаете — вернуть автора можно в настройках.`}
        action="Скрыть автора"
        busy={busy}
        onClose={() => setSheet(null)}
        onConfirm={blockAuthor}
      />
      <ConfirmSheet
        open={confirmClose}
        title="Закрыть набор?"
        text="Новые отклики приниматься не будут, а те, кого вы уже приняли, останутся в списке участников. Открыть набор снова нельзя."
        action="Закрыть набор"
        busy={busy}
        onClose={() => setConfirmClose(false)}
        onConfirm={() => act(() => api.close(inv.id), 'Набор закрыт')}
      />
    </>
  );
}
