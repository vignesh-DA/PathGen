import { useCallback, useMemo } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  MarkerType,
  Position,
} from 'reactflow'
import 'reactflow/dist/style.css'
import './CFGViewer.css'

// ---------------------------------------------------------------------------
// Layout — simple layered layout: group nodes by BFS level from ENTRY
// ---------------------------------------------------------------------------
function computeLayout(nodes, edges, entryId) {
  if (!nodes.length) return []
  const levelMap = {}
  const visited = new Set()
  const queue = [{ id: entryId, level: 0 }]
  visited.add(entryId)

  while (queue.length) {
    const { id, level } = queue.shift()
    levelMap[id] = level
    edges
      .filter(e => e.source === id && !visited.has(e.target))
      .forEach(e => {
        visited.add(e.target)
        queue.push({ id: e.target, level: level + 1 })
      })
  }
  // Nodes not reachable: assign max+1
  const maxLevel = Math.max(0, ...Object.values(levelMap))
  nodes.forEach(n => { if (levelMap[n.id] === undefined) levelMap[n.id] = maxLevel + 1 })

  // Count nodes per level for x-centering
  const levelCounts = {}
  nodes.forEach(n => {
    levelCounts[levelMap[n.id]] = (levelCounts[levelMap[n.id]] || 0) + 1
  })
  const levelPositions = {}
  nodes.forEach(n => {
    const lvl = levelMap[n.id]
    if (!levelPositions[lvl]) levelPositions[lvl] = 0
    const idx = levelPositions[lvl]++
    const count = levelCounts[lvl]
    n.position = {
      x: (idx - (count - 1) / 2) * 220,
      y: lvl * 130,
    }
  })
  return nodes
}

// ---------------------------------------------------------------------------
// Edge label → colour
// ---------------------------------------------------------------------------
const EDGE_COLORS = {
  true:       '#22d3a6',
  false:      '#f05b7a',
  sequential: '#6b7aad',
  back_edge:  '#fbbf24',
}

function getEdgeColor(label) {
  return EDGE_COLORS[label] || EDGE_COLORS.sequential
}

// ---------------------------------------------------------------------------
// Node block_type → colour ring
// ---------------------------------------------------------------------------
const NODE_COLORS = {
  entry:     { bg: 'rgba(91,141,238,0.18)', border: '#5b8dee' },
  exit:      { bg: 'rgba(167,139,250,0.18)', border: '#a78bfa' },
  condition: { bg: 'rgba(251,191,36,0.12)', border: '#fbbf24' },
  body:      { bg: 'rgba(21,29,53,0.9)',    border: '#3a4a7a' },
  merge:     { bg: 'rgba(34,211,166,0.08)', border: '#22d3a6' },
}

// ---------------------------------------------------------------------------
// Custom CFG node
// ---------------------------------------------------------------------------
function CFGNode({ data }) {
  const colors = NODE_COLORS[data.block_type] || NODE_COLORS.body
  return (
    <div
      className="cfg-node"
      style={{ background: colors.bg, borderColor: colors.border }}
      title={data.statements?.join('\n')}
    >
      <div className="cfg-node__type">{data.block_type}</div>
      <div className="cfg-node__label">{data.label}</div>
    </div>
  )
}

const nodeTypes = { cfg: CFGNode }

// ---------------------------------------------------------------------------
// CFGViewer
// ---------------------------------------------------------------------------
export default function CFGViewer({ cfgData, highlightedPath = [] }) {
  const rfNodes = useMemo(() => {
    if (!cfgData?.nodes) return []
    const raw = cfgData.nodes.map(n => ({
      id: n.id,
      type: 'cfg',
      data: {
        label: n.label,
        block_type: n.block_type,
        statements: n.statements,
      },
      position: { x: 0, y: 0 },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      style: highlightedPath.includes(n.id)
        ? { filter: 'drop-shadow(0 0 12px rgba(91,141,238,0.9))' }
        : {},
    }))
    return computeLayout(raw, cfgData.edges || [], cfgData.entry_node)
  }, [cfgData, highlightedPath])

  const rfEdges = useMemo(() => {
    if (!cfgData?.edges) return []
    return cfgData.edges.map((e, i) => {
      const color = getEdgeColor(e.label)
      return {
        id: `e-${i}`,
        source: e.source,
        target: e.target,
        label: e.label,
        style: { stroke: color, strokeWidth: e.label === 'back_edge' ? 2 : 1.5 },
        labelStyle: { fill: color, fontSize: 10, fontFamily: 'JetBrains Mono' },
        labelBgStyle: { fill: 'rgba(10,14,26,0.85)', fillOpacity: 0.9 },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color,
          width: 14,
          height: 14,
        },
        animated: e.label === 'back_edge',
        type: e.label === 'back_edge' ? 'smoothstep' : 'default',
      }
    })
  }, [cfgData])

  const [nodes, , onNodesChange] = useNodesState(rfNodes)
  const [edges, , onEdgesChange] = useEdgesState(rfEdges)

  if (!cfgData) {
    return (
      <div className="cfg-empty">
        <div className="cfg-empty__icon">⬡</div>
        <p>Run <strong>Analyze</strong> to visualise the Control Flow Graph</p>
      </div>
    )
  }

  return (
    <div className="cfg-viewer">
      {/* Stats bar */}
      <div className="cfg-stats">
        <span>Nodes: <strong>{cfgData.node_count}</strong></span>
        <span>Edges: <strong>{cfgData.edge_count}</strong></span>
        <span>CC: <strong>{cfgData.cyclomatic_complexity}</strong></span>
        <span>Function: <strong>{cfgData.function_name}</strong></span>
      </div>

      {/* Legend */}
      <div className="cfg-legend">
        {Object.entries(EDGE_COLORS).map(([label, color]) => (
          <span key={label} className="cfg-legend__item">
            <span className="cfg-legend__dot" style={{ background: color }} />
            {label.replace('_', ' ')}
          </span>
        ))}
      </div>

      <div className="cfg-canvas">
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.25 }}
          attributionPosition="bottom-right"
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#1e2844" gap={20} size={1} />
          <Controls
            style={{ background: 'rgba(21,29,53,0.9)', border: '1px solid rgba(91,141,238,0.2)' }}
          />
          <MiniMap
            nodeColor={n => NODE_COLORS[n.data?.block_type]?.border || '#3a4a7a'}
            style={{ background: 'rgba(10,14,26,0.8)', border: '1px solid rgba(91,141,238,0.2)' }}
          />
        </ReactFlow>
      </div>
    </div>
  )
}
