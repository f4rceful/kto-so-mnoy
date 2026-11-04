import { fmtDayLong } from '../format';
import { SERIES, sumOf } from './metricSeries';

export default function MetricTable({ days }) {
  const rows = [...days].reverse();
  return (
    <div className="table-wrap">
      <table className="data-table">
        <caption className="sr-only">Показатели по дням</caption>
        <thead>
          <tr>
            <th scope="col">День</th>
            {SERIES.map((s) => (
              <th key={s.key} scope="col">{s.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.date}>
              <th scope="row">{fmtDayLong(d.date)}</th>
              {SERIES.map((s) => (
                <td key={s.key}>{d[s.key]}</td>
              ))}
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Итого за период</th>
            {SERIES.map((s) => (
              <td key={s.key}>{sumOf(days, s.key)}</td>
            ))}
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
