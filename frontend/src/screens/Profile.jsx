import { useState } from 'react';
import { Avatar, Button, IconButton, Segmented, Typography } from '@maxhub/max-ui';
import { InvitationList, pendingCount } from '../InvitationCard';
import { api, bridge, openMaxUrl } from '../api';
import { useLoad, useShare } from '../hooks';
import { plural } from '../plural';
import { BotNotice, Empty, ErrorState, Loading, interestName } from '../components';
import { CloseIcon, SettingsIcon } from '../icons';
import { readStorage, writeStorage } from '../storage';

const GRADIENTS = ['blue', 'purple', 'green', 'orange', 'red'];
const PALETTES = {
  blue: ['#3b82f6', '#6366f1'],
  purple: ['#8b5cf6', '#d946ef'],
  green: ['#10b981', '#06b6d4'],
  orange: ['#f59e0b', '#ef4444'],
  red: ['#ef4444', '#ec4899'],
};

const gradientOf = (me) => GRADIENTS[me.id % GRADIENTS.length];

const VISIBLE_TAGS = 3;
const HIDE_INVITE_KEY = 'kto-so-mnoy:hide-invite';
const inviteHidden = () => readStorage(HIDE_INVITE_KEY) === '1';

function initials(name) {
  return (name || '?').split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase();
}

function ProfileAvatar({ me }) {
  const user = bridge?.initDataUnsafe?.user;
  const photo = user?.photo_url ?? user?.photo;
  const gradient = gradientOf(me);
  return (
    <Avatar.Container size={84} form="circle">
      {typeof photo === 'string' && photo ? (
        <Avatar.Image src={photo} fallback={<Avatar.Text gradient={gradient}>{initials(me.display_name)}</Avatar.Text>} />
      ) : (
        <Avatar.Text gradient={gradient}>{initials(me.display_name)}</Avatar.Text>
      )}
    </Avatar.Container>
  );
}

function MyLists({ interests, mine, joined, onOpen }) {
  const [list, setList] = useState('mine');
  const current = list === 'mine' ? mine : joined;
  const tabs = [
    { id: 'mine', title: mine.data ? `Мои · ${mine.data.length}` : 'Мои' },
    { id: 'joined', title: joined.data ? `Участвую · ${joined.data.length}` : 'Участвую' },
  ];
  const items = current.data ?? [];
  const open = items.filter((i) => i.status === 'open');
  const closed = items.filter((i) => i.status !== 'open');
  return (
    <>
      <Segmented items={tabs} activeItem={list} onClick={setList} />
      {current.loading && !current.data ? (
        <Loading />
      ) : !items.length ? (
        current.error ? (
          <ErrorState error={current.error} onRetry={current.reload} />
        ) : (
          <Empty>
            {list === 'mine' ? 'Вы ещё ничего не предлагали. Нажмите «+» внизу.' : 'Вы пока никуда не откликались. Загляните в ленту!'}
          </Empty>
        )
      ) : (
        <>
          {open.length > 0 && <InvitationList items={open} interests={interests} onOpen={onOpen} />}
          {closed.length > 0 && (
            <>
              <Typography.Label variant="medium" className="muted">Закрытые · {closed.length}</Typography.Label>
              <InvitationList items={closed} interests={interests} onOpen={onOpen} split={false} />
            </>
          )}
        </>
      )}
    </>
  );
}

export default function Profile({ me, interests, refreshKey, onOpen, onSettings }) {
  const share = useShare();
  const mine = useLoad(() => api.mine(), [refreshKey]);
  const joined = useLoad(() => api.joined(), [refreshKey]);
  const [hideInvite, setHideInvite] = useState(inviteHidden);
  const [allTags, setAllTags] = useState(false);
  const dismissInvite = () => {
    setHideInvite(true);
    writeStorage(HIDE_INVITE_KEY, '1');
  };

  const invite = () => share('Я в «Кто со мной?» — находим компанию для занятий вне уроков. Заходи, мы из одной школы!', me.school_invite);

  const waiting = (mine.data ?? []).filter((i) => i.status === 'open').map((i) => [i, pendingCount(i)]).filter(([, n]) => n > 0);
  const pending = waiting.reduce((sum, [, n]) => sum + n, 0);

  const [g1, g2] = PALETTES[gradientOf(me)];
  const school = [me.grade && `${me.grade} класс`, me.school].filter(Boolean).join(' · ');
  const tags = allTags ? me.interests : me.interests.slice(0, VISIBLE_TAGS);
  const hidden = me.interests.length - VISIBLE_TAGS;

  return (
    <div className="page profile-page" style={{ '--g1': g1, '--g2': g2 }}>
      <div className="p-head">
        <div className="p-avatar">
          <ProfileAvatar me={me} />
        </div>
        <div className="p-info">
          <Typography.Headline variant="large-strong">{me.display_name || 'Профиль'}</Typography.Headline>
          {school && <Typography.Body variant="medium">{school}</Typography.Body>}
          {me.city && <Typography.Body variant="small" className="muted">{me.city}</Typography.Body>}
        </div>
        <button type="button" className="p-gear" aria-label="Настройки" onClick={onSettings}>
          <SettingsIcon />
        </button>
      </div>

      {tags.length > 0 && (
        <div className="chips">
          {tags.map((id) => (
            <span className="tag" key={id}>{interestName(interests, id)}</span>
          ))}
          {hidden > 0 && (
            <button type="button" className="tag tag-more" onClick={() => setAllTags(!allTags)}>
              {allTags ? 'Свернуть' : `ещё ${hidden}`}
            </button>
          )}
        </div>
      )}

      {me.bot?.state === 'blocked' && (me.notify || me.notify_activity) && <BotNotice bot={me.bot} onOpen={openMaxUrl} compact />}

      {pending > 0 && (
        <button type="button" className="notice" onClick={() => onOpen(waiting[0][0].id)}>
          <span>
            <b>{pending}</b> {plural(pending, ['отклик ждёт', 'отклика ждут', 'откликов ждут'])} вашего ответа
          </span>
          <span className="notice-go">Открыть</span>
        </button>
      )}

      {me.school_invite && !hideInvite && (
        <div className="card">
          <div className="between">
            <Typography.Body variant="medium-strong">Позовите одноклассников</Typography.Body>
            <IconButton type="button" variant="ghost" size="xsmall" aria-label="Скрыть" onClick={dismissInvite}>
              <CloseIcon />
            </IconButton>
          </div>
          <Typography.Body variant="small" className="muted">
            Чем больше людей из школы в приложении, тем живее лента «Моя школа».
          </Typography.Body>
          <Button type="button" stretched size="medium" variant="secondary" onClick={invite}>
            Поделиться ссылкой
          </Button>
        </div>
      )}

      <MyLists interests={interests} mine={mine} joined={joined} onOpen={onOpen} />
    </div>
  );
}
