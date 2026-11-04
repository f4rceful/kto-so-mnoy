import { Suspense, lazy, useCallback, useEffect, useRef, useState } from 'react';
import { Button, Typography } from '@maxhub/max-ui';
import { api, bridge, startInvitationId } from './api';
import { useBackButton } from './hooks';
import { BackButton, BottomNav, Loading, ScrollTopButton } from './components';
import { pendingCount } from './InvitationCard';
import { readSessionJSON, writeSessionJSON } from './storage';
import Feed from './screens/Feed';

const loaders = {
  detail: () => import('./screens/Detail'),
  profile: () => import('./screens/Profile'),
  newInvitation: () => import('./screens/NewInvitation'),
  editInvitation: () => import('./screens/EditInvitation'),
  settings: () => import('./screens/Settings'),
  registration: () => import('./screens/Registration'),
};
const Detail = lazy(loaders.detail);
const Profile = lazy(loaders.profile);
const NewInvitation = lazy(loaders.newInvitation);
const EditInvitation = lazy(loaders.editInvitation);
const Settings = lazy(loaders.settings);
const Registration = lazy(loaders.registration);

const PRELOAD_DELAY = 800;
const preloadScreens = () => [loaders.detail, loaders.profile, loaders.newInvitation].forEach((load) => load());

const NAV_KEY = 'kto-so-mnoy:nav';
const TABS = ['feed', 'profile'];

const restorable = (screen) => (screen?.name === 'detail' && Number.isInteger(screen.id)) || screen?.name === 'settings';

function launchState() {
  const deep = startInvitationId();
  const saved = readSessionJSON(NAV_KEY);
  const fresh = deep && deep !== saved?.deep;
  if (!saved || fresh) return { deep, deepLink: deep, tab: 'feed', stack: [] };
  return {
    deep,
    deepLink: null,
    tab: TABS.includes(saved.tab) ? saved.tab : 'feed',
    stack: Array.isArray(saved.stack) ? saved.stack.filter(restorable) : [],
  };
}

export default function App() {
  const [launch] = useState(launchState);
  const [boot, setBoot] = useState({ loading: true, error: null });
  const [interests, setInterests] = useState([]);
  const [me, setMe] = useState(null);
  const [tab, setTab] = useState(launch.tab);
  const [stack, setStack] = useState(launch.stack);
  const [refreshKey, setRefreshKey] = useState(0);
  const [deepLink, setDeepLink] = useState(launch.deepLink);
  const [waiting, setWaiting] = useState(0);
  const [seed, setSeed] = useState(null);

  const load = useCallback(() => {
    setBoot({ loading: true, error: null });
    api.bootstrap().then(
      ({ me: profile, interests: list, feed, waiting: count }) => {
        setInterests(list);
        setMe(profile);
        setWaiting(count);
        setSeed(feed ? { ...feed, at: Date.now() } : null);
        setBoot({ loading: false, error: null });
      },
      (error) => setBoot({ loading: false, error }),
    );
  }, []);
  useEffect(load, [load]);

  useEffect(() => {
    writeSessionJSON(NAV_KEY, { deep: launch.deep, tab, stack: stack.filter(restorable) });
  }, [launch.deep, tab, stack]);

  useEffect(() => {
    if (!me?.onboarded || refreshKey === 0) return undefined;
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
    if (!me?.onboarded) return undefined;
    const timer = setTimeout(preloadScreens, PRELOAD_DELAY);
    return () => clearTimeout(timer);
  }, [me?.onboarded]);

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
      <div className="page boot-error" role="alert">
        <Typography.Headline variant="large-strong">Не удалось открыть</Typography.Headline>
        <Typography.Body variant="medium" className="muted">{boot.error.message}</Typography.Body>
        <Button size="large" onClick={load}>Повторить</Button>
      </div>
    );
  }

  if (!me.onboarded) {
    return (
      <Suspense fallback={<Loading />}>
        <Registration me={me} interests={interests} onSaved={setMe} />
      </Suspense>
    );
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
        <Suspense fallback={<Loading />}>{screen}</Suspense>
      </>
    );
  }

  const openDetail = (id) => push({ name: 'detail', id });
  const toTop = () => window.scrollTo({ top: 0, behavior: 'smooth' });
  return (
    <>
      {tab === 'feed' && <Feed interests={interests} refreshKey={refreshKey} onOpen={openDetail} seed={seed} />}
      {tab === 'profile' && (
        <Suspense fallback={<Loading />}>
          <Profile
            me={me}
            interests={interests}
            refreshKey={refreshKey}
            onOpen={openDetail}
            onSettings={() => push({ name: 'settings' })}
          />
        </Suspense>
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
