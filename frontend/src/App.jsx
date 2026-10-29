import { useCallback, useEffect, useRef, useState } from 'react';
import { Button, Typography } from '@maxhub/max-ui';
import { api, bridge, startInvitationId } from './api';
import { useBackButton } from './hooks';
import { BackButton, BottomNav, Loading, ScrollTopButton } from './components';
import { pendingCount } from './InvitationCard';
import Detail from './screens/Detail';
import EditInvitation from './screens/EditInvitation';
import Feed from './screens/Feed';
import NewInvitation from './screens/NewInvitation';
import Profile from './screens/Profile';
import Registration from './screens/Registration';
import Settings from './screens/Settings';

export default function App() {
  const [boot, setBoot] = useState({ loading: true, error: null });
  const [interests, setInterests] = useState([]);
  const [me, setMe] = useState(null);
  const [tab, setTab] = useState('feed');
  const [stack, setStack] = useState([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [deepLink, setDeepLink] = useState(startInvitationId);
  const [waiting, setWaiting] = useState(0);

  const load = useCallback(() => {
    setBoot({ loading: true, error: null });
    Promise.all([api.interests(), api.me()]).then(
      ([list, profile]) => {
        setInterests(list);
        setMe(profile);
        setBoot({ loading: false, error: null });
      },
      (error) => setBoot({ loading: false, error }),
    );
  }, []);
  useEffect(load, [load]);

  useEffect(() => {
    if (!me?.onboarded) return undefined;
    let cancelled = false;
    api.mine().then(
      (list) => {
        if (cancelled) return;
        const open = list.filter((i) => i.status === 'open');
        setWaiting(open.reduce((sum, i) => sum + pendingCount(i), 0));
      },
      () => {},
    );
    return () => {
      cancelled = true;
    };
  }, [me?.onboarded, refreshKey]);

  useEffect(() => {
    if (me?.onboarded && deepLink) {
      setStack([{ name: 'detail', id: deepLink }]);
      setDeepLink(null);
    }
  }, [me?.onboarded, deepLink]);

  const push = (screen) => setStack((s) => [...s, screen]);
  const stepBack = useRef(null);
  const back = useCallback(() => {
    if (stepBack.current?.()) return;
    setStack((s) => s.slice(0, -1));
  }, []);
  const bump = () => setRefreshKey((k) => k + 1);

  useBackButton(stack.length, back);

  if (boot.loading) return <Loading />;
  if (boot.error) {
    return (
      <div className="page">
        <div className="hero">
          <Typography.Headline variant="large-strong">Не удалось открыть</Typography.Headline>
          <Typography.Body variant="medium" className="muted">{boot.error.message}</Typography.Body>
        </div>
        <Button stretched onClick={load}>Повторить</Button>
      </div>
    );
  }

  if (!me.onboarded) {
    return <Registration me={me} interests={interests} onSaved={setMe} />;
  }

  const top = stack.at(-1);
  let screen = null;
  if (top?.name === 'detail') {
    screen = <Detail key={top.id} id={top.id} interests={interests} onChanged={bump} onEdit={() => push({ name: 'edit', id: top.id })} onBack={back} />;
  } else if (top?.name === 'settings') {
    screen = (
      <Settings
        me={me}
        interests={interests}
        onSaved={(m) => {
          setMe(m);
          bump();
        }}
      />
    );
  } else if (top?.name === 'edit') {
    screen = (
      <EditInvitation
        key={top.id}
        id={top.id}
        me={me}
        backRef={stepBack}
        interests={interests}
        onSaved={() => {
          bump();
          setStack((s) => s.slice(0, -1));
        }}
      />
    );
  } else if (top?.name === 'new') {
    screen = (
      <NewInvitation
        me={me}
        backRef={stepBack}
        interests={interests}
        defaultInterest={me.interests[0]}
        onCreated={(id) => {
          bump();
          setTab('profile');
          setStack([{ name: 'detail', id }]);
        }}
      />
    );
  }
  if (screen) {
    return (
      <>
        {!bridge?.initData && (
          <div className="back-row">
            <BackButton onClick={back} />
          </div>
        )}
        {screen}
      </>
    );
  }

  const openDetail = (id) => push({ name: 'detail', id });
  const toTop = () => window.scrollTo({ top: 0, behavior: 'smooth' });
  return (
    <>
      {tab === 'feed' && <Feed interests={interests} refreshKey={refreshKey} onOpen={openDetail} />}
      {tab === 'profile' && (
        <Profile
          me={me}
          interests={interests}
          refreshKey={refreshKey}
          onOpen={openDetail}
          onSettings={() => push({ name: 'settings' })}
        />
      )}
      <ScrollTopButton onClick={toTop} />
      <BottomNav
        active={tab}
        badge={waiting}
        onFeed={() => (tab === 'feed' ? toTop() : setTab('feed'))}
        onAdd={() => push({ name: 'new' })}
        onProfile={() => (tab === 'profile' ? toTop() : setTab('profile'))}
      />
    </>
  );
}
