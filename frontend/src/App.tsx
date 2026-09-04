import { Routes, Route, Navigate } from 'react-router-dom'
import LandingPage from '@/pages/landing'
import CompetitionPage from '@/pages/competition'
import ReviewPage from '@/pages/review'
import SubmittedPage from '@/pages/submitted'
import LeaderboardPage from '@/pages/leaderboard'
import AdminPage from '@/pages/admin'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/competition" element={<CompetitionPage />} />
      <Route path="/competition/review" element={<ReviewPage />} />
      <Route path="/submitted" element={<SubmittedPage />} />
      <Route path="/leaderboard" element={<LeaderboardPage />} />
      <Route path="/admin" element={<AdminPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}