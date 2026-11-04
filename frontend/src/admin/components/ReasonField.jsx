export default function ReasonField({ presets, value, onChange, placeholder }) {
  return (
    <>
      <div className="chips">
        {presets.map((p) => (
          <button key={p} type="button" className="chip" aria-pressed={value === p} onClick={() => onChange(p)}>{p}</button>
        ))}
      </div>
      <textarea value={value} maxLength={200} placeholder={placeholder} aria-label="Причина" onChange={(e) => onChange(e.target.value)} />
    </>
  );
}
