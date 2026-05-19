import { useEffect, useRef, useState } from 'react';

export type FlashDirection = 'up' | 'down';

interface UseRankFlashOptions {
  flashDuration?: number;
  minDelta?: number;
  enabled?: boolean;
  resetKey?: string | number;
}

/**
 * Tracks rank changes between renders and exposes a transient map of items
 * whose rank moved by at least `minDelta` positions. Each flagged id is
 * cleared after `flashDuration` ms. First render never flashes; pass
 * `resetKey` (e.g. a category filter) to wipe state when the source list
 * changes meaning.
 */
export function useRankFlash<T extends { id: string }>(
  items: T[],
  options?: UseRankFlashOptions,
): Map<string, FlashDirection> {
  const flashDuration = options?.flashDuration ?? 450;
  const minDelta = options?.minDelta ?? 3;
  const enabled = options?.enabled ?? true;
  const resetKey = options?.resetKey;

  const prevRanksRef = useRef<Map<string, number> | null>(null);
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const lastResetKeyRef = useRef<string | number | undefined>(resetKey);
  const [flashMap, setFlashMap] = useState<Map<string, FlashDirection>>(() => new Map());

  useEffect(() => {
    if (!enabled) return;

    if (resetKey !== lastResetKeyRef.current) {
      lastResetKeyRef.current = resetKey;
      prevRanksRef.current = null;
      timersRef.current.forEach((t) => clearTimeout(t));
      timersRef.current.clear();
      setFlashMap((prev) => (prev.size === 0 ? prev : new Map()));
    }

    const nextRanks = new Map<string, number>();
    items.forEach((item, index) => {
      nextRanks.set(item.id, index);
    });

    if (prevRanksRef.current === null) {
      prevRanksRef.current = nextRanks;
      return;
    }

    const prev = prevRanksRef.current;
    const newlyFlashing: Array<[string, FlashDirection]> = [];

    nextRanks.forEach((newRank, id) => {
      const oldRank = prev.get(id);
      if (oldRank === undefined) return;
      const delta = oldRank - newRank;
      if (Math.abs(delta) >= minDelta) {
        newlyFlashing.push([id, delta > 0 ? 'up' : 'down']);
      }
    });

    prevRanksRef.current = nextRanks;

    if (newlyFlashing.length === 0) return;

    setFlashMap((curr) => {
      const next = new Map(curr);
      newlyFlashing.forEach(([id, dir]) => {
        next.set(id, dir);
      });
      return next;
    });

    newlyFlashing.forEach(([id]) => {
      const existing = timersRef.current.get(id);
      if (existing) clearTimeout(existing);
      const timer = setTimeout(() => {
        setFlashMap((curr) => {
          if (!curr.has(id)) return curr;
          const updated = new Map(curr);
          updated.delete(id);
          return updated;
        });
        timersRef.current.delete(id);
      }, flashDuration);
      timersRef.current.set(id, timer);
    });
  }, [items, flashDuration, minDelta, enabled, resetKey]);

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((t) => clearTimeout(t));
      timers.clear();
    };
  }, []);

  return flashMap;
}
