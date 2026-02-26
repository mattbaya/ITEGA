import { decodeJwt } from 'jose';

const ALS_AUTH_URL =
  import.meta.env.VITE_ALS_AUTH_URL ?? 'https://als.newshare.example/auth';

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
  const authUrl = `${ALS_AUTH_URL}/authorize?redirect_uri=${encodeURIComponent(callbackUrl)}&response_type=token`;
  window.location.href = authUrl;
}

/**
 * Extract the session_token from URL query parameters,
 * decode the JWT, and persist the session in localStorage.
 * Returns the decoded session data or null on failure.
 */
export function handleCallback(): SessionData | null {
  const params = new URLSearchParams(window.location.search);
  const token = params.get('session_token');
  if (!token) return null;

  try {
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
