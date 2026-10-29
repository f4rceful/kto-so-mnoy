export default function Empty({ title, hint }) {
  return (
    <div className="empty">
      <b>{title}</b>
      {hint}
    </div>
  );
}
