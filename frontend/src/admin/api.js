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
  if (res.status === 404 && data.detail === 'Not Found') throw new Error('Модерация выключена: на сервере не задан ADMIN_KEY');
  if (!res.ok) throw new Error(data.detail || `Ошибка ${res.status}`);
  return data;
}

export const adminApi = {
  stats: () => call('/stats'),
  reports: () => call('/reports'),
  invitations: () => call('/invitations'),
  users: () => call('/users'),
  hide: (id, reason) => call(`/invitations/${id}/hide`, 'POST', { reason }),
  restore: (id) => call(`/invitations/${id}/restore`, 'POST'),
  dismiss: (id) => call(`/invitations/${id}/dismiss`, 'POST'),
  ban: (userId) => call(`/users/${userId}/ban`, 'POST'),
  unban: (userId) => call(`/users/${userId}/unban`, 'POST'),
};
