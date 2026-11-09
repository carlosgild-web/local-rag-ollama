import { RotateCcw, X } from "lucide-react";
import type { Job } from "@/api/types";
import { EmptyState, ErrorNote, JOB_LABEL, JobStatusBadge, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useCancelJob, useJobs, useRetryJob } from "@/hooks/queries";
import { useSystemStatus } from "@/hooks/useSystemStatus";
import { formatDate } from "@/lib/utils";

export default function Queue() {
  const jobs = useJobs();
  const retry = useRetryJob();
  const cancel = useCancelJob();
  const system = useSystemStatus();

  return (
    <>
      <PageHeader
        title="Queue"
        description="Background jobs run one at a time. Failed jobs retry automatically, then can be retried by hand."
      />
      <div className="space-y-4 px-8 py-6">
        <ErrorNote error={jobs.error ?? retry.error ?? cancel.error} />
        {jobs.data?.length === 0 && <EmptyState>The queue is empty.</EmptyState>}
        {jobs.data && jobs.data.length > 0 && (
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 font-medium">Job</th>
                  <th className="px-4 py-2 font-medium">Status</th>
                  <th className="w-1/4 px-4 py-2 font-medium">Progress</th>
                  <th className="px-4 py-2 font-medium">Updated</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {jobs.data.map((job) => (
                  <JobRow
                    key={job.id}
                    job={job}
                    onRetry={() => retry.mutate(job.id)}
                    onCancel={() => cancel.mutate(job.id)}
                    retryBlocked={system.processBlocked}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

function JobRow({
  job,
  onRetry,
  onCancel,
  retryBlocked,
}: {
  job: Job;
  onRetry: () => void;
  onCancel: () => void;
  retryBlocked: string | null;
}) {
  const subject = job.subject ?? (job.document_id ? `document ${job.document_id}` : "");
  return (
    <tr className="align-top">
      <td className="px-4 py-3">
        <div className="font-medium">
          #{job.id} {JOB_LABEL[job.job_type] ?? job.job_type}
        </div>
        <div className="text-muted-foreground">{subject}</div>
        {job.error && <div className="mt-1 break-words text-xs text-destructive">{job.error}</div>}
        {job.note && <div className="mt-1 text-xs text-warning">{job.note}</div>}
      </td>
      <td className="px-4 py-3">
        <JobStatusBadge status={job.status} />
        {job.cancel_requested && job.status === "running" && (
          <div className="mt-1 text-xs text-muted-foreground">cancelling…</div>
        )}
        {job.retries > 0 && (
          <div className="mt-1 text-xs text-muted-foreground">retries: {job.retries}</div>
        )}
      </td>
      <td className="px-4 py-3">
        <Progress value={job.progress} className="mt-2" />
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">{formatDate(job.updated_at)}</td>
      <td className="px-4 py-3 text-right">
        {(job.status === "failed" || job.status === "cancelled") && (
          <Button
            variant="outline"
            size="sm"
            onClick={onRetry}
            disabled={!!retryBlocked}
            title={retryBlocked ? `Retry is paused: ${retryBlocked}` : undefined}
          >
            <RotateCcw /> Retry
          </Button>
        )}
        {(job.status === "pending" || (job.status === "running" && !job.cancel_requested)) && (
          <Button variant="ghost" size="sm" onClick={onCancel}>
            <X /> Cancel
          </Button>
        )}
      </td>
    </tr>
  );
}
