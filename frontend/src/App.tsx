import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { PageGate } from "@/components/Paused";
import Chat from "@/pages/Chat";
import Collections from "@/pages/Collections";
import Dashboard from "@/pages/Dashboard";
import Library from "@/pages/Library";
import Queue from "@/pages/Queue";

// The employee portal (decision 0010) is its own bundle, with its own fonts.
const PortalLayout = lazy(() => import("@/portal/PortalLayout"));
const PortalHome = lazy(() => import("@/portal/PortalHome"));
const LunaPage = lazy(() => import("@/portal/LunaPage"));

export default function App() {
  return (
    <Routes>
      <Route
        path="intranet"
        element={
          <Suspense fallback={<div className="h-full bg-[#121735]" />}>
            <PortalLayout />
          </Suspense>
        }
      >
        <Route index element={<PortalHome />} />
        <Route path="luna" element={<LunaPage />} />
        <Route path="*" element={<Navigate to="/intranet" replace />} />
      </Route>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="library" element={<PageGate what="The Library"><Library /></PageGate>} />
        <Route path="collections" element={<PageGate what="Collections"><Collections /></PageGate>} />
        <Route path="queue" element={<PageGate what="The Queue"><Queue /></PageGate>} />
        {/* One route, so starting a new chat keeps the page (and its stream) mounted. */}
        <Route path="chat/:sessionId?" element={<PageGate what="Chat"><Chat /></PageGate>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
