/**
 * TransactionTable.tsx -- Content Access Event Table Component
 *
 * Renders a responsive table of content access events showing timestamp,
 * publisher, article title (linked), wholesale cost (pageClass), retail
 * cost (pageClass * markupRatio), and event type badge. Used on the
 * Transactions page to display the user's reading history across all
 * Newshare Network publishers.
 */

import type { ContentEvent } from '../api/events';

interface TransactionTableProps {
  events: ContentEvent[];
}

/**
 * Maps spec-compliant event type enums to human-readable labels and
 * Tailwind badge color classes for display in the transaction table.
 */
const EVENT_TYPE_LABELS: Record<string, { label: string; className: string }> = {
  content_access: { label: 'Content', className: 'bg-green-100 text-green-700' },
  ad_view: { label: 'Ad View', className: 'bg-blue-100 text-blue-700' },
  subscription_credit: { label: 'Sub Credit', className: 'bg-amber-100 text-amber-700' },
  reward: { label: 'Reward', className: 'bg-purple-100 text-purple-700' },
  authentication: { label: 'Auth', className: 'bg-gray-100 text-gray-700' },
  logout: { label: 'Logout', className: 'bg-gray-100 text-gray-600' },
};

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function TransactionTable({ events }: TransactionTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-navy-600">
            <th className="pb-3 pr-4 font-semibold">Time</th>
            <th className="pb-3 pr-4 font-semibold">Publisher</th>
            <th className="pb-3 pr-4 font-semibold">Article</th>
            <th className="pb-3 pr-4 font-semibold text-right">Wholesale</th>
            <th className="pb-3 pr-4 font-semibold text-right">Retail</th>
            <th className="pb-3 font-semibold">Type</th>
          </tr>
        </thead>
        <tbody>
          {events.map((ev) => {
            const typeInfo = EVENT_TYPE_LABELS[ev.eventType] ?? EVENT_TYPE_LABELS.content_access;
            return (
              <tr
                key={ev.eventId}
                className="border-b border-gray-100 hover:bg-gray-50 transition-colors"
              >
                <td className="py-3 pr-4 text-navy-500 whitespace-nowrap">
                  {formatTimestamp(ev.timestamp)}
                </td>
                <td className="py-3 pr-4 font-medium text-navy-800 whitespace-nowrap">
                  {ev.publisherName}
                </td>
                <td className="py-3 pr-4 text-navy-700 max-w-xs truncate">
                  <a
                    href={ev.articleUrl}
                    className="hover:text-teal-700 hover:underline"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {ev.articleTitle}
                  </a>
                </td>
                <td className="py-3 pr-4 text-right font-mono text-navy-600">
                  ${ev.pageClass.toFixed(2)}
                </td>
                <td className="py-3 pr-4 text-right font-mono text-navy-800 font-medium">
                  ${(ev.pageClass * ev.markupRatio).toFixed(2)}
                </td>
                <td className="py-3">
                  <span className={`badge ${typeInfo.className}`}>
                    {typeInfo.label}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
