/** A content access event logged by the ALS. */
export interface ContentEvent {
  eventId: string;
  timestamp: string;
  publisherName: string;
  articleTitle: string;
  articleUrl: string;
  pageClass: number;
  markupRatio: number;
  eventType: 'page_view' | 'paywall_pass' | 'metered_access' | 'free_access';
}

/**
 * Fetch content access events for the current user.
 * In production this calls the ALS logging service through a home base proxy.
 * Returns demo data for the prototype.
 */
export function getContentEvents(): ContentEvent[] {
  return [
    {
      eventId: 'ev-001',
      timestamp: '2026-02-24T18:32:00Z',
      publisherName: 'Metro Daily News',
      articleTitle: 'City Council Approves New Transit Plan',
      articleUrl: 'https://metrodailynews.com/city-council-transit-2026',
      pageClass: 0.03,
      markupRatio: 1.35,
      eventType: 'paywall_pass',
    },
    {
      eventId: 'ev-002',
      timestamp: '2026-02-24T17:10:00Z',
      publisherName: 'Metro Daily News',
      articleTitle: 'Weather: Storm System Approaching This Weekend',
      articleUrl: 'https://metrodailynews.com/weather-storm-feb-2026',
      pageClass: 0.01,
      markupRatio: 1.35,
      eventType: 'free_access',
    },
    {
      eventId: 'ev-003',
      timestamp: '2026-02-24T14:15:00Z',
      publisherName: 'Pacific Herald',
      articleTitle: 'Tech Giants Report Q4 Earnings Above Expectations',
      articleUrl: 'https://pacificherald.com/tech-q4-earnings',
      pageClass: 0.05,
      markupRatio: 1.35,
      eventType: 'paywall_pass',
    },
    {
      eventId: 'ev-004',
      timestamp: '2026-02-23T09:42:00Z',
      publisherName: 'The National Review',
      articleTitle: 'Analysis: Federal Reserve Signals on Interest Rates',
      articleUrl: 'https://nationalreview.example/fed-rates-analysis',
      pageClass: 0.08,
      markupRatio: 1.35,
      eventType: 'paywall_pass',
    },
    {
      eventId: 'ev-005',
      timestamp: '2026-02-22T20:05:00Z',
      publisherName: 'TechWire Journal',
      articleTitle: 'Open Source AI Models Reshape Enterprise Software',
      articleUrl: 'https://techwirejournal.com/open-source-ai-enterprise',
      pageClass: 0.04,
      markupRatio: 1.35,
      eventType: 'metered_access',
    },
    {
      eventId: 'ev-006',
      timestamp: '2026-02-22T15:30:00Z',
      publisherName: 'Metro Daily News',
      articleTitle: 'Local Schools Receive State Innovation Grants',
      articleUrl: 'https://metrodailynews.com/schools-innovation-grants',
      pageClass: 0.03,
      markupRatio: 1.35,
      eventType: 'paywall_pass',
    },
    {
      eventId: 'ev-007',
      timestamp: '2026-02-21T08:20:00Z',
      publisherName: 'Pacific Herald',
      articleTitle: 'West Coast Housing Market Shows Signs of Cooling',
      articleUrl: 'https://pacificherald.com/housing-market-cooling',
      pageClass: 0.05,
      markupRatio: 1.35,
      eventType: 'paywall_pass',
    },
    {
      eventId: 'ev-008',
      timestamp: '2026-02-20T11:28:00Z',
      publisherName: 'Coastal Times',
      articleTitle: 'Marine Sanctuary Expansion Approved Unanimously',
      articleUrl: 'https://coastaltimes.com/marine-sanctuary-expansion',
      pageClass: 0.02,
      markupRatio: 1.35,
      eventType: 'metered_access',
    },
    {
      eventId: 'ev-009',
      timestamp: '2026-02-19T16:45:00Z',
      publisherName: 'The National Review',
      articleTitle: 'Opinion: The Future of Digital Privacy Legislation',
      articleUrl: 'https://nationalreview.example/digital-privacy-future',
      pageClass: 0.08,
      markupRatio: 1.35,
      eventType: 'paywall_pass',
    },
    {
      eventId: 'ev-010',
      timestamp: '2026-02-19T10:12:00Z',
      publisherName: 'Metro Daily News',
      articleTitle: 'Restaurant Week Returns With 40 New Participants',
      articleUrl: 'https://metrodailynews.com/restaurant-week-2026',
      pageClass: 0.01,
      markupRatio: 1.35,
      eventType: 'free_access',
    },
  ];
}

/** Compute the total wholesale and retail costs for a list of events. */
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
