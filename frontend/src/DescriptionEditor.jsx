import { useLayoutEffect, useRef, useState } from 'react';
import { Textarea, Typography } from '@maxhub/max-ui';
import Markdown from './Markdown';
import { BulletListIcon, RedoIcon, UndoIcon } from './icons';
import { clearFormatting, continueList, createHistory, formatState, toggleInline, toggleList } from './mdEdit';

export default function DescriptionEditor({ value, onChange, max }) {
  const ref = useRef(null);
  const [history] = useState(createHistory);
  const [sel, setSel] = useState({ start: value.length, end: value.length });

  const read = () => ({ value, start: ref.current?.selectionStart ?? sel.start, end: ref.current?.selectionEnd ?? sel.end });
  const pending = useRef(null);
  const place = (next) => {
    pending.current = next;
    setSel({ start: next.start, end: next.end });
  };
  useLayoutEffect(() => {
    const el = ref.current;
    const next = pending.current;
    if (!el || !next) return;
    pending.current = null;
    el.focus();
    el.setSelectionRange(next.start, next.end);
  });
  const apply = (next) => {
    if (!next || next.value.length > max) return;
    history.record(read(), 'edit');
    onChange(next.value);
    place(next);
  };
  const restore = (snapshot) => {
    if (!snapshot) return;
    onChange(snapshot.value);
    place(snapshot);
  };
  const undo = () => restore(history.undo(read()));
  const redo = () => restore(history.redo(read()));

  const actions = {
    bold: () => apply(toggleInline('bold', read(), max)),
    italic: () => apply(toggleInline('italic', read(), max)),
    ul: () => apply(toggleList('ul', read(), max)),
    ol: () => apply(toggleList('ol', read(), max)),
    clear: () => apply(clearFormatting(read())),
  };
  const state = formatState({ value, ...sel });
  const hasFormat = state.bold || state.italic || state.ul || state.ol || state.heading;

  const onKeyDown = (e) => {
    const mod = e.metaKey || e.ctrlKey;
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      const next = continueList(read());
      if (next && next.value.length <= max) {
        e.preventDefault();
        apply(next);
      }
    } else if (mod && e.code === 'KeyZ') {
      e.preventDefault();
      if (e.shiftKey) redo();
      else undo();
    } else if (mod && e.code === 'KeyY') {
      e.preventDefault();
      redo();
    } else if (mod && e.code === 'KeyB') {
      e.preventDefault();
      actions.bold();
    } else if (mod && e.code === 'KeyI') {
      e.preventDefault();
      actions.italic();
    }
  };

  const button = (name, label, content, { onClick, pressed, disabled }) => (
    <button
      key={name}
      type="button"
      className="fmt-btn"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      disabled={disabled}
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
    >
      {content}
    </button>
  );

  return (
    <>
      <div className="fmt-bar" role="toolbar" aria-label="Форматирование">
        {button('undo', 'Отменить', <UndoIcon />, { onClick: undo, disabled: !history.canUndo })}
        {button('redo', 'Повторить', <RedoIcon />, { onClick: redo, disabled: !history.canRedo })}
        <span className="fmt-sep" />
        {button('bold', 'Жирный', <b>B</b>, { onClick: actions.bold, pressed: state.bold })}
        {button('italic', 'Курсив', <i>I</i>, { onClick: actions.italic, pressed: state.italic })}
        <span className="fmt-sep" />
        {button('ul', 'Маркированный список', <BulletListIcon />, { onClick: actions.ul, pressed: state.ul })}
        {button('ol', 'Нумерованный список', <span>1.</span>, { onClick: actions.ol, pressed: state.ol })}
        <span className="fmt-sep" />
        {button('clear', 'Очистить форматирование', <span>T<sub>x</sub></span>, { onClick: actions.clear, disabled: !hasFormat })}
      </div>

      <Textarea
        ref={ref}
        rows={6}
        value={value}
        maxLength={max}
        placeholder="Например: играем 3 на 3, берите сменную обувь"
        onChange={(e) => {
          history.record({ value, ...sel }, 'type');
          onChange(e.target.value);
          setSel({ start: e.target.selectionStart, end: e.target.selectionEnd });
        }}
        onSelect={(e) => setSel({ start: e.target.selectionStart, end: e.target.selectionEnd })}
        onKeyDown={onKeyDown}
      />
      <div className="ni-count">{value.length}/{max}</div>
      <Typography.Body variant="small" className="muted">
        Выделите текст и нажмите кнопку; повторное нажатие снимает форматирование. Enter в списке добавляет пункт, а на пустом пункте выходит из списка.
      </Typography.Body>

      {value.trim() && (
        <div className="field">
          <Typography.Label variant="medium" className="muted">Так увидят другие</Typography.Label>
          <div className="card"><Markdown text={value} /></div>
        </div>
      )}
    </>
  );
}
