import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";
import Shell from "./components/Shell";
import { Spinner } from "./components/ui";
import { EntityModalProvider } from "./components/EntityModalContext";
import { isAuthenticated } from "./lib/auth";

const ArticleDetail = lazy(() => import("./pages/ArticleDetail"));
const Bulletin = lazy(() => import("./pages/Bulletin"));
const Chat = lazy(() => import("./pages/Chat"));
const FeedbackHistory = lazy(() => import("./pages/FeedbackHistory"));
const IntelHub = lazy(() => import("./pages/IntelHub"));
const Investigations = lazy(() => import("./pages/Investigations"));
const InvestigationDetail = lazy(() => import("./pages/InvestigationDetail"));
const Login = lazy(() => import("./pages/Login"));
const Settings = lazy(() => import("./pages/Settings"));

function RouteFallback() {
  return <div className="flex justify-center mt-20"><Spinner size="lg" /></div>;
}

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
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<AuthLayout />}>
            <Route path="/" element={<Bulletin />} />
            <Route path="/articles/:id" element={<ArticleDetail />} />
            <Route path="/intel" element={<IntelHub />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/feedback" element={<FeedbackHistory />} />
            <Route path="/investigations" element={<Investigations />} />
            <Route path="/investigations/:id" element={<InvestigationDetail />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
