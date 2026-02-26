/** User profile as returned by the home base API. */
export interface UserProfile {
  networkUserId: string;
  displayName: string;
  email: string;
  homeBaseName: string;
  homeBaseId: string;
  memberSince: string;
  markupRatio: number;
  privacyLevel: 'open' | 'limited' | 'private';
  adPreference: 'full' | 'links' | 'none';
  doNotTrack: boolean;
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
 * Return demo user profile data.
 * In production this calls the home base REST API.
 */
export function getUserProfile(): UserProfile {
  return {
    networkUserId: 'nuid-7f3a-28b1-e9c4',
    displayName: 'Alex Morgan',
    email: 'alex.morgan@example.com',
    homeBaseName: 'Tribune Media Group',
    homeBaseId: 'hb-tribune-media',
    memberSince: '2024-03-15',
    markupRatio: 1.35,
    privacyLevel: 'limited',
    adPreference: 'links',
    doNotTrack: false,
  };
}

/**
 * Return the list of PPIDs issued to this user across publishers.
 * Each publisher sees a different pseudonymous identifier.
 */
export function getPPIDList(): PPIDRecord[] {
  return [
    {
      publisherName: 'Metro Daily News',
      publisherDomain: 'metrodailynews.com',
      pubMbrId: 'pm-metro-00891',
      ppid: 'ppid-8a3f-d921-4c0e-bb17',
      articlesAccessed: 47,
      lastVisit: '2026-02-24T18:32:00Z',
    },
    {
      publisherName: 'Pacific Herald',
      publisherDomain: 'pacificherald.com',
      pubMbrId: 'pm-pacific-00234',
      ppid: 'ppid-1b7c-e043-9f8a-22d5',
      articlesAccessed: 23,
      lastVisit: '2026-02-24T14:15:00Z',
    },
    {
      publisherName: 'The National Review',
      publisherDomain: 'nationalreview.example',
      pubMbrId: 'pm-natrv-00567',
      ppid: 'ppid-5e9d-a782-3b16-cc40',
      articlesAccessed: 12,
      lastVisit: '2026-02-23T09:42:00Z',
    },
    {
      publisherName: 'TechWire Journal',
      publisherDomain: 'techwirejournal.com',
      pubMbrId: 'pm-twj-01102',
      ppid: 'ppid-c4f1-6823-ae57-1199',
      articlesAccessed: 8,
      lastVisit: '2026-02-22T20:05:00Z',
    },
    {
      publisherName: 'Coastal Times',
      publisherDomain: 'coastaltimes.com',
      pubMbrId: 'pm-coast-00078',
      ppid: 'ppid-92a0-bb14-7de3-5f68',
      articlesAccessed: 3,
      lastVisit: '2026-02-20T11:28:00Z',
    },
  ];
}
