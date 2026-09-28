export const CANDIDATE_PAGE_SIZE = 50;

export function candidatePage<T>(items: T[], requestedPage: number) {
  const pageCount = Math.max(1, Math.ceil(items.length / CANDIDATE_PAGE_SIZE));
  const page = Math.min(Math.max(0, requestedPage), pageCount - 1);
  const start = page * CANDIDATE_PAGE_SIZE;
  return { page, pageCount, start, items: items.slice(start, start + CANDIDATE_PAGE_SIZE) };
}

export function selectCandidatePage(selected: Set<string>, keys: string[]): Set<string> {
  return new Set([...selected, ...keys]);
}

/** Invalidates old reads without mistaking their completion for the current workspace. */
export function createIntakeRequestScope() {
  let generation = 0;
  return {
    begin: () => ++generation,
    current: (ticket: number) => ticket === generation,
    invalidate: () => { generation += 1; },
  };
}
