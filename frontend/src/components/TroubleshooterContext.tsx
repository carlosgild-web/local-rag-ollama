import { createContext, type ReactNode, useCallback, useContext } from "react";
import { useSearchParams } from "react-router-dom";

interface TroubleshooterControls {
  isOpen: boolean;
  open: () => void;
  close: () => void;
}

const Context = createContext<TroubleshooterControls | null>(null);

/** The troubleshooter can be opened from any page; its state lives in the
 * URL (?troubleshoot=1), so a link or a refresh keeps it open. */
export function TroubleshooterProvider({ children }: { children: ReactNode }) {
  const [params, setParams] = useSearchParams();
  const isOpen = params.get("troubleshoot") === "1";
  const open = useCallback(
    () =>
      setParams((p) => {
        p.set("troubleshoot", "1");
        return p;
      }),
    [setParams],
  );
  const close = useCallback(
    () =>
      setParams((p) => {
        p.delete("troubleshoot");
        return p;
      }),
    [setParams],
  );
  return <Context.Provider value={{ isOpen, open, close }}>{children}</Context.Provider>;
}

export function useTroubleshooter(): TroubleshooterControls {
  const controls = useContext(Context);
  if (!controls) throw new Error("useTroubleshooter must be used inside TroubleshooterProvider");
  return controls;
}
