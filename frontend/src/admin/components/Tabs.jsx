export default function Tabs({ sections, counts, active, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {sections.map((s) => (
        <button key={s.id} type="button" role="tab" className="tab" aria-selected={active === s.id} onClick={() => onChange(s.id)}>
          {s.title}
          <span className={s.hot && counts[s.id] ? 'n hot' : 'n'}>{counts[s.id]}</span>
        </button>
      ))}
    </div>
  );
}
