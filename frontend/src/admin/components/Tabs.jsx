export default function Tabs({ sections, counts, active, onChange }) {
  const onKeyDown = (e) => {
    const n = sections.length;
    const i = sections.findIndex((s) => s.id === active);
    const next = { ArrowRight: (i + 1) % n, ArrowLeft: (i - 1 + n) % n, Home: 0, End: n - 1 }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    onChange(sections[next].id);
    document.getElementById(`tab-${sections[next].id}`)?.focus();
  };
  return (
    <div className="tabs" role="tablist" aria-label="Разделы" onKeyDown={onKeyDown}>
      {sections.map((s) => {
        const count = counts[s.id];
        return (
          <button
            key={s.id}
            id={`tab-${s.id}`}
            type="button"
            role="tab"
            className="tab"
            aria-selected={active === s.id}
            aria-controls={`panel-${s.id}`}
            tabIndex={active === s.id ? 0 : -1}
            onClick={() => onChange(s.id)}
          >
            {s.title}
            {count != null && <span className={s.hot && count ? 'n hot' : 'n'}>{count}</span>}
          </button>
        );
      })}
    </div>
  );
}
