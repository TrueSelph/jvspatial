import axios, { type AxiosInstance } from 'axios'
import type {
  GraphExpandResponse,
  GraphSubgraphResponse,
} from '../types/graph'

const TOKEN_KEY = 'jvspatial_admin_graph_token'

export function getAccessToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setAccessToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token)
    else sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    /* ignore */
  }
}

export function createGraphApiClient(apiBase: string): AxiosInstance {
  const client = axios.create({
    baseURL: apiBase,
    headers: { 'Content-Type': 'application/json' },
  })
  client.interceptors.request.use((config) => {
    const t = getAccessToken()
    if (t) {
      config.headers.Authorization = `Bearer ${t}`
    }
    return config
  })
  return client
}

export interface LoginBody {
  email: string
  password: string
}

export interface LoginResponse {
  access_token: string
  refresh_token?: string
}

export async function login(
  apiBase: string,
  body: LoginBody
): Promise<LoginResponse> {
  const client = axios.create({ baseURL: apiBase })
  const { data } = await client.post<LoginResponse>('/api/auth/login', body)
  return data
}

export async function getGraphSubgraph(
  client: AxiosInstance,
  params: {
    root: string
    max_depth?: number
    max_nodes?: number
    max_edges_per_node?: number
    detail_level: 'summary' | 'full'
  }
): Promise<GraphSubgraphResponse> {
  const { data } = await client.get<GraphSubgraphResponse>(
    '/api/graph/subgraph',
    { params }
  )
  return data
}

export async function getGraphExpand(
  client: AxiosInstance,
  params: {
    node_id: string
    limit?: number
    cursor?: number
    detail_level: 'summary' | 'full'
  }
): Promise<GraphExpandResponse> {
  const { data } = await client.get<GraphExpandResponse>('/api/graph/expand', {
    params,
  })
  return data
}
