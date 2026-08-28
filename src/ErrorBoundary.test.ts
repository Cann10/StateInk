import { describe, expect, it } from 'vitest';
import { ErrorBoundary } from './ErrorBoundary';

describe('ErrorBoundary', () => {
  it('starts without an error state', () => {
    const boundary = new ErrorBoundary({ children: null });
    expect(boundary.state.hasError).toBe(false);
  });

  it('switches to the error state when a child throws', () => {
    expect(ErrorBoundary.getDerivedStateFromError()).toEqual({ hasError: true });
  });

  it('renders its children while healthy', () => {
    const boundary = new ErrorBoundary({ children: 'ok' });
    expect(boundary.render()).toBe('ok');
  });
});
