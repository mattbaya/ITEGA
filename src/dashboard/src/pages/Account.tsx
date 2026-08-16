/**
 * Account.tsx -- Account Management Page
 *
 * Displays the user's home base information, network identity details
 * (networkUserId, networkGroupId bitmask, pubMbrId), and provides a form
 * for editing profile fields (display name, email). Also includes a
 * "Danger Zone" for account deletion.
 *
 * In this prototype, profile edits trigger a demo alert. In production,
 * updates would be sent to the home base REST API. The home base is the
 * ONLY party that stores PII -- publishers and the ALS never see it.
 */

import { useEffect, useState } from 'react';
import type { SessionData } from '../api/auth';
import { getHomeBaseName } from '../api/homebase';
import NetworkGroupBadge from '../components/NetworkGroupBadge';

interface AccountProps {
  session: SessionData;
}

export default function Account({ session }: AccountProps) {
  // Name, email and joining date are not here to be edited, because they are
  // not here at all. They live at the reader's home base and never cross into
  // the network -- that is the promise the whole architecture exists to keep,
  // and a settings form on this page would quietly break it.
  const [homeBaseName, setHomeBaseName] = useState('');
  useEffect(() => { getHomeBaseName(session.homeBaseId).then(setHomeBaseName); },
            [session.homeBaseId]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-navy-900">Account</h1>
        <p className="text-navy-500 mt-1">
          Your profile and network membership details.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Home base info */}
        <div className="card">
          <h2 className="text-lg font-semibold text-navy-900 mb-4">
            Home Base
          </h2>
          <dl className="space-y-3">
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Home Base Name</dt>
              <dd className="text-sm font-medium text-navy-800">
                {homeBaseName || session.homeBaseId}
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
          </dl>

          <div className="mt-4 p-3 bg-navy-50 rounded-md">
            <p className="text-xs text-navy-600">
              Your home base is responsible for billing, authentication, and
              managing your subscription. Contact them directly for billing
              questions or to change your subscription plan.
            </p>
          </div>
        </div>

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
              <dt className="text-sm text-navy-500">Network Group ID</dt>
              <dd className="text-sm font-mono text-navy-600">
                {session.networkGroupId} (bitmask)
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Publisher Member ID</dt>
              <dd className="text-sm font-mono text-navy-600">
                {session.pubMbrId}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Privacy Level</dt>
              <dd className="text-sm font-medium text-navy-800 capitalize">
                {'—'}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Ad Preference</dt>
              <dd className="text-sm text-navy-800 capitalize">
                Set at your home base
              </dd>
            </div>
          </dl>
        </div>
      </div>

      {/* Edit profile */}
      <div className="card">
        <h2 className="text-lg font-semibold text-navy-900 mb-4">
          Your name and email
        </h2>
        <div className="p-4 bg-navy-50 rounded-md max-w-lg">
          <p className="text-sm text-navy-700 font-medium mb-1">
            They are not shown here, and cannot be edited here.
          </p>
          <p className="text-xs text-navy-600">
            Your home base holds them and never sends them into the network.
            This dashboard sits on the far side of that boundary: it knows you
            only by an opaque identifier and a subscription tier. To change your
            details, sign in at your home base directly.
          </p>
          <p className="text-xs text-navy-600 mt-2">
            That is the point rather than a limitation &mdash; it is the same
            reason a shop can take your card without learning your bank balance.
          </p>
        </div>
      </div>

      {/* Danger zone */}
      <div className="card border-red-200">
        <h2 className="text-lg font-semibold text-red-800 mb-2">
          Danger Zone
        </h2>
        <p className="text-sm text-navy-500 mb-4">
          These actions are irreversible. Deleting your network account will
          unlink all PPIDs and remove your identity from the network.
        </p>
        <button
          className="btn-danger"
          onClick={() => {
            window.alert(
              'This feature will be available when connected to a live home base. Currently showing demo data.'
            );
          }}
        >
          Delete Network Account
        </button>
      </div>
    </div>
  );
}
