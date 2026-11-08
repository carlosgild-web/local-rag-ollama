import { ChevronDown, FileText, Loader2, RotateCcw, SendHorizontal, Square, ThumbsDown, ThumbsUp } from "lucide-react";
import { type FormEvent, type KeyboardEvent, type ReactNode, useEffect, useRef, useState } from "react";
import type { Message, Source } from "@/api/types";
import { CitedAnswer } from "@/components/CitedAnswer";
import { useChunk, useFeedback } from "@/hooks/queries";
import { cn } from "@/lib/utils";
import { SUGGESTIONS } from "./content";
import { UI, useT } from "./i18n";
import { LogoMark } from "./Logo";
import { documentTitle, isNotFound, sourceKey, useLuna } from "./luna";

type Variant = "page" | "panel";

/** The conversation with Luna: messages, the streaming answer, and the composer. */
export function LunaChat({ variant, autoFocus = false }: { variant: Variant; autoFocus?: boolean }) {
  const t = useT();
  const luna = useLuna();
  const scroller = useRef<HTMLDivElement>(null);
  const messages = luna.session?.messages ?? [];
  const pending = luna.pending;
  const empty = messages.length === 0 && !pending && !luna.sessionLoading;

  // Follow the answer as it streams in.
  const tokenCount = pending?.answer.length ?? 0;
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, tokenCount, pending?.status]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div
        ref={scroller}
        className={cn("min-h-0 flex-1 overflow-y-auto", variant === "page" ? "px-1 py-6" : "px-4 py-4")}
        aria-live="polite"
      >
        <div className={cn("mx-auto flex flex-col gap-5", variant === "page" && "max-w-3xl")}>
          {empty && <Welcome variant={variant} />}
          {messages.map((m) =>
            m.role === "user" ? (
              <Question key={m.id} text={m.content} />
            ) : (
              <SavedAnswer key={m.id} message={m} sessionId={luna.sessionId} />
            ),
          )}
          {pending && (
            <>
              <Question text={pending.question} />
              <Answer
                content={pending.answer}
                sources={pending.sources}
                streaming={pending.status === "streaming"}
                footer={
                  pending.status === "stopped" ? (
                    <p className="text-xs text-hl-muted">{t(UI.luna.stopped)}</p>
                  ) : pending.status === "error" ? (
                    <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                      <p className="font-semibold">{t(UI.luna.error)}</p>
                      <p>{pending.error}</p>
                      <button
                        type="button"
                        onClick={() => luna.ask(pending.question)}
                        className="mt-2 inline-flex items-center gap-1.5 text-sm font-semibold underline-offset-2 hover:underline"
                      >
                        <RotateCcw className="size-3.5" /> {t(UI.luna.retry)}
                      </button>
                    </div>
                  ) : null
                }
              />
            </>
          )}
        </div>
      </div>
      <Composer variant={variant} autoFocus={autoFocus} />
    </div>
  );
}

function Welcome({ variant }: { variant: Variant }) {
  const t = useT();
  const luna = useLuna();
  return (
    <div className={cn("flex flex-col gap-4", variant === "page" ? "pt-6" : "pt-1")}>
      <div className="flex items-start gap-3">
        <Avatar />
        <p className="rounded-2xl rounded-tl-sm bg-hl-card px-4 py-3 text-[0.95rem] leading-relaxed shadow-sm ring-1 ring-hl-line">
          {t(UI.luna.welcome)}
        </p>
      </div>
      <div className="pl-12">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-hl-muted">
          {t(UI.luna.suggestions)}
        </p>
        <ul className="flex flex-wrap gap-2">
          {SUGGESTIONS.map((s) => (
            <li key={s.en}>
              <button
                type="button"
                onClick={() => luna.ask(t(s))}
                className="rounded-full border border-hl-line bg-hl-card px-3.5 py-1.5 text-left text-sm text-hl-ink transition-colors hover:border-hl-cobalt hover:bg-hl-cobalt-soft"
              >
                {t(s)}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function Avatar() {
  return (
    <span className="grid size-9 shrink-0 place-items-center rounded-full bg-hl-night text-hl-moon shadow-sm">
      <LogoMark className="size-7" />
    </span>
  );
}

function Question({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-tr-sm bg-hl-cobalt px-4 py-2.5 text-[0.95rem] leading-relaxed text-white">
        {text}
      </p>
    </div>
  );
}

function SavedAnswer({ message, sessionId }: { message: Message; sessionId: number | null }) {
  return (
    <Answer
      content={message.content}
      sources={message.sources}
      streaming={false}
      footer={<Feedback message={message} sessionId={sessionId} />}
    />
  );
}

function Answer({
  content,
  sources,
  streaming,
  footer,
}: {
  content: string;
  sources: Source[];
  streaming: boolean;
  footer?: ReactNode;
}) {
  const t = useT();
  const [open, setOpen] = useState<number | null>(null);
  const notFound = !streaming && isNotFound(content);

  return (
    <div className="flex items-start gap-3">
      <Avatar />
      <div className="min-w-0 flex-1 rounded-2xl rounded-tl-sm bg-hl-card px-4 py-3 shadow-sm ring-1 ring-hl-line">
        {notFound ? (
          <div>
            <p className="font-semibold">{t(UI.luna.notFoundTitle)}</p>
            <p className="mt-1 text-sm text-hl-muted">{t(UI.luna.notFoundBody)}</p>
          </div>
        ) : content ? (
          <CitedAnswer
            content={content}
            sources={sources}
            highlighted={open}
            onCite={(rank) => setOpen((r) => (r === rank ? null : rank))}
          />
        ) : (
          <p className="flex items-center gap-2 text-sm text-hl-muted">
            <Loader2 className="size-4 animate-spin" /> {t(UI.luna.thinking)}
          </p>
        )}
        {streaming && content && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-hl-cobalt align-middle" />}

        {!notFound && sources.length > 0 && (
          <Sources sources={sources} open={open} onToggle={(rank) => setOpen((r) => (r === rank ? null : rank))} />
        )}
        {footer && <div className="mt-3">{footer}</div>}
      </div>
    </div>
  );
}

function Sources({
  sources,
  open,
  onToggle,
}: {
  sources: Source[];
  open: number | null;
  onToggle: (rank: number) => void;
}) {
  const t = useT();
  return (
    <div className="mt-3 border-t border-hl-line pt-3">
      <p className="mb-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-hl-muted">{t(UI.luna.sources)}</p>
      <ol className="flex flex-col gap-1">
        {sources.map((s) => (
          <li key={sourceKey(s)}>
            <button
              type="button"
              onClick={() => onToggle(s.rank)}
              aria-expanded={open === s.rank}
              className={cn(
                "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition-colors hover:bg-hl-cobalt-soft",
                open === s.rank && "bg-hl-cobalt-soft",
              )}
            >
              <span className="grid size-5 shrink-0 place-items-center rounded bg-hl-cobalt/15 text-[11px] font-bold text-hl-cobalt">
                {s.rank}
              </span>
              <FileText className="size-4 shrink-0 text-hl-muted" />
              <span className="min-w-0 truncate">
                {documentTitle(s.filename)}
                {s.page ? <span className="text-hl-muted"> · {t(UI.luna.page)} {s.page}</span> : null}
              </span>
              <ChevronDown
                className={cn("ml-auto size-4 shrink-0 text-hl-muted transition-transform", open === s.rank && "rotate-180")}
              />
            </button>
            {open === s.rank && <Passage chunkId={s.chunk_id} />}
          </li>
        ))}
      </ol>
    </div>
  );
}

/** The exact passage a citation points at, so the answer can be checked. */
function Passage({ chunkId }: { chunkId: number }) {
  const t = useT();
  const chunk = useChunk(chunkId);
  return (
    <div className="mx-2 mb-1 mt-1 rounded-lg bg-hl-paper px-3 py-2 text-sm ring-1 ring-hl-line">
      {chunk.isLoading && (
        <span className="flex items-center gap-1.5 text-hl-muted">
          <Loader2 className="size-3.5 animate-spin" /> {t(UI.luna.loadingPassage)}
        </span>
      )}
      {chunk.isError && <span className="text-red-700">{t(UI.luna.passageError)}</span>}
      {chunk.data && (
        <p className="max-h-56 overflow-y-auto whitespace-pre-wrap leading-relaxed text-hl-ink/90">{chunk.data.text}</p>
      )}
    </div>
  );
}

function Feedback({ message, sessionId }: { message: Message; sessionId: number | null }) {
  const t = useT();
  const feedback = useFeedback(sessionId);
  const given = message.feedback;
  if (given) {
    return <p className="text-xs text-hl-muted">{t(UI.luna.thanks)}</p>;
  }
  return (
    <div className="flex items-center gap-1 text-xs text-hl-muted">
      <span className="mr-1">{t(UI.luna.helpful)}</span>
      {[
        { up: true, Icon: ThumbsUp, label: t(UI.luna.yes) },
        { up: false, Icon: ThumbsDown, label: t(UI.luna.no) },
      ].map(({ up, Icon, label }) => (
        <button
          key={String(up)}
          type="button"
          title={label}
          aria-label={label}
          disabled={feedback.isPending}
          onClick={() => feedback.mutate({ messageId: message.id, thumbsUp: up })}
          className="grid size-7 place-items-center rounded-full transition-colors hover:bg-hl-cobalt-soft hover:text-hl-cobalt"
        >
          <Icon className="size-3.5" />
        </button>
      ))}
    </div>
  );
}

function Composer({ variant, autoFocus }: { variant: Variant; autoFocus: boolean }) {
  const t = useT();
  const luna = useLuna();
  const [text, setText] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (autoFocus) input.current?.focus();
  }, [autoFocus]);

  // Grow with the text, up to a few lines.
  useEffect(() => {
    const el = input.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [text]);

  const send = (event?: FormEvent) => {
    event?.preventDefault();
    if (!text.trim() || luna.isStreaming) return;
    luna.ask(text);
    setText("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) send(event);
  };

  return (
    <form
      onSubmit={send}
      className={cn("border-t border-hl-line bg-hl-card", variant === "page" ? "px-1 pb-2 pt-3" : "px-3 pb-3 pt-3")}
    >
      <div className={cn("mx-auto", variant === "page" && "max-w-3xl")}>
        <div className="flex items-end gap-2 rounded-2xl bg-hl-paper p-1.5 ring-1 ring-hl-line focus-within:ring-2 focus-within:ring-hl-cobalt">
          <label htmlFor={`luna-input-${variant}`} className="sr-only">
            {t(UI.luna.placeholder)}
          </label>
          <textarea
            id={`luna-input-${variant}`}
            ref={input}
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={t(UI.luna.placeholder)}
            maxLength={4000}
            className="max-h-40 min-h-10 flex-1 resize-none bg-transparent px-3 py-2 text-[0.95rem] outline-none placeholder:text-hl-muted"
          />
          {luna.isStreaming ? (
            <button
              type="button"
              onClick={luna.stop}
              className="grid size-10 shrink-0 place-items-center rounded-xl bg-hl-night text-white transition-opacity hover:opacity-85"
              aria-label={t(UI.luna.stop)}
              title={t(UI.luna.stop)}
            >
              <Square className="size-4 fill-current" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!text.trim()}
              className="grid size-10 shrink-0 place-items-center rounded-xl bg-hl-cobalt text-white transition-opacity hover:opacity-90 disabled:opacity-40"
              aria-label={t(UI.luna.send)}
              title={t(UI.luna.send)}
            >
              <SendHorizontal className="size-4" />
            </button>
          )}
        </div>
        <p className="mt-1.5 px-2 text-[11px] text-hl-muted">{t(UI.luna.disclaimer)}</p>
      </div>
    </form>
  );
}
