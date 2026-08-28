import { useMemo, useState } from 'react'
import './liveOperations.css'

const DEMO_TOKEN = 'xyena-demo'

const initialInputs = {
  registry_identifier: '29ABCDE1234F1Z5',
  gst_invoice_number: 'MICRO/26/101',
  gst_status: 'REGISTERED',
  erp_order_reference: 'PO-1007',
  delivery_seller_id: 'seller_global_tech',
  delivery_invoice_number: 'INV-8942',
  bank_account_token: 'acct_demo_operating',
}

const platforms = [
  {
    id: 'registry',
    number: '01',
    name: 'Business Registry',
    tool: 'registry.businesses.get',
    action: 'Enter registry data',
    url: 'https://registry.gowshik.in/businesses/new',
    note: 'Create or inspect the synthetic legal identity and operating status.',
  },
  {
    id: 'gst',
    number: '02',
    name: 'GST Invoice',
    tool: 'gst.invoices.search',
    action: 'Create GST invoice',
    url: 'https://gst.gowshik.in/invoices/new',
    note: 'Autofill if useful, review the invoice, then click Save yourself.',
  },
  {
    id: 'erp',
    number: '03',
    name: 'Buyer ERP',
    tool: 'erp.purchase_orders.get',
    action: 'Open buyer ERP',
    url: 'https://erp.gowshik.in/purchase-orders',
    note: 'Review the buyer purchase order, receipt and invoice-match evidence.',
  },
  {
    id: 'delivery',
    number: '04',
    name: 'Delivery',
    tool: 'delivery.deliveries.find_by_invoice',
    action: 'Change delivery status',
    url: 'https://delivery.gowshik.in/deliveries',
    note: 'Change status in the delivery dashboard, then refresh this live snapshot.',
  },
  {
    id: 'bank',
    number: '05',
    name: 'Bank',
    tool: 'bank.accounts.get_balance',
    action: 'Open bank transactions',
    url: 'https://bank.gowshik.in/transactions',
    note: 'See the current synthetic balance and its latest credit entries below.',
  },
]

function Brand() {
  return (
    <a className="ops-brand" href="/" aria-label="Xyena home">
      <span>XY</span>
      <div><strong>XYENA</strong><small>Guardian operations</small></div>
    </a>
  )
}

function sourceData(step) {
  if (!step?.output_data || typeof step.output_data !== 'object') return step?.output_data || {}
  return step.output_data.data && typeof step.output_data.data === 'object'
    ? step.output_data.data
    : step.output_data
}

function formatInr(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return value || '—'
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(number)
}

function platformSummary(platform, step) {
  const data = sourceData(step)
  if (!step) return { primary: 'Not read yet', secondary: 'Run the live snapshot to query this source.' }
  if (step.status !== 'verified') return { primary: 'Source unavailable', secondary: data?.error || 'The governed tool call did not complete.' }

  if (platform.id === 'registry') {
    const value = data.business || data
    return {
      primary: value.legal_name || value.trade_name || value.business_id || 'Registry record returned',
      secondary: [value.status, value.classification, value.gstin].filter(Boolean).join(' · '),
    }
  }
  if (platform.id === 'gst') {
    const item = data.items?.[0]
    return {
      primary: item?.invoice_number || 'No matching invoice',
      secondary: item ? `${item.status} · ${formatInr(item.total_invoice_value)}` : 'Change the GST reference and run again.',
    }
  }
  if (platform.id === 'erp') {
    return {
      primary: data.po_number || data.order_number || data.id || 'Purchase order returned',
      secondary: [data.status, data.supplier_name, data.currency && data.total_value ? formatInr(data.total_value) : null].filter(Boolean).join(' · '),
    }
  }
  if (platform.id === 'delivery') {
    const item = data.deliveries?.[0]
    return {
      primary: item?.tracking_number || item?.delivery_number || 'No matching delivery',
      secondary: item ? `${item.status} · version ${item.version}` : 'Update the invoice identity and run again.',
    }
  }
  return {
    primary: formatInr(data.available_balance || data.current_balance),
    secondary: `${data.currency || 'INR'} available · ${data.status || 'source returned'}`,
  }
}

function LiveOperations() {
  const [inputs, setInputs] = useState(initialInputs)
  const [snapshot, setSnapshot] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')
  const [progress, setProgress] = useState([])
  const [openStep, setOpenStep] = useState(null)

  const stepByTool = useMemo(
    () => Object.fromEntries((snapshot?.steps || []).map((step) => [step.tool_name, step])),
    [snapshot],
  )
  const transactionStep = stepByTool['bank.transactions.list']
  const transactionData = sourceData(transactionStep)
  const credits = (transactionData.transactions || []).filter((item) => item.direction === 'CREDIT')

  const updateInput = (event) => {
    setInputs((current) => ({ ...current, [event.target.name]: event.target.value }))
  }

  const runSnapshot = async (event) => {
    event.preventDefault()
    if (running) return
    setRunning(true)
    setError('')
    setSnapshot(null)
    setOpenStep(null)
    setProgress(platforms.map((platform, index) => ({ ...platform, state: index === 0 ? 'active' : 'queued' })))
    const timers = platforms.slice(1).map((_, index) => window.setTimeout(() => {
      setProgress((current) => current.map((platform, platformIndex) => ({
        ...platform,
        state: platformIndex < index + 1 ? 'complete' : platformIndex === index + 1 ? 'active' : 'queued',
      })))
    }, 700 + index * 900))

    try {
      const response = await fetch('/live/api/demo/operations-snapshot', {
        method: 'POST',
        cache: 'no-store',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-Demo-Token': DEMO_TOKEN,
        },
        body: JSON.stringify(inputs),
      })
      if (!response.ok) {
        const body = await response.json().catch(() => ({}))
        const retry = response.headers.get('Retry-After')
        throw new Error(response.status === 429
          ? `A snapshot was just created. Run again in ${retry || 'a few'} seconds.`
          : body.detail || `Live snapshot failed with HTTP ${response.status}.`)
      }
      const receipt = await response.json()
      setSnapshot(receipt)
      setProgress(platforms.map((platform) => {
        const matching = receipt.steps.find((step) => step.tool_name === platform.tool)
        return { ...platform, state: matching?.status === 'verified' ? 'complete' : 'failed' }
      }))
    } catch (requestError) {
      setError(requestError.message || 'The live operations snapshot did not complete.')
      setProgress((current) => current.map((platform) => ({
        ...platform,
        state: platform.state === 'active' ? 'failed' : platform.state,
      })))
    } finally {
      timers.forEach((timer) => window.clearTimeout(timer))
      setRunning(false)
    }
  }

  return (
    <div className="live-operations">
      <header className="ops-header">
        <Brand />
        <nav aria-label="Operations navigation">
          <a href="/live-demo">Judge lab</a>
          <a href="/architecture-live">Architecture</a>
          <a href="/">Platform</a>
        </nav>
        <span className="ops-environment"><i /> Synthetic live systems</span>
      </header>

      <main className="ops-main">
        <section className="ops-intro">
          <div>
            <p className="ops-eyebrow">LIVE OPERATIONS / ONE WORKSPACE</p>
            <h1>Enter the references once.<br /><em>Follow the business event everywhere.</em></h1>
          </div>
          <aside>
            <strong>Human-controlled changes</strong>
            <p>Source dashboards create or change records. Xyena reads the committed result through Guardian and MCP. No button here silently submits a source-system change.</p>
          </aside>
        </section>

        <section className="ops-source-strip" aria-label="Source application workflow">
          {platforms.map((platform) => (
            <a href={platform.url} target="_blank" rel="noreferrer" key={platform.id}>
              <span>{platform.number}</span>
              <div><strong>{platform.name}</strong><small>{platform.action}</small></div>
              <b aria-hidden="true">↗</b>
            </a>
          ))}
        </section>

        <section className="ops-workbench">
          <form className="ops-form" onSubmit={runSnapshot}>
            <header>
              <div><small>Judge inputs</small><h2>Source references</h2></div>
              <button type="button" onClick={() => setInputs(initialInputs)}>Use seeded references</button>
            </header>
            <div className="ops-fields">
              <label><span>Registry GSTIN / number</span><input name="registry_identifier" value={inputs.registry_identifier} onChange={updateInput} required /></label>
              <label><span>GST invoice number</span><input name="gst_invoice_number" value={inputs.gst_invoice_number} onChange={updateInput} required /></label>
              <label><span>GST lifecycle status</span><select name="gst_status" value={inputs.gst_status} onChange={updateInput}><option>REGISTERED</option><option>SUBMITTED</option><option>DRAFT</option></select></label>
              <label><span>Buyer ERP PO</span><input name="erp_order_reference" value={inputs.erp_order_reference} onChange={updateInput} required /></label>
              <label><span>Delivery seller ID</span><input name="delivery_seller_id" value={inputs.delivery_seller_id} onChange={updateInput} required /></label>
              <label><span>Delivery invoice number</span><input name="delivery_invoice_number" value={inputs.delivery_invoice_number} onChange={updateInput} required /></label>
              <label className="is-wide"><span>Bank account token</span><input name="bank_account_token" value={inputs.bank_account_token} onChange={updateInput} required /></label>
            </div>
            <footer>
              <p><strong>Six calls</strong><span>5 platforms · read only · full Guardian receipts</span></p>
              <button type="submit" disabled={running}>{running ? 'Reading live sources…' : 'Run all live MCP reads'}<b>→</b></button>
            </footer>
          </form>

          <div className="ops-progress" aria-live="polite">
            <header><small>Execution rail</small><strong>{running ? 'Reading live systems' : snapshot ? `${snapshot.successful_calls}/${snapshot.total_calls} calls returned` : 'Ready for a judge run'}</strong></header>
            <ol>
              {(progress.length ? progress : platforms.map((platform) => ({ ...platform, state: 'queued' }))).map((platform) => (
                <li className={`is-${platform.state}`} key={platform.id}>
                  <span>{platform.state === 'complete' ? '✓' : platform.number}</span>
                  <div><strong>{platform.name}</strong><code>{platform.tool}</code></div>
                  <em>{platform.state === 'active' ? 'CALLING' : platform.state}</em>
                </li>
              ))}
            </ol>
            {running && <div className="ops-analyzing"><i /><span>Guardian is checking the signed scope and exact tool arguments.</span></div>}
          </div>
        </section>

        {error && <div className="ops-error" role="alert"><strong>Snapshot not completed</strong><span>{error}</span></div>}

        <section className="ops-results" aria-label="Live platform results">
          <header>
            <div><small>Committed source state</small><h2>One workflow, five systems</h2></div>
            {snapshot && <p><strong>{snapshot.status.toUpperCase()}</strong><span>{snapshot.snapshot_id} · {snapshot.duration_ms} ms</span></p>}
          </header>
          <div className="ops-result-grid">
            {platforms.map((platform) => {
              const step = stepByTool[platform.tool]
              const summary = platformSummary(platform, step)
              return (
                <article className={`ops-result-card is-${step?.status || 'idle'}`} key={platform.id}>
                  <header><span>{platform.number}</span><small>{step?.guardian?.outcome || (step ? step.status : 'WAITING')}</small></header>
                  <h3>{platform.name}</h3>
                  <strong>{summary.primary}</strong>
                  <p>{summary.secondary || platform.note}</p>
                  <div className="ops-card-actions">
                    <a href={platform.url} target="_blank" rel="noreferrer">{platform.action} ↗</a>
                    {step && <button type="button" onClick={() => setOpenStep(openStep === step.tool_name ? null : step.tool_name)}>Tool receipt</button>}
                  </div>
                </article>
              )
            })}
          </div>
        </section>

        {openStep && stepByTool[openStep] && (
          <section className="ops-receipt">
            <header><div><small>Actual backend receipt</small><h2>{openStep}</h2></div><button type="button" onClick={() => setOpenStep(null)}>Close</button></header>
            <div>
              <article><small>Request</small><pre>{JSON.stringify(stepByTool[openStep].input_data, null, 2)}</pre></article>
              <article><small>Source response</small><pre>{JSON.stringify(stepByTool[openStep].output_data, null, 2)}</pre></article>
              <article><small>Guardian</small><pre>{JSON.stringify(stepByTool[openStep].guardian, null, 2)}</pre></article>
            </div>
            <footer><span>Call ID {stepByTool[openStep].call_id}</span><span>Provenance {stepByTool[openStep].provenance_hash}</span><span>{stepByTool[openStep].latency_ms} ms</span></footer>
          </section>
        )}

        <section className="ops-bank-panel">
          <header>
            <div><small>Bank / live credit tape</small><h2>Credits received in the selected account</h2></div>
            <a href="https://bank.gowshik.in/transactions" target="_blank" rel="noreferrer">Open full bank ledger ↗</a>
          </header>
          <div className="ops-credit-list">
            {credits.length === 0 && <p className="ops-empty">Run the live snapshot to load the current credit entries.</p>}
            {credits.map((credit) => (
              <article key={credit.reference || `${credit.booked_on}-${credit.amount}`}>
                <time>{credit.booked_on}</time>
                <div><strong>{credit.description}</strong><small>{credit.reference} · {credit.category}</small></div>
                <span>+ {formatInr(credit.amount)}</span>
                <em>LIVE SOURCE</em>
              </article>
            ))}
          </div>
        </section>
      </main>

      <footer className="ops-footer"><span>Xyena + Guardian</span><p>Synthetic, non-production records only. Every result above comes from a fresh MCP call.</p></footer>
    </div>
  )
}

export default LiveOperations
