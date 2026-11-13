import { useState } from "react";
import type { EvalCase, EvalCaseIn } from "@/api/types";
import { ErrorNote } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { useCollections, useDocuments } from "@/hooks/queries";

const ALTERNATIVES = " | ";

const EMPTY: EvalCaseIn = {
  question: "",
  shelf: null,
  expected_sources: [],
  required_facts: [],
  expect_not_found: false,
  kind: "",
  variant_group: null,
  expected_answer_notes: null,
};

const lines = (text: string) =>
  text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

/** Add or edit one golden-set question. Facts are one per line, with
 * alternatives separated by "|": "6 pm | 6:00" accepts either. */
export function CaseEditor({
  open,
  initial,
  saving,
  error,
  onSave,
  onClose,
}: {
  open: boolean;
  initial: EvalCase | null;
  saving: boolean;
  error: unknown;
  onSave: (body: EvalCaseIn) => void;
  onClose: () => void;
}) {
  const start = initial ?? EMPTY;
  const [question, setQuestion] = useState(start.question);
  const [shelf, setShelf] = useState(start.shelf ?? "");
  const [notFound, setNotFound] = useState(start.expect_not_found);
  const [sources, setSources] = useState(start.expected_sources.join("\n"));
  const [facts, setFacts] = useState(start.required_facts.map((g) => g.join(ALTERNATIVES)).join("\n"));
  const [kind, setKind] = useState(start.kind);
  const [group, setGroup] = useState(start.variant_group ?? "");
  const [notes, setNotes] = useState(start.expected_answer_notes ?? "");
  const collections = useCollections();
  const documents = useDocuments();
  const filenames = [...new Set((documents.data ?? []).map((d) => d.filename))].sort();

  const save = () =>
    onSave({
      question: question.trim(),
      shelf: shelf || null,
      expect_not_found: notFound,
      expected_sources: notFound ? [] : lines(sources),
      required_facts: notFound ? [] : lines(facts).map((line) => line.split("|").map((alt) => alt.trim())),
      kind: kind.trim(),
      variant_group: group.trim() || null,
      expected_answer_notes: notes.trim() || null,
    });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={initial ? "Edit question" : "Add a question"}
      description="What a good answer to this question needs. Runs check answers against it."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={save} disabled={saving || !question.trim()}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </>
      }
    >
      <div className="space-y-4 text-sm">
        <Field label="Question">
          <Textarea value={question} onChange={(e) => setQuestion(e.target.value)} rows={2} autoFocus />
        </Field>
        <Field label="Shelf to search">
          <select
            value={shelf}
            onChange={(e) => setShelf(e.target.value)}
            className="h-9 w-full rounded-md border bg-background px-2"
          >
            <option value="">All shelves</option>
            {(collections.data ?? []).map((c) => (
              <option key={c.id} value={c.name}>
                {c.name}
              </option>
            ))}
          </select>
        </Field>
        <label className="flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={notFound}
            onChange={(e) => setNotFound(e.target.checked)}
          />
          <span>
            The answer isn't on this shelf: the right reply is <q>not found in the documents</q>.
          </span>
        </label>
        {!notFound && (
          <>
            <Field label="Expected files" hint="One per line. A passage from any of them counts as a hit.">
              <Textarea
                value={sources}
                onChange={(e) => setSources(e.target.value)}
                rows={2}
                placeholder="08-customer-faq.txt"
              />
              {filenames.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {filenames
                    .filter((name) => !lines(sources).includes(name))
                    .map((name) => (
                      <button
                        key={name}
                        type="button"
                        onClick={() => setSources((text) => [...lines(text), name].join("\n"))}
                        className="rounded border px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-muted"
                      >
                        + {name}
                      </button>
                    ))}
                </div>
              )}
            </Field>
            <Field
              label="Required facts"
              hint="One fact per line; separate ways of writing it with |, for example: 3-5 | three to five"
            >
              <Textarea value={facts} onChange={(e) => setFacts(e.target.value)} rows={3} />
            </Field>
          </>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Field label="Kind" hint="table, number, spanish…">
            <Input value={kind} onChange={(e) => setKind(e.target.value)} />
          </Field>
          <Field label="Wording group" hint="Same name = same question, other words">
            <Input value={group} onChange={(e) => setGroup(e.target.value)} />
          </Field>
        </div>
        <Field label="Notes">
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
        </Field>
        <ErrorNote error={error} />
      </div>
    </Dialog>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="font-medium">{label}</div>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
