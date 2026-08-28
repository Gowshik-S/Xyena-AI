import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import './liveDemo.css'

const DEMO_TOKEN = 'xyena-demo'

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
    <div className="live-demo">
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

        <section className="proof-grid">
          <div className="service-board">
            <div className="section-heading">
              <div><p>01 / SERVICE MESH</p><h2>Live deployment status</h2></div>
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
              <div><p>02 / EVENT LEDGER</p><h2>What just happened</h2></div>
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
            <div><p>03 / EVIDENCE RECEIPT</p><h2>Proof, not presentation</h2></div>
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
              <span>03</span>
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
