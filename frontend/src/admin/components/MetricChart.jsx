import { useLayoutEffect, useRef, useState } from 'react';
import { fmtDay, fmtDayLong } from '../format';
import { SERIES, sumOf, yScale } from './metricSeries';

const LEFT = 34;
const RIGHT = 22;
const HEAD = 24;
const PLOT = 64;
const GAP = 14;
const AXIS = 26;
const PANEL = HEAD + PLOT;
const clamp = (value, low, high) => Math.min(high, Math.max(low, value));

function useWidth(ref) {
  const [width, setWidth] = useState(640);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const measure = () => {
      const w = el.getBoundingClientRect().width;
      setWidth(w > 0 ? Math.max(280, Math.floor(w)) : 640);
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}

export default function MetricChart({ days }) {
  const wrap = useRef(null);
  const width = useWidth(wrap);
  const [active, setActive] = useState(null);

  const n = days.length;
  const plotWidth = width - LEFT - RIGHT;
  const x = (i) => LEFT + (n > 1 ? (i * plotWidth) / (n - 1) : plotWidth / 2);
  const max = Math.max(0, ...SERIES.flatMap((s) => days.map((d) => d[s.key])));
  const { top, ticks } = yScale(max);
  const height = SERIES.length * (PANEL + GAP) - GAP + AXIS;
  const baseline = (panel) => panel * (PANEL + GAP) + PANEL;
  const y = (value, panel) => baseline(panel) - (value / top) * PLOT;
  const labelEvery = n <= 7 ? 1 : n <= 14 ? 2 : 5;

  const indexAt = (clientX) => {
    const rect = wrap.current.getBoundingClientRect();
    return clamp(Math.round(((clientX - rect.left - LEFT) / plotWidth) * (n - 1)), 0, n - 1);
  };

  const onKeyDown = (e) => {
    const moves = {
      ArrowRight: (i) => (i === null ? n - 1 : Math.min(n - 1, i + 1)),
      ArrowLeft: (i) => (i === null ? n - 1 : Math.max(0, i - 1)),
      Home: () => 0,
      End: () => n - 1,
    };
    if (e.key === 'Escape') return setActive(null);
    if (!moves[e.key]) return undefined;
    e.preventDefault();
    return setActive(moves[e.key]);
  };

  const line = (key, panel) => days.map((d, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(d[key], panel).toFixed(1)}`).join('');
  const area = (key, panel) => `${line(key, panel)}L${x(n - 1).toFixed(1)} ${baseline(panel)}L${x(0).toFixed(1)} ${baseline(panel)}Z`;
  const tipOnLeft = active !== null && x(active) > width * 0.55;

  return (
    <div
      className="mc"
      ref={wrap}
      tabIndex={0}
      role="group"
      aria-label="Графики за период. Стрелки влево и вправо выбирают день, полные значения есть в таблице"
      onPointerMove={(e) => setActive(indexAt(e.clientX))}
      onPointerLeave={() => setActive(null)}
      onFocus={(e) => e.target === e.currentTarget && active === null && setActive(n - 1)}
      onBlur={() => setActive(null)}
      onKeyDown={onKeyDown}
    >
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
        {SERIES.map((s, p) => (
          <g key={s.key}>
            <rect x={LEFT} y={p * (PANEL + GAP) + 7} width="14" height="3" rx="1.5" fill={s.color} />
            <text className="mc-title" x={LEFT + 20} y={p * (PANEL + GAP) + 15}>{s.label}</text>
            <text className="mc-sum" x={width - RIGHT} y={p * (PANEL + GAP) + 15} textAnchor="end">{sumOf(days, s.key)}</text>
            {ticks.map((t) => (
              <g key={t}>
                <line className={t === 0 ? 'mc-base' : 'mc-grid'} x1={LEFT} x2={width - RIGHT} y1={y(t, p)} y2={y(t, p)} />
                <text className="mc-tick" x={LEFT - 8} y={y(t, p) + 4} textAnchor="end">{t}</text>
              </g>
            ))}
            <path className="mc-area" d={area(s.key, p)} fill={s.color} />
            <path className="mc-line" d={line(s.key, p)} stroke={s.color} />
            <circle className="mc-dot" cx={x(n - 1)} cy={y(days[n - 1][s.key], p)} r="4" fill={s.color} />
            {active !== null && <circle className="mc-dot" cx={x(active)} cy={y(days[active][s.key], p)} r="4" fill={s.color} />}
          </g>
        ))}
        {active !== null && <line className="mc-cross" x1={x(active)} x2={x(active)} y1={HEAD - 4} y2={height - AXIS} />}
        {days.map((d, i) => (
          (n - 1 - i) % labelEvery === 0 && (
            <text key={d.date} className="mc-tick" x={x(i)} y={height - 8} textAnchor="middle">{fmtDay(d.date)}</text>
          )
        ))}
      </svg>
      {active !== null && (
        <div className="mc-tip" style={tipOnLeft ? { right: width - x(active) + 12, top: HEAD } : { left: x(active) + 12, top: HEAD }}>
          <div className="mc-tip-date">{fmtDayLong(days[active].date)}</div>
          {SERIES.map((s) => (
            <div className="mc-tip-row" key={s.key}>
              <span className="mc-key" style={{ background: s.color }} />
              <b>{days[active][s.key]}</b>
              <span>{s.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
