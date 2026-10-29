import { useEffect, useMemo, useState } from 'react';
import { Button, IconButton, Input, Segmented, Spinner, Typography } from '@maxhub/max-ui';
import { api } from '../api';
import { usePages } from '../hooks';
import HScroll from '../HScroll';
import { InvitationList } from '../InvitationCard';
import { ErrorState, Loading, groupInterests } from '../components';
import { CloseIcon, FilterIcon, SearchIcon, SortIcon } from '../icons';
import { plural } from '../plural';
import { FilterSheet, GroupSheet, NO_FILTER, SORTS, SortSheet } from './FeedSheets';

const SCOPES = [
  { id: 'school', title: 'Моя школа' },
  { id: 'city', title: 'Весь город' },
];

const activeFilters = (f) => (f.fmt ? 1 : 0) + (f.hasSpots ? 1 : 0);

export default function Feed({ interests, refreshKey, onOpen }) {
  const [filter, setFilter] = useState(NO_FILTER);
  const [sort, setSort] = useState('new');
  const [scope, setScope] = useState('school');
  const [query, setQuery] = useState('');
  const [sheet, setSheet] = useState(null);
  const [draft, setDraft] = useState(NO_FILTER);
  const [draftSort, setDraftSort] = useState('new');
  const [groupSheet, setGroupSheet] = useState(null);
  const [groupDraft, setGroupDraft] = useState([]);
  const [openGroup, setOpenGroup] = useState(null);

  const [search, setSearch] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => setSearch(query.trim()), 300);
    return () => clearTimeout(timer);
  }, [query]);

  const { items, total, loading, loadingMore, error, moreError, hasMore, loadMore, reload, sentinel } = usePages(
    (offset) => api.feed({ ...filter, sort, scope, q: search, offset }),
    [filter, sort, scope, search, refreshKey],
  );

  const openFilter = () => {
    setDraft(filter);
    setSheet('filter');
  };
  const openSort = () => {
    setDraftSort(sort);
    setSheet('sort');
  };
  const count = activeFilters(filter);
  const selectedCount = filter.interests.length + count;
  const filtersActive = count > 0 || filter.interests.length > 0 || search;

  const groups = useMemo(() => groupInterests(interests), [interests]);
  const picked = (g) => g.items.filter((i) => filter.interests.includes(i.id)).length;
  const selectedGroups = groups.filter((g) => picked(g) > 0);
  const compact = selectedGroups.length > 0 || count > 0 || sort !== 'new';
  const sheetGroup = groups.find((g) => g.title === groupSheet);
  const sortShort = SORTS.find((s) => s.id === sort).short;

  return (
    <div className="page feed-page">
      <Input
        value={query}
        placeholder="Поиск по названию"
        iconBefore={<SearchIcon />}
        withClearButton
        onChange={(e) => setQuery(e.target.value)}
      />

      <Segmented items={SCOPES} activeItem={scope} onClick={setScope} />

      <div className={compact ? 'toolbar compact' : 'toolbar'}>
        {compact ? (
          <>
            <span className="badge-wrap">
              <IconButton className="tb-dark" variant="secondary" size="small" aria-label={`Фильтр, выбрано: ${selectedCount}`} onClick={openFilter}>
                <FilterIcon />
              </IconButton>
              {selectedCount > 0 && <span className="badge">{selectedCount}</span>}
            </span>
            <span className="badge-wrap">
              <IconButton className="tb-dark" variant="secondary" size="small" aria-label={`Сортировка: ${sortShort}`} onClick={openSort}>
                <SortIcon />
              </IconButton>
              {sort !== 'new' && <span className="badge">1</span>}
            </span>
            <span className="toolbar-sep" />
            <button
              type="button"
              className="clear-all"
              aria-label="Сбросить фильтры и сортировку"
              onClick={() => {
                setFilter(NO_FILTER);
                setSort('new');
                setOpenGroup(null);
              }}
            >
              <CloseIcon />
            </button>
            <HScroll>
              {selectedGroups.map((g) => (
                <button
                  key={g.title}
                  type="button"
                  className="pill"
                  onClick={() => {
                    setGroupDraft(filter.interests);
                    setGroupSheet(g.title);
                  }}
                >
                  {g.title}
                  <b className="pill-count">{picked(g)}</b>
                </button>
              ))}
            </HScroll>
          </>
        ) : (
          <>
            <Button size="small" variant={count ? 'primary' : 'secondary'} iconBefore={<FilterIcon />} onClick={openFilter}>
              {count ? `Фильтр · ${count}` : 'Фильтр'}
            </Button>
            <Button size="small" variant="secondary" iconBefore={<SortIcon />} onClick={openSort}>
              {sortShort}
            </Button>
          </>
        )}
      </div>

      {loading ? (
        <Loading />
      ) : (
        <>
          {!error && (
            <Typography.Label variant="medium" className="muted">
              {total} {plural(total, ['приглашение', 'приглашения', 'приглашений'])}
            </Typography.Label>
          )}
          {error ? (
            <ErrorState error={error} onRetry={reload} />
          ) : (
            <InvitationList
              items={items}
              interests={interests}
              onOpen={onOpen}
              emptyText={
                filtersActive
                  ? 'Ничего не найдено. Попробуйте изменить фильтры.'
                  : scope === 'school'
                    ? 'В вашей школе пока нет приглашений. Предложите первое или загляните в «Весь город».'
                    : 'В вашем городе пока нет приглашений. Предложите первое!'
              }
            />
          )}
          {!error && hasMore && (
            <div ref={sentinel} className="more">
              {moreError ? (
                <Button size="small" variant="secondary" onClick={loadMore}>Не удалось загрузить. Повторить</Button>
              ) : (
                loadingMore && <Spinner />
              )}
            </div>
          )}
          {scope === 'school' && !loading && !error && !items.length && !filtersActive && (
            <Button stretched variant="secondary" onClick={() => setScope('city')}>Показать весь город</Button>
          )}
        </>
      )}

      <GroupSheet
        group={sheetGroup}
        selected={groupDraft}
        onChange={setGroupDraft}
        onClose={() => setGroupSheet(null)}
        onApply={() => {
          setFilter((f) => ({ ...f, interests: groupDraft }));
          setGroupSheet(null);
        }}
      />

      <SortSheet
        open={sheet === 'sort'}
        value={draftSort}
        onChange={setDraftSort}
        onClose={() => setSheet(null)}
        onApply={() => {
          setSort(draftSort);
          setSheet(null);
        }}
      />

      <FilterSheet
        open={sheet === 'filter'}
        groups={groups}
        draft={draft}
        onChange={setDraft}
        openGroup={openGroup}
        onOpenGroup={setOpenGroup}
        onClose={() => setSheet(null)}
        onApply={() => {
          setFilter(draft);
          setSheet(null);
        }}
      />
    </div>
  );
}
