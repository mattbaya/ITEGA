/**
 * Publishers.tsx -- Publisher Relationships Page
 *
 * Displays the list of publishers that the current user has visited on the
 * Newshare Network, along with the unique Pairwise Pseudonymous Identifier
 * (PPID) assigned to the user at each publisher. This page demonstrates a
 * core privacy feature: each publisher sees a completely different opaque ID,
 * making cross-site correlation architecturally impossible.
 */

import type { SessionData } from '../api/auth';
import { getPPIDList } from '../api/profile';

interface PublishersProps {
  session: SessionData;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function Publishers({ session: _session }: PublishersProps) {
  const publishers = getPPIDList();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-navy-900">Publishers</h1>
        <p className="text-navy-500 mt-1">
          Publishers you have visited on the Newshare Network.
        </p>
      </div>

      {/* Privacy callout */}
      <div className="bg-teal-50 border border-teal-200 rounded-lg p-5">
        <div className="flex gap-3">
          <div className="w-10 h-10 bg-teal-100 rounded-full flex items-center justify-center flex-shrink-0">
            <svg
              className="w-5 h-5 text-teal-700"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
              />
            </svg>
          </div>
          <div>
            <h3 className="font-semibold text-teal-900">
              Your identity is protected across publishers
            </h3>
            <p className="text-sm text-teal-800 mt-1">
              Only your home base knows your real identity. The ALS and
              publishers only see pseudonymous identifiers. Each publisher
              gets a different ID, making cross-site tracking architecturally
              impossible without home base cooperation.
            </p>
          </div>
        </div>
      </div>

      {/* Publisher list */}
      <div className="space-y-4">
        {publishers.map((pub) => (
          <div
            key={pub.pubMbrId}
            className="card hover:shadow-md transition-shadow duration-150"
          >
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
              {/* Publisher info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-navy-100 rounded-lg flex items-center justify-center flex-shrink-0">
                    <span className="text-navy-600 font-bold text-sm">
                      {pub.publisherName.charAt(0)}
                    </span>
                  </div>
                  <div>
                    <h3 className="font-semibold text-navy-900">
                      {pub.publisherName}
                    </h3>
                    <p className="text-sm text-navy-500">{pub.publisherDomain}</p>
                  </div>
                </div>
              </div>

              {/* PPID display */}
              <div className="lg:text-right">
                <p className="text-xs font-medium text-navy-500 uppercase tracking-wide">
                  Your PPID at this publisher
                </p>
                <p className="font-mono text-sm text-navy-800 bg-navy-50 px-3 py-1.5 rounded-md mt-1 inline-block">
                  {pub.ppid}
                </p>
              </div>
            </div>

            {/* Stats row */}
            <div className="mt-4 pt-4 border-t border-gray-100 flex flex-wrap gap-6 text-sm">
              <div>
                <span className="text-navy-500">Publisher Member ID: </span>
                <span className="font-mono text-navy-700">{pub.pubMbrId}</span>
              </div>
              <div>
                <span className="text-navy-500">Articles accessed: </span>
                <span className="font-semibold text-navy-800">
                  {pub.articlesAccessed}
                </span>
              </div>
              <div>
                <span className="text-navy-500">Last visit: </span>
                <span className="text-navy-700">{formatDate(pub.lastVisit)}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Summary */}
      <div className="text-center text-sm text-navy-500 py-4">
        {publishers.length} publishers visited with{' '}
        {publishers.length} unique PPIDs issued.
        Each publisher sees a completely independent identity.
      </div>
    </div>
  );
}
