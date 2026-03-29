const LS_SAME_ORIGIN = 'jvspatial_api_same_origin'
/** Normalized API origin only (scheme + host + optional port), e.g. ``http://127.0.0.1:8000``. */
const LS_BASE = 'jvspatial_api_base'

/** Prior structured storage (migrated once into ``LS_BASE``). */
const LS_HOST = 'jvspatial_api_host'
const LS_PORT = 'jvspatial_api_port'
const LS_HTTPS = 'jvspatial_api_https'

export const DEFAULT_API_BASE = 'http://127.0.0.1:8000'

export type ConnectionSettings = {
  sameOrigin: boolean
  /** Normalized origin when connecting remotely; still stored when same-origin is checked (for the form). */
  apiBaseUrl: string
}

/** Normalize base URL: no trailing slash */
export function normalizeApiBase(raw: string): string {
  return raw.trim().replace(/\/+$/, '')
}

/** Hostname suitable for URL (bracket IPv6 when needed). */
function hostnameForUrl(host: string): string {
  const h = host.trim()
  if (!h) return h
  if (h.startsWith('[')) return h
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(h)) return h
  if (h.includes(':')) return `[${h}]`
  return h
}

function isValidPort(port: number): boolean {
  return Number.isInteger(port) && port >= 1 && port <= 65535
}

function composeFromStructured(host: string, port: number, useHttps: boolean): string {
  const rawHost = host.trim()
  if (!rawHost || !isValidPort(port)) return DEFAULT_API_BASE
  const scheme = useHttps ? 'https' : 'http'
  const h = hostnameForUrl(rawHost)
  return normalizeApiBase(`${scheme}://${h}:${port}`)
}

/**
 * Parse user input into a URL ``origin`` (no path). Scheme defaults to ``http`` when omitted.
 * Examples: ``127.0.0.1:8000``, ``https://api.example.com``, ``http://[::1]:8080``.
 */
export function normalizeUserApiUrl(raw: string): string {
  const t = raw.trim()
  if (!t) throw new Error('API URL is required')
  const withScheme = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(t) ? t : `http://${t}`
  let u: URL
  try {
    u = new URL(withScheme)
  } catch {
    throw new Error('Invalid API URL')
  }
  if (!u.hostname) throw new Error('Invalid API URL: missing host')
  return normalizeApiBase(u.origin)
}

function readBool(key: string, defaultVal: boolean): boolean {
  try {
    const v = localStorage.getItem(key)
    if (v === null) return defaultVal
    return v === 'true' || v === '1'
  } catch {
    return defaultVal
  }
}

function readPortLegacy(): number {
  try {
    const v = localStorage.getItem(LS_PORT)
    if (v === null || v === '') return 8000
    const n = parseInt(v, 10)
    return isValidPort(n) ? n : 8000
  } catch {
    return 8000
  }
}

/**
 * Migrate structured host/port/https or legacy ``jvspatial_api_base`` into normalized ``LS_BASE``.
 */
function migrateConnectionStorage(): void {
  try {
    if (localStorage.getItem(LS_HOST) !== null) {
      const host = localStorage.getItem(LS_HOST) ?? '127.0.0.1'
      const port = readPortLegacy()
      const https = readBool(LS_HTTPS, false)
      const composed = composeFromStructured(host, port, https)
      try {
        localStorage.setItem(LS_BASE, normalizeUserApiUrl(composed))
      } catch {
        localStorage.setItem(LS_BASE, DEFAULT_API_BASE)
      }
      localStorage.removeItem(LS_HOST)
      localStorage.removeItem(LS_PORT)
      localStorage.removeItem(LS_HTTPS)
      return
    }

    const existing = localStorage.getItem(LS_BASE)
    if (existing === null || existing.trim() === '') {
      return
    }
    try {
      const normalized = normalizeUserApiUrl(existing)
      if (normalized !== existing) {
        localStorage.setItem(LS_BASE, normalized)
      }
    } catch {
      localStorage.setItem(LS_BASE, DEFAULT_API_BASE)
    }
  } catch {
    /* ignore */
  }
}

export function getConnectionSettings(): ConnectionSettings {
  migrateConnectionStorage()
  try {
    const raw = localStorage.getItem(LS_BASE)
    let apiBaseUrl = DEFAULT_API_BASE
    if (raw !== null && raw.trim() !== '') {
      try {
        apiBaseUrl = normalizeUserApiUrl(raw)
      } catch {
        apiBaseUrl = DEFAULT_API_BASE
      }
    }
    return {
      sameOrigin: readBool(LS_SAME_ORIGIN, false),
      apiBaseUrl,
    }
  } catch {
    return { sameOrigin: false, apiBaseUrl: DEFAULT_API_BASE }
  }
}

export function setConnectionSettings(s: ConnectionSettings): void {
  try {
    localStorage.setItem(LS_SAME_ORIGIN, s.sameOrigin ? 'true' : 'false')
    const trimmed = s.apiBaseUrl.trim()
    const toStore =
      trimmed === ''
        ? DEFAULT_API_BASE
        : (() => {
            try {
              return normalizeUserApiUrl(trimmed)
            } catch {
              return DEFAULT_API_BASE
            }
          })()
    localStorage.setItem(LS_BASE, toStore)
  } catch {
    /* ignore */
  }
}

/**
 * API base for axios (origin only, no path).
 * - Same-origin: ``''`` (requests use relative ``/api/...``).
 * - Otherwise: normalized URL from storage; defaults ``http://127.0.0.1:8000`` when unset.
 * - ``VITE_DEFAULT_API_BASE`` applies only when no saved base exists yet (after migration).
 */
export function getApiBase(): string {
  migrateConnectionStorage()
  try {
    if (readBool(LS_SAME_ORIGIN, false)) {
      return ''
    }

    const raw = localStorage.getItem(LS_BASE)
    if (raw !== null && raw.trim() !== '') {
      try {
        return normalizeUserApiUrl(raw)
      } catch {
        /* fall through */
      }
    }

    const def = import.meta.env.VITE_DEFAULT_API_BASE
    if (def && def.trim()) {
      try {
        return normalizeUserApiUrl(def)
      } catch {
        return normalizeApiBase(def)
      }
    }
    return DEFAULT_API_BASE
  } catch {
    return DEFAULT_API_BASE
  }
}

/** @deprecated Use setConnectionSettings */
export function setStoredApiBase(url: string): void {
  const n = normalizeApiBase(url)
  if (!n) {
    setConnectionSettings({ sameOrigin: true, apiBaseUrl: DEFAULT_API_BASE })
    return
  }
  try {
    setConnectionSettings({ sameOrigin: false, apiBaseUrl: normalizeUserApiUrl(n) })
  } catch {
    setConnectionSettings({ sameOrigin: false, apiBaseUrl: DEFAULT_API_BASE })
  }
}

export function getStoredApiBaseForDisplay(): string {
  const s = getConnectionSettings()
  if (s.sameOrigin) return '(same origin as this page)'
  return s.apiBaseUrl
}
