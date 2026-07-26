import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import RepositoryPage from "./pages/RepositoryPage";
import ConceptPage from "./pages/ConceptPage";
import LearningSessionPage from "./pages/LearningSessionPage";
import ReviewPage from "./pages/ReviewPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/repositories" element={<RepositoryPage />} />
        <Route path="/repositories/:id" element={<RepositoryPage />} />
        <Route path="/concepts/:id" element={<ConceptPage />} />
        <Route path="/session/:itemId" element={<LearningSessionPage />} />
        <Route path="/reviews" element={<ReviewPage />} />

        {/* Legacy aliases — all fold into the unified product */}
        <Route path="/learn" element={<Navigate to="/" replace />} />
        <Route path="/learn/repositories" element={<Navigate to="/repositories" replace />} />
        <Route path="/learn/repositories/:id" element={<LegacyRepoRedirect />} />
        <Route path="/learn/concepts/:id" element={<LegacyConceptRedirect />} />
        <Route path="/learn/session/:itemId" element={<LegacySessionRedirect />} />
        <Route path="/learn/reviews" element={<Navigate to="/reviews" replace />} />
        <Route path="/wiki" element={<Navigate to="/repositories" replace />} />
        <Route path="/wiki-tools" element={<Navigate to="/repositories" replace />} />
        <Route path="/project/:id" element={<Navigate to="/repositories" replace />} />
        <Route path="/project/:id/chat" element={<Navigate to="/repositories" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

function LegacyRepoRedirect() {
  const { id } = useParams();
  return <Navigate to={`/repositories/${id}`} replace />;
}

function LegacyConceptRedirect() {
  const { id } = useParams();
  return <Navigate to={`/concepts/${id}`} replace />;
}

function LegacySessionRedirect() {
  const { itemId } = useParams();
  return <Navigate to={`/session/${itemId}`} replace />;
}
