import { Component, type ErrorInfo, type ReactNode } from 'react';
import { clearSavedWorkspace } from './features/workspace/storage';

interface Props { children: ReactNode }
interface State { hasError: boolean }

/**
 * Last-resort guard so a render-time exception shows a recoverable screen
 * instead of a blank page during a live demo. Recognition, Simulator and
 * Analyzer logic are untouched by this.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('StateInk render error', error, info.componentStack);
  }

  private reload = (): void => {
    window.location.reload();
  };

  private resetAndReload = (): void => {
    clearSavedWorkspace();
    window.location.reload();
  };

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children;
    return (
      <main className="app-error" role="alert">
        <div>
          <h1>問題が発生しました</h1>
          <p>画面の表示中にエラーが発生しました。まず再読み込みをお試しください。繰り返す場合は、保存された作業内容を消してから読み込み直せます。</p>
          <div className="app-error-actions">
            <button className="primary" onClick={this.reload}>再読み込み</button>
            <button className="reset" onClick={this.resetAndReload}>保存データを消して読み込み直す</button>
          </div>
        </div>
      </main>
    );
  }
}
