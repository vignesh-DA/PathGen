import './ExplanationPanel.css'

export default function ExplanationPanel({ testCase, onClose }) {
  if (!testCase) return null

  const steps = testCase.path_steps || []
  const conditions = testCase.path_conditions || []

  return (
    <div className="exp-overlay" onClick={onClose}>
      <aside className="exp-panel fade-up" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="exp-header">
          <div className="exp-header__left">
            <span className="exp-badge">{testCase.test_id}</span>
            <span className="exp-path">{testCase.path_id}</span>
          </div>
          <button id="close-explanation-btn" className="exp-close" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {/* Explanation */}
        {testCase.explanation && (
          <div className="exp-section">
            <div className="section-header">
              <div className="section-dot" />
              <span className="section-title">AI Explanation</span>
            </div>
            <p className="exp-explanation">{testCase.explanation}</p>
          </div>
        )}

        {/* Input Values */}
        <div className="exp-section">
          <div className="section-header">
            <div className="section-dot" style={{ background: 'var(--accent-primary)' }} />
            <span className="section-title">Input Values</span>
          </div>
          <div className="exp-kv">
            {Object.entries(testCase.input_values || {}).map(([k, v]) => (
              <div key={k} className="exp-kv__row">
                <span className="exp-kv__key">{k}</span>
                <span className="exp-kv__eq">=</span>
                <span className="exp-kv__val">{String(v)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Expected Output */}
        <div className="exp-section">
          <div className="section-header">
            <div className="section-dot" style={{ background: 'var(--accent-green)' }} />
            <span className="section-title">Expected Output</span>
          </div>
          <code className="exp-output">{testCase.expected_output}</code>
        </div>

        {/* Conditions along path */}
        {conditions.length > 0 && (
          <div className="exp-section">
            <div className="section-header">
              <div className="section-dot" style={{ background: 'var(--accent-amber)' }} />
              <span className="section-title">Path Decisions</span>
            </div>
            <div className="exp-conditions">
              {conditions.map((c, i) => (
                <div key={i} className="exp-cond">
                  <span
                    className="exp-cond__branch"
                    style={{ color: c.branch_taken === 'true' ? 'var(--accent-green)' : 'var(--accent-red)' }}
                  >
                    {c.branch_taken === 'true' ? '✓ TRUE' : '✗ FALSE'}
                  </span>
                  <code className="exp-cond__expr">{c.condition_expr}</code>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Path steps */}
        {steps.length > 0 && (
          <div className="exp-section">
            <div className="section-header">
              <div className="section-dot" style={{ background: 'var(--accent-purple)' }} />
              <span className="section-title">Execution Path</span>
            </div>
            <div className="exp-steps">
              {steps.map((s, i) => (
                <div key={i} className="exp-step">
                  {i > 0 && <span className="exp-step__arrow">↓</span>}
                  <span className="exp-step__label">{s}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Flags */}
        <div className="exp-flags">
          <span className={`badge ${testCase.boundary_flag ? 'badge--boundary' : 'badge--derived'}`}>
            {testCase.boundary_flag ? '⬡ Boundary Value' : '○ Regular Value'}
          </span>
          <span className={`badge ${testCase.derivation_method?.includes('DERIVED') ? 'badge--derived' : 'badge--suggested'}`}>
            {testCase.derivation_method?.includes('DERIVED') ? '✓ DERIVED' : '⚠ AI-SUGGESTED'}
          </span>
        </div>
      </aside>
    </div>
  )
}
