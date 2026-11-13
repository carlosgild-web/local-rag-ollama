import { useState } from "react";
import type { AuditEntry } from "@/api/types";
import { EmptyState, ErrorNote, PageHeader } from "@/components/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAudit } from "@/hooks/queries";
import { formatDate } from "@/lib/utils";

const PAGE = 100;

/** Plain words for the actions the service layer records (invariant 7). */
const ACTIONS: Record<string, string> = {
  upload: "Upload",
  edit: "Edit",
  rollback: "Rollback",
  delete: "Moved to trash",
  restore: "Restore",
  purge: "Deleted permanently",
  reindex: "Reindex",
  intake_confirm: "Upload confirmed",
  collection_create: "Shelf created",
  collection_portal_visibility: "Portal visibility",
  settings_change: "Settings change",
  model_pull: "Model pulled",
  model_delete: "Model deleted",
  backup: "Backup",
  backup_delete: "Backup deleted",
  demo_seed: "Demo loaded",
  job_cancel: "Job cancelled",
  job_retry: "Job retried",
};

const ENTITY_TYPES: Record<string, string> = {
  document: "Documents",
  collection: "Shelves",
  rag_profile: "Profiles",
  backup: "Backups",
  model: "Models",
  job: "Jobs",
  intake: "Uploads",
};

const DESTRUCTIVE = new Set(["purge", "delete", "backup_delete", "model_delete"]);

export default function Audit() {
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const audit = useAudit({ action: action || undefined, entity_type: entityType || undefined, limit });
  const rows = audit.data ?? [];
  const filter = (set: (value: string) => void) => (value: string) => {
    set(value);
    setLimit(PAGE);
  };

  return (
    <>
      <PageHeader
        title="Audit"
        description="Every upload, edit, rollback, delete, purge, reindex and settings change, newest first. Nothing here can be edited."
      />
      <div className="space-y-4 px-8 py-6">
        <div className="flex flex-wrap items-center gap-2">
          <FilterSelect label="Action" value={action} onChange={filter(setAction)} options={ACTIONS} all="All actions" />
          <FilterSelect
            label="Item type"
            value={entityType}
            onChange={filter(setEntityType)}
            options={ENTITY_TYPES}
            all="All items"
          />
        </div>

        <ErrorNote error={audit.error} />
        {audit.isSuccess && rows.length === 0 ? (
          <EmptyState>{action || entityType ? "No entries match." : "Nothing recorded yet."}</EmptyState>
        ) : (
          <div className="overflow-hidden rounded-lg border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-4 py-2 font-medium">When</th>
                  <th className="px-4 py-2 font-medium">Action</th>
                  <th className="px-4 py-2 font-medium">Item</th>
                  <th className="px-4 py-2 font-medium">Detail</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {rows.map((entry) => (
                  <AuditRow key={entry.id} entry={entry} />
                ))}
              </tbody>
            </table>
          </div>
        )}
        {rows.length === limit && (
          <Button variant="outline" size="sm" onClick={() => setLimit((n) => n + PAGE)} disabled={audit.isFetching}>
            Load more
          </Button>
        )}
      </div>
    </>
  );
}

function AuditRow({ entry }: { entry: AuditEntry }) {
  const type = ENTITY_TYPES[entry.entity_type]?.replace(/s$/, "").toLowerCase() ?? entry.entity_type;
  return (
    <tr>
      <td className="whitespace-nowrap px-4 py-2.5 text-muted-foreground">{formatDate(entry.created_at)}</td>
      <td className="whitespace-nowrap px-4 py-2.5">
        <Badge variant={DESTRUCTIVE.has(entry.action) ? "destructive" : "secondary"}>
          {ACTIONS[entry.action] ?? entry.action}
        </Badge>
      </td>
      <td className="whitespace-nowrap px-4 py-2.5 text-muted-foreground">
        {type}
        {entry.entity_id !== null && ` #${entry.entity_id}`}
      </td>
      <td className="px-4 py-2.5">{entry.detail || <span className="text-muted-foreground">–</span>}</td>
    </tr>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
  all,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Record<string, string>;
  all: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-9 rounded-md border bg-background px-2 text-sm"
      aria-label={label}
    >
      <option value="">{all}</option>
      {Object.entries(options).map(([key, text]) => (
        <option key={key} value={key}>
          {text}
        </option>
      ))}
    </select>
  );
}
