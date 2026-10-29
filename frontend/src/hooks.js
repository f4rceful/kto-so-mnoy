import { useCallback, useEffect, useRef, useState } from 'react';
import { useSnackbar } from '@maxhub/max-ui';
import { bridge, shareLink } from './api';

export function useLoad(fetcher, deps) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    fetcher().then(
      (data) => !cancelled && setState({ data, loading: false, error: null }),
      (error) => !cancelled && setState({ data: null, loading: false, error }),
    );
    return () => {
      cancelled = true;
    };
  }, [...deps, tick]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}

export function usePages(fetchPage, deps) {
  const [state, setState] = useState({ items: [], total: 0, loading: true, loadingMore: false, error: null, moreError: null });
  const [tick, setTick] = useState(0);
  const run = useRef(0);
  const busy = useRef(false);
  const latest = useRef({ fetchPage, state });
  latest.current = { fetchPage, state };

  useEffect(() => {
    const id = ++run.current;
    busy.current = false;
    setState({ items: [], total: 0, loading: true, loadingMore: false, error: null, moreError: null });
    latest.current.fetchPage(0).then(
      ({ items, total }) => run.current === id && setState((s) => ({ ...s, items, total, loading: false })),
      (error) => run.current === id && setState((s) => ({ ...s, loading: false, error })),
    );
  }, [...deps, tick]);

  const hasMore = state.items.length < state.total;
  const loadMore = useCallback(() => {
    const { fetchPage: fetch, state: s } = latest.current;
    if (busy.current || s.loading || s.error || s.items.length >= s.total) return;
    busy.current = true;
    const id = run.current;
    setState((x) => ({ ...x, loadingMore: true, moreError: null }));
    fetch(s.items.length).then(
      ({ items, total }) => {
        if (run.current !== id) return;
        busy.current = false;
        setState((x) => {
          const seen = new Set(x.items.map((i) => i.id));
          return { ...x, items: [...x.items, ...items.filter((i) => !seen.has(i.id))], total, loadingMore: false };
        });
      },
      (moreError) => {
        if (run.current !== id) return;
        busy.current = false;
        setState((x) => ({ ...x, loadingMore: false, moreError }));
      },
    );
  }, []);

  const node = useRef(null);
  const sentinel = useCallback(
    (el) => {
      node.current?.observer?.disconnect();
      node.current = el ? { el } : null;
      if (!el || typeof IntersectionObserver === 'undefined') return;
      const observer = new IntersectionObserver((entries) => entries.some((e) => e.isIntersecting) && loadMore(), { rootMargin: '400px' });
      observer.observe(el);
      node.current.observer = observer;
    },
    [loadMore],
  );

  useEffect(() => {
    const el = node.current?.el;
    if (el && hasMore && !state.loadingMore && !state.moreError && el.getBoundingClientRect().top < window.innerHeight + 400) loadMore();
  }, [state.items.length, hasMore, state.loadingMore, state.moreError, loadMore]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, hasMore, loadMore, reload, sentinel };
}

export function useNotify() {
  const { showSnackbar } = useSnackbar();
  return useCallback(
    (textOrError) =>
      showSnackbar({
        text: textOrError instanceof Error ? textOrError.message : textOrError,
        duration: 3000,
      }),
    [showSnackbar],
  );
}

export function useShare() {
  const notify = useNotify();
  return async (text, link) => {
    const result = await shareLink(text, link);
    if (result === 'copied') notify('Ссылка скопирована');
    if (result === 'failed') notify('Не удалось поделиться ссылкой');
  };
}

export function useBackButton(visible, onBack) {
  useEffect(() => {
    const button = bridge?.BackButton;
    if (!button) return undefined;
    if (visible) {
      button.show();
      button.onClick(onBack);
    } else {
      button.hide();
    }
    return () => button.offClick(onBack);
  }, [visible, onBack]);
}
