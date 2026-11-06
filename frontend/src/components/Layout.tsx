import {
  AlertTriangle,
  Database,
  FolderOpen,
  LayoutDashboard,
  ListTodo,
  Bell,
  BellOff,
  Lock,
  MessageSquare,
  Wrench,
  X,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { Troubleshooter } from "@/components/Troubleshooter";
import { TroubleshooterProvider, useTroubleshooter } from "@/components/TroubleshooterContext";
import { Button } from "@/components/ui/button";
import { type ToastMessage, Toasts } from "@/components/ui/toast";
import { isActiveJob, useDiagnostics, useJobs } from "@/hooks/queries";
import { type SystemState, type SystemStatus, useSystemStatus } from "@/hooks/useSystemStatus";
import { cn } from "@/lib/utils";

type Need = "browse" | "chat" | "process" | null;

const NAV: { to: string; label: string; icon: typeof LayoutDashboard; end?: boolean; needs: Need; partly?: Need }[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true, needs: null },
  { to: "/chat", label: "Chat", icon: MessageSquare, needs: "chat" },
  { to: "/library", label: "Library", icon: FolderOpen, needs: "browse", partly: "process" },
  { to: "/collections", label: "Collections", icon: Database, needs: "browse", partly: "process" },
  { to: "/queue", label: "Queue", icon: ListTodo, needs: "browse", partly: "process" },
];

const PILL: Record<SystemState, { label: string; className: string; dot: string }> = {
  checking: { label: "Checking…", className: "bg-muted text-muted-foreground", dot: "bg-muted-foreground/40" },
  ok: { label: "All systems OK", className: "bg-success/10 text-success", dot: "bg-success" },
  degraded: { label: "Degraded", className: "bg-warning/15 text-warning", dot: "bg-warning" },
  down: { label: "System down", className: "bg-destructive text-destructive-foreground", dot: "bg-white" },
  unreachable: { label: "Server not reachable", className: "bg-destructive text-destructive-foreground", dot: "bg-white" },
};

const TITLE = "Local RAG";

export function Layout() {
  return (
    <TroubleshooterProvider>
      <Shell />
    </TroubleshooterProvider>
  );
}

function Shell() {
  const status = useSystemStatus();
  const troubleshooter = useTroubleshooter();
  const jobs = useJobs();
  const activeJobs = jobs.data?.filter(isActiveJob).length ?? 0;
  const notifications = useDesktopNotifications();
  const toasts = useStatusToasts(status, notifications.send);
  useStatusTitle(status.state);
  useAutoOpenWhenDown(status.state, troubleshooter.open);

  const blockedFor = (need: Need): string | null =>
    need === "browse" ? status.browseBlocked : need === "chat" ? status.chatBlocked : need === "process" ? status.processBlocked : null;
  const pill = PILL[status.state];

  return (
    <div className="flex h-full">
      <aside className="flex w-56 shrink-0 flex-col border-r bg-muted/40">
        <div className="flex items-center gap-2 px-5 pb-3 pt-5">
          <img src="/favicon.svg" alt="" className="size-7" />
          <div>
            <div className="text-sm font-semibold leading-tight">Local RAG</div>
            <div className="text-xs text-muted-foreground">Ollama, on this machine</div>
          </div>
        </div>
        <button
          type="button"
          onClick={troubleshooter.open}
          title="Open troubleshooting"
          className={cn(
            "mx-3 mb-3 flex items-center gap-2 rounded-md px-3 py-2 text-left text-xs font-semibold transition-opacity hover:opacity-85",
            pill.className,
          )}
        >
          <span className={cn("size-2 shrink-0 rounded-full", pill.dot, status.state !== "ok" && "animate-pulse")} />
          <span className="flex-1">
            {pill.label}
            <LastChecked at={status.lastChecked} />
          </span>
          {status.state !== "ok" && status.state !== "checking" && <Wrench className="size-3.5" />}
        </button>
        <NotifyToggle notify={notifications} />
        <nav className="flex flex-1 flex-col gap-0.5 px-3">
          {NAV.map(({ to, label, icon: Icon, end, needs, partly }) => {
            const blocked = blockedFor(needs);
            const partlyBlocked = !blocked ? blockedFor(partly ?? null) : null;
            return (
              <NavLink
                key={to}
                to={to}
                end={end}
                title={
                  blocked
                    ? `${label} is paused: ${blocked}`
                    : partlyBlocked
                      ? `Some actions are paused: ${partlyBlocked}`
                      : undefined
                }
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
                    isActive && "bg-background font-medium text-foreground shadow-sm",
                    blocked && "opacity-60",
                  )
                }
              >
                <Icon className="size-4" />
                <span className="flex-1">{label}</span>
                {blocked && <Lock className="size-3.5 text-warning" />}
                {partlyBlocked && <span className="size-1.5 rounded-full bg-warning" />}
                {to === "/queue" && activeJobs > 0 && (
                  <span className="rounded-full bg-primary px-1.5 text-xs font-medium text-primary-foreground">
                    {activeJobs}
                  </span>
                )}
              </NavLink>
            );
          })}
        </nav>
      </aside>
      <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">
        <StatusBar status={status} onTroubleshoot={troubleshooter.open} />
        <div className="flex-1">
          <Outlet />
        </div>
      </main>
      <Troubleshooter open={troubleshooter.isOpen} onClose={troubleshooter.close} unreachable={status.state === "unreachable"} />
      <Toasts toasts={toasts.items} onDismiss={toasts.dismiss} />
    </div>
  );
}

const WARNINGS_DISMISSED = "status.warningsDismissed";

/** Red or amber bar above every page while something is broken; a grey,
 * dismissible one for warnings the troubleshooter found at start-up. */
function StatusBar({ status, onTroubleshoot }: { status: SystemStatus; onTroubleshoot: () => void }) {
  const broken = status.state === "down" || status.state === "unreachable" || status.state === "degraded";
  // Warnings (e.g. low memory) aren't in /health: run the checks once at start-up.
  const diagnostics = useDiagnostics(status.state === "ok");
  const [dismissed, setDismissed] = useState(() => sessionStorage.getItem(WARNINGS_DISMISSED) === "1");
  const warnings = diagnostics.data?.checks.filter((c) => c.status === "warn") ?? [];

  if (broken) {
    const severe = status.state !== "degraded";
    return (
      <div
        role="alert"
        className={cn(
          "sticky top-0 z-30 flex flex-wrap items-center gap-3 px-6 py-3 text-sm font-medium shadow-sm",
          severe ? "bg-destructive text-destructive-foreground" : "bg-warning text-white",
        )}
      >
        {severe ? <XCircle className="size-5 shrink-0" /> : <AlertTriangle className="size-5 shrink-0" />}
        <span className="flex-1">
          {status.headline}
          {status.simulated.length > 0 && <span className="ml-2 font-normal opacity-90">(simulated for testing)</span>}
        </span>
        <Button size="sm" variant="secondary" onClick={onTroubleshoot}>
          <Wrench /> Troubleshoot
        </Button>
      </div>
    );
  }
  if (status.state === "ok" && warnings.length > 0 && !dismissed) {
    return (
      <div className="sticky top-0 z-30 flex flex-wrap items-center gap-3 border-b bg-muted px-6 py-2 text-sm">
        <AlertTriangle className="size-4 shrink-0 text-warning" />
        <span className="flex-1">
          {warnings.length} warning{warnings.length === 1 ? "" : "s"}: {warnings[0].title.toLowerCase()} — {warnings[0].detail}
        </span>
        <Button size="sm" variant="outline" onClick={onTroubleshoot}>
          Details
        </Button>
        <button
          type="button"
          title="Hide until the next visit"
          className="text-muted-foreground hover:text-foreground"
          onClick={() => {
            sessionStorage.setItem(WARNINGS_DISMISSED, "1");
            setDismissed(true);
          }}
        >
          <X className="size-4" />
        </button>
      </div>
    );
  }
  return null;
}

const MESSAGES: Partial<Record<SystemState, { tone: ToastMessage["tone"]; text: string }>> = {
  ok: { tone: "success", text: "All systems are working again. Paused features are available." },
  degraded: { tone: "warning", text: "Part of the app stopped working. Some features are paused." },
  down: { tone: "error", text: "The system is down. Most features are paused." },
  unreachable: { tone: "error", text: "Lost the connection to the app server." },
};

/** A notice whenever the state changes after the first check; also a
 * desktop notification if the user turned them on and the tab is hidden. */
function useStatusToasts(status: SystemStatus, sendDesktop: (title: string, body: string) => void) {
  const [items, setItems] = useState<ToastMessage[]>([]);
  const previous = useRef<SystemState>("checking");
  useEffect(() => {
    const before = previous.current;
    previous.current = status.state;
    if (before === "checking" || status.state === "checking" || before === status.state) return;
    const message = MESSAGES[status.state];
    if (!message) return;
    setItems((list) => [...list, { id: Date.now(), ...message }]);
    sendDesktop(PILL[status.state].label, status.headline || message.text);
  }, [status.state, status.headline, sendDesktop]);
  const dismiss = useCallback((id: number) => setItems((list) => list.filter((t) => t.id !== id)), []);
  return { items, dismiss };
}

function useStatusTitle(state: SystemState) {
  useEffect(() => {
    document.title =
      state === "down" || state === "unreachable"
        ? `⛔ System down · ${TITLE}`
        : state === "degraded"
          ? `⚠ Degraded · ${TITLE}`
          : TITLE;
  }, [state]);
}

const AUTO_OPENED = "status.troubleshooterAutoOpened";

/** If the app is down when someone opens it, show the troubleshooter once
 * per browser session, so nobody starts working without knowing. */
function useAutoOpenWhenDown(state: SystemState, open: () => void) {
  useEffect(() => {
    if ((state === "down" || state === "unreachable") && sessionStorage.getItem(AUTO_OPENED) !== "1") {
      sessionStorage.setItem(AUTO_OPENED, "1");
      open();
    }
  }, [state, open]);
}

/** "checked 5 s ago" under the status pill, ticking every few seconds. */
function LastChecked({ at }: { at: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(timer);
  }, []);
  if (!at) return null;
  const seconds = Math.max(0, Math.round((now - at) / 1000));
  const text = seconds < 60 ? `${seconds} s ago` : `${Math.round(seconds / 60)} min ago`;
  return <span className="block text-[10px] font-normal opacity-80">checked {text}</span>;
}

const NOTIFY_KEY = "status.desktopNotifications";
type Notifications = ReturnType<typeof useDesktopNotifications>;

/** Opt-in desktop notifications for status changes. They only fire while
 * the tab is hidden: on screen, the bar and the notice already show it. */
function useDesktopNotifications() {
  const supported = typeof window !== "undefined" && "Notification" in window;
  const [enabled, setEnabled] = useState(
    () => supported && Notification.permission === "granted" && localStorage.getItem(NOTIFY_KEY) === "1",
  );
  const [permission, setPermission] = useState(() => (supported ? Notification.permission : "denied"));

  const toggle = async () => {
    if (!supported) return;
    if (enabled) {
      localStorage.setItem(NOTIFY_KEY, "0");
      setEnabled(false);
      return;
    }
    const result = Notification.permission === "granted" ? "granted" : await Notification.requestPermission();
    setPermission(result);
    if (result === "granted") {
      localStorage.setItem(NOTIFY_KEY, "1");
      setEnabled(true);
      new Notification("Local RAG", { body: "You'll be notified here when the system status changes." });
    }
  };

  const send = useCallback(
    (title: string, body: string) => {
      if (enabled && document.hidden) new Notification(`Local RAG: ${title}`, { body, tag: "system-status" });
    },
    [enabled],
  );
  return { supported, enabled, permission, toggle, send };
}

function NotifyToggle({ notify }: { notify: Notifications }) {
  if (!notify.supported) return null;
  const blocked = notify.permission === "denied" && !notify.enabled;
  return (
    <button
      type="button"
      onClick={notify.toggle}
      disabled={blocked}
      title={
        blocked
          ? "Notifications are blocked for this site in your browser settings"
          : notify.enabled
            ? "Turn off desktop notifications"
            : "Get a desktop notification when the system status changes while this tab is in the background"
      }
      className="mx-3 -mt-2 mb-3 flex items-center gap-1.5 rounded px-3 py-1 text-left text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground disabled:opacity-60"
    >
      {notify.enabled ? <Bell className="size-3.5 text-primary" /> : <BellOff className="size-3.5" />}
      {blocked ? "Notifications blocked" : notify.enabled ? "Notifications on" : "Notify me of changes"}
    </button>
  );
}
