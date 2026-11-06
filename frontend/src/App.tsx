import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
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
        <Route path="library" element={<Library />} />
        <Route path="collections" element={<Collections />} />
        <Route path="queue" element={<Queue />} />
        {/* One route, so starting a new chat keeps the page (and its stream) mounted. */}
        <Route path="chat/:sessionId?" element={<Chat />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
