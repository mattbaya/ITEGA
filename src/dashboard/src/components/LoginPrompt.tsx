/**
 * LoginPrompt.tsx -- Login / Landing Page Component
 *
 * Shown when no valid session exists. Provides two login options:
 *   1. "Log in with Home Base" -- initiates the OIDC Authorization Code Flow
 *      via the ALS, which redirects the user to their home base (Keycloak)
 *      for authentication.
 *   2. "Try Demo Mode" -- available when VITE_ALS_AUTH_URL is not configured;
 *      creates a synthetic demo session in localStorage so the dashboard
 *      can be previewed without a running backend.
 *
 * No passwords are shared with publishers -- the home base handles all
 * credential verification through the federated OIDC flow.
 */

import { login, getDemoSession } from '../api/auth';

export default function LoginPrompt() {
  const isDemo = !import.meta.env.VITE_ALS_AUTH_URL;

  const handleDemoLogin = () => {
    const demo = getDemoSession();
    localStorage.setItem('newshare_session', JSON.stringify(demo));
    window.location.href = '/dashboard';
  };

  return (
    <div className="min-h-screen bg-navy-900 flex flex-col items-center justify-center px-4">
      <div className="max-w-md w-full text-center">
        {/* Logo */}
        <div className="mb-8">
          <div className="w-16 h-16 bg-teal-500 rounded-xl flex items-center justify-center mx-auto mb-4">
            <span className="text-white font-bold text-2xl">N</span>
          </div>
          <h1 className="text-3xl font-bold text-white mb-2">
            Newshare Network
          </h1>
          <p className="text-navy-300 text-lg">User Dashboard</p>
        </div>

        {/* Login card */}
        <div className="bg-white rounded-xl shadow-xl p-8">
          <h2 className="text-xl font-semibold text-navy-900 mb-2">
            Sign in to your account
          </h2>
          <p className="text-navy-500 mb-6 text-sm">
            Log in through your home base to view your network activity,
            manage publishers, and control your privacy settings.
          </p>

          <button
            onClick={login}
            className="w-full btn-primary py-3 text-base mb-3"
          >
            Log in with Home Base
          </button>

          {isDemo && (
            <button
              onClick={handleDemoLogin}
              className="w-full btn-secondary py-3 text-base"
            >
              Try Demo Mode
            </button>
          )}

          <p className="mt-6 text-xs text-navy-400">
            Your home base authenticates you through the Account Linking
            Service. No passwords are shared with publishers.
          </p>
        </div>

        <p className="mt-6 text-navy-500 text-sm">
          A four-party federated identity network for news publishers.
        </p>
      </div>
    </div>
  );
}
