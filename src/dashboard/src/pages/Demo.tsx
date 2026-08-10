/**
 * Demo.tsx -- Step-through demonstration of the Newshare Network.
 *
 * Built for the Aug 25 RJI/ITEGA roundtable. It walks an audience through what
 * happens when a reader who has never visited a publisher reads one of its
 * articles, and narrates the exchanges that normally happen invisibly in the
 * background.
 *
 * Two things drive the design:
 *
 *   1. **It runs the real thing.** Each step calls the actual services and
 *      shows the actual responses. Where a service is unreachable it says so
 *      rather than substituting canned data -- the claim being made to a room
 *      of publishers is that this works, and a demo that fakes its way past an
 *      outage would quietly undermine that.
 *
 *   2. **Presenter-paced.** One step at a time, advanced by hand, because Bill
 *      is talking over it. Nothing animates on a timer.
 *
 * The closing steps cover what is logged where, and the wholesale-retail
 * markup -- the part of the model most likely to draw hard questions.
 */

import { useState } from 'react';
import {
  fetchAgentPolicy,
  fetchHomeBases,
  requestQuote,
  resolveHomeBase,
  verifyAiAgent,
  type CallResult,
} from '../api/demo';

/** One step of the walkthrough. */
interface Step {
  /** Short title shown in the progress rail. */
  title: string;
  /** Which party is acting, for the four-party diagram. */
  actor: 'reader' | 'publisher' | 'homebase' | 'itega';
  /** What the audience is being shown. */
  narration: string;
  /** What is happening underneath, that a reader would never see. */
  background?: string;
  /** Live call to run when the step is opened, if any. */
  run?: () => Promise<CallResult>;
}

const PARTIES = {
  reader: { label: 'Reader', color: 'bg-navy-600' },
  publisher: { label: 'Publisher B', color: 'bg-teal-600' },
  homebase: { label: 'Home Base (Publisher C)', color: 'bg-navy-800' },
  itega: { label: 'ITEGA', color: 'bg-teal-800' },
} as const;

const STEPS: Step[] = [
  {
    title: 'A reader follows a link',
    actor: 'reader',
    narration:
      'Susan has an account with Publisher C — her home base — and no account at Publisher B. She follows a link to a Publisher B article.',
    background:
      'Nothing has happened yet. Publisher B does not know who she is, and will not find out.',
  },
  {
    title: 'The paywall does not recognise her',
    actor: 'publisher',
    narration:
      'Publisher B offers her its own subscription, and — because it is an ITEGA member — the option to sign in through the network instead.',
    background:
      'The publisher keeps its existing paywall. Joining the network adds an option; it replaces nothing.',
  },
  {
    title: 'ITEGA finds her home base',
    actor: 'itega',
    narration:
      'She chooses the network. The Authenticator asks who her home base is; she names it, or picks it from the certified list.',
    background:
      'These are the home bases ITEGA currently certifies. A suspended member disappears from this list, and from the network, without redeploying anything.',
    run: fetchHomeBases,
  },
  {
    title: 'Resolving the name she typed',
    actor: 'itega',
    narration:
      'Susan types "Publisher C". The directory resolves it to a certified home base and its endpoints.',
    background:
      'Resolution tries an exact member ID first, then a name, then a hint from her network. If nothing matches she is offered somewhere to sign up rather than a dead end.',
    run: () => resolveHomeBase('Publisher C'),
  },
  {
    title: 'Her home base vouches for her',
    actor: 'homebase',
    narration:
      'She authenticates with Publisher C — the only party that knows who she is. It issues an identifier for use at Publisher B.',
    background:
      'That identifier is pairwise: it is different at every publisher. Publisher B and Publisher A cannot compare notes and discover they have the same reader. Only her home base could link them, and it does not.',
  },
  {
    title: 'Publisher B welcomes her',
    actor: 'publisher',
    narration:
      'She is admitted as a network reader, with her home base named. She never created an account here.',
    background:
      'Publisher B knows a reader arrived from Publisher C and holds a subscription tier. It does not know her name, her email, or that she reads anywhere else.',
  },
  {
    title: 'What her home base will pay',
    actor: 'homebase',
    narration:
      'Publisher C acts as her buying agent. These are the standing instructions it applies on her behalf.',
    background:
      'The markup ratio lives here and only here. Publisher B never learns it — what Publisher C charges its own readers is between them.',
    run: fetchAgentPolicy,
  },
  {
    title: 'Publisher B names its price',
    actor: 'publisher',
    narration:
      'The article is priced at $0.05. Publisher B posts that to Susan\'s home base and waits.',
    background:
      'This is a real exchange, not a lookup. The publisher sets its own price; the home base may accept it, ask to negotiate, or refuse.',
    run: () => requestQuote(0.05, 'open'),
  },
  {
    title: 'A price worth arguing about',
    actor: 'homebase',
    narration:
      'A more expensive article — $0.20 — and the home base asks to negotiate rather than accepting outright.',
    background:
      'Publisher B now chooses: meet the offer, or re-post its price as final. A publisher that never wants to haggle can mark its prices final from the outset.',
    run: () => requestQuote(0.2, 'open'),
  },
  {
    title: 'The publisher holds its price',
    actor: 'publisher',
    narration:
      'Publisher B re-posts $0.20 as final. The home base pays it — it is within what it will spend for this reader.',
    background:
      'The agent gets one turn to ask. After that the exchange resolves, so a negotiation cannot loop.',
    run: () => requestQuote(0.2, 'final', 'demo-negotiation'),
  },
  {
    title: 'An AI engine asks for the same article',
    actor: 'itega',
    narration:
      'A member answer engine identifies itself and is checked against ITEGA\'s membership table, along with the terms it agreed to.',
    background:
      'An engine has no browser and cannot log in, so none of the reader flow applies. It identifies itself on every request and agrees a price machine-to-machine.',
    run: () => verifyAiAgent('ITEGA-AI-0001', 'demo-agent-key-replace-me'),
  },
  {
    title: 'A crawler that is not a member',
    actor: 'itega',
    narration:
      'A non-member is refused — and told where to join, rather than simply blocked.',
    background:
      'A crawler told only "no" learns nothing. One told where to join might become a paying member. That is the entire argument: make paying easier than taking.',
    run: () => verifyAiAgent('ITEGA-AI-9999', 'not-a-member'),
  },
  {
    title: 'What is logged, and where',
    actor: 'itega',
    narration:
      'Every purchase is recorded twice — once by the publisher, once by the reader\'s home base — so the two records can be checked against each other.',
    background:
      'ITEGA sees opaque identifiers and prices. It never sees who Susan is. Publishers get totals grouped by home base, never per-reader detail, so no publisher can reconstruct a reader\'s history.',
  },
  {
    title: 'Settlement, and the markup',
    actor: 'itega',
    narration:
      'Weekly, the logs are aggregated: home bases are debited, publishers are credited, ITEGA takes a small fee.',
    background:
      'Publisher B asked $0.05 and receives $0.05. Publisher C may bill Susan $0.055, or bundle it into her subscription, or absorb it — that spread is its margin for bringing her here, and it is the reason a home base has any interest in sending its readers to someone else\'s site.',
  },
];

export default function Demo() {
  const [current, setCurrent] = useState(0);
  const [results, setResults] = useState<Record<number, CallResult | 'loading'>>({});

  const step = STEPS[current];

  async function go(index: number) {
    setCurrent(index);
    const target = STEPS[index];
    // Re-run on each visit rather than caching: a presenter who steps back and
    // forward should see the system answer again, not a stale transcript.
    if (target.run) {
      setResults((r) => ({ ...r, [index]: 'loading' }));
      const result = await target.run();
      setResults((r) => ({ ...r, [index]: result }));
    }
  }

  const result = results[current];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-navy-900">
          How the Newshare Network works
        </h1>
        <p className="text-navy-600 mt-1">
          A reader with an account at one publisher, reading another. Every step
          below calls the live services.
        </p>
      </div>

      {/* The four parties, with the acting one highlighted. */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {(Object.keys(PARTIES) as (keyof typeof PARTIES)[]).map((key) => {
          const active = step.actor === key;
          return (
            <div
              key={key}
              className={`rounded-lg p-3 text-center text-sm font-medium transition ${
                active
                  ? `${PARTIES[key].color} text-white shadow-md`
                  : 'bg-navy-50 text-navy-400'
              }`}
            >
              {PARTIES[key].label}
            </div>
          );
        })}
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        {/* Progress rail */}
        <ol className="space-y-1 md:col-span-1">
          {STEPS.map((s, i) => (
            <li key={s.title}>
              <button
                onClick={() => go(i)}
                className={`w-full text-left px-3 py-2 rounded text-sm transition ${
                  i === current
                    ? 'bg-teal-600 text-white font-medium'
                    : i < current
                      ? 'text-navy-500 hover:bg-navy-50'
                      : 'text-navy-400 hover:bg-navy-50'
                }`}
              >
                <span className="tabular-nums opacity-60 mr-2">{i + 1}</span>
                {s.title}
              </button>
            </li>
          ))}
        </ol>

        {/* The current step */}
        <div className="md:col-span-2 space-y-4">
          <div className="bg-white rounded-lg border border-navy-100 p-5">
            <h2 className="text-lg font-semibold text-navy-900">{step.title}</h2>
            <p className="mt-2 text-navy-700 leading-relaxed">{step.narration}</p>

            {step.background && (
              <div className="mt-4 border-l-4 border-teal-400 bg-teal-50 px-4 py-3 rounded-r">
                <p className="text-xs font-semibold uppercase tracking-wide text-teal-800">
                  What is happening underneath
                </p>
                <p className="mt-1 text-sm text-navy-700 leading-relaxed">
                  {step.background}
                </p>
              </div>
            )}
          </div>

          {/* Live call, when this step makes one. */}
          {step.run && (
            <div className="bg-navy-900 rounded-lg p-4 overflow-x-auto">
              {result === 'loading' && (
                <p className="text-navy-300 text-sm">Calling the service…</p>
              )}
              {result && result !== 'loading' && (
                <>
                  <p className="text-teal-300 text-xs font-mono mb-2">
                    {result.request}
                  </p>
                  {result.ok ? (
                    <pre className="text-navy-100 text-xs font-mono whitespace-pre-wrap">
                      {JSON.stringify(result.data, null, 2)}
                    </pre>
                  ) : (
                    // Say so plainly. Substituting canned data here would
                    // undermine the only claim the demo is making.
                    <p className="text-amber-300 text-sm">
                      Service did not answer: {result.error}
                    </p>
                  )}
                </>
              )}
              {!result && (
                <p className="text-navy-400 text-sm">
                  This step calls a live service.
                </p>
              )}
            </div>
          )}

          <div className="flex justify-between">
            <button
              onClick={() => go(Math.max(0, current - 1))}
              disabled={current === 0}
              className="px-4 py-2 rounded border border-navy-200 text-navy-700 disabled:opacity-40"
            >
              Back
            </button>
            <button
              onClick={() => go(Math.min(STEPS.length - 1, current + 1))}
              disabled={current === STEPS.length - 1}
              className="px-5 py-2 rounded bg-teal-600 text-white font-medium disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
