import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './liveDemo.css'

const DEMO_TOKEN = 'xyena-demo'

const judgeScenarios = [
  {
    id: 'platform_network',
    label: '6-platform MCP tour',
    reference: 'NETWORK/READ-ONLY',
    description: 'Guardian-governed reads across Registry, GST, ERP, Delivery, Bank and Ledger.',
  },
  {
    id: 'verified_invoice',
    label: 'Verified invoice',
    reference: 'MICRO/26/101',
    description: 'Registered invoice with matching amount, buyer, status and active seller.',
  },
  {
    id: 'amount_mismatch',
    label: 'Amount mismatch',
    reference: 'MICRO/26/101',
    description: 'The source invoice exists, but the submitted amount differs from GST evidence.',
  },
  {
    id: 'submitted_invoice',
    label: 'Not yet registered',
    reference: 'MICRO/26/102',
    description: 'A submitted invoice is found but cannot pass registered-invoice eligibility.',
  },
]

const services = [
  { id: 'api', name: 'Xyena Core API', role: 'Agent sessions and orchestration', endpoint: '/live/api' },
  { id: 'guardian', name: 'Guardian', role: 'Independent action control', endpoint: '/live/guardian' },
  { id: 'mcp', name: 'MCP Gateway', role: 'Tool registry and execution boundary', endpoint: '/live/mcp' },
  { id: 'bank', name: 'Bank connector', role: 'Synthetic banking service', endpoint: '/live/bank' },
  { id: 'gst', name: 'GST portal', role: 'Synthetic invoice registry', endpoint: '/live/gst' },
  { id: 'erp', name: 'Buyer ERP', role: 'Synthetic buyer operations', endpoint: '/live/erp' },
  { id: 'registry', name: 'Business registry', role: 'Synthetic enterprise records', endpoint: '/live/registry' },
  { id: 'funder', name: 'Funder marketplace', role: 'Synthetic funding workflow', endpoint: '/live/funder' },
  { id: 'delivery', name: 'Delivery network', role: 'Synthetic fulfilment evidence', endpoint: '/live/delivery' },
  { id: 'ledger', name: 'Ledger & payments', role: 'Synthetic settlement records', endpoint: '/live/ledger' },
]

const emptyStatuses = Object.fromEntries(services.map(({ id }) => [id, { state: 'idle', latency: null }]))

function BrandMark() {
  return (
    <a className="proof-brand" href="/" aria-label="Xyena home">
      <span className="proof-brand__mark" aria-hidden="true">X</span>
      <span><strong>XYENA</strong><small>Enterprise AI</small></span>
    </a>
  )
}

function StateDot({ state }) {
  return <span className={`state-dot state-dot--${state}`} aria-hidden="true" />
}

function LiveDemo() {
  const [statuses, setStatuses] = useState(emptyStatuses)
  const [events, setEvents] = useState([])
  const [proof, setProof] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [scenario, setScenario] = useState(judgeScenarios[0].id)
  const [trace, setTrace] = useState(null)
  const [traceRunning, setTraceRunning] = useState(false)
  const [traceError, setTraceError] = useState('')
  const [selectedStep, setSelectedStep] = useState(null)
  const [evidenceTab, setEvidenceTab] = useState('response')
  const [pdfFile, setPdfFile] = useState(null)
  const [pdfScan, setPdfScan] = useState(null)
  const [pdfScanning, setPdfScanning] = useState(false)
  const [pdfError, setPdfError] = useState('')
  const fileInput = useRef(null)
  const [clock, setClock] = useState(new Date())
  const mounted = useRef(false)

  const addEvent = useCallback((label, state, detail) => {
    setEvents((current) => [{
      id: crypto.randomUUID(),
      time: new Date(),
      label,
      state,
      detail,
    }, ...current].slice(0, 18))
  }, [])

  const runServiceChecks = useCallback(async () => {
    setStatuses(Object.fromEntries(services.map(({ id }) => [id, { state: 'checking', latency: null }])))
    addEvent('Connectivity sweep', 'checking', 'Requesting fresh readiness responses')

    const results = await Promise.all(services.map(async (service) => {
      const started = performance.now()
      try {
        const response = await fetch(`${service.endpoint}/health/ready?proof=${Date.now()}`, {
          cache: 'no-store',
          headers: { Accept: 'application/json' },
        })
        const latency = Math.round(performance.now() - started)
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const body = await response.json()
        const ready = ['ok', 'ready'].includes(body.status)
        const state = ready ? 'verified' : 'failed'
        setStatuses((current) => ({ ...current, [service.id]: { state, latency } }))
        addEvent(service.name, state, ready ? `Ready in ${latency} ms` : 'Readiness response was not ready')
        return ready
      } catch {
        const latency = Math.round(performance.now() - started)
        setStatuses((current) => ({ ...current, [service.id]: { state: 'failed', latency } }))
        addEvent(service.name, 'failed', `No ready response after ${latency} ms`)
        return false
      }
    }))

    const online = results.filter(Boolean).length
    addEvent('Connectivity sweep', online === services.length ? 'verified' : 'failed', `${online}/${services.length} services ready`)
    return online
  }, [addEvent])

  useEffect(() => {
    if (mounted.current) return
    mounted.current = true
    runServiceChecks()
  }, [runServiceChecks])

  useEffect(() => {
    const timer = window.setInterval(() => setClock(new Date()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const runProof = async () => {
    if (running) return
    setRunning(true)
    setError('')
    setProof(null)
    const online = await runServiceChecks()
    addEvent('Evidence receipt', 'checking', 'Querying PostgreSQL, registry, Guardian, MCP and model provider')
    try {
      const response = await fetch('/live/api/demo/live-proof', {
        method: 'POST',
        cache: 'no-store',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-Demo-Token': DEMO_TOKEN,
        },
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        const retry = response.headers.get('Retry-After')
        throw new Error(response.status === 429
          ? `A proof was just created. Try again in ${retry || 'a few'} seconds.`
          : body.detail || `Proof request failed with HTTP ${response.status}.`)
      }
      const receipt = await response.json()
      setProof(receipt)
      addEvent('Evidence receipt', receipt.status === 'verified' ? 'verified' : 'failed', `${receipt.status.toUpperCase()} · ${receipt.duration_ms} ms`)
      if (online !== services.length || receipt.status !== 'verified') {
        setError('The run completed with degraded evidence. Review the failed item below.')
      }
    } catch (requestError) {
      setError(requestError.message || 'The proof request could not be completed.')
      addEvent('Evidence receipt', 'failed', requestError.message || 'Request failed')
    } finally {
      setRunning(false)
    }
  }

  const runJudgeTrace = async (event) => {
    event?.preventDefault()
    if (traceRunning) return
    setTraceRunning(true)
    setTraceError('')
    setTrace(null)
    setSelectedStep(null)
    addEvent('Judge agent trace', 'checking', `Running ${judgeScenarios.find((item) => item.id === scenario)?.reference}`)
    try {
      const response = await fetch('/live/api/demo/judge-trace', {
        method: 'POST',
        cache: 'no-store',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-Demo-Token': DEMO_TOKEN,
        },
        body: JSON.stringify({ scenario }),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        const retry = response.headers.get('Retry-After')
        throw new Error(response.status === 429
          ? `A trace was just created. Try again in ${retry || 'a few'} seconds.`
          : body.detail || `Agent trace failed with HTTP ${response.status}.`)
      }
      const result = await response.json()
      setTrace(result)
      setSelectedStep(result.steps.find((step) => step.kind === 'tool') || result.steps[0])
      setEvidenceTab('response')
      addEvent('Judge agent trace', result.verified ? 'verified' : 'failed', `${result.verified ? 'VERIFIED' : 'NOT VERIFIED'} · ${result.steps.length} recorded steps`)
    } catch (requestError) {
      setTraceError(requestError.message || 'The agent trace could not be completed.')
      addEvent('Judge agent trace', 'failed', requestError.message || 'Request failed')
    } finally {
      setTraceRunning(false)
    }
  }

  const acceptPdf = (file) => {
    setPdfError('')
    setPdfScan(null)
    if (!file) return
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setPdfFile(null)
      setPdfError('Choose a PDF document.')
      return
    }
    if (file.size > 2 * 1024 * 1024) {
      setPdfFile(null)
      setPdfError('Choose a PDF smaller than 2 MB.')
      return
    }
    setPdfFile(file)
  }

  const loadMaliciousSample = async () => {
    setPdfError('')
    try {
      const response = await fetch('/demo/malicious-invoice-injection.pdf', { cache: 'no-store' })
      if (!response.ok) throw new Error('The sample PDF could not be loaded.')
      const blob = await response.blob()
      acceptPdf(new File([blob], 'malicious-invoice-injection.pdf', { type: 'application/pdf' }))
    } catch (sampleError) {
      setPdfError(sampleError.message || 'The sample PDF could not be loaded.')
    }
  }

  const scanPdf = async (event) => {
    event?.preventDefault()
    if (!pdfFile || pdfScanning) {
      if (!pdfFile) setPdfError('Load the sample or choose a PDF first.')
      return
    }
    setPdfScanning(true)
    setPdfError('')
    setPdfScan(null)
    addEvent('Document defense', 'checking', `Scanning ${pdfFile.name} as untrusted evidence`)
    try {
      const response = await fetch('/live/api/demo/scan-pdf', {
        method: 'POST',
        cache: 'no-store',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/pdf',
          'X-Demo-Token': DEMO_TOKEN,
          'X-File-Name': encodeURIComponent(pdfFile.name),
        },
        body: pdfFile,
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        const retry = response.headers.get('Retry-After')
        throw new Error(response.status === 429
          ? `A document was just scanned. Try again in ${retry || 'a few'} seconds.`
          : body.detail || `PDF scan failed with HTTP ${response.status}.`)
      }
      const report = await response.json()
      setPdfScan(report)
      addEvent('Document defense', report.flagged ? 'failed' : 'verified', `${report.classification} · ${report.findings.length} indicators`)
    } catch (scanError) {
      setPdfError(scanError.message || 'The PDF scan could not be completed.')
      addEvent('Document defense', 'failed', scanError.message || 'Scan failed')
    } finally {
      setPdfScanning(false)
    }
  }

  const onlineCount = useMemo(
    () => Object.values(statuses).filter(({ state }) => state === 'verified').length,
    [statuses],
  )
  const completedChecks = useMemo(
    () => Object.values(statuses).filter(({ state }) => ['verified', 'failed'].includes(state)).length,
    [statuses],
  )
  const overallState = proof?.status || (running ? 'checking' : completedChecks === services.length && onlineCount === services.length ? 'ready' : 'idle')
  const proofSteps = [
    { label: 'Service mesh', done: onlineCount === services.length },
    { label: 'PostgreSQL', done: proof?.database?.status === 'verified' },
    { label: 'MCP + Guardian', done: proof?.mcp_gateway?.status === 'verified' && proof?.guardian?.status === 'verified' },
    { label: 'Model inference', done: proof?.model?.status === 'verified' },
  ]

  return (
    <div className="live-demo" id="top">
      <header className="proof-header">
        <BrandMark />
        <nav aria-label="Live demo navigation">
          <a href="/">Platform</a>
          <a href="/architecture-live">Architecture</a>
          <span className="environment-badge"><i /> Production evidence</span>
        </nav>
      </header>

      <main className="proof-shell">
        <section className="proof-hero">
          <div className="proof-hero__copy">
            <p className="proof-kicker"><span>LIVE / READ-ONLY</span> Judge verification console</p>
            <h1>Don’t take our word for it.<br /><em>Verify the platform live.</em></h1>
            <p className="proof-intro">One run checks every deployed service, queries the PostgreSQL-backed MCP registry, contacts Guardian and the MCP Gateway, then requests a fresh response from the configured model provider.</p>
            <div className="proof-actions">
              <button className="verify-button" type="button" onClick={runProof} disabled={running}>
                <span>{running ? 'Verification running' : 'Run live verification'}</span>
                <b aria-hidden="true">{running ? '•••' : '→'}</b>
              </button>
              <a className="proof-lab-link" href="#judge-lab">Try the agent trace ↓</a>
              <p><span className="lock-icon" aria-hidden="true">◇</span> Synthetic data only. No financial state changes.</p>
            </div>
          </div>

          <aside className={`proof-stamp proof-stamp--${overallState}`} aria-live="polite">
            <div className="proof-stamp__top"><span>Current state</span><time>{clock.toLocaleTimeString('en-IN', { hour12: false })} IST</time></div>
            <strong>{proof?.status === 'verified' ? 'VERIFIED' : proof?.status === 'degraded' ? 'DEGRADED' : running ? 'CHECKING' : onlineCount === services.length ? 'READY' : 'AWAITING RUN'}</strong>
            <p>{proof ? `Proof ${proof.proof_id}` : 'Generate a cryptographically unique receipt backed by current service responses.'}</p>
            <div className="proof-stamp__seal"><span>XY</span><small>Live<br />evidence</small></div>
          </aside>
        </section>

        <section className="verification-rail" aria-label="Verification progress">
          {proofSteps.map((step, index) => (
            <div className={step.done ? 'is-complete' : running ? 'is-active' : ''} key={step.label}>
              <span>{step.done ? '✓' : String(index + 1).padStart(2, '0')}</span>
              <p><small>Evidence layer</small><strong>{step.label}</strong></p>
            </div>
          ))}
        </section>

        {error && <div className="proof-alert" role="status"><strong>Verification note</strong><span>{error}</span></div>}

        <section className="evidence-summary" aria-label="Live evidence summary">
          <article><small>Services ready</small><strong>{onlineCount}<span> / {services.length}</span></strong><p>Fresh HTTP readiness responses</p></article>
          <article><small>Active MCP servers</small><strong>{proof?.registry?.active_servers ?? '—'}</strong><p>Read from the live registry</p></article>
          <article><small>Registered tools</small><strong>{proof?.registry?.active_tools ?? '—'}</strong><p>Active, governed capabilities</p></article>
          <article><small>Model proof</small><strong className="summary-model">{proof?.model?.output || 'Awaiting run'}</strong><p>{proof ? `${proof.model.provider} · ${proof.model.latency_ms} ms` : 'Fresh inference required'}</p></article>
        </section>

        <nav className="judge-walkthrough" aria-label="Judge walkthrough">
          <div><small>Suggested walkthrough</small><strong>Three things to try in 4 minutes</strong></div>
          <a href="#top"><span>1</span><p><strong>Prove it is live</strong><small>Run platform verification</small></p></a>
          <a href="#judge-lab"><span>2</span><p><strong>Inspect tool calls</strong><small>Run an invoice trace</small></p></a>
          <a href="#document-security"><span>3</span><p><strong>Attack the agent</strong><small>Upload the malicious PDF</small></p></a>
        </nav>

        <section className="judge-lab" id="judge-lab">
          <div className="judge-lab__header">
            <div>
              <p className="lab-index">01 / HANDS-ON AGENT TRACE</p>
              <h2>Watch Xyena inspect the evidence network.</h2>
              <p>Start with the six-platform tour or choose an invoice edge case. Every MCP request, returned source record, Guardian authorization and deterministic check remains visible.</p>
            </div>
            <span className="read-only-seal">READ ONLY<br /><b>NO MONEY MOVES</b></span>
          </div>

          <form className="scenario-console" onSubmit={runJudgeTrace}>
            <fieldset>
              <legend>Choose a cross-platform tour or invoice verification case</legend>
              <div className="scenario-options">
                {judgeScenarios.map((item) => (
                  <button
                    className={scenario === item.id ? 'is-selected' : ''}
                    type="button"
                    onClick={() => {
                      setScenario(item.id)
                      setTrace(null)
                      setSelectedStep(null)
                      setTraceError('')
                    }}
                    key={item.id}
                  >
                    <span>{item.label}</span>
                    <code>{item.reference}</code>
                    <small>{item.description}</small>
                  </button>
                ))}
              </div>
            </fieldset>
            <div className="scenario-runner">
              <div><small>Prefilled source reference</small><strong>{judgeScenarios.find((item) => item.id === scenario)?.reference}</strong></div>
              <p>Press Enter or run the trace. Xyena can only call the allowlisted read tools assigned to the selected demonstration.</p>
              <button type="submit" disabled={traceRunning}>
                <span>{traceRunning ? 'Agent is checking evidence' : 'Run agent trace'}</span>
                <b>{traceRunning ? '•••' : '↵'}</b>
              </button>
            </div>
          </form>

          {traceError && <div className="trace-error" role="status"><strong>Trace did not run</strong><span>{traceError}</span></div>}

          {!trace && !traceRunning && (
            <div className="trace-empty">
              <div className="trace-empty__flow" aria-hidden="true">
                <span>Xyena agent</span><i>→</i><span>MCP Gateway</span><i>→</i><span>Guardian</span><i>→</i><span>GST source</span>
              </div>
              <p>The execution tape will appear here with the input and output of every call.</p>
            </div>
          )}

          {traceRunning && (
            <div className="trace-loading" aria-live="polite">
              <div className="trace-loading__tape"><i /><i /><i /><i /><i /></div>
              <div><strong>Agent trace in progress</strong><p>Guardian is evaluating each exact request before MCP retrieves the source evidence.</p></div>
            </div>
          )}

          {trace && (
            <div className={`trace-result trace-result--${trace.status}`}>
              <header className="trace-verdict">
                <div>
                  <small>Deterministic result</small>
                  <strong>{trace.verified ? 'VERIFIED' : trace.status === 'error' ? 'TRACE ERROR' : 'NOT VERIFIED'}</strong>
                </div>
                <p>{trace.summary}</p>
                <dl>
                  <div><dt>Trace</dt><dd>{trace.trace_id.slice(0, 8)}</dd></div>
                  <div><dt>Calls</dt><dd>{trace.steps.filter((step) => step.kind === 'tool').length}</dd></div>
                  <div><dt>Duration</dt><dd>{trace.duration_ms} ms</dd></div>
                  <div><dt>Business state</dt><dd>Unchanged</dd></div>
                  <div><dt>Audit records</dt><dd>Created</dd></div>
                </dl>
              </header>

              {trace.risk && (
                <section className={`risk-decision risk-decision--${trace.risk.band.toLowerCase()}`} aria-labelledby="riskDecisionTitle">
                  <header>
                    <div><small>Final governed tool-call risk</small><h3 id="riskDecisionTitle">One score across every connected platform</h3><p>{trace.risk.explanation}</p></div>
                    <div className="risk-score"><strong>{trace.risk.score}</strong><span>/100</span><em>{trace.risk.band}</em></div>
                    <div className="risk-policy"><small>Policy action</small><strong>{trace.risk.policy_action}</strong><code>{trace.risk.formula_version}</code></div>
                  </header>
                  <div className="risk-formula" aria-label="Final score calculation">
                    <span><small>Highest tool subtotal</small><strong>{trace.risk.calculation.highest_tool_subtotal}</strong></span><b>+</b>
                    <span><small>Platform breadth</small><strong>{trace.risk.calculation.cross_platform_breadth}</strong></span><b>+</b>
                    <span><small>Call volume</small><strong>{trace.risk.calculation.call_volume}</strong></span><b>{trace.risk.calculation.protected_read_reduction < 0 ? '−' : '+'}</b>
                    <span><small>Protected-read reduction</small><strong>{Math.abs(trace.risk.calculation.protected_read_reduction)}</strong></span><b>=</b>
                    <span className="risk-formula__total"><small>Final score</small><strong>{trace.risk.score}</strong></span>
                  </div>
                  <div className="risk-table-wrap">
                    <table className="risk-table">
                      <thead><tr><th>Platform / MCP tool</th><th>Registered class</th><th>Risk pts</th><th>Guardian</th><th>Guardian pts</th><th>Failure pts</th><th>Security pts</th><th>Tool subtotal</th></tr></thead>
                      <tbody>{trace.risk.tools.map((tool) => (
                        <tr key={tool.tool_name}>
                          <td><span>{tool.platform}</span><code>{tool.tool_name}</code></td>
                          <td><em>{tool.risk_class}</em></td>
                          <td>{tool.registered_risk_points}</td>
                          <td><em className={`risk-outcome risk-outcome--${tool.guardian_outcome.toLowerCase()}`}>{tool.guardian_outcome}</em></td>
                          <td>{tool.guardian_points}</td>
                          <td>{tool.execution_points}</td>
                          <td>{tool.security_points}</td>
                          <td><strong>{tool.subtotal}</strong></td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                  <footer><strong>Why highest, not sum?</strong><span>Six safe reads should not become high risk merely because six were called. The highest tool subtotal sets the action risk; breadth and volume are added once.</span></footer>
                </section>
              )}

              <div className="trace-workbench">
                <div className="execution-tape" aria-label="Agent execution steps">
                  <div className="execution-tape__heading"><span>Execution tape</span><code>{trace.correlation_id}</code></div>
                  {trace.steps.map((step) => (
                    <button
                      className={`${selectedStep?.sequence === step.sequence ? 'is-active' : ''} trace-step--${step.status}`}
                      style={{ '--step-delay': `${step.sequence * 55}ms` }}
                      type="button"
                      onClick={() => { setSelectedStep(step); setEvidenceTab('response') }}
                      key={`${step.sequence}-${step.title}`}
                    >
                      <span className="trace-sequence">{String(step.sequence).padStart(2, '0')}</span>
                      <StateDot state={step.status} />
                      <span className="trace-step__copy">
                        <small>{step.actor}</small>
                        <strong>{step.title}</strong>
                        <code>{step.tool_name || step.kind.toUpperCase()}</code>
                      </span>
                      <span className="trace-step__meta">
                        {step.guardian?.outcome && <em>Guardian {step.guardian.outcome}</em>}
                        <code>{step.latency_ms} ms</code>
                      </span>
                    </button>
                  ))}
                </div>

                <div className="evidence-drawer">
                  {selectedStep && (
                    <>
                      <header>
                        <div><small>Selected evidence</small><h3>{selectedStep.title}</h3></div>
                        <span className={`drawer-status drawer-status--${selectedStep.status}`}>{selectedStep.status}</span>
                      </header>
                      <div className="evidence-tabs" role="tablist" aria-label="Evidence views">
                        {['request', 'response', 'guardian'].map((tab) => (
                          <button
                            className={evidenceTab === tab ? 'is-active' : ''}
                            type="button"
                            role="tab"
                            aria-selected={evidenceTab === tab}
                            onClick={() => setEvidenceTab(tab)}
                            key={tab}
                          >{tab}</button>
                        ))}
                      </div>
                      <div className="evidence-meta">
                        <span><small>Tool</small><code>{selectedStep.tool_name || '—'}</code></span>
                        <span><small>Call ID</small><code>{selectedStep.call_id || 'Not applicable'}</code></span>
                        <span><small>Provenance</small><code>{selectedStep.provenance_hash || 'Not applicable'}</code></span>
                      </div>
                      <pre tabIndex="0">{JSON.stringify(
                        evidenceTab === 'request'
                          ? selectedStep.input_data
                          : evidenceTab === 'guardian'
                            ? selectedStep.guardian || { message: 'Guardian is not required for this non-tool step.' }
                            : selectedStep.output_data,
                        null,
                        2,
                      )}</pre>
                    </>
                  )}
                </div>
              </div>
            </div>
          )}
        </section>

        <section className="document-lab" id="document-security">
          <div className="document-lab__header">
            <div>
              <p className="lab-index">02 / ADVERSARIAL DOCUMENT TEST</p>
              <h2>Upload a PDF that tries to control the agent.</h2>
              <p>Xyena extracts bounded text without sending it to the model, detects instruction manipulation, quarantines the content and executes zero tools.</p>
            </div>
            <div className="document-route"><small>Upload and test here</small><code>app.gowshik.in/live-demo<br />↓ Document security lab</code></div>
          </div>

          <div className="document-walkthrough">
            <ol>
              <li><span>1</span><p><strong>Load the supplied attack PDF</strong><small>Or choose your own PDF under 2 MB and 8 pages.</small></p></li>
              <li><span>2</span><p><strong>Run the bounded scan</strong><small>The file is parsed as untrusted data, never as instructions.</small></p></li>
              <li><span>3</span><p><strong>Inspect the block evidence</strong><small>Confirm flagged phrases, zero tools and no model forwarding.</small></p></li>
            </ol>
            <a href="/demo/malicious-invoice-injection.pdf" download>Download sample PDF ↓</a>
          </div>

          <form className="pdf-upload" onSubmit={scanPdf}>
            <input
              ref={fileInput}
              type="file"
              accept="application/pdf,.pdf"
              onChange={(event) => acceptPdf(event.target.files?.[0])}
              tabIndex={-1}
              aria-hidden="true"
            />
            <div
              className={`pdf-dropzone ${pdfFile ? 'has-file' : ''}`}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => { event.preventDefault(); acceptPdf(event.dataTransfer.files?.[0]) }}
            >
              <span className="pdf-glyph" aria-hidden="true">PDF</span>
              <div>
                <small>Untrusted evidence input</small>
                <strong>{pdfFile?.name || 'No PDF selected'}</strong>
                <p>{pdfFile ? `${Math.ceil(pdfFile.size / 1024)} KB ready for bounded inspection` : 'Drop a PDF here, choose a file, or load the supplied malicious sample.'}</p>
              </div>
              <div className="pdf-file-actions">
                <button type="button" onClick={() => fileInput.current?.click()}>Choose PDF</button>
                <button type="button" onClick={loadMaliciousSample}>Load attack sample</button>
              </div>
            </div>
            <div className="pdf-scan-action">
              <p><span>Policy</span> Max 2 MB · Max 8 pages · No OCR · No model context · No tool execution</p>
              <button type="submit" disabled={!pdfFile || pdfScanning}>{pdfScanning ? 'Scanning document…' : 'Scan as untrusted evidence'}</button>
            </div>
          </form>

          {pdfError && <div className="trace-error" role="status"><strong>Document scan</strong><span>{pdfError}</span></div>}

          {pdfScan && (
            <div className={`pdf-report ${pdfScan.flagged ? 'is-flagged' : 'is-clear'}`}>
              <header>
                <div><small>Document decision</small><strong>{pdfScan.flagged ? 'FLAGGED & QUARANTINED' : 'NO INJECTION FOUND'}</strong></div>
                <p>{pdfScan.flagged ? 'The document attempted to influence agent authority. Its text was blocked from model and tool context.' : 'No known prompt-injection phrase was found. This is not a guarantee that the document is trustworthy.'}</p>
                <span><small>Risk score</small><b>{pdfScan.risk_score}</b><em>/100</em></span>
              </header>
              <div className="pdf-safety-facts">
                <article><span>0</span><p><strong>Tools executed</strong><small>Document text cannot initiate MCP calls</small></p></article>
                <article><span>NO</span><p><strong>Sent to model</strong><small>Scanning is deterministic and bounded</small></p></article>
                <article><span>NO</span><p><strong>Business state changed</strong><small>The upload remains a security test</small></p></article>
                <article><span>{pdfScan.findings.length}</span><p><strong>Indicators found</strong><small>{pdfScan.reason_codes.join(' · ') || 'None'}</small></p></article>
              </div>
              <div className="pdf-report__body">
                <div className="threat-findings">
                  <h3>Flagged text</h3>
                  {pdfScan.findings.length === 0 && <p>No matching prompt-injection indicators.</p>}
                  {pdfScan.findings.map((finding, index) => (
                    <article key={`${finding.category}-${index}`}>
                      <span>{finding.severity}</span>
                      <div><strong>{finding.category.replaceAll('_', ' ')}</strong><p>Page {finding.page || 'metadata'} · “{finding.snippet}”</p></div>
                    </article>
                  ))}
                </div>
                <div className="pdf-raw-evidence">
                  <div><h3>Extracted preview</h3><code>SHA-256 {pdfScan.sha256}</code></div>
                  <pre>{pdfScan.extracted_preview || 'No extractable text.'}</pre>
                </div>
              </div>
            </div>
          )}
        </section>

        <section className="proof-grid">
          <div className="service-board">
            <div className="section-heading">
              <div><p>03 / SERVICE MESH</p><h2>Live deployment status</h2></div>
              <span>{completedChecks}/{services.length} checked</span>
            </div>
            <div className="service-list">
              {services.map((service) => {
                const current = statuses[service.id]
                return (
                  <article key={service.id}>
                    <StateDot state={current.state} />
                    <div><strong>{service.name}</strong><p>{service.role}</p></div>
                    <span className={`service-state service-state--${current.state}`}>
                      {current.state === 'checking' ? 'Checking' : current.state === 'verified' ? 'Ready' : current.state === 'failed' ? 'Failed' : 'Queued'}
                    </span>
                    <code>{current.latency === null ? '—' : `${current.latency} ms`}</code>
                  </article>
                )
              })}
            </div>
          </div>

          <aside className="event-ledger">
            <div className="section-heading">
              <div><p>04 / EVENT LEDGER</p><h2>What just happened</h2></div>
              <span className="live-label"><i /> live</span>
            </div>
            <div className="event-list" aria-live="polite">
              {events.length === 0 && <p className="event-empty">No evidence collected yet.</p>}
              {events.map((event) => (
                <article key={event.id}>
                  <time>{event.time.toLocaleTimeString('en-IN', { hour12: false })}</time>
                  <StateDot state={event.state} />
                  <div><strong>{event.label}</strong><p>{event.detail}</p></div>
                </article>
              ))}
            </div>
          </aside>
        </section>

        <section className="receipt-panel">
          <div className="section-heading">
            <div><p>05 / EVIDENCE RECEIPT</p><h2>Proof, not presentation</h2></div>
            {proof && <span className={`receipt-status receipt-status--${proof.status}`}>{proof.status}</span>}
          </div>
          {proof ? (
            <div className="receipt-grid">
              <dl>
                <div><dt>Proof identifier</dt><dd><code>{proof.proof_id}</code></dd></div>
                <div><dt>Generated at</dt><dd>{new Date(proof.checked_at).toLocaleString('en-IN')}</dd></div>
                <div><dt>Total duration</dt><dd>{proof.duration_ms} ms</dd></div>
                <div><dt>Execution scope</dt><dd>synthetic-read-only</dd></div>
                <div><dt>Financial state changed</dt><dd className="safe-value">No</dd></div>
              </dl>
              <div className="receipt-components">
                {[
                  ['PostgreSQL', proof.database],
                  ['MCP registry', proof.registry],
                  ['MCP Gateway', proof.mcp_gateway],
                  ['Guardian', proof.guardian],
                  ['Model provider', proof.model],
                ].map(([label, item]) => (
                  <article key={label}>
                    <StateDot state={item.status} />
                    <div><strong>{label}</strong><p>{item.message}</p></div>
                    <code>{item.latency_ms} ms</code>
                  </article>
                ))}
              </div>
            </div>
          ) : (
            <div className="receipt-placeholder">
              <span>05</span>
              <p><strong>No receipt generated.</strong> Press “Run live verification” to create a current, unique proof record from the deployed stack.</p>
            </div>
          )}
        </section>
      </main>

      <footer className="proof-footer">
        <BrandMark />
        <p>Live checks are non-mutating and use synthetic demonstration services.</p>
        <a href="/">Return to platform overview ↑</a>
      </footer>
    </div>
  )
}

export default LiveDemo
