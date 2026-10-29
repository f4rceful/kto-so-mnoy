import { useCallback, useMemo, useState } from 'react';
import { makeActions } from './actions';
import BanDialog from './components/BanDialog';
import HideDialog from './components/HideDialog';
import Login from './components/Login';
import SectionList from './components/SectionList';
import StatsBar from './components/StatsBar';
import Tabs from './components/Tabs';
import TopBar from './components/TopBar';
import { SECTIONS } from './sections';
import { ToastProvider } from './toasts';
import { useAdminData } from './useAdminData';

function Panel() {
  const [dialog, setDialog] = useState(null);
  const [tabId, setTabId] = useState(SECTIONS[0].id);
  const [query, setQuery] = useState('');
  const admin = useAdminData({ paused: !!dialog });
  const { phase, data, perform } = admin;

  const actions = useMemo(() => makeActions(perform), [perform]);
  const ask = useMemo(
    () => ({
      hide: (item) => setDialog({ type: 'hide', item }),
      ban: (author) => setDialog({ type: 'ban', author }),
    }),
    [],
  );
  const close = useCallback(() => setDialog(null), []);

  if (phase === 'login') return <Login error={admin.loginError} onSubmit={admin.login} />;
  if (phase === 'loading') return <div className="empty">Загрузка…</div>;

  const section = SECTIONS.find((s) => s.id === tabId);
  const counts = Object.fromEntries(SECTIONS.map((s) => [s.id, s.count(data)]));

  return (
    <>
      <TopBar updated={admin.updated} onRefresh={() => admin.refresh()} onLogout={admin.logout} />

      <main>
        <StatsBar stats={data.stats} />
        <Tabs sections={SECTIONS} counts={counts} active={tabId} onChange={setTabId} />
        <input className="search" type="search" value={query} placeholder="Поиск: название, автор, номер…" aria-label="Поиск" onChange={(e) => setQuery(e.target.value)} />
        <div role="tabpanel">
          <SectionList section={section} data={data} query={query} actions={actions} ask={ask} />
        </div>
      </main>

      {dialog?.type === 'hide' && (
        <HideDialog item={dialog.item} onCancel={close} onConfirm={(reason) => { close(); actions.hide(dialog.item, reason); }} />
      )}
      {dialog?.type === 'ban' && (
        <BanDialog author={dialog.author} onCancel={close} onConfirm={() => { close(); actions.ban(dialog.author); }} />
      )}
    </>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <Panel />
    </ToastProvider>
  );
}
