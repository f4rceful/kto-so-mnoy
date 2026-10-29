import { Button, CellSimple, Input, Select, Switch, Typography } from '@maxhub/max-ui';
import { GradePicker, InterestPicker, LegalSheet, Loading, interestName } from '../components';
import PlacePicker from '../PlacePicker';
import { FEDERAL_REGIONS, GRADES, clean } from '../profile';

export function NameStep({ data, set }) {
  return <Input size="large" autoFocus placeholder="Например, Аня" maxLength={30} value={data.displayName} onChange={(e) => set({ displayName: e.target.value })} />;
}

export function RegionStep({ data, regions, onChange }) {
  if (regions.loading && !regions.data) return <Loading />;
  return (
    <Select
      size="large"
      searchable
      searchPlaceholder="Найти регион"
      placeholder="Выберите регион"
      emptyText="Ничего не найдено"
      options={(regions.data ?? []).map((r) => ({ value: r, label: r }))}
      value={data.region || undefined}
      onValueChange={onChange}
    />
  );
}

export function CityStep({ data, load, onChange }) {
  return (
    <PlacePicker key={data.region} load={load} value={data.city} onChange={onChange} placeholder="Например, Казань" maxLength={80} autoFocus emptyHint="Начните вводить название города" />
  );
}

export function SchoolStep({ data, set, load }) {
  return (
    <>
      <PlacePicker
        key={data.city?.id ?? data.city?.name}
        load={load}
        value={data.school}
        onChange={(school) => set({ school })}
        placeholder="Например, Гимназия № 7"
        maxLength={120}
        autoFocus
        emptyHint="Школ из вашего города пока нет — впишите название своей"
      />
      {data.school && (
        <Typography.Body variant="small" className="muted">
          {data.school.members
            ? `Из вашей школы в приложении уже ${data.school.members}. Так вас будет проще найти.`
            : 'Вы первый из этой школы. После регистрации позовите одноклассников: в профиле есть ссылка-приглашение.'}
        </Typography.Body>
      )}
    </>
  );
}

export function GradeStep({ data, set }) {
  return <GradePicker grades={GRADES} value={data.grade} onChange={(grade) => set({ grade })} />;
}

export function InterestsStep({ data, set, interests }) {
  return (
    <>
      <InterestPicker interests={interests} selected={data.interests} onChange={(list) => set({ interests: list })} />
      <CellSimple
        surface="island"
        title="Уведомления"
        subtitle="Сообщать в чат о новых приглашениях по моим интересам"
        after={<Switch checked={data.notify} onChange={(e) => set({ notify: e.target.checked })} />}
      />
    </>
  );
}

export function ConfirmStep({ data, set, interests, terms, doc, onDoc, onEdit }) {
  const rows = [
    ['Имя', clean(data.displayName), 'name'],
    ['Регион', data.region, 'region'],
    ...(FEDERAL_REGIONS.has(data.region) ? [] : [['Город', data.city?.name, 'city']]),
    ['Школа', data.school?.name, 'school'],
    ['Класс', data.grade && `${data.grade} класс`, 'grade'],
    ['Интересы', data.interests.map((id) => interestName(interests, id)).join(', ') || 'Не выбраны', 'interests'],
  ];
  const shown = terms.data?.documents.find((d) => d.id === doc);
  return (
    <>
      <div className="cell-stack">
        {rows.map(([label, value, id]) => (
          <CellSimple key={id} surface="island" overline={label} title={value || '—'} showChevron onClick={() => onEdit(id)} />
        ))}
      </div>

      <hr className="divider" />

      <div className="doc-tabs">
        {(terms.data?.documents ?? []).map((d) => (
          <Button key={d.id} type="button" size="small" variant="secondary" onClick={() => onDoc(d.id)}>
            {d.short ?? d.title}
          </Button>
        ))}
      </div>
      {shown && <LegalSheet doc={shown} onClose={() => onDoc(null)} />}
      <CellSimple
        surface="island"
        title="Принимаю условия"
        subtitle="Условия использования и политику обработки данных"
        after={<Switch checked={data.accepted} onChange={(e) => set({ accepted: e.target.checked })} />}
      />
    </>
  );
}
