import { adminApi } from './api';
import InvitationCard from './components/InvitationCard';
import LogRow from './components/LogRow';
import Metrics from './components/Metrics';
import UserCard from './components/UserCard';

export const SECTIONS = [
  {
    id: 'reports',
    title: 'Жалобы',
    hot: true,
    search: 'Поиск: название, автор, номер…',
    count: (d) => d.stats.reported_invitations,
    items: (d) => d.reports.filter((i) => i.reports.length),
    Card: InvitationCard,
    empty: { title: 'Жалоб нет', hint: 'Всё спокойно. Новые жалобы появятся здесь.' },
  },
  {
    id: 'hidden',
    title: 'Скрытые',
    search: 'Поиск: название, автор, номер…',
    count: (d) => d.stats.hidden,
    items: (d) => d.reports.filter((i) => i.hidden),
    Card: InvitationCard,
    empty: { title: 'Скрытых приглашений нет', hint: 'Скрытое автоматически или вручную появится здесь.' },
  },
  {
    id: 'all',
    title: 'Приглашения',
    search: 'Поиск: название, описание, автор, школа, номер…',
    count: (d) => d.stats.invitations,
    load: adminApi.invitations,
    Card: InvitationCard,
    empty: { title: 'Приглашений пока нет' },
  },
  {
    id: 'users',
    title: 'Пользователи',
    search: 'Поиск: имя, @ник, номер…',
    filters: [
      ['', 'Все'],
      ['true', 'Заблокированные'],
    ],
    count: (d) => d.stats.users,
    load: adminApi.users,
    Card: UserCard,
    empty: { title: 'Пользователей пока нет' },
  },
  {
    id: 'log',
    title: 'Журнал',
    count: () => null,
    load: adminApi.log,
    Card: LogRow,
    empty: { title: 'Действий пока не было', hint: 'Здесь появятся все решения модераторов.' },
  },
  {
    id: 'metrics',
    title: 'Показатели',
    count: () => null,
    View: Metrics,
  },
];
