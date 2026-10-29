import { useEffect, useState } from 'react';
import { BottomSheet, Button, IconButton, Spinner, Typography } from '@maxhub/max-ui';
import { ArrowUpIcon, BackIcon, CheckIcon, ChevronIcon, FeedIcon, PlusIcon, ProfileIcon } from './icons';

const SHOW_AFTER = 500;
export function ScrollTopButton({ onClick }) {
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const update = () => setShown(window.scrollY > SHOW_AFTER);
    update();
    window.addEventListener('scroll', update, { passive: true });
    return () => window.removeEventListener('scroll', update);
  }, []);
  return (
    <div className={shown ? 'to-top on' : 'to-top'}>
      <IconButton type="button" variant="primary" size="small" aria-label="Наверх" tabIndex={shown ? 0 : -1} onClick={onClick}>
        <ArrowUpIcon />
      </IconButton>
    </div>
  );
}

export const BackButton = ({ onClick, variant = 'ghost', size = 'small' }) => (
  <IconButton type="button" variant={variant} size={size} aria-label="Назад" onClick={onClick}>
    <BackIcon />
  </IconButton>
);

export function BottomNav({ active, badge = 0, onFeed, onAdd, onProfile }) {
  return (
    <nav className="bottom-nav" aria-label="Разделы">
      <button type="button" className={active === 'feed' ? 'on' : ''} aria-current={active === 'feed' ? 'page' : undefined} onClick={onFeed}>
        <span className="nav-ico"><FeedIcon /></span>
        <span>Лента</span>
      </button>
      <button type="button" className="add" aria-label="Предложить занятие" onClick={onAdd}>
        <span className="add-pill"><PlusIcon /></span>
        <span>Создать</span>
      </button>
      <button type="button" className={active === 'profile' ? 'on' : ''} aria-current={active === 'profile' ? 'page' : undefined} onClick={onProfile}>
        <span className="nav-ico">
          <ProfileIcon />
          {badge > 0 && <span className="nav-badge" aria-label={`Ждут ответа: ${badge}`}>{badge > 9 ? '9+' : badge}</span>}
        </span>
        <span>Профиль</span>
      </button>
    </nav>
  );
}

export function GradePicker({ grades, value, onChange }) {
  return (
    <div className="grade-grid" role="radiogroup" aria-label="Класс">
      {grades.map((g) => (
        <button key={g} type="button" role="radio" aria-checked={value === g} className={value === g ? 'grade-tile on' : 'grade-tile'} onClick={() => onChange(g)}>
          <b>{g}</b>
          <span>класс</span>
        </button>
      ))}
    </div>
  );
}

export function CategoryItems({ group, selected, onToggle }) {
  return (
    <div className="cat-items" role="group" aria-label={group.title}>
      {group.items.map((i) => {
        const on = selected.includes(i.id);
        return (
          <button key={i.id} type="button" role="checkbox" aria-checked={on} className={on ? 'cat-item on' : 'cat-item'} onClick={() => onToggle(i.id)}>
            <span>{i.name}</span>
            <span className="box" aria-hidden="true">{on && <CheckIcon />}</span>
          </button>
        );
      })}
    </div>
  );
}

export function groupInterests(interests) {
  const groups = [];
  for (const i of interests) {
    let g = groups.find((x) => x.title === i.group);
    if (!g) groups.push((g = { title: i.group, items: [] }));
    g.items.push(i);
  }
  return groups;
}

export function CategoryAccordion({ groups, selected, onToggle, openTitle: outerTitle, onOpenTitle }) {
  const [ownTitle, setOwnTitle] = useState(null);
  const openTitle = onOpenTitle ? outerTitle : ownTitle;
  const setOpenTitle = onOpenTitle ?? setOwnTitle;
  return (
    <div className="cat-list">
      {groups.map((g) => {
        const isOpen = openTitle === g.title;
        const n = g.items.filter((i) => selected.includes(i.id)).length;
        return (
          <div key={g.title} className={isOpen ? 'cat open' : 'cat'}>
            <button type="button" className="cat-head" aria-expanded={isOpen} onClick={() => setOpenTitle(isOpen ? null : g.title)}>
              <span>{g.title}</span>
              {n > 0 && <b className="pill-count">{n}</b>}
              <ChevronIcon />
            </button>
            {isOpen && <CategoryItems group={g} selected={selected} onToggle={onToggle} />}
          </div>
        );
      })}
    </div>
  );
}

export const FORMAT = { offline: 'Очно', online: 'Онлайн' };

export const interestName = (interests, id) => interests.find((i) => i.id === id)?.name ?? id;

export const toggleId = (list, id) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);

export function InterestPicker({ interests, selected, onChange }) {
  const chip = (i) => (
    <Button key={i.id} type="button" size="small" variant={selected.includes(i.id) ? 'primary' : 'secondary'} onClick={() => onChange(toggleId(selected, i.id))}>
      {i.name}
    </Button>
  );
  const groups = groupInterests(interests);
  return (
    <div className="interest-groups">
      {groups.map((g) => (
        <div key={g.title ?? 'all'} className="interest-group">
          {g.title && <Typography.Label variant="medium" className="muted">{g.title}</Typography.Label>}
          <div className="chips">{g.items.map(chip)}</div>
        </div>
      ))}
    </div>
  );
}

export function Loading() {
  return (
    <div className="center">
      <Spinner />
    </div>
  );
}

export function ErrorState({ error, onRetry }) {
  return (
    <div className="empty" role="alert">
      <Typography.Body variant="medium">{error?.message || 'Не получилось загрузить.'}</Typography.Body>
      {onRetry && (
        <div style={{ marginTop: 12 }}>
          <Button type="button" size="small" variant="secondary" onClick={onRetry}>
            Повторить
          </Button>
        </div>
      )}
    </div>
  );
}

export function BotNotice({ bot, onOpen, compact = false }) {
  if (!bot?.link || bot.state === 'ok') return null;
  const blocked = bot.state === 'blocked';
  return (
    <div className={blocked ? 'bot-notice warn' : 'bot-notice'} role="note">
      <Typography.Body variant="medium-strong">{blocked ? 'Уведомления не доходят' : 'Чтобы получать уведомления'}</Typography.Body>
      {!compact && (
        <Typography.Body variant="small" className="muted">
          {blocked
            ? 'Похоже, вы остановили бота. Откройте чат с ним и нажмите «Старт», тогда я снова смогу писать вам о приглашениях и откликах.'
            : 'Откройте чат с ботом и нажмите «Старт»: без этого MAX не разрешает ему писать вам первым.'}
        </Typography.Body>
      )}
      <Button type="button" size="small" variant={blocked ? 'primary' : 'secondary'} onClick={() => onOpen(bot.link)}>
        Открыть чат с ботом
      </Button>
    </div>
  );
}

export function Sheet({ open = true, title, onClose, children }) {
  return (
    <BottomSheet open={open} title={title} onClose={onClose} innerClassNames={{ sheet: 'sheet-narrow' }}>
      <div className="sheet-body">{children}</div>
    </BottomSheet>
  );
}

export function ConfirmSheet({ open, title, text, action, busy, onClose, onConfirm }) {
  return (
    <Sheet open={open} title={title} onClose={onClose}>
      <Typography.Body variant="medium" className="muted">{text}</Typography.Body>
      <div className="row">
        <Button variant="secondary" onClick={onClose}>Отмена</Button>
        <Button
          variant="destructive"
          disabled={busy}
          onClick={() => {
            onClose();
            onConfirm();
          }}
        >
          {action}
        </Button>
      </div>
    </Sheet>
  );
}

export function LegalSheet({ doc, onClose }) {
  return (
    <Sheet title={doc.title} onClose={onClose}>
      <div className="legal">
        {doc.updated && <Typography.Body variant="small" className="muted">Редакция от {doc.updated}</Typography.Body>}
        {doc.sections.map((section) => (
          <section key={section.title}>
            <Typography.Body variant="medium-strong">{section.title}</Typography.Body>
            {section.paragraphs.map((text, i) => (
              <Typography.Body key={i} variant="small">{text}</Typography.Body>
            ))}
          </section>
        ))}
      </div>
      <Button type="button" stretched size="large" onClick={onClose}>Закрыть</Button>
    </Sheet>
  );
}

export function Empty({ children }) {
  return <div className="empty">{children}</div>;
}
