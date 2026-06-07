import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Shell from "./components/Shell";
import { EntityModalProvider } from "./components/EntityModalContext";
import Bulletin from "./pages/Bulletin";
import ArticleDetail from "./pages/ArticleDetail";
import IntelHub from "./pages/IntelHub";
import Chat from "./pages/Chat";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <EntityModalProvider>
        <Shell>
          <Routes>
            <Route path="/" element={<Bulletin />} />
            <Route path="/articles/:id" element={<ArticleDetail />} />
            <Route path="/intel" element={<IntelHub />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Shell>
      </EntityModalProvider>
    </BrowserRouter>
  );
}
