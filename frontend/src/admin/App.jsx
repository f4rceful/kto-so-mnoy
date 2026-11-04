import { useCallback, useMemo, useState } from 'react';
import { makeActions } from './actions';
import BanDialog from './components/BanDialog';
import EditInvitationDialog from './components/EditInvitationDialog';
import ErrorBoundary from './components/ErrorBoundary';
import HideDialog from './components/HideDialog';
import LoadError from './components/LoadError';
import Login from './components/Login';
import PagedList from './components/PagedList';
import SectionList from './components/SectionList';
import StatsBar from './components/StatsBar';
import Tabs from './components/Tabs';
import TopBar from './components/TopBar';
import UserDialog from './components/UserDialog';
import { SECTIONS } from './sections';
import { ToastProvider } from './toasts';
import { useAdminData } from './useAdminData';

function Panel() {
  const [dialog, setDialog] = useState(null);
  const [tabId, setTabId] = useState(SECTIONS[0].id);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('');
  const admin = useAdminData({ paused: !!dialog });
  const { phase, data, perform, busy } = admin;

  const actions = useMemo(() => makeActions(perform), [perform]);
  const ask = useMemo(
    () => ({
      hide: (item) => setDialog({ type: 'hide', item }),
      ban: (author) => setDialog({ type: 'ban', author }),
      edit: (item) => setDialog({ type: 'edit', item }),
      profile: (user) => setDialog({ type: 'profile', id: user.id }),
    }),
    [],
  );
  const close = useCallback(() => setDialog(null), []);
  const openTab = useCallback((id) => {
    setTabId(id);
    setQuery('');
    setFilter('');
  }, []);

  if (phase === 'login') return <Login error={admin.loginError} onSubmit={admin.login} />;
  if (phase === 'loading') return <div className="empty">Загрузка…</div>;
  if (phase === 'error') return <LoadError message={admin.loadError} onRetry={admin.retry} onLogout={admin.logout} />;

  const section = SECTIONS.find((s) => s.id === tabId);
  const counts = Object.fromEntries(SECTIONS.map((s) => [s.id, s.count(data)]));
  const common = { actions, ask, busy };

  let body;
  if (section.View) {
    body = <section.View key={section.id} version={admin.version} onAuthError={admin.expire} />;
  } else if (section.load) {
    body = <PagedList key={section.id} section={section} query={query} filter={filter} version={admin.version} onAuthError={admin.expire} {...common} />;
  } else {
    body = <SectionList section={section} data={data} query={query} {...common} />;
  }

  return (
    <>
      <TopBar updated={admin.updated} onRefresh={() => admin.refresh()} onLogout={admin.logout} />

      <main>
        <StatsBar stats={data.stats} />
        <Tabs sections={SECTIONS} counts={counts} active={tabId} onChange={openTab} />
        {section.search && (
          <input className="search" type="search" value={query} placeholder={section.search} aria-label="Поиск" onChange={(e) => setQuery(e.target.value)} />
        )}
        {section.filters && (
          <div className="chips filters" role="group" aria-label="Фильтр">
            {section.filters.map(([value, label]) => (
              <button key={value} type="button" className="chip" aria-pressed={filter === value} onClick={() => setFilter(value)}>{label}</button>
            ))}
          </div>
        )}
        <div role="tabpanel" id={`panel-${section.id}`} aria-labelledby={`tab-${section.id}`}>
          {body}
        </div>
      </main>

      {dialog?.type === 'hide' && (
        <HideDialog item={dialog.item} onCancel={close} onConfirm={(reason) => { close(); actions.hide(dialog.item, reason); }} />
      )}
      {dialog?.type === 'ban' && (
        <BanDialog author={dialog.author} onCancel={close} onConfirm={(reason, days) => { close(); actions.ban(dialog.author, reason, days); }} />
      )}
      {dialog?.type === 'edit' && (
        <EditInvitationDialog item={dialog.item} onClose={close} onChanged={() => admin.refresh()} onAuthError={admin.expire} />
      )}
      {dialog?.type === 'profile' && (
        <UserDialog userId={dialog.id} onClose={close} onChanged={() => admin.refresh()} onAuthError={admin.expire} />
      )}
    </>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <ErrorBoundary>
        <Panel />
      </ErrorBoundary>
    </ToastProvider>
  );
}
