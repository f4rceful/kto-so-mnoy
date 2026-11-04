import { useState } from 'react';
import { AuthError, adminApi } from '../api';
import { useToast } from '../toasts';
import InvitationEditor from './InvitationEditor';
import Modal from './Modal';

export default function EditInvitationDialog({ item, onClose, onChanged, onAuthError }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  const save = async (patch) => {
    setBusy(true);
    try {
      await adminApi.editInvitation(item.id, patch);
      toast('Приглашение исправлено');
      onChanged();
      onClose();
    } catch (e) {
      setBusy(false);
      if (e instanceof AuthError) onAuthError(e.message);
      else toast(e.message, 'bad');
    }
  };

  return (
    <Modal title={`Изменить приглашение №${item.id}`} onClose={onClose}>
      <InvitationEditor item={item} busy={busy} onSave={save} onCancel={onClose} />
    </Modal>
  );
}
