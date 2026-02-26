import { useState } from 'react';
import type { SessionData } from '../api/auth';
import { getUserProfile } from '../api/profile';
import { getPPIDList } from '../api/profile';

interface PrivacyProps {
  session: SessionData;
}

export default function Privacy({ session: _session }: PrivacyProps) {
  const profile = getUserProfile();
  const publishers = getPPIDList();

  const [privacyLevel, setPrivacyLevel] = useState(profile.privacyLevel);
  const [adPreference, setAdPreference] = useState(profile.adPreference);
  const [doNotTrack, setDoNotTrack] = useState(profile.doNotTrack);
  const [unlinked, setUnlinked] = useState<Set<string>>(new Set());

  const handleUnlink = (pubMbrId: string) => {
    setUnlinked((prev) => new Set([...prev, pubMbrId]));
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-navy-900">Privacy Controls</h1>
        <p className="text-navy-500 mt-1">
          Manage how your identity and data are shared across the network.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Privacy level */}
        <div className="card">
          <h2 className="text-lg font-semibold text-navy-900 mb-2">
            Privacy Level
          </h2>
          <p className="text-sm text-navy-500 mb-4">
            Controls how much information publishers can see about you beyond
            your PPID. Your real identity is never shared with publishers
            regardless of this setting.
          </p>
          <div className="space-y-3">
            {(['open', 'limited', 'private'] as const).map((level) => (
              <label
                key={level}
                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                  privacyLevel === level
                    ? 'border-teal-500 bg-teal-50'
                    : 'border-gray-200 hover:bg-gray-50'
                }`}
              >
                <input
                  type="radio"
                  name="privacyLevel"
                  value={level}
                  checked={privacyLevel === level}
                  onChange={() => setPrivacyLevel(level)}
                  className="mt-0.5"
                />
                <div>
                  <p className="font-medium text-navy-900 capitalize">{level}</p>
                  <p className="text-xs text-navy-500 mt-0.5">
                    {level === 'open' &&
                      'Publishers see your subscription tier and general demographics. Best for personalized content.'}
                    {level === 'limited' &&
                      'Publishers see only your subscription tier. A balanced default for most users.'}
                    {level === 'private' &&
                      'Publishers see only your PPID and access rights. Maximum privacy, minimal personalization.'}
                  </p>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Ad preferences */}
        <div className="card">
          <h2 className="text-lg font-semibold text-navy-900 mb-2">
            Advertising Preferences
          </h2>
          <p className="text-sm text-navy-500 mb-4">
            Choose how advertising is displayed when you visit network
            publishers. Reducing ads may affect your markup ratio.
          </p>
          <div className="space-y-3">
            {([
              { value: 'full' as const, label: 'Full Ads', desc: 'Standard advertising experience. May result in a lower markup ratio.' },
              { value: 'links' as const, label: 'Links Only', desc: 'Text-based ad links only. No display ads, trackers, or video ads.' },
              { value: 'none' as const, label: 'No Ads', desc: 'No advertising shown. Your markup ratio may be higher to compensate publishers.' },
            ]).map((opt) => (
              <label
                key={opt.value}
                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                  adPreference === opt.value
                    ? 'border-teal-500 bg-teal-50'
                    : 'border-gray-200 hover:bg-gray-50'
                }`}
              >
                <input
                  type="radio"
                  name="adPreference"
                  value={opt.value}
                  checked={adPreference === opt.value}
                  onChange={() => setAdPreference(opt.value)}
                  className="mt-0.5"
                />
                <div>
                  <p className="font-medium text-navy-900">{opt.label}</p>
                  <p className="text-xs text-navy-500 mt-0.5">{opt.desc}</p>
                </div>
              </label>
            ))}
          </div>

          {/* Do Not Track */}
          <div className="mt-6 pt-4 border-t border-gray-200">
            <label className="flex items-center justify-between cursor-pointer">
              <div>
                <p className="font-medium text-navy-900">Do Not Track</p>
                <p className="text-xs text-navy-500 mt-0.5">
                  Request that publishers do not track your browsing behavior
                  beyond the current session.
                </p>
              </div>
              <button
                onClick={() => setDoNotTrack(!doNotTrack)}
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  doNotTrack ? 'bg-teal-500' : 'bg-gray-300'
                }`}
                role="switch"
                aria-checked={doNotTrack}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                    doNotTrack ? 'translate-x-5' : ''
                  }`}
                />
              </button>
            </label>
          </div>
        </div>
      </div>

      {/* Unlink publishers */}
      <div className="card">
        <h2 className="text-lg font-semibold text-navy-900 mb-2">
          Unlink from Publishers
        </h2>
        <p className="text-sm text-navy-500 mb-4">
          "Disappear" from a publisher by unlinking your PPID. A new PPID will
          be generated if you visit them again, and the publisher will have no
          way to connect your old activity with your new identity. This action
          cannot be undone.
        </p>
        <div className="space-y-2">
          {publishers.map((pub) => {
            const isUnlinked = unlinked.has(pub.pubMbrId);
            return (
              <div
                key={pub.pubMbrId}
                className={`flex items-center justify-between p-3 rounded-lg border ${
                  isUnlinked
                    ? 'border-red-200 bg-red-50 opacity-60'
                    : 'border-gray-200'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 bg-navy-100 rounded-md flex items-center justify-center">
                    <span className="text-navy-600 font-bold text-xs">
                      {pub.publisherName.charAt(0)}
                    </span>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-navy-900">
                      {pub.publisherName}
                    </p>
                    <p className="text-xs font-mono text-navy-500">
                      {isUnlinked ? 'PPID unlinked' : pub.ppid}
                    </p>
                  </div>
                </div>
                {isUnlinked ? (
                  <span className="text-xs font-medium text-red-600">
                    Unlinked
                  </span>
                ) : (
                  <button
                    onClick={() => handleUnlink(pub.pubMbrId)}
                    className="text-sm text-red-600 hover:text-red-800 font-medium
                               px-3 py-1.5 border border-red-200 rounded-md
                               hover:bg-red-50 transition-colors"
                  >
                    Unlink
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Data export */}
      <div className="card">
        <h2 className="text-lg font-semibold text-navy-900 mb-2">
          Data Export
        </h2>
        <p className="text-sm text-navy-500 mb-4">
          Request a full export of your network data, including all PPIDs,
          transaction history, and privacy settings. The export will be
          delivered to your home base account.
        </p>
        <button className="btn-secondary">
          Request Data Export
        </button>
      </div>

      {/* Save button */}
      <div className="flex justify-end">
        <button className="btn-primary px-8 py-2.5">
          Save Privacy Settings
        </button>
      </div>
    </div>
  );
}
