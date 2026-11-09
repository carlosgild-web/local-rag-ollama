import { AlertTriangle, RefreshCw } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

/** Catches a crash in one part of the page, so the rest of the app keeps
 * working and the user sees what happened instead of a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode; area: string }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`Crash in ${this.props.area}:`, error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="m-6 max-w-xl rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm">
        <p className="flex items-center gap-2 font-semibold text-destructive">
          <AlertTriangle className="size-4" /> Something went wrong in {this.props.area}.
        </p>
        <p className="mt-1 text-muted-foreground">The rest of the app still works. Details: {this.state.error.message}</p>
        <button
          type="button"
          onClick={() => this.setState({ error: null })}
          className="mt-3 inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-1.5 text-xs font-medium hover:bg-muted"
        >
          <RefreshCw className="size-3.5" /> Try again
        </button>
      </div>
    );
  }
}
