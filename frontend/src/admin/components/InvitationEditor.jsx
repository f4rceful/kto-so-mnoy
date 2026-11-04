import { useState } from 'react';

export default function InvitationEditor({ item, busy, onSave, onCancel }) {
  const [title, setTitle] = useState(item.title);
  const [description, setDescription] = useState(item.description ?? '');
  const [when, setWhen] = useState(item.when ?? '');

  const patch = {};
  if (title.trim() !== item.title) patch.title = title;
  if (description !== (item.description ?? '')) patch.description = description;
  if (when !== (item.when ?? '')) patch.when = when;
  const dirty = Object.keys(patch).length > 0;
  const valid = title.trim().length >= 3;

  return (
    <form className="editor" onSubmit={(e) => { e.preventDefault(); if (dirty && valid) onSave(patch); }}>
      <label className="field">
        <span>Название</span>
        <input className="input" value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="field">
        <span>Описание</span>
        <textarea className="input" rows={4} value={description} maxLength={1000} onChange={(e) => setDescription(e.target.value)} />
      </label>
      <label className="field">
        <span>Заметка о времени</span>
        <input className="input" value={when} maxLength={80} onChange={(e) => setWhen(e.target.value)} />
      </label>
      <p className="note">Автор получит сообщение о том, что приглашение исправлено, а у приглашения появится пометка «изменено».</p>
      <div className="dialog-actions">
        <button type="button" className="btn ghost" onClick={onCancel}>Отмена</button>
        <button type="submit" className="btn" disabled={busy || !dirty || !valid}>Сохранить</button>
      </div>
    </form>
  );
}
