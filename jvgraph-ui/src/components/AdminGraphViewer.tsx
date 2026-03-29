import { useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'
import type { Core, EventObject } from 'cytoscape'
import type { AxiosInstance } from 'axios'
import { getGraphExpand, getGraphSubgraph, setAccessToken } from '../api/client'
import type { GraphVizEdge, GraphVizNode } from '../types/graph'
import {
  applyThemeToCy,
  createProgressiveGraphCy,
  destroyCy,
  mergePayloadIntoCy,
  payloadToElements,
  runGraphLayout,
  type GraphLayoutPreset,
} from '../graph/graphCytoscape'
import './AdminGraphViewer.css'
import { JsonInspectorPre } from './JsonInspectorPre'

const EXPAND_LIMIT = 40
const SUBGRAPH_ROOT_DEFAULT = 'n.Root.root'
/** Match server max so the root node’s full edge list loads (including default-entity edges). */
const SUBGRAPH_MAX_DEPTH = 2
const SUBGRAPH_MAX_NODES = 2000
const SUBGRAPH_MAX_EDGES_PER_NODE = 2000

const INSPECTOR_WIDTH_LS_KEY = 'jvgraph_inspector_width'
const INSPECTOR_WIDTH_DEFAULT = 400
const INSPECTOR_WIDTH_MIN = 260
const INSPECTOR_WIDTH_MAX_ABS = 720
const INSPECTOR_WIDTH_MAX_FRAC = 0.68

function readStoredInspectorWidth(): number {
  try {
    const raw = localStorage.getItem(INSPECTOR_WIDTH_LS_KEY)
    if (raw == null) return INSPECTOR_WIDTH_DEFAULT
    const n = parseInt(raw, 10)
    if (Number.isFinite(n)) {
      return Math.min(
        INSPECTOR_WIDTH_MAX_ABS,
        Math.max(INSPECTOR_WIDTH_MIN, n)
      )
    }
  } catch {
    /* ignore */
  }
  return INSPECTOR_WIDTH_DEFAULT
}

type SelectedElement = { kind: 'node' | 'edge'; id: string } | null

type GraphExpandModel = {
  baseNodeIds: Set<string>
  baseEdgeIds: Set<string>
  refCounts: Map<string, number>
  expandBatches: Map<string, Set<string>[]>
  expandedCenters: Set<string>
}

function createExpandModel(): GraphExpandModel {
  return {
    baseNodeIds: new Set(),
    baseEdgeIds: new Set(),
    refCounts: new Map(),
    expandBatches: new Map(),
    expandedCenters: new Set(),
  }
}

function resetExpandModel(
  m: GraphExpandModel,
  nodes: GraphVizNode[],
  edges: GraphVizEdge[]
): void {
  m.baseNodeIds = new Set(nodes.map((n) => n.id))
  m.baseEdgeIds = new Set(edges.map((e) => e.id))
  m.refCounts.clear()
  m.expandBatches.clear()
  m.expandedCenters.clear()
}

function collectNonBaseIdsFromExpand(
  ex: { nodes: GraphVizNode[]; edges: GraphVizEdge[] },
  m: GraphExpandModel
): Set<string> {
  const out = new Set<string>()
  for (const n of ex.nodes) {
    if (!m.baseNodeIds.has(n.id)) out.add(n.id)
  }
  for (const e of ex.edges) {
    if (!m.baseEdgeIds.has(e.id)) out.add(e.id)
  }
  return out
}

function registerExpandBatch(
  m: GraphExpandModel,
  centerId: string,
  batch: Set<string>
): boolean {
  if (batch.size === 0) return false
  for (const id of batch) {
    m.refCounts.set(id, (m.refCounts.get(id) || 0) + 1)
  }
  if (!m.expandBatches.has(centerId)) m.expandBatches.set(centerId, [])
  m.expandBatches.get(centerId)!.push(new Set(batch))
  m.expandedCenters.add(centerId)
  return true
}

function retractExpandCenter(
  cy: Core,
  m: GraphExpandModel,
  centerId: string
): string[] {
  const batches = m.expandBatches.get(centerId)
  if (!batches) return []
  const toRemove = new Set<string>()
  for (const batch of batches) {
    for (const id of batch) {
      if (m.baseNodeIds.has(id) || m.baseEdgeIds.has(id)) continue
      const next = (m.refCounts.get(id) || 0) - 1
      if (next <= 0) {
        m.refCounts.delete(id)
        toRemove.add(id)
      } else {
        m.refCounts.set(id, next)
      }
    }
  }
  m.expandBatches.delete(centerId)
  m.expandedCenters.delete(centerId)

  const edgeEls = cy.collection()
  const nodeEls = cy.collection()
  for (const id of toRemove) {
    const el = cy.getElementById(id)
    if (el.empty()) continue
    const group = el.group()
    if (group === 'edges') edgeEls.merge(el)
    else if (group === 'nodes') nodeEls.merge(el)
  }
  if (!edgeEls.empty()) cy.remove(edgeEls)
  if (!nodeEls.empty()) cy.remove(nodeEls)
  return [...toRemove]
}

function mergeNodeRecord(
  a: GraphVizNode | undefined,
  b: GraphVizNode
): GraphVizNode {
  if (!a) return { ...b }
  return {
    ...a,
    ...b,
    context:
      b.context != null && Object.keys(b.context).length > 0
        ? { ...a.context, ...b.context }
        : a.context ?? b.context,
  }
}

function mergeEdgeRecord(
  a: GraphVizEdge | undefined,
  b: GraphVizEdge
): GraphVizEdge {
  if (!a) return { ...b }
  return {
    ...a,
    ...b,
    context:
      b.context != null && Object.keys(b.context).length > 0
        ? { ...a.context, ...b.context }
        : a.context ?? b.context,
  }
}

function upsertNodes(
  prev: Record<string, GraphVizNode>,
  incoming: GraphVizNode[]
): Record<string, GraphVizNode> {
  const next = { ...prev }
  for (const n of incoming) {
    next[n.id] = mergeNodeRecord(next[n.id], n)
  }
  return next
}

function upsertEdges(
  prev: Record<string, GraphVizEdge>,
  incoming: GraphVizEdge[]
): Record<string, GraphVizEdge> {
  const next = { ...prev }
  for (const e of incoming) {
    next[e.id] = mergeEdgeRecord(next[e.id], e)
  }
  return next
}

function layoutPresetLabel(p: GraphLayoutPreset): string {
  if (p === 'dagre-lr') return 'Horizontal'
  if (p === 'dagre-tb') return 'Vertical'
  return 'Tree'
}

type Props = {
  apiClient: AxiosInstance
  onLogout: () => void
}

export function AdminGraphViewer({ apiClient, onLogout }: Props) {
  const [theme, setTheme] = useState<'light' | 'dark'>(() =>
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light'
  )
  const cyTheme = theme
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [progressiveNodes, setProgressiveNodes] = useState<GraphVizNode[]>([])
  const [progressiveEdges, setProgressiveEdges] = useState<GraphVizEdge[]>([])
  const [expandPagination, setExpandPagination] = useState<{
    nodeId: string
    nextCursor: number
  } | null>(null)
  const [expandBusy, setExpandBusy] = useState(false)
  const [detailLevel, setDetailLevel] = useState<'summary' | 'full'>('full')
  const [layoutPreset, setLayoutPreset] =
    useState<GraphLayoutPreset>('dagre-lr')
  const [selectedElement, setSelectedElement] =
    useState<SelectedElement>(null)
  const [inspectorOpen, setInspectorOpen] = useState(true)
  const [nodeById, setNodeById] = useState<Record<string, GraphVizNode>>({})
  const [edgeById, setEdgeById] = useState<Record<string, GraphVizEdge>>({})
  const [graphRoot, setGraphRoot] = useState(SUBGRAPH_ROOT_DEFAULT)
  const [rootDraft, setRootDraft] = useState(SUBGRAPH_ROOT_DEFAULT)
  const [inspectorWidthPx, setInspectorWidthPx] = useState(
    readStoredInspectorWidth
  )
  const [isLargeSplitLayout, setIsLargeSplitLayout] = useState(
    () =>
      typeof window !== 'undefined' &&
      window.matchMedia('(min-width: 1024px)').matches
  )

  const containerRef = useRef<HTMLDivElement>(null)
  const splitRowRef = useRef<HTMLDivElement>(null)
  const cyRef = useRef<Core | null>(null)
  const expandModelRef = useRef<GraphExpandModel>(createExpandModel())
  const subgraphRootRef = useRef(SUBGRAPH_ROOT_DEFAULT)
  const cyHandlersRef = useRef<{
    onTapBackground: () => void
    onTapNode: (id: string) => void
    onTapEdge: (id: string) => void
    onDblTapNode: (id: string) => void
  } | null>(null)

  const fetchGraph = useCallback(async () => {
    setLoading(true)
    setError(null)
    setExpandPagination(null)
    setSelectedElement(null)
    destroyCy(cyRef.current)
    cyRef.current = null
    resetExpandModel(expandModelRef.current, [], [])
    setNodeById({})
    setEdgeById({})
    const root = graphRoot.trim() || SUBGRAPH_ROOT_DEFAULT
    subgraphRootRef.current = root

    try {
      const sub = await getGraphSubgraph(apiClient, {
        root,
        max_depth: SUBGRAPH_MAX_DEPTH,
        max_nodes: SUBGRAPH_MAX_NODES,
        max_edges_per_node: SUBGRAPH_MAX_EDGES_PER_NODE,
        detail_level: detailLevel,
      })
      setProgressiveNodes(sub.nodes)
      setProgressiveEdges(sub.edges)
      resetExpandModel(expandModelRef.current, sub.nodes, sub.edges)
      const nMap: Record<string, GraphVizNode> = {}
      const eMap: Record<string, GraphVizEdge> = {}
      for (const n of sub.nodes) nMap[n.id] = n
      for (const e of sub.edges) eMap[e.id] = e
      setNodeById(nMap)
      setEdgeById(eMap)
    } catch (err: unknown) {
      if (axios.isAxiosError(err)) {
        const st = err.response?.status
        if (st === 403) {
          setError(
            'Forbidden: graph APIs require an admin role for this jvspatial app.'
          )
        } else if (st === 401) {
          setError('Unauthorized: sign in again.')
        } else {
          setError(
            err.response?.data
              ? JSON.stringify(err.response.data).slice(0, 280)
              : err.message
          )
        }
      } else {
        setError(err instanceof Error ? err.message : 'Failed to load graph')
      }
    } finally {
      setLoading(false)
    }
  }, [apiClient, detailLevel, graphRoot])

  useEffect(() => {
    void fetchGraph()
  }, [fetchGraph])

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 1024px)')
    const apply = () => setIsLargeSplitLayout(mq.matches)
    apply()
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [])

  const handleInspectorResizeMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      if (e.button !== 0) return
      const startX = e.clientX
      const startW = inspectorWidthPx
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'

      const clampW = (raw: number) => {
        const rowW = splitRowRef.current?.getBoundingClientRect().width ?? 1400
        const cap = Math.min(
          INSPECTOR_WIDTH_MAX_ABS,
          Math.floor(rowW * INSPECTOR_WIDTH_MAX_FRAC)
        )
        return Math.min(cap, Math.max(INSPECTOR_WIDTH_MIN, raw))
      }

      let lastW = startW

      const onMove = (ev: MouseEvent) => {
        lastW = clampW(startW + startX - ev.clientX)
        setInspectorWidthPx(lastW)
      }

      const onUp = () => {
        window.removeEventListener('mousemove', onMove)
        window.removeEventListener('mouseup', onUp)
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
        try {
          localStorage.setItem(INSPECTOR_WIDTH_LS_KEY, String(lastW))
        } catch {
          /* ignore */
        }
      }

      window.addEventListener('mousemove', onMove)
      window.addEventListener('mouseup', onUp)
    },
    [inspectorWidthPx]
  )

  const applyLayout = useCallback(
    (animate = true) => {
      const cy = cyRef.current
      if (!cy) return
      runGraphLayout(cy, layoutPreset, subgraphRootRef.current, animate)
    },
    [layoutPreset]
  )

  const expandOrRetractNode = useCallback(
    async (nodeId: string, cursor = 0) => {
      const cy = cyRef.current
      if (!cy) return
      const m = expandModelRef.current

      if (cursor === 0 && m.expandedCenters.has(nodeId)) {
        const removed = retractExpandCenter(cy, m, nodeId)
        setNodeById((prev) => {
          const next = { ...prev }
          for (const id of removed) delete next[id]
          return next
        })
        setEdgeById((prev) => {
          const next = { ...prev }
          for (const id of removed) delete next[id]
          return next
        })
        setSelectedElement((sel) =>
          sel && removed.includes(sel.id) ? null : sel
        )
        setExpandPagination((p) => (p?.nodeId === nodeId ? null : p))
        applyLayout(true)
        return
      }

      setExpandBusy(true)
      try {
        const ex = await getGraphExpand(apiClient, {
          node_id: nodeId,
          limit: EXPAND_LIMIT,
          cursor,
          detail_level: detailLevel,
        })
        if (!ex.found) return

        const batch = collectNonBaseIdsFromExpand(ex, m)
        const hadNew = registerExpandBatch(m, nodeId, batch)

        mergePayloadIntoCy(cy, ex.nodes, ex.edges)
        setNodeById((prev) => upsertNodes(prev, ex.nodes))
        setEdgeById((prev) => upsertEdges(prev, ex.edges))

        if (hadNew || cursor > 0) {
          applyLayout(true)
        }

        if (ex.pagination.has_more && ex.pagination.next_cursor != null) {
          setExpandPagination({ nodeId, nextCursor: ex.pagination.next_cursor })
        } else {
          setExpandPagination(null)
        }
      } catch (e: unknown) {
        if (axios.isAxiosError(e) && e.response?.status === 403) {
          setError(
            'Forbidden: graph expand requires an admin role for this jvspatial app.'
          )
        } else {
          setError(e instanceof Error ? e.message : 'Failed to expand node')
        }
      } finally {
        setExpandBusy(false)
      }
    },
    [apiClient, detailLevel, applyLayout]
  )

  cyHandlersRef.current = {
    onTapBackground: () => {
      cyRef.current?.nodes().unselect()
      cyRef.current?.edges().unselect()
      setSelectedElement(null)
    },
    onTapNode: (id: string) => {
      cyRef.current?.nodes().unselect()
      cyRef.current?.edges().unselect()
      cyRef.current?.$(`#${CSS.escape(id)}`).select()
      setSelectedElement({ kind: 'node', id })
    },
    onTapEdge: (id: string) => {
      cyRef.current?.nodes().unselect()
      cyRef.current?.edges().unselect()
      cyRef.current?.$(`#${CSS.escape(id)}`).select()
      setSelectedElement({ kind: 'edge', id })
    },
    onDblTapNode: (id: string) => {
      setExpandPagination(null)
      void expandOrRetractNode(id, 0)
    },
  }

  useEffect(() => {
    if (loading || !containerRef.current) return

    const container = containerRef.current
    destroyCy(cyRef.current)
    cyRef.current = null

    if (progressiveNodes.length === 0 && progressiveEdges.length === 0) {
      return
    }

    const cy = createProgressiveGraphCy({
      container,
      theme: cyTheme,
      elements: payloadToElements(progressiveNodes, progressiveEdges),
      initialLayout: layoutPreset,
      rootId: subgraphRootRef.current,
    })
    cyRef.current = cy

    const bg = () => cyHandlersRef.current?.onTapBackground()
    const tn = (evt: EventObject) =>
      cyHandlersRef.current?.onTapNode(evt.target.id())
    const te = (evt: EventObject) =>
      cyHandlersRef.current?.onTapEdge(evt.target.id())
    const dn = (evt: EventObject) =>
      cyHandlersRef.current?.onDblTapNode(evt.target.id())

    cy.on('tap', bg)
    cy.on('tap', 'node', tn)
    cy.on('tap', 'edge', te)
    cy.on('dbltap', 'node', dn)

    /* Container flex size is often 0×0 on the same tick as first mount; Cytoscape
       then lays out with a bad viewport (stacked / invisible nodes & edges).
       Defer resize + full style refresh + relayout + fit to the next frames. */
    let cancelled = false
    requestAnimationFrame(() => {
      if (cancelled) return
      requestAnimationFrame(() => {
        if (cancelled || cy.destroyed()) return
        cy.resize()
        applyThemeToCy(cy, cyTheme)
        runGraphLayout(cy, layoutPreset, subgraphRootRef.current, false)
        cy.fit(undefined, 48)
      })
    })

    let resizeTimeout: ReturnType<typeof setTimeout> | undefined
    const ro = new ResizeObserver(() => {
      clearTimeout(resizeTimeout)
      resizeTimeout = setTimeout(() => {
        const inst = cyRef.current
        if (!inst || inst.destroyed()) return
        inst.resize()
      }, 120)
    })
    ro.observe(container)

    return () => {
      cancelled = true
      cy.removeListener('tap', bg)
      cy.removeListener('tap', 'node', tn)
      cy.removeListener('tap', 'edge', te)
      cy.removeListener('dbltap', 'node', dn)
      clearTimeout(resizeTimeout)
      ro.disconnect()
      destroyCy(cyRef.current)
      cyRef.current = null
    }
    /* Intentionally omit cyTheme: theme is handled by applyThemeToCy only so toggling
       light/dark does not destroy the graph (expanded nodes, pan/zoom preserved). */
  }, [loading, progressiveNodes, progressiveEdges, layoutPreset])

  useEffect(() => {
    if (loading || !cyRef.current) return
    applyThemeToCy(cyRef.current, cyTheme)
  }, [theme, cyTheme, loading])

  useEffect(() => {
    if (loading || !cyRef.current) return
    applyLayout(true)
  }, [layoutPreset, loading, applyLayout])

  const handleZoomIn = () => {
    const cy = cyRef.current
    if (!cy) return
    cy.zoom(cy.zoom() * 1.25)
  }

  const handleZoomOut = () => {
    const cy = cyRef.current
    if (!cy) return
    cy.zoom(cy.zoom() / 1.25)
  }

  const handleResetZoom = () => {
    cyRef.current?.fit(undefined, 48)
  }

  const handleLogout = () => {
    setAccessToken(null)
    onLogout()
  }

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      /* ignore */
    }
  }

  const inspectorBody = (() => {
    if (!selectedElement) {
      return (
        <p className="inspector-placeholder">
          Tap a node or edge to inspect. Use <strong>Full</strong> detail for
          context fields.
        </p>
      )
    }
    if (selectedElement.kind === 'node') {
      const n = nodeById[selectedElement.id]
      if (!n) {
        return (
          <p className="inspector-warn">No data for this node (reload if needed).</p>
        )
      }
      const ctxJson =
        n.context && Object.keys(n.context).length > 0
          ? JSON.stringify(n.context, null, 2)
          : null
      return (
        <div className="inspector-detail">
          <div className="inspector-head">
            <span className="inspector-title">Node</span>
            <button
              type="button"
              className="linkish"
              onClick={() => void copyText(n.id)}
            >
              Copy id
            </button>
          </div>
          <dl className="inspector-dl">
            <div>
              <dt>id</dt>
              <dd className="mono">{n.id}</dd>
            </div>
            <div>
              <dt>entity</dt>
              <dd>{n.entity}</dd>
            </div>
            <div>
              <dt>label</dt>
              <dd>{n.label}</dd>
            </div>
            <div>
              <dt>degree</dt>
              <dd>{n.degree}</dd>
            </div>
            {n.missing && <div className="inspector-warn">Missing record</div>}
          </dl>
          {detailLevel === 'summary' && (
            <p className="inspector-hint">
              Switch to <strong>Full</strong> and refresh for{' '}
              <code>context</code>.
            </p>
          )}
          {detailLevel === 'full' && (
            <div className="inspector-ctx">
              <div className="inspector-ctx-head">
                <span>context</span>
                {ctxJson && (
                  <button
                    type="button"
                    className="linkish"
                    onClick={() => void copyText(ctxJson)}
                  >
                    Copy JSON
                  </button>
                )}
              </div>
              {ctxJson ? (
                <JsonInspectorPre code={ctxJson} variant={theme} />
              ) : (
                <p className="inspector-muted">Empty context</p>
              )}
            </div>
          )}
        </div>
      )
    }
    const e = edgeById[selectedElement.id]
    if (!e) {
      return (
        <p className="inspector-warn">No data for this edge (reload if needed).</p>
      )
    }
    const ctxJson =
      e.context && Object.keys(e.context).length > 0
        ? JSON.stringify(e.context, null, 2)
        : null
    return (
      <div className="inspector-detail">
        <div className="inspector-head">
          <span className="inspector-title">Edge</span>
          <button
            type="button"
            className="linkish"
            onClick={() => void copyText(e.id)}
          >
            Copy id
          </button>
        </div>
        <dl className="inspector-dl">
          <div>
            <dt>id</dt>
            <dd className="mono">{e.id}</dd>
          </div>
          <div>
            <dt>entity / label</dt>
            <dd>
              {e.entity} / {e.label}
            </dd>
          </div>
          <div>
            <dt>source → target</dt>
            <dd className="mono small">
              {e.source} → {e.target}
            </dd>
          </div>
          <div>
            <dt>bidirectional</dt>
            <dd>{String(e.bidirectional)}</dd>
          </div>
          {e.direction != null && (
            <div>
              <dt>direction</dt>
              <dd>{e.direction}</dd>
            </div>
          )}
        </dl>
        {detailLevel === 'summary' && (
          <p className="inspector-hint">
            Switch to <strong>Full</strong> and refresh for edge{' '}
            <code>context</code>.
          </p>
        )}
        {detailLevel === 'full' && (
          <div className="inspector-ctx">
            <div className="inspector-ctx-head">
              <span>context</span>
              {ctxJson && (
                <button
                  type="button"
                  className="linkish"
                  onClick={() => void copyText(ctxJson)}
                >
                  Copy JSON
                </button>
              )}
            </div>
            {ctxJson ? (
              <JsonInspectorPre code={ctxJson} variant={theme} />
            ) : (
              <p className="inspector-muted">Empty context</p>
            )}
          </div>
        )}
      </div>
    )
  })()

  const graphHint =
    'Tap: inspect · Double-click: expand neighbors (again to retract) · Summary/Full reloads data · Layout presets arrange the graph. ' +
    `Subgraph uses BFS from the root (default ${SUBGRAPH_ROOT_DEFAULT}) with the server’s full per-node edge budget so every incident edge at the root is requested.`

  return (
    <div className={`agv-root agv-theme-${theme}`}>
      <header className="agv-header">
        <div className="agv-header-main">
          <h1>Graph</h1>
          <p className="agv-hint">{graphHint}</p>
        </div>
        <div className="agv-toolbar">
          <div className="agv-toolbar-root-group">
            <label className="agv-root-inline" htmlFor="agv-root-input">
              Root id
            </label>
            <input
              id="agv-root-input"
              className="agv-root-input"
              value={rootDraft}
              onChange={(e) => setRootDraft(e.target.value)}
              disabled={loading}
              spellCheck={false}
              autoComplete="off"
              title={`Leave blank or use ${SUBGRAPH_ROOT_DEFAULT} for the platform default root`}
            />
            <button
              type="button"
              className="btn-ghost"
              disabled={loading}
              onClick={() =>
                setGraphRoot(rootDraft.trim() || SUBGRAPH_ROOT_DEFAULT)
              }
            >
              Apply root
            </button>
          </div>
          <div className="seg">
            <button
              type="button"
              className={detailLevel === 'summary' ? 'active' : ''}
              onClick={() => setDetailLevel('summary')}
            >
              Summary
            </button>
            <button
              type="button"
              className={detailLevel === 'full' ? 'active' : ''}
              onClick={() => setDetailLevel('full')}
            >
              Full
            </button>
          </div>
          <select
            value={layoutPreset}
            onChange={(e) =>
              setLayoutPreset(e.target.value as GraphLayoutPreset)
            }
            aria-label="Layout"
          >
            <option value="dagre-lr">{layoutPresetLabel('dagre-lr')}</option>
            <option value="dagre-tb">{layoutPresetLabel('dagre-tb')}</option>
            <option value="breadthfirst">
              {layoutPresetLabel('breadthfirst')}
            </option>
          </select>
          <button
            type="button"
            className="btn-ghost"
            onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
          >
            {theme === 'dark' ? 'Light' : 'Dark'}
          </button>
          <button
            type="button"
            className="btn-ghost"
            onClick={() => void fetchGraph()}
            disabled={loading}
          >
            Refresh
          </button>
          {expandPagination && (
            <button
              type="button"
              className="btn-warn"
              disabled={expandBusy}
              onClick={() =>
                void expandOrRetractNode(
                  expandPagination.nodeId,
                  expandPagination.nextCursor
                )
              }
            >
              {expandBusy ? 'Loading…' : 'Load more neighbors'}
            </button>
          )}
          <button
            type="button"
            className="btn-ghost"
            onClick={() => setInspectorOpen((o) => !o)}
          >
            {inspectorOpen ? 'Hide inspector' : 'Inspector'}
          </button>
          <button type="button" className="btn-outline" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </header>

      {error && (
        <div className="agv-banner agv-banner-error">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      <div className="agv-body" ref={splitRowRef}>
        <div className="agv-graph-col">
          {loading && (
            <div className="agv-overlay">
              <div className="spinner" />
              <p>Loading graph…</p>
            </div>
          )}
          <div className="agv-zoom">
            <button type="button" onClick={handleZoomIn} title="Zoom in">
              +
            </button>
            <button type="button" onClick={handleZoomOut} title="Zoom out">
              −
            </button>
            <button type="button" onClick={handleResetZoom} title="Fit">
              ⊡
            </button>
          </div>
          <div ref={containerRef} className="agv-cy" />
        </div>
        {inspectorOpen && isLargeSplitLayout && (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Drag to resize inspector"
            className="agv-inspector-resize"
            onMouseDown={(e) => handleInspectorResizeMouseDown(e)}
          >
            <span className="agv-inspector-resize-line" aria-hidden />
          </div>
        )}
        {inspectorOpen && (
          <aside
            className="agv-inspector"
            style={
              isLargeSplitLayout
                ? {
                    width: inspectorWidthPx,
                    flexShrink: 0,
                    minWidth: INSPECTOR_WIDTH_MIN,
                    maxWidth: `${INSPECTOR_WIDTH_MAX_FRAC * 100}%`,
                  }
                : undefined
            }
          >
            <div className="agv-inspector-head">
              <h3>Inspector</h3>
            </div>
            <div className="agv-inspector-body">{inspectorBody}</div>
          </aside>
        )}
      </div>
    </div>
  )
}
