import { useState } from 'react'
import axios from 'axios'
import './AdminGraphViewer.css'
import { login, setAccessToken } from '../api/client'
import {
  DEFAULT_API_BASE,
  getConnectionSettings,
  normalizeUserApiUrl,
  setConnectionSettings,
} from '../config/apiBase'

type Props = {
  onLoggedIn: () => void
}

export function LoginPage({ onLoggedIn }: Props) {
  const initial = getConnectionSettings()
  const [sameOrigin, setSameOrigin] = useState(initial.sameOrigin)
  const [apiUrl, setApiUrl] = useState(initial.apiBaseUrl)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      let normalizedBase = DEFAULT_API_BASE
      if (!sameOrigin) {
        if (!apiUrl.trim()) {
          setError('Enter the jvspatial API URL, or enable “same origin”.')
          return
        }
        try {
          normalizedBase = normalizeUserApiUrl(apiUrl)
        } catch {
          setError(
            'Invalid API URL. Use a host or origin, e.g. 127.0.0.1:8000 or https://api.example.com'
          )
          return
        }
      }

      setConnectionSettings({
        sameOrigin,
        apiBaseUrl: sameOrigin ? apiUrl.trim() || normalizedBase : normalizedBase,
      })

      const base = sameOrigin ? '' : normalizedBase

      const data = await login(base, { email, password })
      if (!data.access_token) {
        setError('Login response missing access_token')
        return
      }
      setAccessToken(data.access_token)
      onLoggedIn()
    } catch (err) {
      if (axios.isAxiosError(err)) {
        const st = err.response?.status
        const detail = err.response?.data as { detail?: string } | undefined
        const msg =
          typeof detail?.detail === 'string'
            ? detail.detail
            : err.response?.data
              ? JSON.stringify(err.response.data).slice(0, 200)
              : err.message
        setError(st ? `${st}: ${msg}` : msg)
      } else {
        setError(err instanceof Error ? err.message : 'Login failed')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <h1>jvspatial admin graph</h1>
        <p className="login-lead">
          Sign in with an <strong>admin</strong> account to inspect the graph for
          this deployment.
        </p>
        <form onSubmit={(e) => void handleSubmit(e)}>
          <label className="field checkbox-field">
            <input
              type="checkbox"
              checked={sameOrigin}
              onChange={(e) => setSameOrigin(e.target.checked)}
            />
            <span>Use same origin as this page (embedded UI / relative API)</span>
          </label>
          {!sameOrigin && (
            <label className="field">
              <span>API URL</span>
              <input
                type="text"
                placeholder={DEFAULT_API_BASE}
                value={apiUrl}
                onChange={(e) => setApiUrl(e.target.value)}
                autoComplete="off"
                spellCheck={false}
              />
            </label>
          )}
          <p className="dev-hint">
            Dev and static builds talk to the API directly from the browser. Ensure
            jvspatial <strong>CORS</strong> allows this page’s origin (see jvspatial
            docs). Default remote target is <code>{DEFAULT_API_BASE}</code> (HTTP;
            include <code>https://</code> when needed). Port is optional when it is
            the default for the scheme.
          </p>
          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="username"
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
            />
          </label>
          {error && <div className="error-banner">{error}</div>}
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
