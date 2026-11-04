import { useCallback, useEffect, useState } from 'react';
import { unbanned } from '../actions';
import { AuthError, adminApi } from '../api';
import { fmtDate } from '../format';
import { useToast } from '../toasts';
import { BAN_TERMS } from './BanDialog';
import InvitationEditor from './InvitationEditor';
import Modal from './Modal';
import ReasonField from './ReasonField';
import SchoolPicker from './SchoolPicker';

const GRADES = [5, 6, 7, 8, 9, 10, 11];
const BAN_PRESETS = ['Нарушение правил', 'Оскорбления', 'Спам или реклама', 'Бессмысленные данные'];
const BOT = { ok: 'бот доступен', blocked: 'остановил бота', unknown: 'бота не запускал' };

function Row({ label, children }) {
  return (
    <div className="kv-row">
      <dt>{label}</dt>
      <dd>{children || '—'}</dd>
    </div>
  );
}

function banLine(profile) {
  const reason = profile.ban_reason ? `: ${profile.ban_reason}` : '';
  return profile.ban_until ? `до ${fmtDate(profile.ban_until)}${reason}` : `навсегда${reason}`;
}

export default function UserDialog({ userId, onClose, onChanged, onAuthError }) {
  const toast = useToast();
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ display_name: '', grade: '', school: null, schoolName: '' });
  const [banReason, setBanReason] = useState('');
  const [banDays, setBanDays] = useState(null);
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    try {
      const data = await adminApi.user(userId);
      setProfile(data);
      setForm({ display_name: data.display_name, grade: data.grade ?? '', school: null, schoolName: data.school });
      setError('');
    } catch (e) {
      if (e instanceof AuthError) onAuthError(e.message);
      else setError(e.message);
    }
  }, [userId, onAuthError]);

  useEffect(() => {
    load();
  }, [load]);

  const run = async (label, action) => {
    if (busy) return false;
    setBusy(true);
    try {
      const result = await action();
      toast(typeof label === 'function' ? label(result) : label);
      await load();
      onChanged();
      return true;
    } catch (e) {
      if (e instanceof AuthError) onAuthError(e.message);
      else toast(e.message, 'bad');
      return false;
    } finally {
      setBusy(false);
    }
  };

  if (!profile) {
    return (
      <Modal title="Профиль" onClose={onClose} wide>
        {error ? <div className="err" role="alert">{error}</div> : <div className="empty">Загрузка…</div>}
      </Modal>
    );
  }

  const patch = {};
  if (form.display_name.trim() !== profile.display_name) patch.display_name = form.display_name;
  if (form.grade !== '' && Number(form.grade) !== profile.grade) patch.grade = Number(form.grade);
  if (form.school && form.school.id !== profile.school_id) patch.school_id = form.school.id;
  const dirty = Object.keys(patch).length > 0;
  const set = (change) => setForm((f) => ({ ...f, ...change }));
  const renamed = profile.school_custom && form.schoolName.trim() && form.schoolName.trim() !== profile.school;

  return (
    <Modal title={profile.public_name} onClose={onClose} wide>
      <div className="row">
        <span className="tag">id {profile.id}</span>
        {profile.username && <span className="tag">@{profile.username}</span>}
        {profile.banned && <span className="tag red">Заблокирован {banLine(profile)}</span>}
        {profile.reports > 0 && <span className="tag warn">жалоб на автора: {profile.reports}</span>}
      </div>

      <h3 className="part">Данные профиля</h3>
      <dl className="kv">
        <Row label="Имя в MAX">{profile.name}</Row>
        <Row label="Публичное имя">{profile.display_name}</Row>
        <Row label="Класс">{profile.grade}</Row>
        <Row label="Школа">{profile.school}{profile.school_custom ? ' (добавлена пользователем)' : ''}</Row>
        <Row label="Город">{profile.city}</Row>
        <Row label="Регион">{profile.region}</Row>
        <Row label="Интересы">{profile.interests.join(', ')}</Row>
        <Row label="Уведомления">{profile.notify || profile.notify_activity ? 'включены' : 'выключены'} · {BOT[profile.bot_state] ?? profile.bot_state}</Row>
        <Row label="Условия">{profile.terms_version ? `версия ${profile.terms_version}, принято ${fmtDate(profile.consented_at)}` : 'не приняты'}</Row>
        <Row label="Активность">приглашений: {profile.invitations.length}, откликов: {profile.responses}</Row>
      </dl>

      <h3 className="part">Исправить данные</h3>
      <p className="note">«Имя в MAX» берётся из аккаунта и обновляется само. Другие участники видят только публичное имя и школу.</p>
      <div className="editor">
        <label className="field">
          <span>Публичное имя</span>
          <div className="inline">
            <input className="input" value={form.display_name} maxLength={30} onChange={(e) => set({ display_name: e.target.value })} />
            <button type="button" className="btn ghost small" onClick={() => set({ display_name: '' })}>Сбросить</button>
          </div>
        </label>
        <label className="field">
          <span>Класс</span>
          <select className="input" value={form.grade} onChange={(e) => set({ grade: e.target.value })}>
            <option value="">—</option>
            {GRADES.map((g) => <option key={g} value={g}>{g} класс</option>)}
          </select>
        </label>
        <div className="field">
          <span>Школа</span>
          <div className="current">{form.school ? <>Будет выбрана: <b>{form.school.name}</b> ({form.school.city})</> : <>Сейчас: <b>{profile.school || '—'}</b></>}</div>
          <SchoolPicker onPick={(school) => set({ school })} onAuthError={onAuthError} />
          {form.school && <button type="button" className="link" onClick={() => set({ school: null })}>Отменить выбор школы</button>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn" disabled={busy || !dirty} onClick={() => run('Данные сохранены', () => adminApi.editUser(profile.id, patch))}>Сохранить</button>
        </div>
      </div>

      {profile.school_custom && (
        <div className="editor">
          <label className="field">
            <span>Название школы (видят все её ученики)</span>
            <div className="inline">
              <input className="input" value={form.schoolName} maxLength={120} onChange={(e) => set({ schoolName: e.target.value })} />
              <button type="button" className="btn ghost small" disabled={busy || !renamed} onClick={() => run('Школа переименована', () => adminApi.renameSchool(profile.school_id, form.schoolName))}>Переименовать</button>
            </div>
          </label>
        </div>
      )}

      <h3 className="part">Блокировка</h3>
      {profile.banned ? (
        <div className="editor">
          <p className="note">Заблокирован {banLine(profile)}</p>
          <div className="dialog-actions">
            <button type="button" className="btn ok" disabled={busy} onClick={() => run(unbanned, () => adminApi.unban(profile.id))}>Разблокировать</button>
          </div>
        </div>
      ) : (
        <div className="editor">
          <div className="chips" role="group" aria-label="Срок блокировки">
            {BAN_TERMS.map(([days, label]) => (
              <button key={label} type="button" className="chip" aria-pressed={banDays === days} onClick={() => setBanDays(days)}>{label}</button>
            ))}
          </div>
          <ReasonField presets={BAN_PRESETS} value={banReason} onChange={setBanReason} placeholder="Причина (её увидит пользователь)" />
          <div className="dialog-actions">
            <button type="button" className="btn danger" disabled={busy} onClick={() => run('Пользователь заблокирован', () => adminApi.ban(profile.id, banReason.trim(), banDays))}>
              {banDays ? 'Заблокировать на срок' : 'Заблокировать навсегда'}
            </button>
          </div>
        </div>
      )}

      <h3 className="part">Приглашения ({profile.invitations.length})</h3>
      {!profile.invitations.length && <p className="note">Приглашений нет.</p>}
      {profile.invitations.map((inv) => (
        <div className="inv-row" key={inv.id}>
          <div className="row">
            <span className="tag">№{inv.id}</span>
            {inv.hidden && <span className="tag dark">Скрыто</span>}
            {inv.status === 'closed' && <span className="tag">Набор закрыт</span>}
            <time className="log-time" dateTime={inv.created_at}>{fmtDate(inv.created_at)}</time>
          </div>
          <div className="title">{inv.title}</div>
          {editing === inv.id ? (
            <InvitationEditor
              item={inv}
              busy={busy}
              onCancel={() => setEditing(null)}
              onSave={async (change) => { if (await run('Приглашение исправлено', () => adminApi.editInvitation(inv.id, change))) setEditing(null); }}
            />
          ) : (
            <button type="button" className="btn ghost small" onClick={() => setEditing(inv.id)}>Изменить</button>
          )}
        </div>
      ))}
    </Modal>
  );
}
