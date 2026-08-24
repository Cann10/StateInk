import { describe, expect, it } from 'vitest';
import { joinApiUrl, resolveApiBaseUrl } from './config';

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

describe('joinApiUrl', () => {
  it('joins a Render origin with the recognition endpoint', () => {
    expect(joinApiUrl('https://stateink.onrender.com/', '/api/recognize'))
      .toBe('https://stateink.onrender.com/api/recognize');
  });

  it('does not duplicate an api path from an environment value', () => {
    expect(joinApiUrl('https://stateink.onrender.com/api', '/api/recognize'))
      .toBe('https://stateink.onrender.com/api/recognize');
    expect(joinApiUrl('https://stateink.onrender.com/api/recognize', '/api/recognize'))
      .toBe('https://stateink.onrender.com/api/recognize');
  });

  it('uses a relative endpoint for local proxy and same-origin deployments', () => {
    expect(joinApiUrl('', '/api/recognize')).toBe('/api/recognize');
  });
});
