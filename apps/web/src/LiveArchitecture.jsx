import { useEffect, useRef, useState } from 'react'
import './liveArchitecture.css'

const runSteps = [
  {
    id: 'identity', code: 'ID', name: 'Identity and Scope Resolver', group: 'Trusted ingress',
    task: 'Resolving the authenticated tenant, MSME, user, case and consent boundary.',
    collected: ['Workload identity xyena-web-01', 'User role finance_operator', 'Consent reference consent_55', 'Requested case case_1023'],
    verified: ['Tenant and MSME membership match', 'User role permits case creation', 'Consent covers the requested purpose'],
    mcp: 'Identity and Access Service', mcpTools: ['identity.resolve_scope', 'consent.verify_purpose'],
    controls: ['RBAC and attribute policy', 'Cross-MSME isolation', 'Trusted runtime scope injection'],
    result: 'Immutable trusted scope created for tenant_01 / msme_442 / case_1023.',
  },
  {
    id: 'intake', code: 'IN', name: 'Intake Agent', group: 'Multi-agent runtime',
    task: 'Creating the financing case and checking whether investigation can begin.',
    collected: ['Invoice artifact metadata', 'Requested product invoice finance', 'Financing purpose working capital', 'Four submitted evidence references'],
    verified: ['Malware scan passed', 'Required artifact types present', 'Case scope matches authenticated user'],
    mcp: 'Supply Finance MCP', mcpTools: ['case.create', 'case.evidence_checklist.get'],
    controls: ['Submission schema v2.4', 'Artifact metadata allowlist', 'No financial execution capability'],
    result: 'Case case_1023 created with a versioned evidence checklist.',
  },
  {
    id: 'evidence', code: 'EV', name: 'Evidence Trust Gateway', group: 'Evidence trust',
    task: 'Treating every upload and external payload as untrusted data before agent use.',
    collected: ['Invoice INV-1023', 'GST e-Invoice response', 'ERP delivery record', 'Account Aggregator payload'],
    verified: ['Type, size and encoding accepted', 'No hidden instructions or active content', 'Schema projection completed', 'Four gateway signatures valid'],
    mcp: 'Evidence Receipt Service', mcpTools: ['evidence.normalize', 'evidence.issue_receipt'],
    controls: ['Content sandbox', 'Instruction-like text detector', 'Canonical hashing', 'Security classification'],
    result: 'Signed receipts evr_gst_8921, evr_erp_5510, evr_aa_2044 and evr_po_7721 issued.',
  },
  {
    id: 'context', code: 'CX', name: 'Context Assembler', group: 'Context and memory',
    task: 'Building the minimum sufficient context envelope for this case.',
    collected: ['Tenant policy sf_3.7', 'Verified MSME profile', 'User workflow preferences', 'Case and session memory'],
    verified: ['Every item has source and trust label', 'Freshness and sensitivity limits applied', 'Retrieval remained inside tenant and MSME scope'],
    mcp: 'Internal Context Runtime', mcpTools: ['context.retrieve_scoped', 'context.assemble_envelope'],
    controls: ['Metadata-filtered retrieval', 'Token and sensitivity budget', 'Memory is never authority'],
    result: 'Immutable ContextEnvelope ctx_44 created with 12 scoped references.',
  },
  {
    id: 'supervisor', code: 'WS', name: 'Workflow Supervisor', group: 'Multi-agent runtime',
    task: 'Dispatching six independent verification tasks using least-privilege capabilities.',
    collected: ['Context envelope ctx_44', 'Evidence requirement set sf_invoice_v3', 'Six specialist output schemas'],
    verified: ['Each agent received only approved tools', 'Correlation corr_5001 attached', 'Contradictions will remain visible'],
    mcp: 'Workflow Runtime', mcpTools: ['workflow.dispatch_agent_runs', 'workflow.observe_findings'],
    controls: ['Deny-by-default tool access', 'Schema-validated findings', 'Guardian call telemetry'],
    result: 'Six isolated agent runs dispatched with one evidence snapshot.',
  },
  {
    id: 'business', code: 'BU', name: 'Business Agent', group: 'Specialist verification',
    task: 'Verifying registration, ownership consistency, operating status and eligibility.',
    collected: ['GST registration 29ABCDE1234F1Z5', 'Bank ownership receipt evr_bank_310', 'KYB ownership graph', 'Tenant eligibility policy'],
    verified: ['GST status ACTIVE', 'Legal name matches bank account owner', 'Business is eligible for invoice finance'],
    mcp: 'Registry and Bank MCP', mcpTools: ['gst.business.verify', 'bank.accounts.get', 'bank.beneficiaries.verify'],
    controls: ['Official connector receipts', 'Ownership graph consistency', 'Read-only capability'],
    result: 'Business identity and beneficiary ownership verified with no mismatch.',
  },
  {
    id: 'invoice', code: 'IV', name: 'Invoice Agent', group: 'Specialist verification',
    task: 'Authenticating the invoice and checking duplicate-financing indicators.',
    collected: ['Invoice INV-1023', 'e-Invoice receipt evr_gst_8921', 'Purchase order PO-7721', 'Receivable graph results'],
    verified: ['Seller, buyer, tax and date match', 'Invoice value ₹10,00,000', 'No duplicate financing path found'],
    mcp: 'Supply Finance MCP', mcpTools: ['gst.verify_invoice', 'erp.purchase_order.get', 'receivable.duplicates.search'],
    controls: ['Invoice text treated as untrusted', 'Cross-source claim comparison', 'Provenance signature check'],
    result: 'Invoice authentic and unique. Supported value is ₹10,00,000.',
  },
  {
    id: 'delivery', code: 'DE', name: 'Delivery Agent', group: 'Specialist verification',
    task: 'Confirming that the invoiced goods were fulfilled and accepted.',
    collected: ['Dispatch note DN-888', 'ERP fulfilment record', 'Logistics delivery event', 'Buyer acceptance BA-419'],
    verified: ['Delivered quantity matches invoice', 'Buyer accepted the shipment', 'Supported delivery value ₹10,00,000'],
    mcp: 'Supply Finance MCP', mcpTools: ['erp.fulfilment.get', 'logistics.delivery.verify', 'buyer.acceptance.get'],
    controls: ['Independent buyer evidence', 'Date and quantity consistency', 'Receipt freshness check'],
    result: '100% of the invoiced value is supported by verified delivery.',
  },
  {
    id: 'payment', code: 'PA', name: 'Payment Agent', group: 'Specialist verification',
    task: 'Reconciling account activity to calculate the supported outstanding receivable.',
    collected: ['AA consent consent_55', 'Bounded 90-day transaction window', 'Invoice payment references', 'Internal ledger entries'],
    verified: ['Purpose and consent scope valid', 'No payment matched INV-1023', 'Outstanding amount ₹10,00,000'],
    mcp: 'Bank MCP', mcpTools: ['bank.aa.fetch_information', 'bank.transactions.list', 'bank.transfers.get_status'],
    controls: ['Sensitive-read minimization', 'Tokenized account identifiers', 'Raw AA JSON routed through evidence gateway'],
    result: 'The full ₹10,00,000 receivable remains outstanding.',
  },
  {
    id: 'risk', code: 'FR', name: 'Fraud and Risk Agent', group: 'Specialist verification',
    task: 'Inspecting provenance, counterparties, duplicates, behaviour and action chains.',
    collected: ['Evidence lineage graph', 'Counterparty relationship graph', 'Connector health signals', 'Historical behaviour baseline'],
    verified: ['No circular trading pattern', 'No compromised connector signal', 'No suspicious destination change', 'Risk score 18/100'],
    mcp: 'Risk Intelligence MCP', mcpTools: ['risk.graph.inspect', 'counterparty.intelligence.get', 'connector.health.read'],
    controls: ['Scoped graph traversal', 'Anomaly is not treated as proof', 'Guardian owns final verdict'],
    result: 'Low risk posture with no blocking anomaly detected.',
  },
  {
    id: 'credit', code: 'CR', name: 'Credit Agent', group: 'Specialist verification',
    task: 'Recommending safe capacity from cash flow, exposure and program policy.',
    collected: ['Verified domain findings', 'Available account balance evidence', 'Company limit ₹20,00,000', 'Current exposure ₹12,00,000'],
    verified: ['Available capacity ₹8,00,000', '70% receivable cap ₹7,00,000', 'Repayment behaviour within policy'],
    mcp: 'Bank MCP and Exposure Service', mcpTools: ['bank.accounts.get_balance', 'bank.limits.get', 'exposure.aggregate.get'],
    controls: ['Deterministic limit calculation', 'Cross-funder exposure', 'No approval or disbursement capability'],
    result: 'Recommended financing capacity is ₹7,00,000.',
  },
  {
    id: 'orchestrator', code: 'OR', name: 'Decision Orchestrator', group: 'Proposal control',
    task: 'Combining structured findings into one exact proposed financial action.',
    collected: ['Six schema-valid findings', 'Evidence completeness result', 'Exposure recommendation', 'Verified beneficiary ben_tok_14'],
    verified: ['No contradiction hidden', 'Exact source, destination and amount fixed', 'Preparation moves no money'],
    mcp: 'Bank MCP', mcpTools: ['bank.transfers.prepare'],
    controls: ['Canonical action serialization', 'Action hash generation', 'No execution capability'],
    result: 'ProposedAction act_9001 created with canonical hash sha256:8d21.',
  },
  {
    id: 'exposure', code: 'EX', name: 'Exposure and Eligibility Engine', group: 'Deterministic control',
    task: 'Applying aggregate cross-funder capacity and verified-receivable policy.',
    collected: ['Company limit ₹20,00,000', 'Current exposure ₹12,00,000', 'Verified receivable ₹10,00,000', 'Requested amount ₹7,00,000'],
    verified: ['Available company capacity ₹8,00,000', '70% cap equals ₹7,00,000', 'Request fits both constraints'],
    mcp: 'Internal Policy Engine', mcpTools: ['exposure.calculate', 'eligibility.evaluate'],
    controls: ['Atomic exposure read', 'Versioned policy sf_3.7', 'No model override'],
    result: 'Eligible financing amount fixed at ₹7,00,000.',
  },
  {
    id: 'funding', code: 'FU', name: 'Funding Agent', group: 'Funding preparation',
    task: 'Selecting a compliant funder route and preparing the exact disbursement.',
    collected: ['Three eligible funder offers', 'Verified beneficiary ben_tok_14', 'Bank rail and account limits', 'Aggregate exposure decision'],
    verified: ['Funder SF-04 is policy compliant', 'NEFT rail limit permits amount', 'Beneficiary is unchanged and active'],
    mcp: 'Supply Finance MCP and Bank MCP', mcpTools: ['funder.offers.list', 'funder.offer.reserve', 'bank.beneficiaries.verify'],
    controls: ['Offer expiry', 'Exact amount constraint', 'Cannot call bank.transfers.execute'],
    result: 'Funder SF-04 reserved and route prepared for Guardian review.',
  },
  {
    id: 'guardian', code: 'GU', name: 'Guardian', group: 'Independent governance',
    task: 'Evaluating the exact action against identity, mandate, evidence, exposure and behaviour.',
    collected: ['Action hash sha256:8d21', 'Signed evidence receipts', 'Mandate and policy versions', 'Action graph and risk score'],
    verified: ['12 governance controls passed', 'Evidence is complete and fresh', 'Beneficiary and amount match proposal', 'No anomalous action chain'],
    mcp: 'Guardian Governance Service', mcpTools: ['guardian.evaluate_action', 'guardian.issue_authorization'],
    controls: ['Independent decision boundary', 'ALLOW / CONSTRAIN / VERIFY / BLOCK / ESCALATE', 'Short-lived single-use token'],
    result: 'ALLOW. Authorization auth_71 bound to the exact action hash and scope.',
  },
  {
    id: 'execution', code: 'EG', name: 'Execution Gateway', group: 'Protected execution',
    task: 'Rechecking authorization and invoking the exact Bank MCP execution call.',
    collected: ['Proposed action act_9001', 'Guardian authorization auth_71', 'Idempotency key case_1023-disbursement-1', 'Current mandate and limits'],
    verified: ['Guardian signature valid', 'Action hash equality confirmed', 'Authorization unused and unexpired', 'Exposure reservation acquired'],
    mcp: 'Bank MCP', mcpTools: ['bank.transfers.execute'],
    controls: ['Exact-argument equality', 'Atomic reservation', 'Idempotency and replay protection', 'Fail-closed execution'],
    result: 'Transfer accepted with execution ID exec_801 and tokenized bank reference.',
  },
  {
    id: 'monitoring', code: 'MO', name: 'Monitoring Agent', group: 'Reconciliation and monitoring',
    task: 'Reconciling the external outcome and updating exposure, audit and future posture.',
    collected: ['Execution ID exec_801', 'Bank receipt br_991', 'Authorization consumption event', 'Exposure reservation state'],
    verified: ['Bank status SETTLED', 'Canonical action hash unchanged', 'No duplicate execution', 'Exposure updated to ₹19,00,000'],
    mcp: 'Bank MCP and Audit Service', mcpTools: ['bank.transfers.get_status', 'audit.append_event', 'exposure.commit'],
    controls: ['Unknown outcomes are never blindly retried', 'Append-only audit', 'Behaviour posture update'],
    result: 'Case funded, reconciled and committed to the append-only decision record.',
  },
]

const wireNodes = {
  case: { x: 595, y: 16, w: 210, h: 64, label: 'FINANCING REQUEST', sub: 'INV-1023 / ₹7,00,000', step: -1 },
  identity: { x: 40, y: 105, w: 230, h: 70, label: 'IDENTITY + SCOPE', sub: 'tenant / MSME / user', step: 0 },
  intake: { x: 395, y: 105, w: 230, h: 70, label: 'INTAKE AGENT', sub: 'case creation', step: 1 },
  evidence: { x: 750, y: 105, w: 230, h: 70, label: 'EVIDENCE TRUST', sub: 'normalize / sign receipts', step: 2 },
  context: { x: 1105, y: 105, w: 230, h: 70, label: 'CONTEXT ASSEMBLER', sub: 'minimum scoped context', step: 3 },
  supervisor: { x: 385, y: 220, w: 300, h: 76, label: 'WORKFLOW SUPERVISOR', sub: 'isolated agent dispatch', step: 4 },
  mcp: { x: 915, y: 220, w: 300, h: 76, label: 'MCP TOOL FABRIC', sub: 'capability / scope / telemetry', step: 4 },
  business: { x: 105, y: 340, w: 250, h: 74, label: 'BUSINESS AGENT', sub: 'identity + eligibility', step: 5 },
  invoice: { x: 575, y: 340, w: 250, h: 74, label: 'INVOICE AGENT', sub: 'authenticity + duplicate', step: 6 },
  delivery: { x: 1045, y: 340, w: 250, h: 74, label: 'DELIVERY AGENT', sub: 'fulfilment evidence', step: 7 },
  payment: { x: 105, y: 445, w: 250, h: 74, label: 'PAYMENT AGENT', sub: 'outstanding amount', step: 8 },
  risk: { x: 575, y: 445, w: 250, h: 74, label: 'FRAUD + RISK', sub: 'graph + behaviour', step: 9 },
  credit: { x: 1045, y: 445, w: 250, h: 74, label: 'CREDIT AGENT', sub: 'safe capacity', step: 10 },
  orchestrator: { x: 170, y: 565, w: 290, h: 76, label: 'DECISION ORCHESTRATOR', sub: 'canonical ProposedAction', step: 11 },
  exposure: { x: 555, y: 565, w: 290, h: 76, label: 'EXPOSURE ENGINE', sub: 'limit + 70% cap', step: 12 },
  funding: { x: 940, y: 565, w: 290, h: 76, label: 'FUNDING AGENT', sub: 'route preparation', step: 13 },
  guardian: { x: 555, y: 675, w: 290, h: 80, label: 'GUARDIAN', sub: 'independent authorization', step: 14 },
  execution: { x: 260, y: 790, w: 280, h: 72, label: 'EXECUTION GATEWAY', sub: 'Bank MCP execute', step: 15 },
  monitoring: { x: 860, y: 790, w: 280, h: 72, label: 'MONITORING AGENT', sub: 'reconcile + update posture', step: 16 },
}

const wireDefs = [
  { from: 'case', fs: 'left', to: 'identity', ts: 'top', label: 'authenticated scope', step: 0 },
  { from: 'case', fs: 'bot', to: 'intake', ts: 'top', label: 'request', step: 1 },
  { from: 'intake', fs: 'right', to: 'evidence', ts: 'left', label: 'untrusted artifacts', step: 2 },
  { from: 'identity', fs: 'right', to: 'context', ts: 'left', label: 'trusted scope', step: 3 },
  { from: 'evidence', fs: 'right', to: 'context', ts: 'left', label: 'signed receipts', step: 3 },
  { from: 'context', fs: 'bot', to: 'supervisor', ts: 'top', label: 'ContextEnvelope', step: 4 },
  { from: 'supervisor', fs: 'right', to: 'mcp', ts: 'left', label: 'scoped capabilities', step: 4 },
  { from: 'supervisor', fs: 'left', to: 'business', ts: 'top', label: 'BusinessTask', step: 5 },
  { from: 'mcp', fs: 'bot', to: 'business', ts: 'right', label: 'registry reads', step: 5 },
  { from: 'supervisor', fs: 'left', to: 'invoice', ts: 'top', label: 'InvoiceTask', step: 6 },
  { from: 'mcp', fs: 'bot', to: 'invoice', ts: 'right', label: 'GST / ERP', step: 6 },
  { from: 'supervisor', fs: 'bot', to: 'delivery', ts: 'top', label: 'DeliveryTask', step: 7 },
  { from: 'mcp', fs: 'bot', to: 'delivery', ts: 'right', label: 'logistics', step: 7 },
  { from: 'supervisor', fs: 'bot', to: 'payment', ts: 'top', label: 'PaymentTask', step: 8 },
  { from: 'mcp', fs: 'bot', to: 'payment', ts: 'right', label: 'Bank MCP', step: 8 },
  { from: 'supervisor', fs: 'right', to: 'risk', ts: 'top', label: 'RiskTask', step: 9 },
  { from: 'mcp', fs: 'bot', to: 'risk', ts: 'right', label: 'graph reads', step: 9 },
  { from: 'supervisor', fs: 'right', to: 'credit', ts: 'top', label: 'CreditTask', step: 10 },
  { from: 'mcp', fs: 'bot', to: 'credit', ts: 'right', label: 'limits / balance', step: 10 },
  { from: 'business', fs: 'bot', to: 'orchestrator', ts: 'top', label: 'BusinessFinding', step: 11 },
  { from: 'invoice', fs: 'bot', to: 'orchestrator', ts: 'top', label: 'InvoiceFinding', step: 11 },
  { from: 'delivery', fs: 'bot', to: 'orchestrator', ts: 'top', label: 'DeliveryFinding', step: 11 },
  { from: 'payment', fs: 'bot', to: 'orchestrator', ts: 'top', label: 'PaymentFinding', step: 11 },
  { from: 'risk', fs: 'bot', to: 'orchestrator', ts: 'right', label: 'RiskFinding', step: 11 },
  { from: 'credit', fs: 'bot', to: 'orchestrator', ts: 'right', label: 'CreditFinding', step: 11 },
  { from: 'orchestrator', fs: 'right', to: 'exposure', ts: 'left', label: 'action hash', step: 12 },
  { from: 'exposure', fs: 'right', to: 'funding', ts: 'left', label: '₹7,00,000 eligible', step: 13 },
  { from: 'funding', fs: 'bot', to: 'guardian', ts: 'right', label: 'ProposedAction', step: 14 },
  { from: 'guardian', fs: 'left', to: 'execution', ts: 'top', label: 'auth_71 / ALLOW', step: 15 },
  { from: 'execution', fs: 'right', to: 'mcp', ts: 'bot', label: 'bank.transfers.execute', step: 15 },
  { from: 'execution', fs: 'right', to: 'monitoring', ts: 'left', label: 'execution receipt', step: 16 },
  { from: 'monitoring', fs: 'top', to: 'guardian', ts: 'right', label: 'posture update', step: 16 },
]

function clamp(value) { return Math.max(0, Math.min(1, value)) }
function ease(value) { return value < 0.5 ? 2 * value * value : 1 - ((-2 * value + 2) ** 2) / 2 }

function nodeEdge(id, side) {
  const node = wireNodes[id]
  const cx = node.x + node.w / 2
  const cy = node.y + node.h / 2
  if (side === 'top') return { x: cx, y: node.y }
  if (side === 'bot') return { x: cx, y: node.y + node.h }
  if (side === 'left') return { x: node.x, y: cy }
  return { x: node.x + node.w, y: cy }
}

function curveGeometry(definition) {
  const from = nodeEdge(definition.from, definition.fs)
  const to = nodeEdge(definition.to, definition.ts)
  const dx = to.x - from.x
  const dy = to.y - from.y
  const length = Math.sqrt((dx * dx) + (dy * dy)) || 1
  const bend = Math.min(length * 0.28, 76)
  const mx = (from.x + to.x) / 2
  const my = (from.y + to.y) / 2
  const control = { x: mx - (dy / length) * bend, y: my + (dx / length) * bend }
  const estimatedLength = (Math.hypot(control.x - from.x, control.y - from.y) + Math.hypot(to.x - control.x, to.y - control.y)) * 1.06
  return { ...definition, from, to, control, length: estimatedLength, d: `M${from.x},${from.y} Q${control.x},${control.y} ${to.x},${to.y}` }
}

const wireGeometry = wireDefs.map(curveGeometry)

function curvePoint(wire, t) {
  const inverse = 1 - t
  return {
    x: inverse * inverse * wire.from.x + 2 * inverse * t * wire.control.x + t * t * wire.to.x,
    y: inverse * inverse * wire.from.y + 2 * inverse * t * wire.control.y + t * t * wire.to.y,
  }
}

function WireDiagram({ progress, onSelect }) {
  const activeIndex = Math.min(runSteps.length - 1, Math.floor(clamp(progress) * runSteps.length))

  return (
    <svg className="xyena-wireframe" viewBox="0 0 1400 875" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Live XYENA enterprise architecture wireframe">
      <defs>
        <filter id="activeGlow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="5" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      {wireGeometry.map((wire, index) => {
        const start = Math.max(0, (wire.step - 0.8) / runSteps.length)
        const end = Math.min(1, (wire.step + 0.3) / runSteps.length)
        const local = ease(clamp((progress - start) / Math.max(end - start, 0.01)))
        const packet = local > 0.06 && local < 0.94 ? curvePoint(wire, local) : null
        const complete = wire.step < activeIndex
        const active = wire.step === activeIndex
        const color = complete ? '#2f6b4f' : active ? '#ad462b' : '#98a4b1'
        return (
          <g key={`${wire.from}-${wire.to}-${index}`}>
            <path className="wire-path" d={wire.d} stroke={color} strokeDasharray={wire.length} strokeDashoffset={wire.length * (1 - local)} />
            {packet && <circle className="wire-packet" cx={packet.x} cy={packet.y} r="4" fill={color} />}
            {local > 0.84 && (
              <g className="wire-label" opacity={Math.min(0.88, (local - 0.84) * 6)}>
                <rect x={(wire.from.x + wire.to.x) / 2 - 68} y={(wire.from.y + wire.to.y) / 2 - 12} width="136" height="24" rx="3" />
                <text x={(wire.from.x + wire.to.x) / 2} y={(wire.from.y + wire.to.y) / 2 + 4}>{wire.label}</text>
              </g>
            )}
          </g>
        )
      })}

      {Object.entries(wireNodes).map(([id, node]) => {
        const revealAt = node.step < 0 ? 0 : Math.max(0, (node.step - 0.45) / runSteps.length)
        const alpha = node.step <= 0 ? 1 : ease(clamp((progress - revealAt) / 0.05))
        const active = node.step === activeIndex && id !== 'mcp'
        const complete = node.step >= 0 && node.step < activeIndex
        const stroke = active ? '#ad462b' : complete ? '#2f6b4f' : id === 'case' ? '#536273' : '#9aa5b1'
        const step = runSteps.find((item) => item.id === id)
        const interactive = Boolean(step)
        return (
          <g
            key={id}
            className={`wire-node ${interactive ? 'is-interactive' : ''} ${active ? 'is-active' : ''}`}
            opacity={alpha}
            onClick={() => step && onSelect(step)}
            onKeyDown={(event) => step && (event.key === 'Enter' || event.key === ' ') && onSelect(step)}
            tabIndex={interactive && alpha > 0.6 ? 0 : undefined}
            role={interactive ? 'button' : undefined}
            aria-label={interactive ? `Inspect ${step.name}` : undefined}
          >
            <rect className="wire-node__halo" x={node.x - 8} y={node.y - 8} width={node.w + 16} height={node.h + 16} rx="5" fill={stroke} opacity={active ? 0.1 : 0.025} />
            <rect className="wire-node__card" x={node.x} y={node.y} width={node.w} height={node.h} rx="3" stroke={stroke} strokeWidth={active ? 2 : 1.1} filter={active ? 'url(#activeGlow)' : undefined} />
            <line x1={node.x + 4} y1={node.y} x2={node.x + node.w * 0.52} y2={node.y} stroke={stroke} strokeWidth={active ? 3 : 1.8} />
            <text className="wire-node__title" x={node.x + node.w / 2} y={node.y + node.h / 2 - 5}>{node.label}</text>
            <text className="wire-node__sub" x={node.x + node.w / 2} y={node.y + node.h / 2 + 12}>{node.sub}</text>
            {active && <circle className="active-node-dot" cx={node.x + node.w - 12} cy={node.y + 11} r="4" fill="#ad462b" />}
          </g>
        )
      })}
    </svg>
  )
}

function Brand() {
  return (
    <a className="brand" href="/" aria-label="XYENA home">
      <svg className="brand__mark" viewBox="0 0 48 48" aria-hidden="true">
        <rect x="2" y="2" width="44" height="44" rx="11" fill="currentColor" />
        <path d="M14.5 14.5 33.5 33.5M33.5 14.5 14.5 33.5" fill="none" stroke="white" strokeWidth="5" strokeLinecap="round" />
      </svg>
      <span className="brand__word">XYENA</span><span className="brand__descriptor">Enterprise AI</span>
    </a>
  )
}

function CheckIcon() {
  return <svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="8" /><path d="m6.5 10 2.2 2.2 4.8-5" /></svg>
}

function DetailDrawer({ step, onClose }) {
  useEffect(() => {
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const closeOnEscape = (event) => event.key === 'Escape' && onClose()
    window.addEventListener('keydown', closeOnEscape)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', closeOnEscape)
    }
  }, [onClose])

  return (
    <div className="activity-overlay" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <aside className="activity-drawer" role="dialog" aria-modal="true" aria-labelledby="activity-title" data-lenis-prevent>
        <div className="activity-drawer__header">
          <div className="drawer-agent-code">{step.code}</div>
          <div><span>Verified activity record</span><h2 id="activity-title">{step.name}</h2></div>
          <button type="button" onClick={onClose} aria-label="Close activity details"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg></button>
        </div>
        <div className="activity-drawer__body">
          <section className="activity-section activity-section--collected">
            <div className="activity-section__title"><span>01</span><h3>Collected for this run</h3></div>
            <ul>{step.collected.map((item) => <li key={item}><i />{item}</li>)}</ul>
          </section>
          <section className="activity-section activity-section--verified">
            <div className="activity-section__title"><span>02</span><h3>Verified by the component</h3></div>
            <ul>{step.verified.map((item) => <li key={item}><CheckIcon />{item}</li>)}</ul>
          </section>
          <section className="activity-section activity-section--mcp">
            <div className="activity-section__title"><span>03</span><h3>MCP activity</h3></div>
            <div className="mcp-server-record"><small>MCP server</small><strong>{step.mcp}</strong><span><i /> Authenticated</span></div>
            <div className="mcp-call-list">{step.mcpTools.map((tool, index) => <div className="mcp-call" key={tool}><span>tc_{String(index + 1).padStart(2, '0')}</span><code>{tool}</code><strong>SUCCESS</strong></div>)}</div>
          </section>
          <section className="activity-section activity-section--controls">
            <div className="activity-section__title"><span>04</span><h3>Tools and controls applied</h3></div>
            <div className="control-tags">{step.controls.map((control) => <span key={control}>{control}</span>)}</div>
          </section>
          <section className="activity-result"><span>Signed output</span><p>{step.result}</p><div><i /> Recorded under correlation corr_5001</div></section>
        </div>
      </aside>
    </div>
  )
}

function LiveArchitecture() {
  const storyRef = useRef(null)
  const [progress, setProgress] = useState(0)
  const [selectedStep, setSelectedStep] = useState(null)
  const activeIndex = Math.min(runSteps.length - 1, Math.floor(clamp(progress) * runSteps.length))
  const active = runSteps[activeIndex]

  useEffect(() => {
    let frame = 0
    const updateFromScroll = () => {
      if (!storyRef.current) return
      const rect = storyRef.current.getBoundingClientRect()
      const travel = storyRef.current.offsetHeight - window.innerHeight
      const raw = travel > 0 ? -rect.top / travel : 0
      setProgress(clamp(raw))
    }
    const onScroll = () => { window.cancelAnimationFrame(frame); frame = window.requestAnimationFrame(updateFromScroll) }
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
    updateFromScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => { window.cancelAnimationFrame(frame); window.removeEventListener('scroll', onScroll); window.removeEventListener('resize', onScroll) }
  }, [])

  return (
    <div className="live-page live-page--wire">
      <header className="live-header"><div className="live-header__inner"><Brand /><div className="live-header__title"><span>Live architecture</span><small>Scroll-driven wire protocol</small></div><div className="live-header__meta"><span className="environment-pill"><i /> Demo environment</span><span className="header-case">CASE / INV-1023</span><a href="/">Back to overview</a></div></div></header>
      <div className="wire-global-progress" aria-hidden="true"><span style={{ width: `${progress * 100}%` }} /></div>
      <main>
        <section className="wire-scroll-stage" ref={storyRef} aria-label="Scroll through the live XYENA architecture wireframe">
          <div className="wire-sticky">
            <div className="wire-stage-meta">
              <div><span><i /> LIVE CASE RUN</span><strong>Aruna Components Pvt Ltd</strong></div>
              <div className="stage-counter"><span>{String(activeIndex + 1).padStart(2, '0')}</span><i>/</i><small>{String(runSteps.length).padStart(2, '0')}</small></div>
              <div><span>ACTIVE COMPONENT</span><strong>{active.name}</strong></div>
            </div>
            <WireDiagram progress={progress} onSelect={setSelectedStep} />
            <div className="wire-stage-footer">
              <div className="scroll-cue"><span>Scroll to draw the architecture</span><svg viewBox="0 0 18 24" aria-hidden="true"><rect x="1" y="1" width="16" height="22" rx="8" /><circle cx="9" cy="7" r="1.5" /></svg></div>
              <button type="button" onClick={() => setSelectedStep(active)}><span>WORKING NOW</span><strong>{active.mcpTools[0]}</strong><i>Inspect node ↗</i></button>
              <div className="stage-boundary"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 20 6v6c0 5-3 8-8 10-5-2-8-5-8-10V6Z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></svg><span>Guardian remains independent<br /><strong>Every call stays observable</strong></span></div>
            </div>
          </div>
        </section>
      </main>
      {selectedStep && <DetailDrawer step={selectedStep} onClose={() => setSelectedStep(null)} />}
    </div>
  )
}

export default LiveArchitecture
