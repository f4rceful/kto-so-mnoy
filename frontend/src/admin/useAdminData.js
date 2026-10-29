import { useCallback, useEffect, useRef, useState } from 'react';
import { AuthError, adminApi } from './api';
import { getKey, setKey } from './session';
import { useToast } from './toasts';

const REFRESH_MS = 30000;

export function useAdminData({ paused = false } = {}) {
  const toast = useToast();
  const [phase, setPhase] = useState(() => (getKey() ? 'loading' : 'login'));
  const [loginError, setLoginError] = useState('');
  const [data, setData] = useState(null);
  const [updated, setUpdated] = useState(null);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;
  const hasData = useRef(false);

  const toLogin = useCallback((message = '') => {
    setKey('');
    hasData.current = false;
    setData(null);
    setLoginError(message);
    setPhase('login');
  }, []);

  const refresh = useCallback(
    async (silent = false) => {
      try {
        const [stats, reports, all, users] = await Promise.all([adminApi.stats(), adminApi.reports(), adminApi.invitations(), adminApi.users()]);
        hasData.current = true;
        setData({ stats, reports: reports.items, all: all.items, users: users.items });
        setUpdated(new Date());
        setPhase('ready');
      } catch (e) {
        if (e instanceof AuthError) {
          toLogin(e.message);
        } else if (!hasData.current) {
          toLogin(e.message);
        } else if (!silent) {
          toast(e.message, 'bad');
        }
      }
    },
    [toast, toLogin],
  );

  useEffect(() => {
    if (getKey()) refresh();
  }, [refresh]);

  useEffect(() => {
    if (phase !== 'ready') return undefined;
    const timer = setInterval(() => {
      if (!document.hidden && !pausedRef.current) refresh(true);
    }, REFRESH_MS);
    return () => clearInterval(timer);
  }, [phase, refresh]);

  const login = useCallback(
    (key) => {
      setKey(key);
      setLoginError('');
      setPhase('loading');
      refresh();
    },
    [refresh],
  );

  const perform = useCallback(
    async (label, action) => {
      try {
        await action();
        toast(label);
        await refresh();
      } catch (e) {
        if (e instanceof AuthError) toLogin(e.message);
        else toast(e.message, 'bad');
      }
    },
    [toast, toLogin, refresh],
  );

  return { phase, loginError, data, updated, login, logout: () => toLogin(''), refresh, perform };
}
