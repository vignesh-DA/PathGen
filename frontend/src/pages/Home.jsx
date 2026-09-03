import { useState, useCallback } from 'react'
import CodeEditor from '../components/CodeEditor'
import CFGViewer from '../components/CFGViewer'
import TestCaseTable from '../components/TestCaseTable'
import ExplanationPanel from '../components/ExplanationPanel'
import { analyzeCode, generateTests } from '../api/client'
import './Home.css'

const DEFAULT_CODE = {
  c: `#include <stdio.h>

int classify_age(int age) {
    if (age >= 18) {
        printf("Adult\\n");
        return 1;
    } else {
        printf("Minor\\n");
        return 0;
    }
}

int main() {
    int age;
    scanf("%d", &age);
    classify_age(age);
    return 0;
}
`,
  python: `def classify_age(age):
    if age >= 18:
        print("Adult")
        return 1
    else:
        print("Minor")
        return 0

age = int(input("Enter age: "))
classify_age(age)
`,
  javascript: `function classifyAge(age) {
    if (age >= 18) {
        console.log("Adult");
        return 1;
    } else {
        console.log("Minor");
        return 0;
    }
}

const age = parseInt(prompt("Enter age: "));
classifyAge(age);
`,
  typescript: `function classifyAge(age: number): number {
    if (age >= 18) {
        console.log("Adult");
        return 1;
    } else {
        console.log("Minor");
        return 0;
    }
}

const age: number = parseInt(prompt("Enter age: ") || "0");
classifyAge(age);
`,
}

const LANGUAGE_OPTIONS = [
  { value: 'c', label: 'C' },
  { value: 'python', label: 'Python' },
  { value: 'javascript', label: 'JavaScript' },
  { value: 'typescript', label: 'TypeScript' },
]

// ---------------------------------------------------------------------------
// Export helpers
// ---------------------------------------------------------------------------
function downloadJSON(data, filename) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

function downloadCSV(testCases, filename) {
  const headers = ['test_id','path_id','input_values','expected_output','boundary_flag','derivation_method','explanation']
  const rows = testCases.map(tc => [
    tc.test_id,
    tc.path_id,
    Object.entries(tc.input_values || {}).map(([k,v]) => `${k}=${v}`).join('; '),
    tc.expected_output,
    tc.boundary_flag ? 'yes' : 'no',
    tc.derivation_method,
    `"${(tc.explanation || '').replace(/"/g,'""')}"`,
  ])
  const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

// ---------------------------------------------------------------------------
// Home
// ---------------------------------------------------------------------------
export default function Home() {
  const [code, setCode]           = useState(DEFAULT_CODE)
  const [funcName, setFuncName]   = useState('classify_age')
  const [cfgData, setCfgData]     = useState(null)
  const [testData, setTestData]   = useState(null)
  const [selectedTC, setSelectedTC] = useState(null)
  const [highlightPath, setHighlightPath] = useState([])

  const [analyzing, setAnalyzing]   = useState(false)
  const [generating, setGenerating] = useState(false)
  const [analyzeErr, setAnalyzeErr] = useState(null)
  const [generateErr, setGenerateErr] = useState(null)

  // Phase tracker
  const phase = cfgData ? (testData ? 3 : 2) : 1

  // ---- Analyze ----
  const handleAnalyze = useCallback(async () => {
    setAnalyzing(true)
    setAnalyzeErr(null)
    setCfgData(null)
    setTestData(null)
    setSelectedTC(null)
    try {
      const result = await analyzeCode(code, funcName)
      setCfgData(result)
    } catch (err) {
      const msg = err.response?.data?.detail?.message
        || err.response?.data?.detail
        || err.message
      setAnalyzeErr(String(msg))
    } finally {
      setAnalyzing(false)
    }
  }, [code, funcName])

  // ---- Generate Tests ----
  const handleGenerate = useCallback(async () => {
    setGenerating(true)
    setGenerateErr(null)
    try {
      const result = await generateTests(code, funcName)
      setTestData(result)
    } catch (err) {
      const msg = err.response?.data?.detail?.message
        || err.response?.data?.detail
        || err.message
      setGenerateErr(String(msg))
    } finally {
      setGenerating(false)
    }
  }, [code, funcName])

  // ---- Row click ----
  const handleRowClick = useCallback(tc => {
    setSelectedTC(tc)
    // Highlight path nodes in CFG
    const nodeIds = (tc.path_steps || []).map(label => {
      // find node id by label
      return cfgData?.nodes?.find(n => n.label === label)?.id
    }).filter(Boolean)
    setHighlightPath(nodeIds)
  }, [cfgData])

  // ---- Export ----
  const handleExport = useCallback(format => {
    if (!testData?.test_cases) return
    if (format === 'json') downloadJSON(testData.test_cases, 'pathgen_test_cases.json')
    else downloadCSV(testData.test_cases, 'pathgen_test_cases.csv')
  }, [testData])

  return (
    <div className="home">
      {/* ─── Navbar ─── */}
      <header className="navbar">
        <div className="navbar__brand">
          <span className="navbar__logo">⬡</span>
          <span className="navbar__name">PathGen</span>
          <span className="navbar__tagline">Compiler-Based Test Generation</span>
        </div>
        <nav className="navbar__steps">
          {['Code', 'CFG', 'Tests'].map((s, i) => (
            <div key={s} className={`step ${phase > i ? 'step--done' : ''} ${phase === i + 1 ? 'step--active' : ''}`}>
              <span className="step__num">{i + 1}</span>
              <span className="step__label">{s}</span>
            </div>
          ))}
        </nav>
        <a
          className="navbar__docs"
          href="http://localhost:8000/docs"
          target="_blank"
          rel="noreferrer"
          id="swagger-docs-link"
        >
          API Docs ↗
        </a>
      </header>

      {/* ─── Main layout ─── */}
      <main className="main-layout">
        {/* Left panel — Code editor */}
        <section className="panel panel--code glass">
          <div className="panel__header">
            <div className="section-header">
              <div className="section-dot" />
              <span className="section-title">C Source Code</span>
            </div>
            <div className="panel__controls">
              <input
                id="function-name-input"
                className="func-input"
                value={funcName}
                onChange={e => setFuncName(e.target.value)}
                placeholder="function name"
                title="Function to analyse"
              />
              <button
                id="analyze-btn"
                className="btn btn--primary"
                onClick={handleAnalyze}
                disabled={analyzing}
              >
                {analyzing ? <><span className="spinner" /> Analyzing…</> : '▶ Analyze'}
              </button>
            </div>
          </div>
          <div className="panel__body panel__body--editor">
            <CodeEditor value={code} onChange={setCode} />
          </div>
          {analyzeErr && <div className="error-box">{analyzeErr}</div>}
        </section>

        {/* Right panel — CFG + Tests */}
        <div className="right-panels">
          {/* CFG */}
          <section className="panel panel--cfg glass">
            <div className="panel__header">
              <div className="section-header">
                <div className="section-dot" style={{ background: 'var(--accent-amber)' }} />
                <span className="section-title">Control Flow Graph</span>
                {cfgData && (
                  <span className="info-chip">
                    CC = {cfgData.cyclomatic_complexity}
                  </span>
                )}
              </div>
              {cfgData && (
                <button
                  id="generate-tests-btn"
                  className="btn btn--success"
                  onClick={handleGenerate}
                  disabled={generating}
                >
                  {generating ? <><span className="spinner" /> Generating…</> : '⚡ Generate Tests'}
                </button>
              )}
            </div>
            <div className="panel__body panel__body--cfg">
              <CFGViewer cfgData={cfgData} highlightedPath={highlightPath} />
            </div>
            {generateErr && <div className="error-box">{generateErr}</div>}
          </section>

          {/* Test Cases */}
          <section className="panel panel--tests glass">
            <div className="panel__header">
              <div className="section-header">
                <div className="section-dot" style={{ background: 'var(--accent-green)' }} />
                <span className="section-title">Generated Test Cases</span>
                {testData && (
                  <span className="info-chip">
                    {testData.total_test_cases} cases · {testData.total_paths_enumerated} paths
                  </span>
                )}
              </div>
            </div>
            <div className="panel__body panel__body--tests">
              <TestCaseTable
                testCases={testData?.test_cases}
                onRowClick={handleRowClick}
                onExport={handleExport}
              />
            </div>
          </section>
        </div>
      </main>

      {/* Explanation side panel */}
      {selectedTC && (
        <ExplanationPanel
          testCase={selectedTC}
          onClose={() => { setSelectedTC(null); setHighlightPath([]) }}
        />
      )}
    </div>
  )
}
