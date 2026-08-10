/**
 * demo.ts -- Live calls behind the step-through demonstration.
 *
 * The demo narrates the network by actually exercising it. Each step below
 * makes a real request to a real service and returns what came back, so what
 * an audience sees on Aug 25 is the system working rather than a recording of
 * it having once worked.
 *
 * Where a service is unreachable, the caller is told plainly. A demo that
 * silently falls back to canned data would be worse than one that admits a
 * service is down -- the whole claim being made is that this runs.
 */

const DISCOVERY_URL =
  import.meta.env.VITE_DISCOVERY_URL ?? 'https://network.newshare.example';
const AGENT_C_URL =
  import.meta.env.VITE_AGENT_C_URL ?? 'https://agent-c.newshare.example';
const ALS_AUTH_URL =
  import.meta.env.VITE_ALS_AUTH_URL ?? 'https://als.newshare.example';

/** Outcome of one live call: what was asked, what came back, and whether it worked. */
export interface CallResult {
  ok: boolean;
  /** Human-readable description of the request, for the narration panel. */
  request: string;
  /** Parsed response body, or null when the call failed. */
  data: unknown;
  /** Set when the call failed, so the UI can say so rather than inventing data. */
  error?: string;
}

async function call(
  label: string,
  url: string,
  init?: RequestInit,
): Promise<CallResult> {
  try {
    const res = await fetch(url, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    });
    if (!res.ok) {
      return {
        ok: false,
        request: label,
        data: null,
        error: `${res.status} ${res.statusText}`,
      };
    }
    return { ok: true, request: label, data: await res.json() };
  } catch (err) {
    return {
      ok: false,
      request: label,
      data: null,
      error: err instanceof Error ? err.message : 'Service unreachable',
    };
  }
}

/** Which home bases ITEGA currently certifies. */
export function fetchHomeBases(): Promise<CallResult> {
  return call(
    `GET ${DISCOVERY_URL}/discovery/home-bases`,
    `${DISCOVERY_URL}/discovery/home-bases`,
  );
}

/** Resolve a reader to their home base the way the Authenticator does. */
export function resolveHomeBase(q: string): Promise<CallResult> {
  const url = `${DISCOVERY_URL}/discovery/home-bases/resolve?q=${encodeURIComponent(q)}`;
  return call(`GET ${DISCOVERY_URL}/discovery/home-bases/resolve?q=${q}`, url);
}

/** The buying policy a home base applies on its readers' behalf. */
export function fetchAgentPolicy(): Promise<CallResult> {
  return call(`GET ${AGENT_C_URL}/agent/policy`, `${AGENT_C_URL}/agent/policy`);
}

/**
 * Ask the reader's home base to authorise a purchase.
 *
 * This is the exchange in script step 28 -- the publisher naming its price and
 * the home base answering. `terms` lets the demo show both a negotiable price
 * and a take-it-or-leave-it one.
 */
export function requestQuote(
  wholesalePrice: number,
  terms: 'open' | 'final' = 'open',
  negotiationId = '',
): Promise<CallResult> {
  return call(
    `POST ${AGENT_C_URL}/agent/quote  ($${wholesalePrice.toFixed(2)}, ${terms})`,
    `${AGENT_C_URL}/agent/quote`,
    {
      method: 'POST',
      body: JSON.stringify({
        networkUserId: 'demo-ppid-at-publisher-b',
        homeBaseId: 'HB001',
        pubMbrId: 'ITEGA-PB-0001',
        resourceId: 'https://publisher-b.example/story/water-rights',
        wholesalePrice,
        sessionId: 'demo-session',
        negotiationId,
        terms,
      }),
    },
  );
}

/** Verify an AI answer engine's membership, as a publisher's code would. */
export function verifyAiAgent(
  agentMbrId: string,
  apiKey: string,
): Promise<CallResult> {
  return call(
    `POST ${ALS_AUTH_URL}/ai-agent/verify  (${agentMbrId})`,
    `${ALS_AUTH_URL}/ai-agent/verify`,
    {
      method: 'POST',
      body: JSON.stringify({
        agentMbrId,
        apiKey,
        pubMbrId: 'ITEGA-PB-0001',
        resourceId: 'https://publisher-b.example/story/water-rights',
      }),
    },
  );
}
