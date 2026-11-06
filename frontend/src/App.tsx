import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { PageGate } from "@/components/Paused";
import Chat from "@/pages/Chat";
import Collections from "@/pages/Collections";
import Dashboard from "@/pages/Dashboard";
import Library from "@/pages/Library";
import Queue from "@/pages/Queue";

export default function App() {
  return (
    <Routes>
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
