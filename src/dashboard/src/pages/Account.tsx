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

import { useState } from 'react';
import type { SessionData } from '../api/auth';
import { getUserProfile } from '../api/profile';
import NetworkGroupBadge from '../components/NetworkGroupBadge';

interface AccountProps {
  session: SessionData;
}

export default function Account({ session }: AccountProps) {
  const profile = getUserProfile();
  const [displayName, setDisplayName] = useState(profile.displayName);
  const [email, setEmail] = useState(profile.email);

  const memberSinceDate = new Date(profile.memberSince).toLocaleDateString(
    'en-US',
    { year: 'numeric', month: 'long', day: 'numeric' },
  );

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
                {profile.homeBaseName}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Home Base ID</dt>
              <dd className="text-sm font-mono text-navy-600">
                {profile.homeBaseId}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Member Since</dt>
              <dd className="text-sm text-navy-800">{memberSinceDate}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Markup Ratio</dt>
              <dd className="text-sm font-mono font-medium text-navy-800">
                {profile.markupRatio}x
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
                {profile.privacyLevel}
              </dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-sm text-navy-500">Ad Preference</dt>
              <dd className="text-sm text-navy-800 capitalize">
                {profile.adPreference === 'full'
                  ? 'Full Ads'
                  : profile.adPreference === 'links'
                    ? 'Links Only'
                    : 'No Ads'}
              </dd>
            </div>
          </dl>
        </div>
      </div>

      {/* Edit profile */}
      <div className="card">
        <h2 className="text-lg font-semibold text-navy-900 mb-4">
          Edit Profile
        </h2>
        <p className="text-sm text-navy-500 mb-4">
          These preferences are stored at your home base and are not shared
          with publishers.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            alert('Profile update would be sent to home base API in production.');
          }}
          className="space-y-4 max-w-lg"
        >
          <div>
            <label
              htmlFor="displayName"
              className="block text-sm font-medium text-navy-700 mb-1"
            >
              Display Name
            </label>
            <input
              id="displayName"
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm
                         focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
            />
          </div>
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-navy-700 mb-1"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm
                         focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-teal-500"
            />
            <p className="text-xs text-navy-400 mt-1">
              Your email is stored at your home base only.
            </p>
          </div>
          <div className="pt-2">
            <button type="submit" className="btn-primary">
              Update Profile
            </button>
          </div>
        </form>
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
