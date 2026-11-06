import { Loader2, MessageSquarePlus, Send, Square, ThumbsDown, ThumbsUp } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import type { Message, Source } from "@/api/types";
import { CitedAnswer, SourceList } from "@/components/CitedAnswer";
import { ErrorNote } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { useCollections, useFeedback, useSession, useSessions } from "@/hooks/queries";
import { useChatStream } from "@/hooks/useChatStream";
import { cn, formatDate } from "@/lib/utils";

export default function Chat() {
  const params = useParams();
  const navigate = useNavigate();
  const sessionId = params.sessionId ? Number(params.sessionId) : null;

  const sessions = useSessions();
  const session = useSession(sessionId);
  const collections = useCollections();
  const shelves = collections.data ?? [];
  // The shelf to search: the open session's, else the one used last.
  const [chosen, setChosen] = useState<number | undefined>(() => {
    const stored = Number(localStorage.getItem(LAST_SHELF_KEY));
    return Number.isFinite(stored) && stored > 0 ? stored : undefined;
  });
  const sessionShelf = sessionId === null ? undefined : session.data?.collection_id;
  useEffect(() => {
    if (sessionShelf != null) setChosen(sessionShelf);
  }, [sessionShelf]);
  const shelfId = shelves.some((c) => c.id === chosen)
    ? chosen
    : shelves.length === 1
      ? shelves[0].id
      : undefined;
  // An open session whose shelf was rebuilt: the server follows it to the new copy.
  const needsShelfChoice = shelfId === undefined && sessionId === null && shelves.length > 1;
  const chooseShelf = (id: number) => {
    setChosen(id);
    localStorage.setItem(LAST_SHELF_KEY, String(id));
  };
  const [question, setQuestion] = useState("");

  const onSession = useCallback((id: number) => navigate(`/chat/${id}`, { replace: true }), [navigate]);
  const { pending, ask, stop, reset, isStreaming } = useChatStream(onSession);

  const bottom = useRef<HTMLDivElement>(null);
  const messages = sessionId === null ? [] : (session.data?.messages ?? []);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, pending?.answer]);

  const submit = () => {
    const text = question.trim();
    if (!text || isStreaming || needsShelfChoice || shelves.length === 0) return;
    setQuestion("");
    ask(text, sessionId, shelfId);
  };

  return (
    <div className="flex h-full">
      <aside className="flex w-64 shrink-0 flex-col border-r">
        <div className="p-3">
          <Button
            variant="outline"
            className="w-full"
            onClick={() => {
              reset();
              navigate("/chat");
            }}
          >
            <MessageSquarePlus /> New chat
          </Button>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {sessions.data?.map((s) => (
            <Link
              key={s.id}
              to={`/chat/${s.id}`}
              className={cn(
                "block rounded-md px-3 py-2 text-sm hover:bg-muted",
                s.id === sessionId && "bg-muted font-medium",
              )}
            >
              <div className="truncate">{s.title}</div>
              <div className="text-xs font-normal text-muted-foreground">{formatDate(s.created_at)}</div>
            </Link>
          ))}
          {sessions.data?.length === 0 && (
            <p className="px-3 py-2 text-xs text-muted-foreground">No conversations yet.</p>
          )}
        </nav>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl space-y-6 px-6 py-8">
            {messages.length === 0 && !pending && <Welcome />}
            <ErrorNote error={session.error} />
            {messages.map((m) => (
              <MessageView key={m.id} message={m} sessionId={sessionId} />
            ))}
            {pending && (
              <>
                {/* A new session loads with the question already saved; don't show it twice. */}
                {!endsWithQuestion(messages, pending.question) && <UserBubble text={pending.question} />}
                <AssistantBubble
                  content={pending.answer}
                  sources={pending.sources}
                  streaming={pending.status === "streaming"}
                  idleText={
                    pending.status === "stopped"
                      ? "Stopped before the answer started."
                      : pending.status === "error"
                        ? "No answer."
                        : undefined
                  }
                  footer={
                    pending.status === "stopped" && (
                      <p className="mt-2 text-xs text-muted-foreground">Stopped. The partial answer is saved.</p>
                    )
                  }
                />
                {pending.error && <ErrorNote error={pending.error} />}
              </>
            )}
            <div ref={bottom} />
          </div>
        </div>

        <div className="border-t bg-background px-6 py-4">
          <div className="mx-auto max-w-3xl space-y-2">
            <div className="flex items-end gap-2">
              <Textarea
                rows={2}
                value={question}
                placeholder="Ask about your documents… (Enter to send, Shift+Enter for a new line)"
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    submit();
                  }
                }}
                className="resize-none"
              />
              {isStreaming ? (
                <Button variant="outline" size="icon" className="size-10" title="Stop" onClick={stop}>
                  <Square />
                </Button>
              ) : (
                <Button
                  size="icon"
                  className="size-10"
                  title="Send"
                  onClick={submit}
                  disabled={!question.trim() || needsShelfChoice || shelves.length === 0}
                >
                  <Send />
                </Button>
              )}
            </div>
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Answers use only your documents and cite them. Each question is answered on its own.</span>
              {collections.isSuccess && shelves.length === 0 ? (
                <span className="text-warning">
                  No shelves yet: <Link to="/library" className="underline">upload documents</Link> first.
                </span>
              ) : (
                <label className={cn("flex items-center gap-1.5", needsShelfChoice && "text-warning")}>
                  {needsShelfChoice ? "Choose a shelf:" : "Shelf:"}
                  <select
                    className="rounded border bg-background px-1 py-0.5 text-foreground"
                    value={shelfId ?? ""}
                    onChange={(e) => chooseShelf(Number(e.target.value))}
                  >
                    {shelfId === undefined && <option value="">—</option>}
                    {shelves.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

const LAST_SHELF_KEY = "chat.lastShelf";

function endsWithQuestion(messages: Message[], question: string) {
  const last = messages.at(-1);
  return last?.role === "user" && last.content === question;
}

function Welcome() {
  return (
    <div className="py-16 text-center">
      <h2 className="text-lg font-semibold">Ask your documents</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Answers come only from the files in your <Link to="/library" className="underline">library</Link>,
        with numbered citations. If the answer isn't there, it says so.
      </p>
    </div>
  );
}

function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">
        {text}
      </div>
    </div>
  );
}

function AssistantBubble({
  content,
  sources,
  streaming,
  idleText,
  footer,
}: {
  content: string;
  sources: Source[];
  streaming?: boolean;
  /** Shown instead of the spinner when there is no answer and none is coming. */
  idleText?: string;
  footer?: ReactNode;
}) {
  const [highlighted, setHighlighted] = useState<number | null>(null);
  const toggle = (rank: number) => setHighlighted((h) => (h === rank ? null : rank));
  return (
    <div className="max-w-[92%] rounded-2xl rounded-bl-sm border bg-muted/30 px-4 py-3">
      {content ? (
        <CitedAnswer content={content} sources={sources} highlighted={highlighted} onCite={toggle} />
      ) : idleText ? (
        <p className="text-sm text-muted-foreground">{idleText}</p>
      ) : (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          {sources.length ? "Writing the answer…" : "Searching your documents…"}
        </div>
      )}
      {streaming && content && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-foreground/60 align-middle" />}
      <SourceList sources={sources} highlighted={highlighted} onSelect={toggle} />
      {footer}
    </div>
  );
}

function MessageView({ message, sessionId }: { message: Message; sessionId: number | null }) {
  const feedback = useFeedback(sessionId);
  if (message.role === "user") return <UserBubble text={message.content} />;
  const vote = message.feedback?.thumbs_up;
  return (
    <AssistantBubble
      content={message.content}
      sources={message.sources}
      footer={
        <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
          <Button
            variant="ghost"
            size="icon"
            className={cn("size-7", vote === true && "text-success")}
            title="Helpful"
            onClick={() => feedback.mutate({ messageId: message.id, thumbsUp: true })}
          >
            <ThumbsUp />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className={cn("size-7", vote === false && "text-destructive")}
            title="Not helpful"
            onClick={() => feedback.mutate({ messageId: message.id, thumbsUp: false })}
          >
            <ThumbsDown />
          </Button>
          <span className="ml-auto">
            {message.rag_profile_id !== null && `profile #${message.rag_profile_id} · `}
            {formatDate(message.created_at)}
          </span>
        </div>
      }
    />
  );
}
