import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Copy, Download, Headset, Loader2, Send } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";
import { api } from "@/api/client";
import type { SupportDraft, SupportTicket, SupportTicketIn } from "@/api/types";
import { ErrorNote } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { cn, formatDate } from "@/lib/utils";

// ServiceNow's default matrix: priority from impact and urgency.
const PRIORITY: Record<string, string> = {
  "1-1": "1 - Critical", "1-2": "2 - High", "1-3": "3 - Moderate",
  "2-1": "2 - High", "2-2": "3 - Moderate", "2-3": "4 - Low",
  "3-1": "3 - Moderate", "3-2": "4 - Low", "3-3": "5 - Planning",
};
const LEVEL = { 1: "1 - High", 2: "2 - Medium", 3: "3 - Low" } as const;
const IMPACT_HELP: Record<number, string> = {
  1: "The whole team or business can't work",
  2: "Some people or an important part of the app is affected",
  3: "Only me, or a minor inconvenience",
};
const URGENCY_HELP: Record<number, string> = {
  1: "It must be fixed now: work has stopped",
  2: "It should be fixed today",
  3: "It can wait",
};

type Step = "form" | "review" | "done";

/** "Send to L2 support": a service-desk incident like the one a real
 * integration (e.g. ServiceNow) would receive. Simulated: submitting saves
 * it on this computer; nothing is sent anywhere. */
export function ServiceDeskTicket({ open, onBack, onClose }: { open: boolean; onBack: () => void; onClose: () => void }) {
  const draft = useQuery({ queryKey: ["support-draft"], queryFn: api.supportDraft, enabled: open, staleTime: 0 });
  const [step, setStep] = useState<Step>("form");
  const [form, setForm] = useState<SupportTicketIn | null>(null);
  const submit = useMutation({ mutationFn: api.submitSupportTicket, onSuccess: () => setStep("done") });

  useEffect(() => {
    if (draft.data && !form) {
      setForm({
        caller_name: draft.data.environment.user_name,
        impact: draft.data.impact,
        urgency: draft.data.urgency,
        short_description: draft.data.short_description,
        description: "",
      });
    }
  }, [draft.data, form]);

  const reset = () => {
    setStep("form");
    setForm(null);
    submit.reset();
  };

  return (
    <Dialog
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      className="max-w-4xl"
      title={
        <span className="flex items-center gap-2">
          <Headset className="size-5" />
          {step === "done" && submit.data ? `Incident ${submit.data.number}` : "New incident for L2 support"}
          <span className="rounded bg-warning/15 px-2 py-0.5 text-xs font-medium text-warning">simulated</span>
        </span>
      }
      description="Service desk · simulated: nothing leaves this computer. The incident is saved in the app's data folder exactly as it would be sent."
      footer={
        <Footer
          step={step}
          canReview={!!form && form.caller_name.trim() !== "" && form.short_description.trim() !== "" && form.description.trim() !== ""}
          submitting={submit.isPending}
          onBack={() => (step === "review" ? setStep("form") : (reset(), onBack()))}
          onReview={() => setStep("review")}
          onSubmit={() => form && submit.mutate(form)}
          onClose={() => {
            reset();
            onClose();
          }}
        />
      }
    >
      <ErrorNote error={draft.error ?? submit.error} />
      {(draft.isLoading || !form) && !draft.error && (
        <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Collecting the details for support…
        </p>
      )}
      {draft.data && form && step === "form" && <TicketForm draft={draft.data} form={form} onChange={setForm} />}
      {draft.data && form && step === "review" && <TicketReview draft={draft.data} form={form} />}
      {step === "done" && submit.data && <TicketFiled ticket={submit.data} />}
    </Dialog>
  );
}

function Footer({
  step,
  canReview,
  submitting,
  onBack,
  onReview,
  onSubmit,
  onClose,
}: {
  step: Step;
  canReview: boolean;
  submitting: boolean;
  onBack: () => void;
  onReview: () => void;
  onSubmit: () => void;
  onClose: () => void;
}) {
  if (step === "done") return <Button onClick={onClose}>Close</Button>;
  return (
    <>
      <Button variant="outline" className="mr-auto" onClick={onBack} disabled={submitting}>
        <ArrowLeft /> {step === "review" ? "Edit" : "Back to troubleshooting"}
      </Button>
      {step === "form" ? (
        <Button onClick={onReview} disabled={!canReview} title={canReview ? undefined : "Fill in the fields marked *"}>
          Review
        </Button>
      ) : (
        <Button onClick={onSubmit} disabled={submitting}>
          {submitting ? <Loader2 className="animate-spin" /> : <Send />} Submit to service desk
        </Button>
      )}
    </>
  );
}

function Field({ label, required, hint, children, wide }: { label: string; required?: boolean; hint?: string; children: ReactNode; wide?: boolean }) {
  return (
    <label className={cn("block space-y-1", wide && "sm:col-span-2")}>
      <span className="text-xs font-medium text-muted-foreground">
        {label}
        {required && <span className="text-destructive"> *</span>}
      </span>
      {children}
      {hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
    </label>
  );
}

function ReadOnly({ value }: { value: string }) {
  return <div className="flex h-9 items-center truncate rounded-md border bg-muted/60 px-3 text-sm" title={value}>{value}</div>;
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h3 className="border-b pb-1 text-sm font-semibold">{title}</h3>
      {children}
    </section>
  );
}

function TicketForm({ draft, form, onChange }: { draft: SupportDraft; form: SupportTicketIn; onChange: (f: SupportTicketIn) => void }) {
  const set = <K extends keyof SupportTicketIn>(key: K, value: SupportTicketIn[K]) => onChange({ ...form, [key]: value });
  const env = draft.environment;
  const level = (value: number, onPick: (n: number) => void, help: Record<number, string>) => (
    <select
      className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
      value={value}
      onChange={(e) => onPick(Number(e.target.value))}
    >
      {[1, 2, 3].map((n) => (
        <option key={n} value={n}>
          {LEVEL[n as 1 | 2 | 3]}: {help[n]}
        </option>
      ))}
    </select>
  );
  return (
    <div className="space-y-6 text-sm">
      <Section title="Caller and computer">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Caller" required>
            <Input value={form.caller_name} onChange={(e) => set("caller_name", e.target.value)} />
          </Field>
          <Field label="How to reach you" hint="e-mail, phone or extension">
            <Input value={form.contact ?? ""} onChange={(e) => set("contact", e.target.value)} placeholder="e.g. ext. 1234" />
          </Field>
          <Field label="Computer name">
            <ReadOnly value={env.computer_name} />
          </Field>
          <Field label="Best time to contact you">
            <Input
              value={form.best_time_to_contact ?? ""}
              onChange={(e) => set("best_time_to_contact", e.target.value)}
              placeholder="e.g. today after 2 pm"
            />
          </Field>
          <Field label="Configuration item">
            <ReadOnly value={env.configuration_item} />
          </Field>
          <Field label="Operating system">
            <ReadOnly value={env.os} />
          </Field>
        </div>
      </Section>

      <Section title="Classification">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Category">
            <ReadOnly value={`${draft.category} / ${draft.subcategory}`} />
          </Field>
          <Field label="Assignment group">
            <ReadOnly value={draft.assignment_group} />
          </Field>
          <Field label="Impact" hint="Suggested from the checks; change it if needed.">
            {level(form.impact, (n) => set("impact", n), IMPACT_HELP)}
          </Field>
          <Field label="Urgency">{level(form.urgency, (n) => set("urgency", n), URGENCY_HELP)}</Field>
          <Field label="Priority (from impact and urgency)">
            <ReadOnly value={PRIORITY[`${form.impact}-${form.urgency}`]} />
          </Field>
          <Field label="System status found by the checks">
            <ReadOnly value={{ ok: "OK", warn: "Warnings", fail: "Failing" }[draft.system_status]} />
          </Field>
        </div>
      </Section>

      <Section title="What happened">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Short description" required wide>
            <Input maxLength={160} value={form.short_description} onChange={(e) => set("short_description", e.target.value)} />
          </Field>
          <Field label="Describe the problem in your own words" required wide hint="Anything that helps L2: what you were doing, what you saw, what you expected.">
            <Textarea
              rows={4}
              maxLength={4000}
              value={form.description}
              onChange={(e) => set("description", e.target.value)}
              placeholder="e.g. After the patch from yesterday the system is down. The chat says Ollama can't be reached."
            />
          </Field>
          <Field label="When did it start?">
            <Input value={form.started_at ?? ""} onChange={(e) => set("started_at", e.target.value)} placeholder="e.g. this morning around 9:00" />
          </Field>
          <Field label="Who is affected?">
            <Input value={form.users_affected ?? ""} onChange={(e) => set("users_affected", e.target.value)} placeholder="e.g. only me / the whole HR team" />
          </Field>
          <Field label="Recent changes" wide hint="Patches, updates, new documents, a new computer, moved folders…">
            <Input
              value={form.recent_changes ?? ""}
              onChange={(e) => set("recent_changes", e.target.value)}
              placeholder="e.g. Windows update installed yesterday evening"
            />
          </Field>
          <Field label="Steps to reproduce" wide>
            <Textarea
              rows={2}
              value={form.steps_to_reproduce ?? ""}
              onChange={(e) => set("steps_to_reproduce", e.target.value)}
              placeholder="e.g. 1. Open Chat  2. Ask any question  3. The answer never arrives"
            />
          </Field>
        </div>
      </Section>

      <Section title="Attached automatically (work notes)">
        <Problems draft={draft} />
        <p className="text-xs text-muted-foreground">
          Also attached: the full troubleshooting report (diagnostics.json), app {env.app_version}, Python {env.python},
          Ollama at {env.ollama_base_url}, models {env.chat_model} and {env.embedding_model}, and the last failed jobs.
          Never attached: the text of your documents or chats.
        </p>
      </Section>
    </div>
  );
}

function Problems({ draft }: { draft: SupportDraft }) {
  if (draft.problems.length === 0) return <p className="text-muted-foreground">The checks found no problems.</p>;
  return (
    <ul className="space-y-1.5">
      {draft.problems.map((p) => (
        <li key={p.title} className={cn("rounded-md border px-3 py-2", p.status === "fail" ? "border-destructive/30 bg-destructive/5" : "border-warning/30 bg-warning/5")}>
          <span className="font-medium">{p.title}</span>: {p.detail}
        </li>
      ))}
      {draft.simulated_faults.length > 0 && (
        <li className="text-xs text-warning">Simulated faults: {draft.simulated_faults.join(", ")}</li>
      )}
    </ul>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  if (value === undefined || value === null || value === "") return null;
  return (
    <div className="grid grid-cols-[11rem_1fr] gap-3 border-b py-1.5 last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="whitespace-pre-wrap break-words">{value}</dd>
    </div>
  );
}

function TicketReview({ draft, form }: { draft: SupportDraft; form: SupportTicketIn }) {
  const env = draft.environment;
  return (
    <div className="space-y-4 text-sm">
      <p className="rounded-md border border-primary/30 bg-accent px-3 py-2">
        Please check the incident below. <span className="font-medium">Submit to service desk</span> files it with L2
        support (simulated).
      </p>
      <dl>
        <Row label="Caller" value={form.caller_name} />
        <Row label="Contact" value={[form.contact, form.best_time_to_contact].filter(Boolean).join(" · ")} />
        <Row label="Computer" value={`${env.computer_name} (${env.os})`} />
        <Row label="Configuration item" value={env.configuration_item} />
        <Row label="Category" value={`${draft.category} / ${draft.subcategory}`} />
        <Row label="Assignment group" value={draft.assignment_group} />
        <Row label="Impact / urgency" value={`${LEVEL[form.impact as 1 | 2 | 3]} / ${LEVEL[form.urgency as 1 | 2 | 3]}`} />
        <Row label="Priority" value={<span className="font-semibold">{PRIORITY[`${form.impact}-${form.urgency}`]}</span>} />
        <Row label="Short description" value={form.short_description} />
        <Row label="Description" value={form.description} />
        <Row label="Started" value={form.started_at} />
        <Row label="Affected" value={form.users_affected} />
        <Row label="Recent changes" value={form.recent_changes} />
        <Row label="Steps to reproduce" value={form.steps_to_reproduce} />
      </dl>
      <Section title="Work notes">
        <Problems draft={draft} />
      </Section>
    </div>
  );
}

function TicketFiled({ ticket }: { ticket: SupportTicket }) {
  const [copied, setCopied] = useState(false);
  const incident = ticket.incident;
  const json = JSON.stringify(incident, null, 2);
  const download = () => {
    const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${ticket.number}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="space-y-4 text-sm">
      <div className="flex items-start gap-3 rounded-lg border border-success/40 bg-success/5 px-4 py-3">
        <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" />
        <div>
          <p className="font-semibold">Incident {ticket.number} was filed with {incident.assignment_group} (simulated).</p>
          <p className="text-muted-foreground">Quote this number if you contact support about this problem.</p>
        </div>
      </div>
      <dl className="rounded-md border px-3">
        <Row label="Number" value={<span className="font-mono">{ticket.number}</span>} />
        <Row label="State" value={incident.state} />
        <Row label="Priority" value={incident.priority} />
        <Row label="Assignment group" value={incident.assignment_group} />
        <Row label="Opened" value={formatDate(incident.opened_at)} />
        <Row label="Response due by" value={formatDate(incident.response_due)} />
        <Row label="Saved on this computer" value={<span className="break-all text-xs">{ticket.saved_to}</span>} />
      </dl>
      <details>
        <summary className="cursor-pointer text-xs font-medium">Show the full incident as sent</summary>
        <pre className="mt-2 max-h-72 overflow-auto rounded bg-muted p-2 text-xs">{json}</pre>
      </details>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={async () => {
            await navigator.clipboard.writeText(json);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
        >
          {copied ? <CheckCircle2 className="text-success" /> : <Copy />} Copy
        </Button>
        <Button variant="outline" size="sm" onClick={download}>
          <Download /> Download
        </Button>
      </div>
    </div>
  );
}
