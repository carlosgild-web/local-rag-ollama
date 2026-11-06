import { Database, FolderOpen, LayoutDashboard, ListTodo, MessageSquare } from "lucide-react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { isActiveJob, useHealth, useJobs } from "@/hooks/queries";
import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/chat", label: "Chat", icon: MessageSquare },
  { to: "/library", label: "Library", icon: FolderOpen },
  { to: "/collections", label: "Collections", icon: Database },
  { to: "/queue", label: "Queue", icon: ListTodo },
];

const STATUS_COLOR = { ok: "bg-success", degraded: "bg-warning", down: "bg-destructive" } as const;

export function Layout() {
  const health = useHealth();
  const jobs = useJobs();
  const activeJobs = jobs.data?.filter(isActiveJob).length ?? 0;
  const status = health.data?.status ?? (health.isError ? "down" : undefined);

  return (
    <div className="flex h-full">
      <aside className="flex w-56 shrink-0 flex-col border-r bg-muted/40">
        <div className="flex items-center gap-2 px-5 py-5">
          <img src="/favicon.svg" alt="" className="size-7" />
          <div>
            <div className="text-sm font-semibold leading-tight">Local RAG</div>
            <div className="text-xs text-muted-foreground">Ollama, on this machine</div>
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5 px-3">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground",
                  isActive && "bg-background font-medium text-foreground shadow-sm",
                )
              }
            >
              <Icon className="size-4" />
              <span className="flex-1">{label}</span>
              {to === "/queue" && activeJobs > 0 && (
                <span className="rounded-full bg-primary px-1.5 text-xs font-medium text-primary-foreground">
                  {activeJobs}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <Link
          to="/?troubleshoot=1"
          title="Open troubleshooting"
          className="flex items-center gap-2 border-t px-5 py-4 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <span className={cn("size-2 rounded-full bg-muted-foreground/40", status && STATUS_COLOR[status])} />
          {status ? `System ${status}` : "Checking…"}
          {status && status !== "ok" && <span className="ml-auto underline">Troubleshoot</span>}
        </Link>
      </aside>
      <main className="min-w-0 flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  );
}
