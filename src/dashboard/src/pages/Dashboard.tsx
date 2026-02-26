/**
 * Dashboard.tsx -- Main Dashboard Overview Page
 *
 * The primary landing page after authentication. Displays a summary of the
 * user's Newshare Network activity including:
 *   - Quick stats: publishers visited, articles this week, estimated charges,
 *     session expiration countdown
 *   - Network identity details (networkUserId, homeBaseId, networkGroupId)
 *   - Current session information (JWT-based, no cookies)
 *
 * All data is sourced from demo APIs in the prototype. In production, this
 * page would fetch live data from the home base and ALS services.
 */

import type { SessionData } from '../api/auth';
import { getUserProfile } from '../api/profile';
import { getPPIDList } from '../api/profile';
import { getContentEvents, computeTotals } from '../api/events';
import NetworkGroupBadge from '../components/NetworkGroupBadge';

interface DashboardProps {
  session: SessionData;
}

export default function Dashboard({ session }: DashboardProps) {
  const profile = getUserProfile();
  const publishers = getPPIDList();
  const events = getContentEvents();
  const totals = computeTotals(events);

  const expiresAt = new Date(session.exp * 1000);
  const now = new Date();
  const minutesRemaining = Math.max(
    0,
    Math.round((expiresAt.getTime() - now.getTime()) / 60000),
  );

  // Count articles this week
  const oneWeekAgo = new Date();
  oneWeekAgo.setDate(oneWeekAgo.getDate() - 7);
  const articlesThisWeek = events.filter(
    (ev) => new Date(ev.timestamp) >= oneWeekAgo,
  ).length;

  return (
    <div className="space-y-6">
      {/* Welcome header */}
      <div>
        <h1 className="text-2xl font-bold text-navy-900">
          Welcome back, {profile.displayName}
        </h1>
        <p className="text-navy-500 mt-1">
          Here is your Newshare Network activity overview.
        </p>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="card">
          <p className="text-sm font-medium text-navy-500">Publishers Visited</p>
          <p className="text-3xl font-bold text-navy-900 mt-1">
            {publishers.length}
          </p>
          <p className="text-xs text-navy-400 mt-1">
            Each with a unique PPID
          </p>
        </div>
        <div className="card">
          <p className="text-sm font-medium text-navy-500">Articles This Week</p>
          <p className="text-3xl font-bold text-navy-900 mt-1">
            {articlesThisWeek}
          </p>
          <p className="text-xs text-navy-400 mt-1">Across all publishers</p>
        </div>
        <div className="card">
          <p className="text-sm font-medium text-navy-500">
            Estimated Charges
          </p>
          <p className="text-3xl font-bold text-teal-700 mt-1">
            ${totals.retailTotal.toFixed(2)}
          </p>
          <p className="text-xs text-navy-400 mt-1">
            Wholesale: ${totals.wholesaleTotal.toFixed(2)}
          </p>
        </div>
        <div className="card">
          <p className="text-sm font-medium text-navy-500">Session Expires</p>
          <p className="text-3xl font-bold text-navy-900 mt-1">
            {minutesRemaining}m
          </p>
          <p className="text-xs text-navy-400 mt-1">
            {expiresAt.toLocaleTimeString()}
          </p>
        </div>
      </div>

      {/* Identity and session info */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Network identity */}
        <div className="card">
          <h2 className="text-lg font-semibold text-navy-900 mb-4">
            Network Identity
          </h2>
          <dl className="space-y-3">
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Network User ID</dt>
              <dd className="text-sm font-mono font-medium text-navy-800">
                {session.networkUserId}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Home Base</dt>
              <dd className="text-sm font-medium text-navy-800">
                {profile.homeBaseName}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Home Base ID</dt>
              <dd className="text-sm font-mono text-navy-600">
                {session.homeBaseId}
              </dd>
            </div>
            <div className="flex justify-between items-start">
              <dt className="text-sm text-navy-500 pt-0.5">Subscription Tier</dt>
              <dd>
                <NetworkGroupBadge groupId={session.networkGroupId} />
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Publisher Member ID</dt>
              <dd className="text-sm font-mono text-navy-600">
                {session.pubMbrId}
              </dd>
            </div>
          </dl>
        </div>

        {/* Session info */}
        <div className="card">
          <h2 className="text-lg font-semibold text-navy-900 mb-4">
            Current Session
          </h2>
          <dl className="space-y-3">
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Session ID</dt>
              <dd className="text-sm font-mono text-navy-600">
                {session.sessionId}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Expires At</dt>
              <dd className="text-sm text-navy-800">
                {expiresAt.toLocaleString()}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Time Remaining</dt>
              <dd className="text-sm font-medium text-navy-800">
                {minutesRemaining} minutes
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Privacy Level</dt>
              <dd className="text-sm font-medium text-navy-800 capitalize">
                {profile.privacyLevel}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Markup Ratio</dt>
              <dd className="text-sm font-mono text-navy-800">
                {profile.markupRatio}x
              </dd>
            </div>
          </dl>

          <div className="mt-4 p-3 bg-navy-50 rounded-md">
            <p className="text-xs text-navy-600">
              Your session was issued by the Account Linking Service (ALS) after
              authenticating through your home base. The session token is a JWT
              containing your network identity but no personal information.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
