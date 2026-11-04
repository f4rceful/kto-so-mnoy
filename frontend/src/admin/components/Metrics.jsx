import { useEffect, useState } from 'react';
import { AuthError, adminApi } from '../api';
import Empty from './Empty';
import MetricChart from './MetricChart';
import MetricTable from './MetricTable';
import { SERIES } from './metricSeries';

const RANGES = [
  [7, '7 дней'],
  [14, '14 дней'],
  [30, '30 дней'],
];
const VIEWS = [
  ['chart', 'График'],
  ['table', 'Таблица'],
];

const ratio = (a, b) => (b ? (a / b).toFixed(1).replace('.', ',') : '—');

export default function Metrics({ version, onAuthError }) {
  const [range, setRange] = useState(7);
  const [view, setView] = useState('chart');
  const [state, setState] = useState({ data: null, error: '', loading: true });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: '' }));
    adminApi.metrics(range).then(
      (data) => !cancelled && setState({ data, error: '', loading: false }),
      (e) => {
        if (cancelled) return;
        if (e instanceof AuthError) onAuthError(e.message);
        else setState((s) => ({ ...s, error: e.message, loading: false }));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [range, version, tick, onAuthError]);

  const { data, error, loading } = state;
  if (!data) {
    return error ? (
      <Empty title="Не удалось загрузить" hint={<><br />{error}<br /><button type="button" className="btn ghost small" onClick={() => setTick((t) => t + 1)}>Повторить</button></>} />
    ) : (
      <div className="empty">Загрузка…</div>
    );
  }

  const { totals, days } = data;
  const quiet = days.every((d) => SERIES.every((s) => d[s.key] === 0));
  const tiles = [
    [totals.invitations, 'приглашений всего'],
    [totals.responses, 'откликов всего'],
    [totals.accepted, 'откликов принято'],
    [totals.held, 'занятий состоялось'],
    [ratio(totals.responses, totals.invitations), 'откликов на приглашение'],
  ];
  return (
    <div className="metrics">
      <div className="toolbar">
        <div className="chips" role="group" aria-label="Период">
          {RANGES.map(([value, label]) => (
            <button key={value} type="button" className="chip" aria-pressed={range === value} onClick={() => setRange(value)}>{label}</button>
          ))}
        </div>
        <div className="chips" role="group" aria-label="Вид">
          {VIEWS.map(([value, label]) => (
            <button key={value} type="button" className="chip" aria-pressed={view === value} onClick={() => setView(value)}>{label}</button>
          ))}
        </div>
      </div>

      <div className="stats">
        {tiles.map(([value, label]) => (
          <div key={label} className="stat">
            <b>{value}</b>
            <span>{label}</span>
          </div>
        ))}
      </div>
      <p className="note">Карточки показывают всё время, график и таблица — выбранный период. «Состоялось» — приглашения с прошедшей датой и хотя бы одним принятым откликом. Дни считаются по московскому времени.</p>

      <div className={loading ? 'card chart reloading' : 'card chart'}>
        {error && <div className="err" role="alert">{error}</div>}
        {quiet ? (
          <Empty title="За этот период ничего не было" hint="Новых приглашений и откликов нет. Выберите период подлиннее." />
        ) : view === 'chart' ? (
          <MetricChart days={days} />
        ) : (
          <MetricTable days={days} />
        )}
      </div>
    </div>
  );
}
