const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? '';

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
