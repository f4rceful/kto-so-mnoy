import { adminApi } from './api';

export const unbanned = (result) => (result?.restored ? `Пользователь разблокирован, приглашений возвращено: ${result.restored}` : 'Пользователь разблокирован');

export function makeActions(perform) {
  return {
    hide: (item, reason) => perform('Приглашение скрыто', () => adminApi.hide(item.id, reason)),
    restore: (item) => perform('Приглашение возвращено в ленту', () => adminApi.restore(item.id)),
    dismiss: (item) => perform('Жалобы закрыты', () => adminApi.dismiss(item.id)),
    ban: (author, reason, days) => perform('Пользователь заблокирован', () => adminApi.ban(author.id, reason, days)),
    unban: (userId) => perform(unbanned, () => adminApi.unban(userId)),
  };
}
