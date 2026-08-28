import { useEffect, useRef, useState } from 'react'
import Lenis from 'lenis'

const navItems = [
  ['Platform', '#platform'],
  ['How it works', '#process'],
  ['Guardian', '#guardian'],
  ['Live architecture', '/architecture-live'],
  ['Verify live', '/live-demo'],
]

const agents = [
  ['Business', 'Identity and eligibility'],
  ['Invoice', 'Authenticity and duplication'],
  ['Delivery', 'Fulfilment evidence'],
  ['Payment', 'Outstanding reconciliation'],
  ['Fraud / Risk', 'Anomalies and action chains'],
  ['Credit', 'Financing capacity'],
]

const capabilities = [
  {
    index: '01',
    title: 'Verify the receivable',
    copy: 'Six specialist agents inspect the business, invoice, delivery, payments, risk signals and credit capacity against the same evidence snapshot.',
    icon: 'verify',
  },
  {
    index: '02',
    title: 'Control the exposure',
    copy: 'One aggregate view accounts for existing commitments across funders, available company capacity and the 70% verified-receivable cap.',
    icon: 'exposure',
  },
  {
    index: '03',
    title: 'Govern the action',
    copy: 'Guardian checks identity, authority, intent, provenance, evidence, behaviour and policy before a financial tool can execute.',
    icon: 'shield',
  },
]

function useLenis() {
  useEffect(() => {
    const lenis = new Lenis({
      duration: 1.05,
      smoothWheel: true,
      wheelMultiplier: 0.9,
      touchMultiplier: 1.1,
    })

    let frame
    const raf = (time) => {
      lenis.raf(time)
      frame = requestAnimationFrame(raf)
    }
    frame = requestAnimationFrame(raf)

    const onAnchorClick = (event) => {
      const anchor = event.target.closest('a[href^="#"]')
      if (!anchor) return
      const target = document.querySelector(anchor.getAttribute('href'))
      if (!target) return
      event.preventDefault()
      lenis.scrollTo(target, { offset: -88 })
    }
    document.addEventListener('click', onAnchorClick)

    return () => {
      cancelAnimationFrame(frame)
      document.removeEventListener('click', onAnchorClick)
      lenis.destroy()
    }
  }, [])
}

function useReveals() {
  useEffect(() => {
    const items = document.querySelectorAll('.js-reveal')
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible')
            observer.unobserve(entry.target)
          }
        })
      },
      { threshold: 0.16, rootMargin: '0px 0px -6% 0px' },
    )
    items.forEach((item) => observer.observe(item))
    return () => observer.disconnect()
  }, [])
}

function Logo({ inverse = false }) {
  return (
    <a className={`brand ${inverse ? 'brand--inverse' : ''}`} href="#top" aria-label="XYENA home">
      <svg className="brand__mark" viewBox="0 0 48 48" aria-hidden="true">
        <rect x="2" y="2" width="44" height="44" rx="11" fill="currentColor" />
        <path d="M14.5 14.5 33.5 33.5M33.5 14.5 14.5 33.5" fill="none" stroke="white" strokeWidth="5" strokeLinecap="round" />
      </svg>
      <span className="brand__word">XYENA</span>
      <span className="brand__descriptor">Enterprise AI</span>
    </a>
  )
}

function Arrow({ direction = 'right' }) {
  return (
    <svg className={`arrow arrow--${direction}`} viewBox="0 0 20 20" aria-hidden="true">
      <path d="M3 10h13M11 5l5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function Icon({ type }) {
  if (type === 'exposure') {
    return (
      <svg viewBox="0 0 56 56" aria-hidden="true">
        <rect x="7" y="10" width="42" height="36" rx="5" fill="none" stroke="currentColor" strokeWidth="2" />
        <path d="M15 36V26M24 36V20M33 36V29M42 36V16" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      </svg>
    )
  }
  if (type === 'shield') {
    return (
      <svg viewBox="0 0 56 56" aria-hidden="true">
        <path d="M28 6 45 13v13c0 12-7 20-17 25C18 46 11 38 11 26V13Z" fill="none" stroke="currentColor" strokeWidth="2.4" />
        <path d="m19 28 6 6 12-14" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 56 56" aria-hidden="true">
      <circle cx="28" cy="28" r="21" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="m18 28 7 7 14-17" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M28 7v5M49 28h-5M28 49v-5M7 28h5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

function DecisionRail() {
  return (
    <svg className="decision-rail" viewBox="0 0 720 570" role="img" aria-labelledby="rail-title rail-desc">
      <title id="rail-title">XYENA governed financing decision flow</title>
      <desc id="rail-desc">A financing request moves through six verification agents, exposure controls, Guardian and an allowed funding action.</desc>
      <defs>
        <marker id="rail-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0 0 10 5 0 10Z" fill="#0d213f" />
        </marker>
        <clipPath id="shield-clip">
          <path d="M360 320 430 346v64c0 58-28 97-70 122-42-25-70-64-70-122v-64Z" />
        </clipPath>
      </defs>

      <path className="rail-grid" d="M40 70H680M40 170H680M40 270H680M40 370H680M40 470H680" />
      <text x="40" y="35" className="rail-kicker">LIVE DECISION PATH</text>
      <text x="680" y="35" textAnchor="end" className="rail-meta">CASE / INV-1023</text>

      <g className="rail-stage rail-stage--request">
        <rect x="40" y="72" width="152" height="74" rx="7" />
        <text x="58" y="100" className="rail-label">FINANCING REQUEST</text>
        <text x="58" y="127" className="rail-value">₹7,00,000</text>
      </g>

      <path className="rail-path rail-path--one" d="M192 109H251" markerEnd="url(#rail-arrow)" />

      <g className="rail-stage rail-stage--agents">
        <rect x="252" y="58" width="428" height="102" rx="7" />
        <text x="272" y="84" className="rail-label">SPECIALIST AGENT REVIEW</text>
        {['BUS', 'INV', 'DEL', 'PAY', 'RSK', 'CRD'].map((label, index) => (
          <g key={label} transform={`translate(${272 + index * 64} 99)`}>
            <rect width="48" height="38" rx="5" className="agent-node" />
            <text x="24" y="24" textAnchor="middle" className="agent-node__text">{label}</text>
          </g>
        ))}
      </g>

      <path className="rail-path rail-path--two" d="M466 160V214" markerEnd="url(#rail-arrow)" />

      <g className="rail-stage rail-stage--control">
        <rect x="205" y="216" width="510" height="80" rx="7" />
        <text x="226" y="243" className="rail-label">EXPOSURE + ELIGIBILITY CONTROL</text>
        <text x="226" y="273" className="rail-copy">₹20L limit  −  ₹12L exposure  =  ₹8L available</text>
        <rect x="568" y="236" width="126" height="38" rx="19" className="cap-pill" />
        <text x="631" y="260" textAnchor="middle" className="cap-pill__text">70% CAP ✓</text>
      </g>

      <path className="rail-path rail-path--three" d="M460 296V332" markerEnd="url(#rail-arrow)" />

      <g className="guardian-visual">
        <path className="guardian-visual__body" d="M360 320 430 346v64c0 58-28 97-70 122-42-25-70-64-70-122v-64Z" />
        <rect className="guardian-visual__fill" x="285" y="475" width="150" height="60" clipPath="url(#shield-clip)" />
        <path className="guardian-visual__check" d="m332 406 20 20 40-48" />
        <text x="360" y="365" textAnchor="middle" className="guardian-visual__title">GUARDIAN</text>
        <text x="360" y="458" textAnchor="middle" className="guardian-visual__score">RISK 18 / 100</text>
      </g>

      <g className="rail-stage rail-stage--result">
        <rect x="486" y="365" width="194" height="118" rx="7" />
        <text x="510" y="394" className="rail-label">DECISION</text>
        <text x="510" y="430" className="result-allow">ALLOW</text>
        <text x="510" y="455" className="rail-copy">Authorized amount</text>
        <text x="510" y="478" className="rail-copy rail-copy--strong">₹7,00,000</text>
      </g>

      <path className="rail-path rail-path--four" d="M430 418H484" markerEnd="url(#rail-arrow)" />

      <g className="rail-footer">
        <circle cx="51" cy="530" r="5" />
        <text x="67" y="535">Every finding, tool call and decision remains auditable.</text>
      </g>
    </svg>
  )
}

function TextReveal({ children, as: Tag = 'span', delay = 0, className = '' }) {
  return (
    <Tag className={`text-reveal ${className}`} style={{ '--reveal-delay': `${delay}ms` }}>
      <span className="text-reveal__inner">{children}</span>
    </Tag>
  )
}

function App() {
  const [menuOpen, setMenuOpen] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const headerRef = useRef(null)

  useLenis()
  useReveals()

  useEffect(() => {
    const timer = window.setTimeout(() => setLoaded(true), 90)
    const onScroll = () => headerRef.current?.classList.toggle('is-scrolled', window.scrollY > 24)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      clearTimeout(timer)
      window.removeEventListener('scroll', onScroll)
    }
  }, [])

  return (
    <div className={`site ${loaded ? 'is-loaded' : ''}`} id="top">
      <header className="site-header" ref={headerRef}>
        <div className="shell site-header__inner">
          <Logo />
          <nav className={`site-nav ${menuOpen ? 'is-open' : ''}`} aria-label="Primary navigation">
            {navItems.map(([label, href]) => (
              <a href={href} key={href} onClick={() => setMenuOpen(false)}>{label}</a>
            ))}
          </nav>
          <a className="button button--small button--navy header-cta" href="#contact">Request a pilot <Arrow /></a>
          <button className="menu-toggle" type="button" aria-expanded={menuOpen} aria-label="Toggle navigation" onClick={() => setMenuOpen((value) => !value)}>
            <span /><span />
          </button>
        </div>
      </header>

      <main>
        <section className="hero">
          <div className="hero__rule" aria-hidden="true" />
          <div className="shell hero__grid">
            <div className="hero__copy">
              <p className="eyebrow hero-enter hero-enter--1"><span className="eyebrow__dot" /> Secure autonomous supply finance</p>
              <h1 className="hero__title">
                <TextReveal as="span" delay={80}>Working capital,</TextReveal>
                <TextReveal as="span" delay={170}>governed at</TextReveal>
                <TextReveal as="span" delay={260} className="hero__title-accent">machine speed.</TextReveal>
              </h1>
              <p className="hero__lede hero-enter hero-enter--2">
                XYENA verifies MSME receivables, controls aggregate exposure and independently governs every AI-generated financial action before execution.
              </p>
              <div className="hero__actions hero-enter hero-enter--3">
                <a className="button button--maroon" href="#process">Explore the decision flow <Arrow /></a>
                <a className="text-link" href="/xyena-enterprise-architecture.svg" target="_blank" rel="noreferrer">View architecture <Arrow direction="up" /></a>
              </div>
              <div className="hero__audience hero-enter hero-enter--4">
                <span>Built for</span>
                <strong>MSMEs</strong>
                <i />
                <strong>Lenders</strong>
                <i />
                <strong>Enterprise risk teams</strong>
              </div>
            </div>
            <div className="hero__visual hero-enter hero-enter--visual">
              <div className="hero__visual-head">
                <span>Governed financing decision</span>
                <span className="status"><i /> System ready</span>
              </div>
              <DecisionRail />
            </div>
          </div>
        </section>

        <section className="fact-strip" aria-label="Platform facts">
          <div className="shell fact-strip__grid">
            <div><strong>06</strong><span>specialist verification agents</span></div>
            <div><strong>01</strong><span>aggregate exposure view</span></div>
            <div><strong>05</strong><span>graduated Guardian decisions</span></div>
            <div><strong>24/7</strong><span>post-execution monitoring</span></div>
          </div>
        </section>

        <section className="section section--intro" id="platform">
          <div className="shell">
            <div className="section-heading js-reveal">
              <p className="eyebrow"><span className="eyebrow__dot" /> The confidence layer</p>
              <h2>
                <TextReveal as="span">The funding gap is not only credit.</TextReveal>
                <TextReveal as="span" delay={100}>It is confidence.</TextReveal>
              </h2>
              <p>XYENA brings verification, financing control and autonomous-agent governance into one accountable flow.</p>
            </div>

            <div className="capability-grid">
              {capabilities.map((capability, index) => (
                <article className="capability js-reveal" style={{ '--item-delay': `${index * 90}ms` }} key={capability.title}>
                  <div className="capability__top">
                    <span className="capability__index">{capability.index}</span>
                    <span className="capability__icon"><Icon type={capability.icon} /></span>
                  </div>
                  <h3>{capability.title}</h3>
                  <p>{capability.copy}</p>
                  <div className="capability__line" />
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="section section--process" id="process">
          <div className="shell">
            <div className="process-head js-reveal">
              <div>
                <p className="eyebrow eyebrow--light"><span className="eyebrow__dot" /> One controlled workflow</p>
                <h2>
                  <TextReveal as="span">Agents investigate.</TextReveal>
                  <TextReveal as="span" delay={100}>Guardian decides what executes.</TextReveal>
                </h2>
              </div>
              <p>Parallel intelligence improves speed. Separation of duties preserves control.</p>
            </div>

            <div className="agent-system js-reveal">
              <div className="agent-system__label">Evidence snapshot</div>
              <div className="agent-system__agents">
                {agents.map(([title, copy]) => (
                  <div className="agent-card" key={title}>
                    <span>{title.slice(0, 2).toUpperCase()}</span>
                    <div><strong>{title}</strong><small>{copy}</small></div>
                  </div>
                ))}
              </div>
              <div className="agent-system__spine" aria-hidden="true"><span /><span /><span /></div>
              <div className="agent-system__outcome">
                <div><small>Orchestrator</small><strong>ProposedAction</strong></div>
                <Arrow />
                <div><small>Exposure engine</small><strong>Eligible amount</strong></div>
                <Arrow />
                <div className="agent-system__guardian"><small>Independent control</small><strong>Guardian</strong></div>
              </div>
            </div>
          </div>
        </section>

        <section className="section guardian-section" id="guardian">
          <div className="shell guardian-section__grid">
            <div className="guardian-section__copy js-reveal">
              <p className="eyebrow"><span className="eyebrow__dot" /> Automated maker-checker</p>
              <h2>
                <TextReveal as="span">Permission is not the same</TextReveal>
                <TextReveal as="span" delay={100}>as legitimate intent.</TextReveal>
              </h2>
              <p>Guardian verifies the action - not just the credentials - at the final safe moment before money or financial state can move.</p>
              <a className="text-link text-link--maroon" href="/live-demo">Verify the platform live <Arrow /></a>
            </div>

            <div className="guardian-matrix js-reveal">
              {['Agent identity', 'Authority and mandate', 'Intent provenance', 'Evidence integrity', 'Counterparty trust', 'Behaviour and action chain', 'Exposure and policy', 'Tool and data trust'].map((item, index) => (
                <div key={item} style={{ '--matrix-delay': `${index * 45}ms` }}>
                  <svg viewBox="0 0 22 22" aria-hidden="true"><circle cx="11" cy="11" r="9" /><path d="m7 11 3 3 5-7" /></svg>
                  <span>{item}</span>
                </div>
              ))}
              <div className="guardian-verdicts">
                <span>ALLOW</span><span>CONSTRAIN</span><span>VERIFY</span><span>BLOCK</span><span>ESCALATE</span>
              </div>
            </div>
          </div>
        </section>

        <section className="section architecture-section" id="architecture">
          <div className="shell">
            <div className="section-heading section-heading--split js-reveal">
              <div>
                <p className="eyebrow"><span className="eyebrow__dot" /> Enterprise architecture</p>
                <h2>
                  <TextReveal as="span">Every agent gets context.</TextReveal>
                  <TextReveal as="span" delay={100}>Every tool gets a boundary.</TextReveal>
                </h2>
              </div>
              <p>User, MSME, case and session memory remain isolated. MCP standardizes tool access. Guardian remains the authority boundary.</p>
            </div>

            <div className="architecture-grid js-reveal">
              <div className="architecture-card architecture-card--context">
                <span className="architecture-card__label">Context + memory</span>
                <h3>Minimum sufficient context</h3>
                <p>Each agent receives only the scoped, consented and relevant context needed for its task.</p>
                <svg viewBox="0 0 460 210" aria-hidden="true">
                  <rect x="12" y="18" width="122" height="46" rx="6" /><text x="73" y="46" textAnchor="middle">USER</text>
                  <rect x="12" y="82" width="122" height="46" rx="6" /><text x="73" y="110" textAnchor="middle">MSME</text>
                  <rect x="12" y="146" width="122" height="46" rx="6" /><text x="73" y="174" textAnchor="middle">CASE</text>
                  <path d="M134 41h74M134 105h74M134 169h74" />
                  <rect x="208" y="54" width="238" height="102" rx="8" className="svg-solid" />
                  <text x="327" y="92" textAnchor="middle" className="svg-solid-text">CONTEXT ENVELOPE</text>
                  <text x="327" y="121" textAnchor="middle" className="svg-solid-sub">scope · consent · provenance</text>
                </svg>
              </div>

              <div className="architecture-card architecture-card--mcp">
                <span className="architecture-card__label">MCP tool fabric</span>
                <h3>Tools are capable, not unrestricted</h3>
                <p>Allowlisted tools receive trusted scope, validated arguments and complete provenance.</p>
                <svg viewBox="0 0 460 210" aria-hidden="true">
                  <rect x="12" y="76" width="116" height="58" rx="7" /><text x="70" y="100" textAnchor="middle">AGENT</text><text x="70" y="119" textAnchor="middle" className="svg-small">tool call</text>
                  <path d="M128 105h66" />
                  <rect x="194" y="56" width="128" height="98" rx="8" className="svg-solid" /><text x="258" y="96" textAnchor="middle" className="svg-solid-text">MCP</text><text x="258" y="122" textAnchor="middle" className="svg-solid-sub">GATEWAY</text>
                  <path d="M322 105h42" />
                  <rect x="364" y="26" width="84" height="42" rx="6" /><text x="406" y="52" textAnchor="middle">GST</text>
                  <rect x="364" y="84" width="84" height="42" rx="6" /><text x="406" y="110" textAnchor="middle">ERP</text>
                  <rect x="364" y="142" width="84" height="42" rx="6" /><text x="406" y="168" textAnchor="middle">LEDGER</text>
                </svg>
              </div>

              <div className="architecture-card architecture-card--execution">
                <span className="architecture-card__label">Protected execution</span>
                <h3>No Guardian decision, no execution</h3>
                <p>Financial tools require a short-lived authorization bound to the exact amount, beneficiary and action.</p>
                <svg viewBox="0 0 460 210" aria-hidden="true">
                  <path className="svg-shield" d="M92 34 154 57v51c0 48-25 79-62 99-37-20-62-51-62-99V57Z" />
                  <path className="svg-check" d="m65 105 19 19 38-46" />
                  <path d="M158 105h62" />
                  <rect x="220" y="64" width="214" height="82" rx="8" className="svg-solid" />
                  <text x="327" y="98" textAnchor="middle" className="svg-solid-text">AUTHORIZED</text>
                  <text x="327" y="124" textAnchor="middle" className="svg-solid-sub">hash-bound · single-use</text>
                </svg>
              </div>
            </div>
          </div>
        </section>

        <section className="contact-section" id="contact">
          <div className="shell contact-section__inner js-reveal">
            <div>
              <p className="eyebrow eyebrow--light"><span className="eyebrow__dot" /> Build trust into the transaction</p>
              <h2>
                <TextReveal as="span">Move legitimate financing faster.</TextReveal>
                <TextReveal as="span" delay={100}>Stop unsafe actions earlier.</TextReveal>
              </h2>
            </div>
            <a className="button button--white" href="mailto:pilot@xyena.ai">Start a pilot conversation <Arrow /></a>
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="shell site-footer__top">
          <Logo inverse />
          <p>Secure autonomous supply-finance orchestration for MSMEs, lenders and enterprise risk teams.</p>
          <div className="site-footer__links">
            <a href="#platform">Platform</a><a href="#guardian">Guardian</a><a href="/architecture-live">Live architecture</a><a href="/live-demo">Verify live</a>
          </div>
        </div>
        <div className="shell site-footer__bottom"><span>© 2026 XYENA Enterprise AI</span><span>Verified receivables. Governed action.</span></div>
      </footer>
    </div>
  )
}

export default App
