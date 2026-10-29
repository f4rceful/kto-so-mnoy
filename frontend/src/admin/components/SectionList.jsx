import { matches } from '../search';
import Empty from './Empty';

export default function SectionList({ section, data, query, actions, ask }) {
  const all = section.items(data);
  const found = all.filter((item) => matches(item, query));
  const Card = section.Card;

  if (found.length) {
    return found.map((item) => <Card key={`${section.id}-${item.id}`} item={item} actions={actions} ask={ask} />);
  }
  if (query.trim() && all.length) return <Empty title="Ничего не найдено" hint="Попробуйте другой запрос." />;
  return <Empty {...section.empty} />;
}
