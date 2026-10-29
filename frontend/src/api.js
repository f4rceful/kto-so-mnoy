const webApp = window.WebApp;

const urlParams = () => new URLSearchParams(location.search);
const devUser = urlParams().get('dev');
const devUsername = urlParams().get('devname');

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

const OFFLINE = 'Нет связи с сервером. Проверьте интернет и попробуйте ещё раз.';
const UNAVAILABLE = 'Сервер временно недоступен. Попробуйте чуть позже.';
const FALLBACK = {
  401: 'Не удалось войти. Закройте приложение и откройте его заново из MAX.',
  404: 'Не найдено. Возможно, это уже удалили.',
  429: 'Слишком много запросов. Подождите немного и повторите.',
};

function errorMessage(status, data) {
  if (Array.isArray(data?.detail)) return 'Проверьте заполнение полей';
  if (status === 401) return FALLBACK[401];
  if (typeof data?.detail === 'string' && data.detail) return data.detail;
  if (status >= 500) return UNAVAILABLE;
  return FALLBACK[status] ?? 'Не получилось. Попробуйте ещё раз.';
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const RETRY_DELAY = 500;

async function request(path, method = 'GET', body, withHeaders = false) {
  const headers = { 'Content-Type': 'application/json' };
  if (devUser) {
    headers['X-Dev-User'] = devUser;
    if (devUsername) headers['X-Dev-Username'] = devUsername;
  }
  else if (webApp?.initData) headers['X-Init-Data'] = webApp.initData;

  const attempts = method === 'GET' ? 2 : 1;
  for (let attempt = 1; ; attempt++) {
    let res;
    try {
      res = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
    } catch {
      if (attempt < attempts) {
        await wait(RETRY_DELAY);
        continue;
      }
      throw new ApiError(OFFLINE, 0);
    }
    if ([502, 503, 504].includes(res.status) && attempt < attempts) {
      await wait(RETRY_DELAY);
      continue;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(errorMessage(res.status, data), res.status);
    return withHeaders ? { data, headers: res.headers } : data;
  }
}

const FEED_PAGE = 20;

export const api = {
  interests: () => request('/interests'),
  regions: () => request('/regions'),
  cities: (region, q) => request(`/cities?${new URLSearchParams({ region, q })}`),
  schools: (cityId, q) => request(`/schools?${new URLSearchParams({ city_id: cityId, q })}`),
  terms: () => request('/terms'),
  school: (id) => request(`/schools/${id}`),
  me: () => request('/me'),
  saveMe: (profile) => request('/me', 'PUT', profile),
  feed: async ({ interests, fmt, hasSpots, sort, scope, q = '', offset = 0, limit = FEED_PAGE }) => {
    const params = new URLSearchParams({ sort, scope, offset, limit });
    if (interests.length) params.set('interest', interests.join(','));
    if (fmt) params.set('fmt', fmt);
    if (hasSpots) params.set('has_spots', 'true');
    if (q) params.set('q', q);
    const { data, headers } = await request(`/invitations?${params}`, 'GET', undefined, true);
    return { items: data, total: Number(headers.get('X-Total-Count') ?? data.length) };
  },
  mine: () => request('/invitations/mine'),
  joined: () => request('/invitations/joined'),
  detail: (id) => request(`/invitations/${id}`),
  create: (invitation) => request('/invitations', 'POST', invitation),
  update: (id, invitation) => request(`/invitations/${id}`, 'PUT', invitation),
  respond: (id) => request(`/invitations/${id}/respond`, 'POST'),
  accept: (responseId) => request(`/responses/${responseId}/accept`, 'POST'),
  decline: (responseId) => request(`/responses/${responseId}/decline`, 'POST'),
  close: (id) => request(`/invitations/${id}/close`, 'POST'),
  reportReasons: () => request('/report-reasons'),
  report: (id, body) => request(`/invitations/${id}/report`, 'POST', body),
  blockAuthor: (id) => request(`/invitations/${id}/block-author`, 'POST'),
  blocks: () => request('/blocks'),
  unblock: (id) => request(`/blocks/${id}`, 'DELETE'),
};

function startParamId(prefix) {
  const param = webApp?.initDataUnsafe?.start_param ?? urlParams().get('start');
  const match = new RegExp(`^${prefix}_(\\d+)$`).exec(param ?? '');
  return match ? Number(match[1]) : null;
}

export const startInvitationId = () => startParamId('inv');
export const startSchoolId = () => startParamId('school');

export async function shareLink(text, link) {
  try {
    if (webApp?.shareMaxContent) {
      webApp.shareMaxContent({ text, link });
      return 'shared';
    }
    await navigator.clipboard.writeText(`${text} ${link}`);
    return 'copied';
  } catch {
    return 'failed';
  }
}

export function openMaxUrl(url) {
  if (webApp?.openMaxLink) webApp.openMaxLink(url);
  else window.open(url, '_blank', 'noopener');
}

export const openContact = (username) => openMaxUrl(`https://max.ru/${username}`);

export const bridge = webApp;
