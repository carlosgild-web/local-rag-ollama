import { lazy, type ReactNode, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { PageGate } from "@/components/Paused";
import Chat from "@/pages/Chat";
import Collections from "@/pages/Collections";
import Dashboard from "@/pages/Dashboard";
import Library from "@/pages/Library";
import Queue from "@/pages/Queue";
import Backups from "@/pages/Backups";
import Audit from "@/pages/Audit";
import Evaluation from "@/pages/Evaluation";
import Inspector from "@/pages/Inspector";

// The employee portal (decision 0010) is its own bundle, with its own fonts.
const PortalLayout = lazy(() => import("@/portal/PortalLayout"));
const PortalHome = lazy(() => import("@/portal/PortalHome"));
const LunaPage = lazy(() => import("@/portal/LunaPage"));
// The company's public website (decision 0011), also its own bundle.
const SiteLayout = lazy(() => import("@/site/SiteLayout"));
const SiteHome = lazy(() => import("@/site/SiteHome"));
const SiteCatalog = lazy(() => import("@/site/SiteCatalog"));
const SiteWholesale = lazy(() => import("@/site/SiteWholesale"));
const SiteHelp = lazy(() => import("@/site/SiteHelp"));
const StaffSignIn = lazy(() => import("@/site/StaffSignIn"));

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
      <Route
        path="site"
        element={
          <Suspense fallback={<div className="h-full bg-[#fbf6ee]" />}>
            <SiteLayout />
          </Suspense>
        }
      >
        <Route index element={<SitePage><SiteHome /></SitePage>} />
        <Route path="catalog" element={<SitePage><SiteCatalog /></SitePage>} />
        <Route path="wholesale" element={<SitePage><SiteWholesale /></SitePage>} />
        <Route path="help" element={<SitePage><SiteHelp /></SitePage>} />
        <Route path="staff" element={<SitePage><StaffSignIn /></SitePage>} />
        <Route path="*" element={<Navigate to="/site" replace />} />
      </Route>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="library" element={<PageGate what="The Library"><Library /></PageGate>} />
        <Route path="collections" element={<PageGate what="Collections"><Collections /></PageGate>} />
        <Route path="queue" element={<PageGate what="The Queue"><Queue /></PageGate>} />
        <Route path="backups" element={<PageGate what="Backups"><Backups /></PageGate>} />
        <Route path="audit" element={<PageGate what="The Audit log"><Audit /></PageGate>} />
        <Route path="evaluation" element={<PageGate what="Evaluation"><Evaluation /></PageGate>} />
        <Route path="inspector" element={<PageGate what="The Retrieval inspector"><Inspector /></PageGate>} />
        {/* One route, so starting a new chat keeps the page (and its stream) mounted. */}
        <Route path="chat/:sessionId?" element={<PageGate what="Chat"><Chat /></PageGate>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

/** Keeps the site's header and footer on screen while a page's chunk loads. */
function SitePage({ children }: { children: ReactNode }) {
  return <Suspense fallback={<div className="min-h-[60vh]" />}>{children}</Suspense>;
}
