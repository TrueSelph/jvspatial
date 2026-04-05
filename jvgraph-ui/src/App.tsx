import { lazy, Suspense, useMemo, useState } from 'react'
import { createGraphApiClient, getAccessToken } from './api/client'
import { getApiBase } from './config/apiBase'
import { LoginPage } from './components/LoginPage'

const AdminGraphViewer = lazy(async () => {
  const m = await import('./components/AdminGraphViewer')
  return { default: m.AdminGraphViewer }
})

export default function App() {
  const [authed, setAuthed] = useState(() => !!getAccessToken())

  const apiClient = useMemo(() => createGraphApiClient(getApiBase()), [authed])

  if (!authed) {
    return <LoginPage onLoggedIn={() => setAuthed(true)} />
  }

  return (
    <Suspense
      fallback={
        <div className="app-graph-loading" role="status" aria-live="polite">
          Loading graph viewer…
        </div>
      }
    >
      <AdminGraphViewer
        apiClient={apiClient}
        onLogout={() => setAuthed(false)}
      />
    </Suspense>
  )
}
