import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Lock } from "lucide-react";
import { type ReactNode, useState } from "react";
import { api } from "@/api/client";
import { ErrorNote } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function useAuthStatus() {
  return useQuery({ queryKey: ["auth"], queryFn: api.authStatus, staleTime: 60_000, retry: false });
}

/**
 * Shows the sign-in screen when the app has a password and this browser has
 * no session (decision 0026). Without a password it renders its children
 * straight away. If the server can't be reached the children render too, so
 * the console's own "server not reachable" state shows.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const status = useAuthStatus();
  if (status.isPending) return null;
  if (status.data?.enabled && !status.data.signed_in) return <SignIn />;
  return <>{children}</>;
}

function SignIn() {
  const client = useQueryClient();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.login(password);
      setPassword("");
      // Everything fetched while signed out failed: fetch it again.
      await client.invalidateQueries();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="grid min-h-screen place-items-center bg-muted/40 px-4">
      <form
        className="w-full max-w-sm space-y-4 rounded-xl border bg-background p-6 shadow-sm"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div className="flex items-center gap-2">
          <Lock className="size-5 text-primary" />
          <h1 className="text-lg font-semibold">Sign in</h1>
        </div>
        <p className="text-sm text-muted-foreground">This app has a password. It covers the console and the employee portal.</p>
        <label className="block space-y-1 text-sm">
          <span className="font-medium">Password</span>
          <Input
            type="password"
            autoComplete="current-password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        <ErrorNote error={error} />
        <Button type="submit" className="w-full" disabled={!password || busy}>
          {busy && <Loader2 className="animate-spin" />} Sign in
        </Button>
        <p className="text-xs text-muted-foreground">
          Forgot it? On the machine running the app: <code>python -m app.cli clear-password</code>, or change{" "}
          <code>APP_PASSWORD</code>.
        </p>
      </form>
    </main>
  );
}

/** "Sign out", shown only when the app has a password. */
export function SignOutButton({ className }: { className?: string }) {
  const status = useAuthStatus();
  const client = useQueryClient();
  if (!status.data?.enabled) return null;
  return (
    <button
      type="button"
      className={className}
      onClick={async () => {
        await api.logout();
        client.clear();
        await client.invalidateQueries({ queryKey: ["auth"] });
      }}
    >
      Sign out
    </button>
  );
}
