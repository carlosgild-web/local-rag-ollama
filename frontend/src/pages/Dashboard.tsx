import { AlertTriangle, CheckCircle2, MessageSquare, Upload, Wrench, XCircle } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { Troubleshooter } from "@/components/Troubleshooter";
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
  // ?troubleshoot=1 opens the panel (the sidebar health indicator links here).
  const [params, setParams] = useSearchParams();
  const troubleshooting = params.get("troubleshoot") === "1";
  const openTroubleshooter = () => setParams({ troubleshoot: "1" });
  const closeTroubleshooter = () => setParams({});
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
        {(health.isError || (health.data && health.data.status !== "ok")) && (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm">
            <AlertTriangle className="size-4 shrink-0 text-warning" />
            <span className="flex-1">
              Something needs attention
              {health.data?.status === "down" ? ": the app can't work until it's fixed." : "."}
            </span>
            <Button size="sm" onClick={openTroubleshooter}>
              <Wrench /> Troubleshoot
            </Button>
          </div>
        )}
        <Troubleshooter open={troubleshooting} onClose={closeTroubleshooter} />

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
