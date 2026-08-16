/**
 * App.tsx -- Root Application Component with Routing and OIDC Callback Handling
 *
 * Manages top-level application state (authentication session) and provides
 * client-side routing via React Router. On mount, the component checks for:
 *   1. A session_token query parameter (indicates returning from OIDC login
 *      via the ALS) -- if found, decodes the JWT and stores the session.
 *   2. An existing valid session in localStorage -- if found, restores it.
 *
 * If no valid session exists, the LoginPrompt is shown. Otherwise, the
 * authenticated layout (Header + page routes) is rendered.
 *
 * Routes:
 *   /            -> redirects to /dashboard
 *   /demo        -> Step-through demonstration of the network (Aug 25 roundtable)
 *   /dashboard   -> Dashboard overview
 *   /publishers  -> Publisher PPID list
 *   /transactions -> Content access history
 *   /privacy     -> Privacy controls
 *   /account     -> Account management
 */

import { Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import Header from './components/Header';
import LoginPrompt from './components/LoginPrompt';
import Dashboard from './pages/Dashboard';
import Demo from './pages/Demo';
import Publishers from './pages/Publishers';
import Transactions from './pages/Transactions';
import Privacy from './pages/Privacy';
import Account from './pages/Account';
import { getSession, handleCallback, isAuthenticated } from './api/auth';
import type { SessionData } from './api/auth';

export default function App() {
  const [session, setSession] = useState<SessionData | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    // Returning from sign-in? Ask handleCallback, rather than guessing here
    // where the token might be.
    //
    // This used to test window.location.search for a session_token before
    // bothering to call it. When the hand-off moved to the URL fragment --
    // which a static page must use, because it has no server to receive a POST
    // -- the guard went on inspecting the query string, found nothing, and
    // never called the handler at all. The token arrived correctly and was
    // ignored, and the reader was returned to the login screen.
    //
    // One place decides where the token lives, and it is handleCallback.
    const result = handleCallback();
    if (result) {
      setSession(result);
    } else if (isAuthenticated()) {
      setSession(getSession());
    }
    setChecked(true);
  }, []);

  if (!checked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-navy-500 text-lg">Loading...</p>
      </div>
    );
  }

  // The walkthrough explains how the network works and shows nobody's personal
  // data, so it sits outside the sign-in gate: it has to be presentable to a
  // room, and linkable to people who have no account and are being persuaded
  // to want one.
  if (!session) {
    return (
      <Routes>
        <Route
          path="/demo"
          element={
            <div className="min-h-screen bg-gray-50">
              <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <Demo />
              </main>
            </div>
          }
        />
        <Route path="*" element={<LoginPrompt />} />
      </Routes>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header session={session} onLogout={() => setSession(null)} />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/demo" element={<Demo />} />
          <Route path="/dashboard" element={<Dashboard session={session} />} />
          <Route path="/publishers" element={<Publishers session={session} />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/privacy" element={<Privacy session={session} />} />
          <Route path="/account" element={<Account session={session} />} />
        </Routes>
      </main>
    </div>
  );
}
