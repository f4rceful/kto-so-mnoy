import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Steps, Typography } from '@maxhub/max-ui';
import { api, bridge, startSchoolId } from '../api';
import { useBackButton, useLoad, useNotify } from '../hooks';
import { BackButton, Loading } from '../components';
import { FEDERAL_REGIONS, clean, federalCity, place, placeFields } from '../profile';
import { readStorageJSON, removeStorage, writeStorage } from '../storage';
import { CityStep, ConfirmStep, GradeStep, InterestsStep, NameStep, RegionStep, SchoolStep } from './RegistrationSteps';

const DRAFT_KEY = 'kto-so-mnoy:registration';

const STEPS = [
  {
    id: 'name',
    title: 'Как вас зовут?',
    hint: 'Так вас увидят другие. Лучше только имя: фамилию и контакты мы не показываем.',
    valid: (d) => clean(d.displayName).length >= 2,
  },
  {
    id: 'region',
    title: 'Откуда вы?',
    hint: 'Выберите регион, где находится ваша школа.',
    valid: (d) => !!d.region && (!FEDERAL_REGIONS.has(d.region) || !!d.city),
  },
  {
    id: 'city',
    title: 'В каком вы городе?',
    hint: 'Начните вводить название. Если его нет в списке, добавьте своё.',
    valid: (d) => !!d.city,
  },
  {
    id: 'school',
    title: 'Где вы учитесь?',
    hint: 'Найдите свою школу. Если её нет в списке, впишите номер или название, например «Гимназия № 7».',
    valid: (d) => !!d.school,
  },
  {
    id: 'grade',
    title: 'В каком вы классе?',
    hint: 'Так мы поймём, с кем вам будет проще найти компанию.',
    valid: (d) => !!d.grade,
  },
  {
    id: 'interests',
    title: 'Что вам интересно?',
    hint: 'Выберите интересы — мы подскажем подходящие приглашения. Можно пропустить и выбрать позже.',
    valid: () => true,
  },
  {
    id: 'confirm',
    title: 'Проверьте и подтвердите',
    hint: 'Всё верно? Нажмите на строку, чтобы изменить.',
    valid: (d) => d.accepted,
  },
];

const stepsFor = (data) => (FEDERAL_REGIONS.has(data.region) ? STEPS.filter((s) => s.id !== 'city') : STEPS);
const firstIncomplete = (data) => {
  const steps = stepsFor(data);
  return (steps.find((s) => !s.valid(data)) ?? steps.at(-1)).id;
};

const buildData = (me, draft) => ({
  region: me.region || draft?.data?.region || '',
  city: place(me.city_id, me.city) ?? place(draft?.data?.city?.id, draft?.data?.city?.name),
  school: place(me.school_id, me.school) ?? place(draft?.data?.school?.id, draft?.data?.school?.name),
  grade: me.grade || draft?.data?.grade || null,
  interests: me.interests.length ? me.interests : draft?.data?.interests ?? [],
  notify: me.notify,
  displayName: draft?.data?.displayName ?? me.display_name ?? '',
  accepted: me.accepted_terms,
});

export default function Registration({ me, interests, onSaved }) {
  const [init] = useState(() => {
    const draft = readStorageJSON(DRAFT_KEY);
    const data = buildData(me, draft);
    const known = stepsFor(data).some((s) => s.id === draft?.stepId);
    return { data, stepId: known ? draft.stepId : data.region ? firstIncomplete(data) : 'name' };
  });
  const [data, setData] = useState(init.data);
  const [stepId, setStepId] = useState(init.stepId);
  const [fromSummary, setFromSummary] = useState(false);
  const [doc, setDoc] = useState(null);
  useEffect(() => {
    if (stepId !== 'confirm') setDoc(null);
  }, [stepId]);
  const [busy, setBusy] = useState(false);
  const show = useNotify();
  const regions = useLoad(() => api.regions(), []);
  const terms = useLoad(() => api.terms(), []);

  const inviteId = useMemo(startSchoolId, []);
  const [invite, setInvite] = useState({ loading: !!inviteId && !me.school_id, school: null });
  useEffect(() => {
    if (!invite.loading) return;
    api.school(inviteId).then(
      (school) => {
        const next = {
          ...init.data,
          region: school.region,
          city: { id: school.city_id, name: school.city },
          school: { id: school.id, name: school.name, members: school.members },
        };
        setData(next);
        setStepId(firstIncomplete(next));
        setInvite({ loading: false, school });
      },
      () => setInvite({ loading: false, school: null }),
    );
  }, []);

  const steps = useMemo(() => stepsFor(data), [data.region]);
  const index = Math.max(0, steps.findIndex((s) => s.id === stepId));
  const current = steps[index];
  const last = current.id === 'confirm';

  const set = (patch) => setData((d) => ({ ...d, ...patch }));
  const setRegion = (region) => {
    if (region === data.region) return;
    set({ region, city: null, school: null });
    federalCity(region).then((city) => city && setData((d) => (d.region === region ? { ...d, city } : d)));
  };
  const setCity = (city) => set({ city, school: null });
  const loadCities = useCallback((q) => api.cities(data.region, q), [data.region]);
  const loadSchools = useCallback((q) => (data.city?.id ? api.schools(data.city.id, q) : Promise.resolve([])), [data.city?.id]);

  useEffect(() => writeStorage(DRAFT_KEY, JSON.stringify({ stepId, data: { ...data, accepted: false } })), [stepId, data]);

  const back = useCallback(() => {
    if (fromSummary) {
      setFromSummary(false);
      setStepId('confirm');
    } else {
      setStepId(steps[Math.max(0, index - 1)].id);
    }
  }, [fromSummary, steps, index]);

  useBackButton(index > 0, back);

  const edit = (id) => {
    setFromSummary(true);
    setStepId(id);
  };

  const next = async () => {
    if (!current.valid(data)) return;
    if (fromSummary) {
      const pending = steps.find((s) => s.id !== 'confirm' && !s.valid(data));
      setStepId(pending?.id ?? 'confirm');
      if (!pending) setFromSummary(false);
      return;
    }
    if (!last) {
      setStepId(steps[index + 1].id);
      return;
    }
    setBusy(true);
    try {
      const saved = await api.saveMe({
        region: data.region,
        ...placeFields('city', data.city),
        ...placeFields('school', data.school),
        grade: data.grade,
        interests: data.interests,
        notify: data.notify,
        display_name: clean(data.displayName),
        accept_terms: true,
      });
      removeStorage(DRAFT_KEY);
      onSaved(saved);
    } catch (e) {
      show(e);
    } finally {
      setBusy(false);
    }
  };

  if (invite.loading) return <Loading />;

  const stepProps = { data, set };
  const body = {
    name: <NameStep {...stepProps} />,
    region: <RegionStep data={data} regions={regions} onChange={setRegion} />,
    city: <CityStep data={data} load={loadCities} onChange={setCity} />,
    school: <SchoolStep {...stepProps} load={loadSchools} />,
    grade: <GradeStep {...stepProps} />,
    interests: <InterestsStep {...stepProps} interests={interests} />,
    confirm: <ConfirmStep {...stepProps} interests={interests} terms={terms} doc={doc} onDoc={setDoc} onEdit={edit} />,
  }[current.id];

  return (
    <>
      <div className="reg-top">
        <Steps count={steps.length} progress={index + 1} />
      </div>

      <form
        className="page"
        onSubmit={(e) => {
          e.preventDefault();
          next();
        }}
      >
        <div className="hero">
          <Typography.Label variant="medium" className="muted">
            Шаг {index + 1} из {steps.length}
          </Typography.Label>
          {index === 0 && (
            <Typography.Body variant="medium" className="muted">
              Привет! Расскажите немного о себе, чтобы «Кто со мной?» помог найти компанию.
            </Typography.Body>
          )}
          {invite.school && current.id === 'grade' && (
            <Typography.Body variant="medium" className="muted">
              Вас позвали в школу «{invite.school.name}». Осталось пара шагов.
            </Typography.Body>
          )}
          <Typography.Headline variant="large-strong">{current.title}</Typography.Headline>
          <Typography.Body variant="medium" className="muted">{current.hint}</Typography.Body>
        </div>
        {body}
        <input type="submit" hidden />
      </form>

      <div className="bottom-bar bar-row">
        {index > 0 && !bridge?.initData && <BackButton variant="secondary" size="large" onClick={back} />}
        <Button type="button" stretched size="large" loading={busy} disabled={!current.valid(data)} onClick={next}>
          {last ? 'Готово' : current.id === 'interests' && !data.interests.length ? 'Пропустить' : 'Далее'}
        </Button>
      </div>
    </>
  );
}
