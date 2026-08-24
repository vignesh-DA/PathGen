import { useState, useCallback } from 'react'
import './TestCaseTable.css'

function derivationBadge(method) {
  if (!method) return null
  const isDerived = method.includes('DERIVED')
  return (
    <span className={`badge ${isDerived ? 'badge--derived' : 'badge--suggested'}`}>
      {isDerived ? '✓ DERIVED' : '⚠ AI-SUGGESTED'}
    </span>
  )
}

function inputStr(vals) {
  if (!vals || Object.keys(vals).length === 0) return '—'
  return Object.entries(vals)
    .map(([k, v]) => `${k} = ${v}`)
    .join(', ')
}

export default function TestCaseTable({ testCases, onRowClick, onExport }) {
  const [sortKey, setSortKey] = useState('test_id')
  const [sortAsc, setSortAsc] = useState(true)
  const [activeId, setActiveId] = useState(null)

  const handleSort = key => {
    if (sortKey === key) setSortAsc(a => !a)
    else { setSortKey(key); setSortAsc(true) }
  }

  const sorted = [...(testCases || [])].sort((a, b) => {
    const av = a[sortKey] ?? ''
    const bv = b[sortKey] ?? ''
    const cmp = String(av).localeCompare(String(bv), undefined, { numeric: true })
    return sortAsc ? cmp : -cmp
  })

  const handleRow = tc => {
    setActiveId(tc.test_id)
    onRowClick?.(tc)
  }

  if (!testCases?.length) {
    return (
      <div className="tc-empty">
        <div className="tc-empty__icon">◈</div>
        <p>Click <strong>Generate Tests</strong> to derive test cases from the CFG</p>
      </div>
    )
  }

  const SortIcon = ({ col }) => (
    <span className="sort-icon">
      {sortKey === col ? (sortAsc ? '↑' : '↓') : '↕'}
    </span>
  )

  return (
    <div className="tc-wrapper fade-up">
      {/* Toolbar */}
      <div className="tc-toolbar">
        <span className="tc-count">{testCases.length} test case{testCases.length !== 1 ? 's' : ''}</span>
        <div className="tc-toolbar__actions">
          <button id="export-json-btn" className="btn btn--secondary" onClick={() => onExport?.('json')}>
            ↓ JSON
          </button>
          <button id="export-csv-btn" className="btn btn--secondary" onClick={() => onExport?.('csv')}>
            ↓ CSV
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="tc-scroll">
        <table className="tc-table">
          <thead>
            <tr>
              {[
                ['test_id',         'ID'],
                ['path_id',         'Path'],
                ['input_values',    'Input Values'],
                ['expected_output', 'Expected Output'],
                ['boundary_flag',   'Boundary?'],
                ['derivation_method', 'Method'],
              ].map(([key, label]) => (
                <th
                  key={key}
                  className="tc-th"
                  onClick={() => handleSort(key)}
                  id={`th-${key}`}
                >
                  {label} <SortIcon col={key} />
                </th>
              ))}
              <th className="tc-th">Explanation</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((tc, i) => (
              <tr
                key={tc.test_id}
                className={`tc-row ${activeId === tc.test_id ? 'tc-row--active' : ''} ${i % 2 === 0 ? 'tc-row--even' : ''}`}
                onClick={() => handleRow(tc)}
                id={`tc-row-${tc.test_id}`}
                style={{ animationDelay: `${i * 30}ms` }}
              >
                <td className="tc-td tc-td--id">
                  <span className="tc-id">{tc.test_id}</span>
                  {tc.boundary_flag && <span className="badge badge--boundary ml-2">⬡ BND</span>}
                </td>
                <td className="tc-td tc-td--mono">{tc.path_id}</td>
                <td className="tc-td tc-td--mono tc-td--input">{inputStr(tc.input_values)}</td>
                <td className="tc-td tc-td--output">{tc.expected_output}</td>
                <td className="tc-td tc-td--center">
                  {tc.boundary_flag ? <span className="tc-bool tc-bool--yes">Yes</span> : <span className="tc-bool tc-bool--no">No</span>}
                </td>
                <td className="tc-td">{derivationBadge(tc.derivation_method)}</td>
                <td className="tc-td tc-td--explain">
                  {tc.explanation
                    ? <span className="tc-explain">{tc.explanation}</span>
                    : <span className="tc-explain tc-explain--empty">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
