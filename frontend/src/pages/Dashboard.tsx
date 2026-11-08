import { Building2, CheckCircle2, ExternalLink, MessageSquare, Upload, Wrench, XCircle } from "lucide-react";
import { Link } from "react-router-dom";
import { useTroubleshooter } from "@/components/TroubleshooterContext";
import type { ComponentHealth } from "@/api/types";
import { ErrorNote, JOB_LABEL, JobStatusBadge, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  isActiveJob,
  useCollections,
  useDocuments,
  useHealth,
  useJobs,
  usePortalSessions,
  useProfiles,
  useSessions,
} from "@/hooks/queries";
import { formatDate } from "@/lib/utils";

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
