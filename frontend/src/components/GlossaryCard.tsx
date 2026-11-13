import { X } from "lucide-react";
import { useState } from "react";
import { api } from "@/api/client";
import { ErrorNote } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useGlossary, useGlossaryMutation } from "@/hooks/queries";

/** Words people use and the words the documents use (decision 0021). Every
 * question, in the chat and in the portal, is asked with these meanings added. */
export function GlossaryCard() {
  const glossary = useGlossary();
  const [term, setTerm] = useState("");
  const [means, setMeans] = useState("");
  const [sample, setSample] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const add = useGlossaryMutation((body: { term: string; means: string }) => api.addGlossaryTerm(body));
  const remove = useGlossaryMutation((id: number) => api.deleteGlossaryTerm(id));
  const loadDemo = useGlossaryMutation(() => api.loadDemoGlossary());
  const rows = glossary.data ?? [];

  const submit = () =>
    add.mutate(
      { term: term.trim(), means: means.trim() },
      {
        onSuccess: () => {
          setTerm("");
          setMeans("");
        },
      },
    );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Glossary</CardTitle>
        <CardDescription>
          Words people ask with, and the words your documents use for them. A question about <q>vacation</q> is asked
          as <q>vacation (PTO, paid time off)</q>, so the search and the model find the PTO policy. It applies to every
          shelf, in the chat and in the portal.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {rows.length > 0 ? (
          <ul className="flex flex-wrap gap-2">
            {rows.map((row) => (
              <li key={row.id} className="flex items-center gap-1 rounded-md border px-2 py-1">
                <span className="font-medium">{row.term}</span>
                <span className="text-muted-foreground">→ {row.means}</span>
                <button
                  type="button"
                  aria-label={`Remove ${row.term}`}
                  className="ml-1 text-muted-foreground hover:text-destructive"
                  onClick={() => remove.mutate(row.id)}
                >
                  <X className="size-3.5" />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          glossary.isSuccess && (
            <p className="text-muted-foreground">
              Empty.{" "}
              <button type="button" className="underline" onClick={() => loadDemo.mutate(undefined)}>
                Add the demo company's words
              </button>
            </p>
          )
        )}
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <Input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Word people use" className="w-44" />
          <span className="text-muted-foreground">means</span>
          <Input
            value={means}
            onChange={(e) => setMeans(e.target.value)}
            placeholder="Words in the documents"
            className="w-64"
          />
          <Button type="submit" size="sm" disabled={!term.trim() || !means.trim() || add.isPending}>
            Add
          </Button>
        </form>
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            if (sample.trim()) setPreview((await api.glossaryPreview(sample.trim())).expanded);
          }}
        >
          <Input
            value={sample}
            onChange={(e) => {
              setSample(e.target.value);
              setPreview(null);
            }}
            placeholder="Try a question"
            className="w-72"
          />
          <Button type="submit" size="sm" variant="outline" disabled={!sample.trim()}>
            Show as asked
          </Button>
          {preview !== null && <span className="text-muted-foreground">{preview}</span>}
        </form>
        <ErrorNote error={glossary.error ?? add.error ?? remove.error ?? loadDemo.error} />
      </CardContent>
    </Card>
  );
}
