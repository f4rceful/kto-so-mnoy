import { useCallback, useEffect, useRef, useState } from 'react';
import { AuthError, adminApi } from './api';
import { getKey, setKey } from './session';
import { useToast } from './toasts';

const REFRESH_MS = 30000;

export function useAdminData({ paused = false } = {}) {
  const toast = useToast();
  const [phase, setPhase] = useState(() => (getKey() ? 'loading' : 'login'));
  const [loginError, setLoginError] = useState('');
  const [loadError, setLoadError] = useState('');
  const [data, setData] = useState(null);
  const [updated, setUpdated] = useState(null);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
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
        const [stats, reports] = await Promise.all([adminApi.stats(), adminApi.reports()]);
        hasData.current = true;
        setData({ stats, reports: reports.items });
        setUpdated(new Date());
        if (!silent) setVersion((v) => v + 1);
        setPhase('ready');
      } catch (e) {
        if (e instanceof AuthError) {
          toLogin(e.message);
        } else if (!hasData.current) {
          setLoadError(e.message);
          setPhase('error');
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

  const retry = useCallback(() => {
    setPhase('loading');
    refresh();
  }, [refresh]);

  const perform = useCallback(
    async (label, action) => {
      if (busyRef.current) return;
      busyRef.current = true;
      setBusy(true);
      try {
        const result = await action();
        toast(typeof label === 'function' ? label(result) : label);
        await refresh();
      } catch (e) {
        if (e instanceof AuthError) toLogin(e.message);
        else toast(e.message, 'bad');
      } finally {
        busyRef.current = false;
        setBusy(false);
      }
    },
    [toast, toLogin, refresh],
  );

  return { phase, loginError, loadError, data, updated, version, busy, login, logout: () => toLogin(''), expire: toLogin, retry, refresh, perform };
}
