import { useEffect, useMemo, useState } from 'react';
import { Button, Input, Steps, Typography } from '@maxhub/max-ui';
import { api } from '../api';
import { useNotify } from '../hooks';
import DescriptionEditor from '../DescriptionEditor';
import WhenPicker from '../WhenPicker';
import { EMPTY_WHEN, whenEmpty, whenFields, whenStateFrom, whenValid } from '../when';
import { groupInterests } from '../components';
import { CategoryStep, DetailsStep, MAX_PEOPLE, SummaryStep } from './NewInvitationSteps';

const TITLE_MAX = 120;
const DESCRIPTION_MAX = 1000;

const STEPS = [
  { id: 'what', title: 'Что хотите делать?', hint: 'Опишите коротко, чтобы сразу было понятно, чем займётесь.' },
  { id: 'about', title: 'Расскажите подробнее', hint: 'Необязательно: что будете делать, что взять с собой, для кого это.' },
  { id: 'category', title: 'К какой категории это относится?', hint: 'По ней приглашение найдут те, кому это интересно.' },
  { id: 'when', title: 'Когда?', hint: 'Можно пропустить — тогда договоритесь в чате.' },
  { id: 'details', title: 'Как и с кем?', hint: 'Выберите формат и сколько человек вам нужно.' },
  { id: 'confirm', title: 'Всё верно?', hint: 'Нажмите на строку, чтобы изменить. Его увидят в ленте вашей школы и города.' },
];
const ids = STEPS.map((s) => s.id);

const buildPayload = ({ interest, title, description, whenState, fmt, people }) => ({
  interest,
  title: title.trim(),
  description: description.trim(),
  ...whenFields(whenState),
  fmt,
  max_participants: people,
});

export default function NewInvitation({ me, interests, defaultInterest, onCreated, onSaved, editing, backRef }) {
  const groups = useMemo(() => groupInterests(interests), [interests]);
  const start = editing?.interest ?? defaultInterest ?? interests[0]?.id;
  const root = editing ? 'confirm' : 'what';
  const minPeople = Math.max(1, editing?.accepted ?? 0);
  const [step, setStep] = useState(root);
  const [fromSummary, setFromSummary] = useState(false);
  const [interest, setInterest] = useState(start);
  const [groupTitle, setGroupTitle] = useState(() => interests.find((i) => i.id === start)?.group ?? groups[0]?.title);
  const [title, setTitle] = useState(editing?.title ?? '');
  const [description, setDescription] = useState(editing?.description ?? '');
  const [whenState, setWhenState] = useState(() => (editing ? whenStateFrom(editing) : EMPTY_WHEN));
  const [fmt, setFmt] = useState(editing?.fmt ?? 'offline');
  const [people, setPeople] = useState(editing?.max_participants ?? 5);
  const [busy, setBusy] = useState(false);
  const notify = useNotify();

  const index = ids.indexOf(step);
  const current = STEPS[index];
  const last = step === 'confirm';
  const group = groups.find((g) => g.title === groupTitle) ?? groups[0];
  const clampPeople = (n) => setPeople(Math.min(MAX_PEOPLE, Math.max(minPeople, n)));

  const payload = buildPayload({ interest, title, description, whenState, fmt, people });
  const [initial] = useState(() => JSON.stringify(payload));
  const changed = JSON.stringify(payload) !== initial;

  const valid = { what: payload.title.length >= 3, category: !!interest, when: whenValid(whenState) };
  const ok = (id) => valid[id] ?? true;
  const allOk = ids.every(ok);

  const back = () => {
    if (fromSummary) {
      setFromSummary(false);
      setStep('confirm');
    } else {
      setStep(ids[Math.max(0, index - 1)]);
    }
  };
  useEffect(() => {
    if (!backRef) return undefined;
    backRef.current = () => {
      if (step === root && !fromSummary) return false;
      back();
      return true;
    };
    return () => {
      backRef.current = null;
    };
  });

  const edit = (id) => {
    setFromSummary(true);
    setStep(id);
  };

  const submit = async () => {
    setBusy(true);
    try {
      if (editing) {
        const inv = await api.update(editing.id, payload);
        notify('Изменения сохранены');
        onSaved(inv);
        return;
      }
      const inv = await api.create(payload);
      notify('Приглашение опубликовано');
      onCreated(inv.id);
    } catch (e) {
      notify(e);
      setBusy(false);
    }
  };

  const next = () => {
    if (!ok(step)) return;
    if (fromSummary) {
      setFromSummary(false);
      setStep('confirm');
    } else if (last) {
      if (allOk && (!editing || changed)) submit();
    } else {
      setStep(ids[index + 1]);
    }
  };

  let body;
  if (step === 'what') {
    body = (
      <>
        <Input size="large" autoFocus value={title} maxLength={TITLE_MAX} placeholder="Например, поиграть в баскетбол после уроков" onChange={(e) => setTitle(e.target.value)} />
        <div className="ni-count">{title.length}/{TITLE_MAX}</div>
      </>
    );
  } else if (step === 'about') {
    body = <DescriptionEditor value={description} onChange={setDescription} max={DESCRIPTION_MAX} />;
  } else if (step === 'category') {
    body = <CategoryStep groups={groups} group={group} onGroup={setGroupTitle} interests={interests} interest={interest} onChange={setInterest} />;
  } else if (step === 'when') {
    body = <WhenPicker value={whenState} onChange={setWhenState} />;
  } else if (step === 'details') {
    body = <DetailsStep fmt={fmt} onFmt={setFmt} people={people} onPeople={clampPeople} minPeople={minPeople} accepted={editing?.accepted} />;
  } else {
    body = <SummaryStep me={me} interests={interests} payload={payload} description={description} accepted={editing?.accepted ?? 0} onEdit={edit} />;
  }

  const label = last ? (editing ? 'Сохранить' : 'Опубликовать') : fromSummary ? 'Готово' : (step === 'when' && whenEmpty(whenState)) || (step === 'about' && !description.trim()) ? 'Пропустить' : 'Далее';
  return (
    <>
      {!editing && (
        <div className="reg-top">
          <Steps count={STEPS.length} progress={index + 1} />
        </div>
      )}

      <form
        className="page"
        onSubmit={(e) => {
          e.preventDefault();
          next();
        }}
      >
        <div className="hero">
          {!editing && <Typography.Label variant="medium" className="muted">Шаг {index + 1} из {STEPS.length}</Typography.Label>}
          <Typography.Headline variant="large-strong">{editing && last ? 'Редактирование' : current.title}</Typography.Headline>
          <Typography.Body variant="medium" className="muted">
            {editing && last
              ? 'Нажмите на строку, чтобы изменить. Откликнувшимся придёт сообщение, если изменится время, формат или название.'
              : current.hint}
          </Typography.Body>
        </div>
        {body}
        <input type="submit" hidden />
      </form>

      <div className="bottom-bar">
        <Button type="button" stretched size="large" loading={busy} disabled={!ok(step) || (last && (!allOk || (editing && !changed)))} onClick={next}>
          {label}
        </Button>
      </div>
    </>
  );
}
