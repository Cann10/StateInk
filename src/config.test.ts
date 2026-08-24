import { describe, expect, it } from 'vitest';
import { joinApiUrl } from './config';

describe('joinApiUrl', () => {
  it('joins a Render origin with the recognition endpoint', () => {
    expect(joinApiUrl('https://stateink-api.onrender.com/', '/api/recognize'))
      .toBe('https://stateink-api.onrender.com/api/recognize');
  });

  it('does not duplicate an api path from an environment value', () => {
    expect(joinApiUrl('https://stateink-api.onrender.com/api', '/api/recognize'))
      .toBe('https://stateink-api.onrender.com/api/recognize');
    expect(joinApiUrl('https://stateink-api.onrender.com/api/recognize', '/api/recognize'))
      .toBe('https://stateink-api.onrender.com/api/recognize');
  });

  it('uses a relative endpoint for local proxy and same-origin deployments', () => {
    expect(joinApiUrl('', '/api/recognize')).toBe('/api/recognize');
  });
});
