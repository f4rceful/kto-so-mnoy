import { useState } from 'react';
import { CellSimple, Switch, Typography } from '@maxhub/max-ui';
import { api, openMaxUrl } from '../api';
import { useLoad, useNotify } from '../hooks';
import { BotNotice, LegalSheet, interestName } from '../components';
import { BlockedEditor, GradeEditor, InterestsEditor, NameEditor, SchoolEditor } from './SettingsEditors';

const interestsSummary = (me, interests) => {
  if (!me.interests.length) return 'Не выбраны';
  const names = me.interests.slice(0, 3).map((id) => interestName(interests, id));
  const rest = me.interests.length - names.length;
  return names.join(', ') + (rest > 0 ? ` и ещё ${rest}` : '');
};

export default function Settings({ me, interests, onSaved }) {
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);
  const [switches, setSwitches] = useState({ notify: me.notify, notify_activity: me.notify_activity });
  const show = useNotify();
  const terms = useLoad(() => api.terms(), []);

  const save = async (patch) => {
    setBusy(true);
    try {
      onSaved(await api.saveMe(patch));
      show('Сохранено');
      setEditing(null);
    } catch (e) {
      show(e);
    } finally {
      setBusy(false);
    }
  };

  const toggle = async (field, value) => {
    setSwitches((s) => ({ ...s, [field]: value }));
    try {
      onSaved(await api.saveMe({ [field]: value }));
    } catch (e) {
      setSwitches((s) => ({ ...s, [field]: !value }));
      show(e);
    }
  };

  const close = () => setEditing(null);
  const docs = terms.data?.documents ?? [];

  return (
    <>
      <div className="page">
        <Typography.Headline variant="large-strong">Настройки</Typography.Headline>

        <section className="settings-section">
          <Typography.Label variant="medium" className="muted">Профиль</Typography.Label>
          <div className="cell-stack">
            <CellSimple surface="island" overline="Имя" title={me.display_name} showChevron onClick={() => setEditing('name')} />
            <CellSimple surface="island" overline="Школа" title={me.school} subtitle={[me.city, me.region].filter((x, i, a) => x && a.indexOf(x) === i).join(', ')} showChevron onClick={() => setEditing('school')} />
            <CellSimple surface="island" overline="Класс" title={`${me.grade} класс`} showChevron onClick={() => setEditing('grade')} />
          </div>
          <Typography.Body variant="small" className="muted">
            Другие участники видят только ваше имя и школу. Регион, город и класс скрыты.
          </Typography.Body>
        </section>

        <section className="settings-section">
          <Typography.Label variant="medium" className="muted">Интересы</Typography.Label>
          <CellSimple
            surface="island"
            overline={me.interests.length ? `Выбрано: ${me.interests.length}` : undefined}
            title={interestsSummary(me, interests)}
            subtitle={me.interests.length ? undefined : 'Выберите интересы, чтобы видеть подходящие приглашения'}
            showChevron
            onClick={() => setEditing('interests')}
          />
        </section>

        <section className="settings-section">
          <Typography.Label variant="medium" className="muted">Уведомления</Typography.Label>
          {me.bot?.state === 'blocked' && (switches.notify || switches.notify_activity) && <BotNotice bot={me.bot} onOpen={openMaxUrl} />}
          <div className="cell-stack">
            <CellSimple
              surface="island"
              title="Новые приглашения"
              subtitle="Когда в вашем городе появляется приглашение по вашим интересам. Не больше 5 в сутки и не ночью"
              after={<Switch checked={switches.notify} onChange={(e) => toggle('notify', e.target.checked)} />}
            />
            <CellSimple
              surface="island"
              title="О моих приглашениях"
              subtitle="Отклики, ответы автора, изменения, когда набор собран или закрыт, и напоминания о встрече"
              after={<Switch checked={switches.notify_activity} onChange={(e) => toggle('notify_activity', e.target.checked)} />}
            />
          </div>
          <Typography.Body variant="small" className="muted">
            В чате с ботом то же можно сделать командами /notify on и /notify off. Сообщения от модерации приходят всегда.
          </Typography.Body>
        </section>

        <section className="settings-section">
          <Typography.Label variant="medium" className="muted">Безопасность</Typography.Label>
          <CellSimple
            surface="island"
            title="Скрытые авторы"
            subtitle="Их приглашений вы не видите. Пожаловаться или скрыть можно на странице приглашения"
            showChevron
            onClick={() => setEditing('blocked')}
          />
        </section>

        <section className="settings-section">
          <Typography.Label variant="medium" className="muted">О сервисе</Typography.Label>
          <div className="cell-stack">
            {docs.map((d) => (
              <CellSimple key={d.id} surface="island" title={d.title} showChevron onClick={() => setEditing({ doc: d })} />
            ))}
          </div>
        </section>
      </div>

      {editing === 'name' && <NameEditor me={me} busy={busy} onSave={save} onClose={close} />}
      {editing === 'school' && <SchoolEditor me={me} busy={busy} onSave={save} onClose={close} />}
      {editing === 'grade' && <GradeEditor me={me} busy={busy} onSave={save} onClose={close} />}
      {editing === 'interests' && <InterestsEditor me={me} interests={interests} busy={busy} onSave={save} onClose={close} />}
      {editing === 'blocked' && <BlockedEditor onClose={close} />}
      {editing?.doc && <LegalSheet doc={editing.doc} onClose={close} />}
    </>
  );
}
