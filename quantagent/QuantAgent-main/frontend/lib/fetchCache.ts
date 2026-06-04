/**
 * Simple client-side fetch cache with TTL.
 * Reuses API responses across page navigations so switching tabs feels instant.
 */

interface CacheEntry {
  data: any;
  ts: number;
}

const cache = new Map<string, CacheEntry>();
const DEFAULT_TTL = 30_000; // 30 seconds

export function getCached(key: string, ttl = DEFAULT_TTL): any | undefined {
  const entry = cache.get(key);
  if (!entry) return undefined;
  if (Date.now() - entry.ts > ttl) {
    cache.delete(key);
    return undefined;
  }
  return entry.data;
}

export function setCached(key: string, data: any): void {
  cache.set(key, { data, ts: Date.now() });
}

/**
 * Fetch with cache. Returns cached data if available within TTL,
 * otherwise fetches from the network and caches the result.
 */
export async function fetchCached<T = any>(
  url: string,
  options?: RequestInit,
  ttl?: number
): Promise<T> {
  const cached = getCached(url, ttl);
  if (cached) return cached as T;

  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
  const data = await res.json();
  setCached(url, data);
  return data as T;
}

/** Clear all cached entries (e.g., on manual refresh) */
export function clearFetchCache(): void {
  cache.clear();
}
