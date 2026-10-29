import { adminApi } from './api';

export function makeActions(perform) {
  return {
    hide: (item, reason) => perform('Приглашение скрыто', () => adminApi.hide(item.id, reason)),
    restore: (item) => perform('Приглашение возвращено в ленту', () => adminApi.restore(item.id)),
    dismiss: (item) => perform('Жалобы закрыты', () => adminApi.dismiss(item.id)),
    ban: (author) => perform('Автор заблокирован', () => adminApi.ban(author.id)),
    unban: (userId) => perform('Пользователь разблокирован', () => adminApi.unban(userId)),
  };
}
