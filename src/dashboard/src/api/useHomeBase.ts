/**
 * useHomeBase -- the reader's home base, by name, wherever we address them.
 *
 * Copy like "contact your home base for billing questions" is correct and
 * useless: it names a role in an architecture rather than an organisation the
 * reader could actually contact. Once they are signed in we know exactly which
 * member vouched for them, so the page should say it.
 *
 * Falls back to the generic phrase rather than an id or an empty gap, so the
 * sentence still reads properly while the registry is being fetched, or if it
 * cannot be reached at all.
 */
import { useEffect, useState } from 'react';
import { getHomeBaseName } from './homebase';

export function useHomeBase(homeBaseId: string, fallback = 'your home base'): string {
  const [name, setName] = useState(fallback);

  useEffect(() => {
    let live = true;
    getHomeBaseName(homeBaseId).then((n) => {
      if (live && n) setName(n);
    });
    return () => { live = false; };
  }, [homeBaseId, fallback]);

  return name;
}
