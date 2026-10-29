import { useCallback, useMemo, useState } from 'react';
import { Button, CellSimple, Input, Typography } from '@maxhub/max-ui';
import { api } from '../api';
import { useLoad, useNotify } from '../hooks';
import { CategoryAccordion, GradePicker, Loading, Sheet, groupInterests, toggleId } from '../components';
import PlacePicker from '../PlacePicker';
import { FEDERAL_REGIONS, GRADES, clean, federalCity, place, placeFields, samePlace } from '../profile';

const sameSet = (a, b) => a.length === b.length && a.every((x) => b.includes(x));

function EditSheet({ title, onClose, onSave, canSave, busy, children }) {
  return (
    <Sheet title={title} onClose={onClose}>
      {children}
      {onSave && (
        <Button stretched size="large" loading={busy} disabled={!canSave} onClick={onSave}>
          Сохранить
        </Button>
      )}
    </Sheet>
  );
}

export function NameEditor({ me, busy, onSave, onClose }) {
  const [name, setName] = useState(me.display_name);
  const value = clean(name);
  return (
    <EditSheet title="Ваше имя" onClose={onClose} busy={busy} canSave={value.length >= 2 && value !== me.display_name} onSave={() => onSave({ display_name: value })}>
      <div className="field">
        <Input size="large" autoFocus maxLength={30} value={name} onChange={(e) => setName(e.target.value)} />
        <Typography.Body variant="small" className="muted">
          Так вас видят другие участники. Лучше только имя: фамилию и контакты мы не показываем.
        </Typography.Body>
      </div>
    </EditSheet>
  );
}

export function SchoolEditor({ me, busy, onSave, onClose }) {
  const regions = useLoad(() => api.regions(), []);
  const [form, setForm] = useState({ region: me.region, city: place(me.city_id, me.city), school: place(me.school_id, me.school) });
  const federal = FEDERAL_REGIONS.has(form.region);

  const setRegion = (region) => {
    if (region === form.region) return;
    setForm({ region, city: null, school: null });
    if (region) federalCity(region).then((city) => city && setForm((f) => (f.region === region ? { ...f, city } : f)));
  };
  const loadRegions = useCallback(
    (q) => Promise.resolve((regions.data ?? []).filter((r) => r.toLowerCase().includes(q.toLowerCase())).map((r) => ({ id: r, name: r }))),
    [regions.data],
  );
  const loadCities = useCallback((q) => api.cities(form.region, q), [form.region]);
  const loadSchools = useCallback((q) => (form.city?.id ? api.schools(form.city.id, q) : Promise.resolve([])), [form.city?.id]);

  const changed = form.region !== me.region || !samePlace(form.city, place(me.city_id, me.city)) || !samePlace(form.school, place(me.school_id, me.school));
  return (
    <EditSheet
      title="Школа"
      onClose={onClose}
      busy={busy}
      canSave={!!(form.region && form.city && form.school && changed)}
      onSave={() => onSave({ region: form.region, ...placeFields('city', form.city), ...placeFields('school', form.school) })}
    >
      <div className="field">
        <Typography.Label variant="medium" className="muted">Регион</Typography.Label>
        <PlacePicker
          allowAdd={false}
          load={loadRegions}
          value={form.region ? { id: form.region, name: form.region } : null}
          onChange={(v) => setRegion(v?.name ?? '')}
          placeholder="Найти регион"
          emptyHint="Начните вводить название региона"
        />
      </div>
      {form.region && !federal && (
        <div className="field">
          <Typography.Label variant="medium" className="muted">Город</Typography.Label>
          <PlacePicker key={form.region} load={loadCities} value={form.city} onChange={(city) => setForm((f) => ({ ...f, city, school: null }))} placeholder="Начните вводить название" maxLength={80} emptyHint="Начните вводить название города" />
        </div>
      )}
      {form.city && (
        <div className="field">
          <Typography.Label variant="medium" className="muted">Школа</Typography.Label>
          <PlacePicker
            key={form.city.id ?? form.city.name}
            load={loadSchools}
            value={form.school}
            onChange={(school) => setForm((f) => ({ ...f, school }))}
            placeholder="Например, Гимназия № 7"
            maxLength={120}
            emptyHint="Школ из вашего города пока нет — впишите название своей"
          />
          <Typography.Body variant="small" className="muted">
            От школы зависит лента приглашений «Моя школа».
          </Typography.Body>
        </div>
      )}
    </EditSheet>
  );
}

export function GradeEditor({ me, busy, onSave, onClose }) {
  const [grade, setGrade] = useState(me.grade);
  return (
    <EditSheet title="Класс" onClose={onClose} busy={busy} canSave={!!grade && grade !== me.grade} onSave={() => onSave({ grade })}>
      <GradePicker grades={GRADES} value={grade} onChange={setGrade} />
    </EditSheet>
  );
}

export function InterestsEditor({ me, interests, busy, onSave, onClose }) {
  const groups = useMemo(() => groupInterests(interests), [interests]);
  const [selected, setSelected] = useState(me.interests);
  const toggle = (id) => setSelected((s) => toggleId(s, id));
  return (
    <EditSheet title="Интересы" onClose={onClose} busy={busy} canSave={!sameSet(selected, me.interests)} onSave={() => onSave({ interests: selected })}>
      <Typography.Body variant="small" className="muted">
        Выбрано: {selected.length}. По ним мы подбираем приглашения и присылаем уведомления.
      </Typography.Body>
      <CategoryAccordion groups={groups} selected={selected} onToggle={toggle} />
    </EditSheet>
  );
}

export function BlockedEditor({ onClose }) {
  const { data, loading, error, reload } = useLoad(() => api.blocks(), []);
  const show = useNotify();
  const [busyId, setBusyId] = useState(null);
  const restore = async (id) => {
    setBusyId(id);
    try {
      await api.unblock(id);
      reload();
    } catch (e) {
      show(e);
    } finally {
      setBusyId(null);
    }
  };
  return (
    <EditSheet title="Скрытые авторы" onClose={onClose}>
      {loading && !data ? (
        <Loading />
      ) : error ? (
        <Typography.Body variant="medium" className="muted">{error.message}</Typography.Body>
      ) : !data.length ? (
        <Typography.Body variant="medium" className="muted">
          Вы никого не скрывали. Скрыть автора можно на странице его приглашения.
        </Typography.Body>
      ) : (
        <div className="cell-stack">
          {data.map((b) => (
            <CellSimple
              key={b.id}
              surface="island"
              title={b.name}
              after={
                <Button size="small" variant="secondary" disabled={busyId === b.id} onClick={() => restore(b.id)}>
                  Вернуть
                </Button>
              }
            />
          ))}
        </div>
      )}
    </EditSheet>
  );
}
