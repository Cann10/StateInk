import { describe, expect, it } from 'vitest';
import { resolveApiBaseUrl } from './config';

describe('resolveApiBaseUrl', () => {
  it('uses a configured absolute backend URL and removes trailing slashes', () => {
    expect(resolveApiBaseUrl('https://api.example.com///', 'state-ink.vercel.app'))
      .toBe('https://api.example.com');
  });

  it('falls back to the production backend when Vercel receives a placeholder value', () => {
    expect(resolveApiBaseUrl('VITE_API_BASE_URL', 'state-ink.vercel.app'))
      .toBe('https://stateink.onrender.com');
  });

  it('unwraps a key-value assignment mistakenly pasted into Vercel', () => {
    expect(resolveApiBaseUrl('VITE_API_BASE_URL=https://stateink.onrender.com', 'preview.vercel.app'))
      .toBe('https://stateink.onrender.com');
  });

  it('keeps local development on the same origin when the variable is missing', () => {
    expect(resolveApiBaseUrl(undefined, 'localhost')).toBe('');
  });
});
