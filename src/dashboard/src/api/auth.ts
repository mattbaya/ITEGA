/**
 * auth.ts -- Newshare Network Authentication Module
 *
 * Handles OIDC-based authentication for the Newshare User Dashboard.
 * In production, the login flow works as follows:
 *   1. The user clicks "Log in with Home Base" and is redirected to the ALS
 *      OIDC authorization endpoint (Authorization Code Flow per OIDC 1.0).
 *   2. The ALS authenticates the user via their home base (Keycloak IdSP).
 *   3. The ALS redirects back with a session_token query parameter containing
 *      a signed JWT with the user's network claims (networkUserId, homeBaseId,
 *      networkGroupId, pubMbrId, etc.).
 *   4. The dashboard decodes the JWT and stores the session in localStorage.
 *
 * When VITE_ALS_AUTH_URL is not set, a demo session is used instead so that
 * the dashboard can be previewed without a running backend.
 *
 * IMPORTANT: No cookies are used. Authentication state is passed exclusively
 * via HTTP headers and signed JWT tokens, per the Newshare protocol spec.
 */

import { decodeJwt } from 'jose';

/** Base URL for the ALS authentication service. Falls back to a placeholder. */
// The dashboard is itself a registered OIDC client of the ALS.
const DASHBOARD_CLIENT_ID =
  import.meta.env.VITE_DASHBOARD_CLIENT_ID ?? 'dashboard';

const ALS_AUTH_URL =
  import.meta.env.VITE_ALS_AUTH_URL ?? 'https://als.newshare.example/auth';

/** localStorage key for the decoded session claims. */
const STORAGE_KEY = 'newshare_session';

/** Claims embedded in the ALS-issued session JWT. */
export interface SessionData {
  networkUserId: string;
  homeBaseId: string;
  networkGroupId: number;
  pubMbrId: string;
  sessionId: string;
  exp: number;
  iat?: number;
}

/**
 * Redirect the browser to the ALS OIDC authorization endpoint.
 * The ALS will authenticate the user via their home base (Keycloak)
 * and redirect back with a session_token query parameter.
 */
export function login(): void {
  const callbackUrl = `${window.location.origin}/dashboard`;
  // Authorization Code Flow (OIDC 1.0). The ALS exchanges the code with the
  // reader's home base and hands the session JWT back to the redirect URI.
  //
  // Three details this got wrong and that cost a 404: the flow lives under
  // /auth/ rather than at the host root, the ALS rejects any request from an
  // unregistered client so client_id is required, and scope is not optional.
  const params = new URLSearchParams({
    client_id: DASHBOARD_CLIENT_ID,
    redirect_uri: callbackUrl,
    response_type: 'code',
    scope: 'openid',
  });
  window.location.href = `${ALS_AUTH_URL}/auth/authorize?${params.toString()}`;
}

/**
 * Extract the session_token from URL query parameters,
 * decode the JWT, and persist the session in localStorage.
 * Returns the decoded session data or null on failure.
 */
export function handleCallback(): SessionData | null {
  // The token arrives in the URL fragment, not the query string.
  //
  // This page has no server behind it, so the exchange cannot hand the token
  // over in a POST body the way it does to a WordPress publisher -- there is
  // nothing here that can read one, and the reader simply lands on a freshly
  // loaded, signed-out page. That was the login loop Bill hit.
  //
  // A fragment is the right carrier rather than merely a convenient one: a
  // browser never transmits it, so unlike a query parameter it cannot end up
  // in an access log, a Referer header, or a proxy's history.
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const query = new URLSearchParams(window.location.search);
  const token = hash.get('session_token') ?? query.get('session_token');
  if (!token) return null;

  // Take it out of the address bar once read, so a shared or bookmarked URL
  // does not carry a live session with it.
  if (hash.get('session_token')) {
    window.history.replaceState(null, '', window.location.pathname);
  }

  try {
    // NOTE: We use decodeJwt() (decode-only, no signature verification) here
    // intentionally. This is acceptable for the prototype because:
    //   1. The dashboard only uses the token claims to display user info in the
    //      UI -- it does NOT make access-control decisions based on these claims.
    //   2. The ALS Auth Service is the trusted token issuer; in a production
    //      deployment, the dashboard SHOULD verify the JWT signature against
    //      the ALS JWKS endpoint (e.g., https://als.newshare.example/auth/.well-known/jwks.json)
    //      using jose.jwtVerify() before trusting the claims.
    //   3. Adding JWKS verification would require an async fetch and caching of
    //      the ALS public keys, which adds complexity beyond the pilot scope.
    const claims = decodeJwt(token) as unknown as SessionData;
    const session: SessionData = {
      networkUserId: claims.networkUserId,
      homeBaseId: claims.homeBaseId,
      networkGroupId: claims.networkGroupId,
      pubMbrId: claims.pubMbrId,
      sessionId: claims.sessionId,
      exp: claims.exp,
      iat: claims.iat,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    localStorage.setItem(`${STORAGE_KEY}_raw`, token);
    return session;
  } catch {
    console.error('Failed to decode session token');
    return null;
  }
}

/** Clear session data and redirect to the application root. */
export function logout(): void {
  localStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem(`${STORAGE_KEY}_raw`);
  window.location.href = '/';
}

/** Retrieve the decoded session from localStorage, or null if absent. */
export function getSession(): SessionData | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SessionData;
  } catch {
    return null;
  }
}

/** Returns true if a valid, non-expired session exists. */
export function isAuthenticated(): boolean {
  const session = getSession();
  if (!session) return false;
  const nowSec = Math.floor(Date.now() / 1000);
  return session.exp > nowSec;
}

/**
 * Return a demo session for prototype use when no real backend is available.
 * This is called automatically when VITE_ALS_AUTH_URL is not configured.
 */
export function getDemoSession(): SessionData {
  const nowSec = Math.floor(Date.now() / 1000);
  return {
    networkUserId: 'nuid-7f3a-28b1-e9c4',
    homeBaseId: 'hb-tribune-media',
    networkGroupId: 4096 | 8 | 2, // Paid + Digital Subscriber + Registered
    pubMbrId: 'pm-tribune-00142',
    sessionId: 'sess-a84c-3f19-bb02',
    exp: nowSec + 3600,
    iat: nowSec,
  };
}
