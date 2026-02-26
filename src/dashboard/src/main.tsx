/**
 * main.tsx -- Application Entry Point
 *
 * Bootstraps the React 19 application by rendering the root App component
 * inside React.StrictMode and BrowserRouter. The BrowserRouter is required
 * for client-side routing (React Router v7). CSS is loaded via index.css
 * which includes Tailwind CSS directives.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
