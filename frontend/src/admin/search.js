const searchable = (item) => [
  item.title, item.description, item.name, item.username,
  item.author?.name, item.author?.username, item.school, item.id, item.author?.id,
];

export function matches(item, query) {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  const haystack = searchable(item)
    .filter((v) => v != null && v !== '')
    .join(' ')
    .toLowerCase();
  return haystack.includes(q);
}
