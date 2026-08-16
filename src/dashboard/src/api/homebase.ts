/**
 * homebase.ts -- resolving a home base id to the organisation's name.
 *
 * The session token carries `homeBaseId` and nothing friendlier, because the
 * exchange has no business embedding display strings in a credential. The name
 * comes from the network's own public registry instead, which is the party that
 * decides who is certified and what they are called.
 *
 * The dashboard previously showed "Tribune Media Group" here, hardcoded, for
 * every reader regardless of where they actually banked.
 */

const DISCOVERY_URL =
  import.meta.env.VITE_DISCOVERY_URL ?? 'https://network.itega.org';

let cache: Record<string, string> | null = null;

/** The certified home base's display name, or '' if it cannot be resolved. */
export async function getHomeBaseName(homeBaseId: string): Promise<string> {
  if (!homeBaseId) return '';
  if (cache) return cache[homeBaseId] ?? '';

  try {
    const resp = await fetch(`${DISCOVERY_URL}/discovery/home-bases`);
    if (!resp.ok) return '';
    const bases = await resp.json();
    cache = {};
    for (const hb of bases) {
      // Registered under both identifiers, since callers hold one or the other.
      if (hb.id) cache[hb.id] = hb.name ?? '';
      if (hb.publishing_member_id) cache[hb.publishing_member_id] = hb.name ?? '';
    }
    return cache[homeBaseId] ?? '';
  } catch {
    // Falling back to the raw id is honest. Inventing a name is not.
    return '';
  }
}
