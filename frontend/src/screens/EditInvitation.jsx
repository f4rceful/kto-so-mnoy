import { api } from '../api';
import { useLoad } from '../hooks';
import { ErrorState, Loading } from '../components';
import NewInvitation from './NewInvitation';

export default function EditInvitation({ id, ...props }) {
  const { data: inv, loading, error, reload } = useLoad(() => api.detail(id), [id]);
  if (loading && !inv) return <Loading />;
  if (error) return <div className="page"><ErrorState error={error} onRetry={reload} /></div>;
  return <NewInvitation editing={inv} {...props} />;
}
