import InvitationCard from './components/InvitationCard';
import UserCard from './components/UserCard';

export const SECTIONS = [
  {
    id: 'reports',
    title: 'Жалобы',
    hot: true,
    count: (d) => d.stats.reported_invitations,
    items: (d) => d.reports.filter((i) => i.reports.length),
    Card: InvitationCard,
    empty: { title: 'Жалоб нет', hint: 'Всё спокойно. Новые жалобы появятся здесь.' },
  },
  {
    id: 'hidden',
    title: 'Скрытые',
    count: (d) => d.stats.hidden,
    items: (d) => d.reports.filter((i) => i.hidden),
    Card: InvitationCard,
    empty: { title: 'Скрытых приглашений нет', hint: 'Скрытое автоматически или вручную появится здесь.' },
  },
  {
    id: 'all',
    title: 'Все приглашения',
    count: (d) => d.stats.invitations,
    items: (d) => d.all,
    Card: InvitationCard,
    empty: { title: 'Приглашений пока нет' },
  },
  {
    id: 'banned',
    title: 'Заблокированные',
    count: (d) => d.stats.banned,
    items: (d) => d.users,
    Card: UserCard,
    empty: { title: 'Заблокированных нет' },
  },
];
