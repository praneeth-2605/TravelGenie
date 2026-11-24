import type { ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { AuthProvider, useApplyTheme, useAuth } from './lib/auth'
import { AppShell } from './components/AppShell'
import { KnowledgeBase } from './components/KnowledgeBase'
import { AuthPage } from './pages/AuthPage'
import { Dashboard } from './pages/Dashboard'
import { NewTrip } from './pages/NewTrip'
import { SettingsPage } from './pages/SettingsPage'
import { SharedTrip } from './pages/SharedTrip'
import { PrivacyPolicy, TermsOfUse } from './pages/Legal'
import { TripWorkspace } from './pages/TripWorkspace'

function Splash() {
  return <div className="grid h-full place-items-center"><Loader2 className="size-6 animate-spin text-faint" /></div>
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <Splash />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <>{children}</>
}

function PublicOnly({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <Splash />
  if (user) return <Navigate to="/" replace />
  return <>{children}</>
}

function Routed() {
  const { settings } = useAuth()
  useApplyTheme(settings?.theme)
  return (
    <Routes>
      <Route path="/login" element={<PublicOnly><AuthPage mode="login" /></PublicOnly>} />
      <Route path="/signup" element={<PublicOnly><AuthPage mode="signup" /></PublicOnly>} />
      <Route path="/share/:token" element={<SharedTrip />} />
      <Route path="/privacy" element={<PrivacyPolicy />} />
      <Route path="/terms" element={<TermsOfUse />} />
      <Route element={<RequireAuth><AppShell /></RequireAuth>}>
        <Route index element={<Dashboard />} />
        <Route path="new" element={<NewTrip />} />
        <Route path="trips/:tripId" element={<TripWorkspace />} />
        <Route path="knowledge" element={<KnowledgeBase />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Routed />
    </AuthProvider>
  )
}
