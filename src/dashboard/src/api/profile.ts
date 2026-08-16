/**
 * profile.ts -- the signed-in reader, as far as this page is permitted to know
 *
 * Provides hardcoded demo user profile and PPID (Pairwise Pseudonymous
 * Identifier) data that simulates what the home base API would return in
 * production.
 *
 * Key concept: Each publisher gets a DIFFERENT pseudonymous identifier (PPID)
 * for the same user. This is a core privacy feature of the Newshare Network
 * architecture -- it makes cross-site user correlation architecturally
 * impossible without home base cooperation. The PPID list below demonstrates
 * this by showing five distinct PPIDs for five different publishers, all
 * belonging to the same user.
 *
 * In production, profile data is fetched from the home base REST API.
 * PII (email, display name) NEVER leaves the home base -- it is only shown
 * in this dashboard because the dashboard is served by the home base itself.
 */

import { getSession } from './auth';

/** What the session token actually says about the reader. Nothing more. */
export interface UserProfile {
  networkUserId: string;
  homeBaseId: string;
  networkGroupId: number;
  sessionId: string;
  exp: number;
}

/** Per-publisher pseudonymous ID record. */
export interface PPIDRecord {
  publisherName: string;
  publisherDomain: string;
  pubMbrId: string;
  ppid: string;
  articlesAccessed: number;
  lastVisit: string;
}

/**
 * The signed-in reader, built from their own session token.
 *
 * There is no name here, and that is not an omission. The token carries a
 * pairwise identifier, a tier and a home base, and no personal information at
 * all -- the architecture's central promise is that a reader's name never
 * leaves their home base, and this page is on the far side of that line.
 *
 * This function used to return "Alex Morgan of Tribune Media Group" with a
 * membership date and a markup ratio, none of which had any connection to
 * whoever was actually signed in. Real session values sat beside invented ones
 * with nothing marking which was which, on a system whose whole argument is
 * that it is running rather than simulated.
 */
export function getUserProfile(): UserProfile | null {
  const session = getSession();
  if (!session) return null;
  return {
    networkUserId: session.networkUserId,
    homeBaseId: session.homeBaseId,
    networkGroupId: session.networkGroupId,
    sessionId: session.sessionId,
    exp: session.exp,
  };
}

/**
 * The reader's identifiers at each publisher.
 *
 * Deliberately empty. A pairwise identifier is minted by the home base for one
 * publisher, and is never handed to anybody else -- so this page can only ever
 * know the one issued for itself. The invented list of five that used to sit
 * here demonstrated the idea by contradicting it.
 *
 * Showing a reader their own identifiers is a legitimate feature; it belongs at
 * the home base, which is the only party that holds them all.
 */
export function getPPIDList(): PPIDRecord[] {
  return [];
}
