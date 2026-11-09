import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { Session, Source } from "@/api/types";
import { useSession } from "@/hooks/queries";
import { type PendingAnswer, useChatStream } from "@/hooks/useChatStream";
import { useLang } from "./i18n";

/**
 * One conversation with Luna, shared by the floating bubble and the full
 * page. The stream lives here, above both, so switching views mid-answer
 * doesn't cut the answer off.
 */

const CURRENT_KEY = "hl-luna-session";
const RECENT_KEY = "hl-luna-recent";
const RECENT_MAX = 12;

export interface RecentChat {
  id: number;
  title: string;
}

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage blocked: the chat still works, it just isn't remembered
  }
}

interface LunaState {
  sessionId: number | null;
  session: Session | undefined;
  sessionLoading: boolean;
  pending: PendingAnswer | null;
  isStreaming: boolean;
  recent: RecentChat[];
  ask: (question: string) => void;
  stop: () => void;
  newChat: () => void;
  openChat: (id: number) => void;
  bubbleOpen: boolean;
  setBubbleOpen: (open: boolean) => void;
}

const LunaContext = createContext<LunaState | null>(null);

export function LunaProvider({ children }: { children: ReactNode }) {
  const { lang } = useLang();
  const [sessionId, setSessionId] = useState<number | null>(() => read<number | null>(CURRENT_KEY, null));
  const [recent, setRecent] = useState<RecentChat[]>(() => read<RecentChat[]>(RECENT_KEY, []));
  const [bubbleOpen, setBubbleOpen] = useState(false);
  const lastQuestion = useRef("");

  const session = useSession(sessionId);
  // A remembered conversation that no longer exists (a fresh data folder):
  // start over instead of showing an error.
  useEffect(() => {
    if (session.isError && sessionId !== null) {
      setSessionId(null);
      write(CURRENT_KEY, null);
    }
  }, [session.isError, sessionId]);

  const onSession = useCallback((id: number) => {
    setSessionId(id);
    write(CURRENT_KEY, id);
    setRecent((list) => {
      const title = lastQuestion.current.slice(0, 80);
      const next = [{ id, title }, ...list.filter((c) => c.id !== id)].slice(0, RECENT_MAX);
      write(RECENT_KEY, next);
      return next;
    });
  }, []);

  const stream = useChatStream(onSession);

  const ask = useCallback(
    (question: string) => {
      const text = question.trim();
      if (!text) return;
      lastQuestion.current = text;
      void stream.ask(text, sessionId, undefined, { channel: "intranet", answer_language: lang });
    },
    [stream, sessionId, lang],
  );

  const newChat = useCallback(() => {
    stream.reset();
    setSessionId(null);
    write(CURRENT_KEY, null);
  }, [stream]);

  const openChat = useCallback(
    (id: number) => {
      stream.reset();
      setSessionId(id);
      write(CURRENT_KEY, id);
    },
    [stream],
  );

  const value = useMemo<LunaState>(
    () => ({
      sessionId,
      session: session.data,
      sessionLoading: session.isLoading,
      pending: stream.pending,
      isStreaming: stream.isStreaming,
      recent,
      ask,
      stop: () => void stream.stop(),
      newChat,
      openChat,
      bubbleOpen,
      setBubbleOpen,
    }),
    [sessionId, session.data, session.isLoading, stream, recent, ask, newChat, openChat, bubbleOpen],
  );

  return <LunaContext.Provider value={value}>{children}</LunaContext.Provider>;
}

export function useLuna(): LunaState {
  const state = useContext(LunaContext);
  if (!state) throw new Error("useLuna needs a LunaProvider");
  return state;
}

// The prompt asks for exactly "not found in the documents"; with the answer
// language set to Spanish the model sometimes translates it. Only short
// replies count, so an answer that merely mentions the phrase is kept.
const NOT_FOUND = [
  /not found in the documents/i,
  /no se encuentr\w* en los documentos/i,
  /no (?:est[aá]|aparece)\w* en los documentos/i,
  /no (?:se )?encontr\w* en los documentos/i,
];

export function isNotFound(answer: string): boolean {
  const text = answer.trim();
  return text.length > 0 && text.length < 160 && NOT_FOUND.some((re) => re.test(text));
}

/** "05-holiday-announcement.pdf" → "Holiday announcement";
 * "Hilda & Luna Beadworks - Sample HR Policy.docx" → "Sample HR Policy". */
export function documentTitle(filename: string | null): string {
  if (!filename) return "—";
  const base = filename
    .replace(/\.[a-z0-9]+$/i, "")
    .replace(/^\d+[-_ ]+/, "")
    .replace(/^Hilda\s*&\s*Luna(?: Beadworks)?\s+[-–—]\s+/i, "");
  const spaced = base.includes(" ") ? base : base.replace(/[-_]+/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function sourceKey(s: Source): string {
  return `${s.rank}-${s.chunk_id}`;
}
