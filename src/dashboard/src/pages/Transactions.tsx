/**
 * Transactions.tsx -- Transaction History Page
 *
 * Displays the user's content access history and associated charges across
 * all Newshare Network publishers. Shows both wholesale costs (pageClass,
 * set by publishers) and retail costs (pageClass * markupRatio, what the
 * user pays through their home base).
 *
 * Includes a pricing explanation and running totals. In production, events
 * would be fetched from the ALS Logging Service (TimescaleDB).
 */

import { getContentEvents, computeTotals } from '../api/events';
import TransactionTable from '../components/TransactionTable';

export default function Transactions() {
  const events = getContentEvents();
  const totals = computeTotals(events);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-navy-900">Transactions</h1>
        <p className="text-navy-500 mt-1">
          Your content access history and associated charges.
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="card">
          <p className="text-sm font-medium text-navy-500">Total Events</p>
          <p className="text-2xl font-bold text-navy-900 mt-1">
            {totals.eventCount}
          </p>
        </div>
        <div className="card">
          <p className="text-sm font-medium text-navy-500">
            Wholesale Total (pageClass)
          </p>
          <p className="text-2xl font-bold text-navy-900 mt-1">
            ${totals.wholesaleTotal.toFixed(2)}
          </p>
          <p className="text-xs text-navy-400 mt-1">
            Base price set by publishers
          </p>
        </div>
        <div className="card">
          <p className="text-sm font-medium text-navy-500">
            Retail Total (your cost)
          </p>
          <p className="text-2xl font-bold text-teal-700 mt-1">
            ${totals.retailTotal.toFixed(2)}
          </p>
          <p className="text-xs text-navy-400 mt-1">
            pageClass x markupRatio (1.35x)
          </p>
        </div>
      </div>

      {/* Explanation */}
      <div className="bg-navy-50 border border-navy-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-navy-800 mb-1">
          How pricing works
        </h3>
        <p className="text-sm text-navy-600">
          Each article has a wholesale price (pageClass) set by the publisher.
          Your home base applies a markup ratio to cover network costs and its
          own services, resulting in your retail price. Free and metered content
          may carry a nominal or zero charge depending on the publisher's
          configuration.
        </p>
      </div>

      {/* Transaction table */}
      <div className="card">
        <h2 className="text-lg font-semibold text-navy-900 mb-4">
          Recent Transactions
        </h2>
        <TransactionTable events={events} />
      </div>

      {/* Running totals footer */}
      <div className="card bg-navy-900 text-white">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h3 className="font-semibold text-lg">Running Total</h3>
            <p className="text-navy-300 text-sm">
              {totals.eventCount} transactions across {new Set(events.map((e) => e.publisherName)).size} publishers
            </p>
          </div>
          <div className="text-right">
            <p className="text-sm text-navy-300">Your estimated total</p>
            <p className="text-3xl font-bold text-teal-400">
              ${totals.retailTotal.toFixed(2)}
            </p>
            <p className="text-xs text-navy-400">
              Wholesale: ${totals.wholesaleTotal.toFixed(2)}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
