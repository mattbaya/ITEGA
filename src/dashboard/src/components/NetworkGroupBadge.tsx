/**
 * NetworkGroupBadge.tsx -- Subscription Tier Badge Component
 *
 * Decodes a NetworkGroupId bitmask into a set of colored badges, one per
 * active bit. The NetworkGroupId is a custom claim in the OIDC ID Token
 * that encodes subscription attributes as a bitmask (e.g., bit 2 =
 * Registered, bit 8 = Digital Subscriber, bit 4096 = Paid). Multiple
 * bits can be set simultaneously, and each is rendered as a separate
 * badge with a distinct color.
 */

import { decodeBitmaskWithBits, BIT_COLORS } from '../utils/networkGroupId';

interface NetworkGroupBadgeProps {
  groupId: number;
}

export default function NetworkGroupBadge({ groupId }: NetworkGroupBadgeProps) {
  const entries = decodeBitmaskWithBits(groupId);

  if (entries.length === 0) {
    return <span className="badge bg-gray-100 text-gray-600">Unknown</span>;
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.map(({ bit, label }) => (
        <span
          key={bit}
          className={`badge ${BIT_COLORS[bit] ?? 'bg-gray-100 text-gray-800'}`}
        >
          {label}
        </span>
      ))}
    </div>
  );
}
