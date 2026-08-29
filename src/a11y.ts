/** scrollIntoView that respects the viewer's reduced-motion preference. */
export function scrollIntoViewGently(element: Element | null | undefined): void {
  if (!element) return;
  const reduce = typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  element.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'nearest' });
}
