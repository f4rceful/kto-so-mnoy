import Dialog from './Dialog';

export default function BanDialog({ author, onConfirm, onCancel }) {
  return (
    <Dialog
      title="Заблокировать автора?"
      text={`${author.name || 'Пользователь'} (id ${author.id}) потеряет доступ к сервису, все его приглашения будут скрыты. Разблокировать можно во вкладке «Заблокированные», но приглашения придётся возвращать по одному.`}
      confirmLabel="Заблокировать"
      danger
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}
