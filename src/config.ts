const productionApiBaseUrl = 'https://stateink.onrender.com';

export function resolveApiBaseUrl(value: string | undefined, hostname: string): string {
  const candidate = (value ?? '')
    .trim()
    .replace(/^VITE_API_BASE_URL\s*=\s*/, '')
    .replace(/\/+$/, '');
  const isAbsoluteHttpUrl = /^https?:\/\/[^/]+/i.test(candidate);

  if (isAbsoluteHttpUrl) return candidate;
  if (hostname === 'state-ink.vercel.app') return productionApiBaseUrl;
  return '';
}

const apiBaseUrl = resolveApiBaseUrl(
  import.meta.env.VITE_API_BASE_URL,
  typeof window === 'undefined' ? '' : window.location.hostname,
);

export function joinApiUrl(baseUrl: string, path: `/${string}`): string {
  const base = baseUrl.trim().replace(/\/+$/, '');
  if (!base) return path;
  if (base.endsWith(path)) return base;
  if (base.endsWith('/api') && path.startsWith('/api/')) return `${base}${path.slice(4)}`;
  return `${base}${path}`;
}

export function apiUrl(path: `/${string}`): string {
  return joinApiUrl(apiBaseUrl, path);
}
