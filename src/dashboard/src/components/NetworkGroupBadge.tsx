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
