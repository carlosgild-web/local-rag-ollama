import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Copy, Download, Headset, Loader2, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import type { SupportTicket } from "@/api/types";
import { ErrorNote } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";

/** "Send to L2 support", simulated: the server builds the report a real
 * integration would send and saves it as a ticket file on this computer.
 * Nothing leaves the machine (CLAUDE.md: no third-party calls at runtime). */
export function SupportTicketForm({ onCancel }: { onCancel: () => void }) {
  const [note, setNote] = useState("");
  const send = useMutation({ mutationFn: () => api.createSupportTicket(note) });
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => box.current?.scrollIntoView({ behavior: "smooth", block: "start" }), []);

  if (send.data) return <TicketSent ticket={send.data} onDone={onCancel} />;

  return (
    <div ref={box} className="mb-5 space-y-3 rounded-lg border bg-muted/40 p-4 text-sm">
      <h3 className="flex items-center gap-2 font-semibold">
        <Headset className="size-4" /> Send the details to L2 support
      </h3>
      <p className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs">
        <span className="font-medium">Simulated:</span> nothing leaves this computer. The app creates the ticket a real
        support integration would send and saves it in the app's data folder, so you can see exactly what would be
        shared.
      </p>
      <div>
        <p className="mb-1 font-medium">What is included</p>
        <ul className="list-disc space-y-0.5 pl-5 text-muted-foreground">
          <li>every troubleshooting check, with its result and details</li>
          <li>app, Python and operating-system versions; the Ollama address and model names</li>
          <li>the last 10 failed jobs and their error messages</li>
          <li>your note below</li>
        </ul>
        <p className="mt-1 text-xs text-muted-foreground">Never included: the text of your documents or chats.</p>
      </div>
      <label className="block space-y-1">
        <span className="font-medium">What were you doing when it went wrong? (optional)</span>
        <Textarea
          rows={3}
          maxLength={2000}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="e.g. I uploaded the HR folder and then the chat stopped answering."
        />
      </label>
      <ErrorNote error={send.error} />
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel} disabled={send.isPending}>
          Cancel
        </Button>
        <Button onClick={() => send.mutate()} disabled={send.isPending}>
          {send.isPending ? <Loader2 className="animate-spin" /> : <Send />} Send to L2 support
        </Button>
      </div>
    </div>
  );
}

function TicketSent({ ticket, onDone }: { ticket: SupportTicket; onDone: () => void }) {
  const [copied, setCopied] = useState(false);
  const json = JSON.stringify(ticket.report, null, 2);
  const download = () => {
    const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${ticket.ticket_id}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="mb-5 space-y-3 rounded-lg border border-success/40 bg-success/5 p-4 text-sm">
      <h3 className="flex items-center gap-2 font-semibold">
        <CheckCircle2 className="size-4 text-success" /> Ticket {ticket.ticket_id} created (simulated)
      </h3>
      <p>
        L2 support would receive {ticket.problems === 0 ? "a report with no problems found" : `${ticket.problems} problem${ticket.problems === 1 ? "" : "s"}`}{" "}
        and your note. Quote the ticket number if you contact them.
      </p>
      <p className="break-all text-xs text-muted-foreground">Saved on this computer: {ticket.saved_to}</p>
      <details>
        <summary className="cursor-pointer text-xs font-medium">Show the report</summary>
        <pre className="mt-2 max-h-64 overflow-auto rounded bg-background p-2 text-xs">{json}</pre>
      </details>
      <div className="flex flex-wrap justify-end gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={async () => {
            await navigator.clipboard.writeText(json);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
        >
          {copied ? <CheckCircle2 className="text-success" /> : <Copy />} Copy report
        </Button>
        <Button variant="outline" size="sm" onClick={download}>
          <Download /> Download
        </Button>
        <Button size="sm" onClick={onDone}>
          Done
        </Button>
      </div>
    </div>
  );
}
