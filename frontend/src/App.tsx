import { Navigate, Route, Routes } from 'react-router-dom'
import LandingPage from '@/pages/landing'
import CompetitionPage from '@/pages/competition'
import ReviewPage from '@/pages/review'
import SubmittedPage from '@/pages/submitted'
import LeaderboardPage from '@/pages/leaderboard'
import { AdminLayout } from '@/pages/admin/AdminLayout'
import DashboardPage from '@/pages/admin/DashboardPage'
import EvalPage from '@/pages/admin/EvalPage'
import ParticipantsPage from '@/pages/admin/ParticipantsPage'
import CriteriaPage from '@/pages/admin/CriteriaPage'
import ExportPage from '@/pages/admin/ExportPage'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/competition" element={<CompetitionPage />} />
      <Route path="/competition/review" element={<ReviewPage />} />
      <Route path="/submitted" element={<SubmittedPage />} />
      <Route path="/leaderboard" element={<LeaderboardPage />} />
      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="participants" element={<ParticipantsPage />} />
        <Route path="eval" element={<EvalPage />} />
        <Route path="criteria" element={<CriteriaPage />} />
        <Route path="export" element={<ExportPage />} />
        <Route path="test" element={<Navigate to="/admin" replace />} />
        <Route path="participation" element={<Navigate to="/admin/participants" replace />} />
        <Route path="registrations" element={<Navigate to="/admin/participants" replace />} />
        <Route path="monitor" element={<Navigate to="/admin/eval" replace />} />
        <Route path="cost" element={<Navigate to="/admin/eval" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
