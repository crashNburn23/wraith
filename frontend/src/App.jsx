import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import Shell from "./components/Shell";
import { EntityModalProvider } from "./components/EntityModalContext";
import { isAuthenticated } from "./lib/auth";
import ArticleDetail from "./pages/ArticleDetail";
import Bulletin from "./pages/Bulletin";
import Chat from "./pages/Chat";
import FeedbackHistory from "./pages/FeedbackHistory";
import IntelHub from "./pages/IntelHub";
import Login from "./pages/Login";
import Settings from "./pages/Settings";

function AuthLayout() {
  if (!isAuthenticated()) return <Navigate to="/login" replace />;
  return (
    <EntityModalProvider>
      <Shell>
        <Outlet />
      </Shell>
    </EntityModalProvider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<AuthLayout />}>
          <Route path="/" element={<Bulletin />} />
          <Route path="/articles/:id" element={<ArticleDetail />} />
          <Route path="/intel" element={<IntelHub />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/feedback" element={<FeedbackHistory />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
