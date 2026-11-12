import { useState } from "react";
import { Building2, CheckCircle2, Download, ExternalLink, FolderOpen, Globe, Loader2, MessageSquare, Sparkles, Upload, Wrench, XCircle } from "lucide-react";
import { API_BASE } from "@/api/client";
import { Link } from "react-router-dom";
import { useTroubleshooter } from "@/components/TroubleshooterContext";
import type { ComponentHealth } from "@/api/types";
import { ErrorNote, JOB_LABEL, JobStatusBadge, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  isActiveJob,
  useCollections,
  useDemo,
  useDemoFiles,
  useFeedbackSummary,
  useDocuments,
  useHealth,
  useJobs,
  usePortalSessions,
  useProfiles,
  useSeedDemo,
  useSessions,
} from "@/hooks/queries";
import { formatBytes, formatDate } from "@/lib/utils";

const COMPONENTS = [
  ["ollama", "Ollama"],
  ["sqlite", "SQLite"],
  ["vector_store", "Vector store"],
  ["job_worker", "Job worker"],
] as const;

export default function Dashboard() {
  const health = useHealth();
  const { open: openTroubleshooter } = useTroubleshooter();
  const documents = useDocuments();
  const collections = useCollections();
  const sessions = useSessions();
  const jobs = useJobs();
  const profiles = useProfiles();
  const profile = profiles.data?.find((p) => p.name === "default") ?? profiles.data?.[0];

  const stats = [
    { label: "Documents", value: documents.data?.length },
    { label: "Collections", value: collections.data?.length },
    { label: "Chat sessions", value: sessions.data?.length },
    { label: "Jobs in progress", value: jobs.data?.filter(isActiveJob).length },
  ];

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Everything runs locally: Ollama for models, SQLite and Chroma for storage."
        actions={
          <>
            <Button variant="outline" asChild>
              <a href="/site" target="_blank" rel="noreferrer" title="Opens the Hilda & Luna public website in a new tab">
                <Globe /> Company site <ExternalLink className="size-3.5" />
              </a>
            </Button>
            <Button variant="outline" asChild>
              <a href="/intranet" target="_blank" rel="noreferrer" title="Opens the Hilda & Luna employee portal in a new tab">
                <Building2 /> Employee portal <ExternalLink className="size-3.5" />
              </a>
            </Button>
            <Button variant="outline" asChild>
              <Link to="/library">
                <Upload /> Upload
              </Link>
            </Button>
            <Button asChild>
              <Link to="/chat">
                <MessageSquare /> Ask a question
              </Link>
            </Button>
          </>
        }
      />
      <div className="space-y-6 px-8 py-6">
        <ErrorNote error={health.error} />

        <DemoCard onTroubleshoot={openTroubleshooter} />

        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {stats.map((s) => (
            <Card key={s.label}>
              <CardHeader>
                <CardDescription>{s.label}</CardDescription>
                <CardTitle className="text-3xl tabular-nums">{s.value ?? "–"}</CardTitle>
              </CardHeader>
            </Card>
          ))}
        </section>

        <section className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader className="flex-row items-start justify-between">
              <div className="space-y-1">
                <CardTitle>System health</CardTitle>
                <CardDescription>
                  {health.data ? `Overall: ${health.data.status}` : "Checking…"}
                </CardDescription>
              </div>
              <Button variant="outline" size="sm" onClick={openTroubleshooter}>
                <Wrench /> Troubleshoot
              </Button>
            </CardHeader>
            <CardContent>
              <ul className="divide-y">
                {COMPONENTS.map(([key, label]) => (
                  <HealthRow key={key} label={label} component={health.data?.[key]} />
                ))}
              </ul>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Answering with</CardTitle>
              <CardDescription>The active RAG profile used for new answers.</CardDescription>
            </CardHeader>
            <CardContent>
              {profile ? (
                <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
                  <dt className="text-muted-foreground">Profile</dt>
                  <dd>
                    {profile.name} v{profile.version}
                  </dd>
                  <dt className="text-muted-foreground">Chat model</dt>
                  <dd className="font-mono text-xs">{profile.chat_model}</dd>
                  <dt className="text-muted-foreground">Embedding model</dt>
                  <dd className="font-mono text-xs">{profile.embedding_model}</dd>
                  <dt className="text-muted-foreground">Top k</dt>
                  <dd>{profile.retrieval_top_k}</dd>
                  <dt className="text-muted-foreground">Temperature</dt>
                  <dd>{profile.temperature}</dd>
                </dl>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Created automatically with the first question.
                </p>
              )}
            </CardContent>
          </Card>
        </section>

        <EmployeeQuestions />

        <AnswerFeedback />

        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle>Recent jobs</CardTitle>
            <Button variant="ghost" size="sm" asChild>
              <Link to="/queue">View all</Link>
            </Button>
          </CardHeader>
          <CardContent>
            {jobs.data?.length ? (
              <ul className="divide-y text-sm">
                {jobs.data.slice(0, 5).map((job) => (
                  <li key={job.id} className="flex items-center gap-3 py-2">
                    <JobStatusBadge status={job.status} />
                    <span>{JOB_LABEL[job.job_type] ?? job.job_type}</span>
                    <span className="truncate text-muted-foreground">
                      {job.subject ?? ""}
                    </span>
                    <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                      {formatDate(job.updated_at)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No jobs yet. Upload a document to start.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

/**
 * First run: offers to load the demo company while the library is empty, shows
 * its progress, and points to the site and the intranet when it's done.
 */
function DemoCard({ onTroubleshoot }: { onTroubleshoot: () => void }) {
  const demo = useDemo();
  const seed = useSeedDemo();
  // Keep the card up after loading, until the page is left, to show the links.
  const [startedHere, setStartedHere] = useState(false);
  const [showFiles, setShowFiles] = useState(false);
  const status = demo.data;
  if (!status?.available) return null;

  const job = status.job;
  const active = job !== null && isActiveJob(job);
  const failed = startedHere && job?.status === "failed";
  const done = startedHere && job?.status === "completed";
  if (status.documents > 0 && !active && !failed && !done) return null;

  const start = () => {
    setStartedHere(true);
    seed.mutate();
  };
  const result = job?.result as { ingested?: number; skipped?: number } | null;

  return (
    <Card className="border-primary/40 bg-primary/5">
      <CardHeader className="flex-row items-start gap-3">
        <Sparkles className="mt-0.5 size-5 shrink-0 text-primary" />
        <div className="space-y-1">
          <CardTitle>{done ? "The demo company is loaded" : "New here? Load the demo company"}</CardTitle>
          <CardDescription>
            {done
              ? `${result?.ingested ?? 0} documents indexed${result?.skipped ? `, ${result.skipped} already there` : ""}. Open the company's website, sign in as an employee and ask Luna.`
              : "Hilda & Luna Beadworks is a fictional bead maker with 11 documents: a handbook, safety training, a catalog, prices, an FAQ and more. Look through them first if you like; loading them takes a few minutes on a laptop."}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {active && (
          <div className="space-y-1.5">
            <Progress value={job?.progress ?? 0} />
            <p className="text-xs text-muted-foreground">
              {job?.status === "pending" ? "Waiting to start…" : `Indexing… ${Math.round((job?.progress ?? 0) * 100)}%`}
            </p>
          </div>
        )}
        {failed && (
          <p className="text-sm text-destructive">
            Loading stopped: {job?.error ?? "unknown error"}. The troubleshooter can usually tell why, for example a
            missing model.
          </p>
        )}
        <ErrorNote error={seed.error} />
        <div className="flex flex-wrap gap-2">
          {done ? (
            <>
              <Button asChild>
                <a href="/site" target="_blank" rel="noreferrer">
                  <Globe /> Company website <ExternalLink className="size-3.5" />
                </a>
              </Button>
              <Button variant="outline" asChild>
                <a href="/intranet" target="_blank" rel="noreferrer">
                  <Building2 /> Employee portal <ExternalLink className="size-3.5" />
                </a>
              </Button>
            </>
          ) : (
            <Button onClick={start} disabled={active || seed.isPending}>
              {active || seed.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
              {failed ? "Try again" : "Load the demo company"}
            </Button>
          )}
          {failed && (
            <Button variant="outline" onClick={onTroubleshoot}>
              <Wrench /> Troubleshoot
            </Button>
          )}
          <Button variant="outline" onClick={() => setShowFiles((v) => !v)} aria-expanded={showFiles}>
            <FolderOpen /> {showFiles ? "Hide the documents" : "See the documents"}
          </Button>
        </div>
        {showFiles && <DemoFiles loaded={done} />}
      </CardContent>
    </Card>
  );
}

/** The demo company's original documents, grouped by the shelf each loads into. */
function DemoFiles({ loaded }: { loaded: boolean }) {
  const files = useDemoFiles(true);
  const shelves = new Map<string, NonNullable<typeof files.data>>();
  for (const f of files.data ?? []) shelves.set(f.shelf, [...(shelves.get(f.shelf) ?? []), f]);
  return (
    <div className="rounded-md border bg-background">
      <ErrorNote error={files.error} />
      {files.isLoading && <p className="p-3 text-sm text-muted-foreground">Loading the list…</p>}
      <ul className="divide-y text-sm">
        {[...shelves.entries()].map(([shelf, list]) => (
          <li key={shelf} className="px-3 py-2">
            <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Shelf: {shelf}</p>
            <ul className="space-y-1">
              {list.map((f) => {
                const href = `${API_BASE}/demo/files/${encodeURIComponent(f.shelf)}/${encodeURIComponent(f.name)}`;
                return (
                  <li key={f.name} className="flex items-center gap-3">
                    <span className="w-10 shrink-0 rounded bg-muted px-1.5 py-0.5 text-center font-mono text-[11px] uppercase">{f.type}</span>
                    <span className="truncate">{f.name}</span>
                    <span className="ml-auto shrink-0 text-xs text-muted-foreground">{formatBytes(f.size)}</span>
                    <Button variant="ghost" size="sm" asChild className="shrink-0">
                      {f.opens_in_browser ? (
                        <a href={href} target="_blank" rel="noreferrer">
                          Open <ExternalLink className="size-3.5" />
                        </a>
                      ) : (
                        <a href={href}>
                          Download <Download className="size-3.5" />
                        </a>
                      )}
                    </Button>
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ul>
      <p className="border-t px-3 py-2 text-xs text-muted-foreground">
        {loaded
          ? "These are the originals the answers come from. Each one also has an Open original button in the Library."
          : "PDFs and text files open in a new tab; Word files download. They're also in your copy of the project, in backend/demo/hilda-luna. Nothing is indexed until you click Load the demo company."}
      </p>
    </div>
  );
}

/** How answers were rated, and the latest "not helpful" ones: what the documents may be missing. */
function AnswerFeedback() {
  const summary = useFeedbackSummary();
  const s = summary.data;
  const total = s ? s.helpful + s.not_helpful : 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Answer feedback</CardTitle>
        <CardDescription>
          {total === 0
            ? "When people rate answers in Chat or in Luna, the ratings show up here."
            : `${Math.round((100 * (s?.helpful ?? 0)) / total)}% helpful · ${s?.helpful} helpful, ${s?.not_helpful} not helpful`}
        </CardDescription>
      </CardHeader>
      {s && s.recent_not_helpful.length > 0 && (
        <CardContent>
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Latest "not helpful"</p>
          <ul className="divide-y text-sm">
            {s.recent_not_helpful.map((item) => (
              <li key={item.message_id} className="space-y-1 py-2">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{item.question || "(question not found)"}</span>
                  <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                    {item.channel === "intranet" ? "Luna" : "Chat"} · {formatDate(item.created_at)}
                  </span>
                </div>
                <p className="line-clamp-2 text-muted-foreground">{item.answer}</p>
                {item.comment && <p className="italic">“{item.comment}”</p>}
                <div className="flex flex-wrap items-center gap-1">
                  {item.sources.map((f) => (
                    <span key={f} className="rounded bg-muted px-1.5 py-0.5 text-xs">
                      {f}
                    </span>
                  ))}
                  <Link to={`/chat/${item.session_id}`} className="ml-auto text-xs underline">
                    Open the conversation
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        </CardContent>
      )}
    </Card>
  );
}

/** What employees asked Luna in the portal: shows what the documents need to cover. */
function EmployeeQuestions() {
  const sessions = usePortalSessions();
  const list = sessions.data ?? [];
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between">
        <div className="space-y-1">
          <CardTitle>Employee questions</CardTitle>
          <CardDescription>
            Asked to Luna in the employee portal. {list.length > 0 && `${list.length} conversation${list.length === 1 ? "" : "s"}.`}
          </CardDescription>
        </div>
        <Button variant="ghost" size="sm" asChild>
          <a href="/intranet/luna" target="_blank" rel="noreferrer">
            Try Luna <ExternalLink className="size-3.5" />
          </a>
        </Button>
      </CardHeader>
      <CardContent>
        {list.length ? (
          <ul className="divide-y text-sm">
            {list.slice(0, 5).map((s) => (
              <li key={s.id} className="flex items-center gap-3 py-2">
                <MessageSquare className="size-4 shrink-0 text-muted-foreground" />
                <span className="truncate">{s.title}</span>
                <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                  {Math.ceil(s.message_count / 2)} question{s.message_count > 2 ? "s" : ""} · {formatDate(s.created_at)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            No questions yet. Open the employee portal and ask Luna something about the documents.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function HealthRow({ label, component }: { label: string; component?: ComponentHealth }) {
  return (
    <li className="flex items-center gap-3 py-2 text-sm">
      {component === undefined ? (
        <span className="size-4 rounded-full bg-muted" />
      ) : component.ok ? (
        <CheckCircle2 className="size-4 text-success" />
      ) : (
        <XCircle className="size-4 text-destructive" />
      )}
      <span className="font-medium">{label}</span>
      <span className="ml-auto truncate text-muted-foreground">{component?.detail}</span>
    </li>
  );
}
