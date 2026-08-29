import { describe, expect, it, vi } from 'vitest';
import { scrollIntoViewGently } from './a11y';

describe('scrollIntoViewGently', () => {
  it('does nothing for a missing element', () => {
    expect(() => scrollIntoViewGently(null)).not.toThrow();
    expect(() => scrollIntoViewGently(undefined)).not.toThrow();
  });

  it('scrolls a real element into view without throwing', () => {
    const scrollIntoView = vi.fn();
    scrollIntoViewGently({ scrollIntoView } as unknown as Element);
    expect(scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({ block: 'nearest' }));
  });
});
