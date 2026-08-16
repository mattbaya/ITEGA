/**
 * events.ts -- Demo Event Data for the Newshare User Dashboard
 *
 * Provides hardcoded demo content-access events that simulate what the ALS
 * Logging Service would return in production. Each event represents an article
 * access logged by the ALS with wholesale pricing (pageClass) set by the
 * publisher and a retail markup (markupRatio) applied by the user's home base.
 *
 * Event type enums follow the Newshare protocol spec:
 *   - content_access  -- user accessed a piece of content
 *   - ad_view         -- an ad impression was served
 *   - subscription_credit -- credit applied from a subscription
 *   - reward          -- reward/loyalty credit
 *   - authentication  -- login event
 *   - logout          -- logout event
 *
 * In production, events would be fetched from the ALS Logging Service
 * (TimescaleDB) via the home base proxy, filtered by the user's
 * networkUserId.
 */

/** A content access event logged by the ALS. */
export interface ContentEvent {
  eventId: string;
  timestamp: string;
  publisherName: string;
  articleTitle: string;
  articleUrl: string;
  /** Wholesale price set by the publisher for this page/article. */
  pageClass: number;
  /** Retail markup ratio applied by the user's home base. */
  markupRatio: number;
  /**
   * Event type enum per the Newshare protocol spec.
   * - content_access: user viewed/accessed content
   * - ad_view: an ad impression was logged
   * - subscription_credit: a subscription offset was applied
   * - reward: a reward/loyalty credit was applied
   * - authentication: user authenticated to the network
   * - logout: user logged out
   */
  eventType: 'content_access' | 'ad_view' | 'subscription_credit' | 'reward' | 'authentication' | 'logout';
}

const LOGGING_URL =
  import.meta.env.VITE_LOGGING_URL ?? 'https://als.itega.org';

/**
 * This reader's own record, from the logging service.
 *
 * Authenticated by the reader's own session token rather than an API key: a
 * key belonging to the network cannot be handed to a browser, and this asks
 * about exactly one reader, who is already holding a signed token naming
 * themselves. The service takes the identifier from inside the token, so there
 * is no way to ask it about anybody else.
 *
 * This used to return seven invented purchases at newspapers that do not
 * exist. A reader looking at their own spending is precisely the wrong place
 * to show them fiction.
 */
export async function getContentEvents(): Promise<ContentEvent[]> {
  const raw = localStorage.getItem('newshare_session_raw');
  if (!raw) return [];

  try {
    const resp = await fetch(`${LOGGING_URL}/log/report/me`, {
      headers: { Authorization: `Bearer ${raw}` },
    });
    if (!resp.ok) return [];
    const data = await resp.json();
    return (data.events ?? []).map((e: Record<string, unknown>, i: number) => ({
      eventId: `ev-${i}`,
      timestamp: String(e.timestamp ?? ''),
      publisherName: String(e.pubMbrId ?? ''),
      articleTitle: String(e.resourceId ?? ''),
      articleUrl: String(e.resourceId ?? ''),
      pageClass: Number(e.wholesale ?? 0),
      markupRatio: Number(e.markupRatio ?? 1),
      eventType: (e.eventType ?? 'content_access') as ContentEvent['eventType'],
    }));
  } catch {
    // An unreachable logging service means we do not know what they read. It
    // does not mean they read nothing, and it certainly does not mean we may
    // invent something. Show an empty table and let the page say why.
    return [];
  }
}

export function computeTotals(events: ContentEvent[]): {
  wholesaleTotal: number;
  retailTotal: number;
  eventCount: number;
} {
  let wholesaleTotal = 0;
  let retailTotal = 0;
  for (const ev of events) {
    wholesaleTotal += ev.pageClass;
    retailTotal += ev.pageClass * ev.markupRatio;
  }
  return {
    wholesaleTotal: Math.round(wholesaleTotal * 100) / 100,
    retailTotal: Math.round(retailTotal * 100) / 100,
    eventCount: events.length,
  };
}
