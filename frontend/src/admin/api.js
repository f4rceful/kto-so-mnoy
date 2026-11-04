import { getKey } from './session';

export class AuthError extends Error {}

async function call(path, method = 'GET', body) {
  const res = await fetch(`/api/admin${path}`, {
    method,
    headers: { 'X-Admin-Key': getKey(), 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) throw new AuthError(data.detail || 'Неверный ключ');
  if (res.status === 429) throw new AuthError(data.detail || 'Слишком много попыток. Попробуйте позже.');
  if (res.status === 404 && data.detail === 'Not Found') throw new Error('Модерация выключена: на сервере не задан ADMIN_KEY');
  if (!res.ok) throw new Error(data.detail || `Ошибка ${res.status}`);
  return data;
}

const query = (params = {}) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== '' && value != null) search.set(key, value);
  }
  const text = search.toString();
  return text ? `?${text}` : '';
};

export const adminApi = {
  stats: () => call('/stats'),
  reports: () => call('/reports'),
  invitations: (params) => call(`/invitations${query(params)}`),
  users: (params) => call(`/users${query(params)}`),
  log: (params) => call(`/log${query(params)}`),
  links: () => call('/links'),
  metrics: (days) => call(`/metrics${query({ days })}`),
  hide: (id, reason) => call(`/invitations/${id}/hide`, 'POST', { reason }),
  restore: (id) => call(`/invitations/${id}/restore`, 'POST'),
  dismiss: (id) => call(`/invitations/${id}/dismiss`, 'POST'),
  ban: (userId, reason, days) => call(`/users/${userId}/ban`, 'POST', { reason, days }),
  user: (id) => call(`/users/${id}`),
  editUser: (id, patch) => call(`/users/${id}`, 'PATCH', patch),
  schools: (q) => call(`/schools${query({ q })}`),
  renameSchool: (id, name) => call(`/schools/${id}`, 'PATCH', { name }),
  editInvitation: (id, patch) => call(`/invitations/${id}`, 'PATCH', patch),
  unban: (userId) => call(`/users/${userId}/unban`, 'POST'),
};
