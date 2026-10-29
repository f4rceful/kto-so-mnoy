import { createRoot } from 'react-dom/client';
import { MaxUI, SnackbarProvider } from '@maxhub/max-ui';
import '@maxhub/max-ui/dist/styles.css';
import './app.css';
import App from './App.jsx';

createRoot(document.getElementById('root')).render(
  <MaxUI resetBody className="app-root">
    <SnackbarProvider defaultPlacement="bottom-center">
      <div className="shell">
        <App />
      </div>
    </SnackbarProvider>
  </MaxUI>,
);
