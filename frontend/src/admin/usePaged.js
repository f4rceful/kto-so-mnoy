import { useCallback, useEffect, useRef, useState } from 'react';
import { AuthError } from './api';

const merge = (items, more) => {
  const seen = new Set(items.map((i) => i.id));
  return [...items, ...more.filter((i) => !seen.has(i.id))];
};

export function usePaged(fetchPage, params, { version, onAuthError }) {
  const [state, setState] = useState({ items: [], total: 0, loading: true, loadingMore: false, error: '' });
  const [tick, setTick] = useState(0);
  const run = useRef(0);
  const loadingMore = useRef(false);
  const latest = useRef({ fetchPage, params, items: state.items, onAuthError });
  latest.current = { fetchPage, params, items: state.items, onAuthError };
  const key = JSON.stringify(params);

  const fail = useCallback((e, id, patch) => {
    if (run.current !== id) return;
    if (e instanceof AuthError) latest.current.onAuthError(e.message);
    else setState((s) => ({ ...s, ...patch, error: e.message }));
  }, []);

  useEffect(() => {
    const id = ++run.current;
    loadingMore.current = false;
    setState((s) => ({ ...s, loading: true, loadingMore: false, error: '' }));
    latest.current.fetchPage({ ...latest.current.params, offset: 0 }).then(
      ({ items, total }) => run.current === id && setState({ items, total, loading: false, loadingMore: false, error: '' }),
      (e) => fail(e, id, { loading: false }),
    );
  }, [key, version, tick, fail]);

  const loadMore = useCallback(async () => {
    if (loadingMore.current) return;
    const id = run.current;
    loadingMore.current = true;
    setState((s) => ({ ...s, loadingMore: true, error: '' }));
    try {
      const { items, total } = await latest.current.fetchPage({ ...latest.current.params, offset: latest.current.items.length });
      if (run.current === id) setState((s) => ({ ...s, items: merge(s.items, items), total, loadingMore: false }));
    } catch (e) {
      fail(e, id, { loadingMore: false });
    } finally {
      loadingMore.current = false;
    }
  }, [fail]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, loadMore, reload };
}
