/** Node summary from /api/graph/subgraph and /api/graph/expand */
export interface GraphVizNode {
  id: string
  entity: string
  label: string
  degree: number
  missing?: boolean
  context?: Record<string, unknown>
}

export interface GraphVizEdge {
  id: string
  source: string
  target: string
  bidirectional: boolean
  entity: string
  label: string
  direction?: 'outgoing' | 'incoming' | 'loop' | 'undirected'
  context?: Record<string, unknown>
}

export interface GraphExpandPagination {
  cursor: number
  next_cursor: number | null
  has_more: boolean
  total_edge_count: number
  returned_edges: number
}

export interface GraphExpandResponse {
  center_id: string
  nodes: GraphVizNode[]
  edges: GraphVizEdge[]
  pagination: GraphExpandPagination
  found: boolean
}

export interface GraphSubgraphMeta {
  max_depth: number
  max_nodes: number
  max_edges_per_node: number
  truncated: boolean
  node_count: number
  edge_count: number
}

export interface GraphSubgraphResponse {
  root_id: string
  nodes: GraphVizNode[]
  edges: GraphVizEdge[]
  meta: GraphSubgraphMeta
}
