import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ask, fetchProducts } from '../api.js'
import Counters from '../Counters.jsx'

const BADGE = {
  TIER1_HIT: { cls: 'b-t1', label: 'TIER 1 HIT', hint: 'exact hash match — no embedding, no search' },
  TIER2_HIT: { cls: 'b-t2', label: 'TIER 2 HIT', hint: 'semantic reuse, permitted by the provenance rule' },
  MISS: { cls: 'b-miss', label: 'MISS', hint: 'the model ran' },
  BYPASS: { cls: 'b-bypass', label: 'BYPASS', hint: 'dynamic content, never cached' },
}

const fmt = (v) => (v === null || v === undefined ? '—' : v.toFixed(4))

export default function ProductChat() {
  const { docId } = useParams()
  const [product, setProduct] = useState(null)
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState([])
  const [busy, setBusy] = useState(false)
  const endRef = useRef(null)

  useEffect(() => {
    fetchProducts()
      .then((ps) => setProduct(ps.find((p) => p.doc_id === docId) ?? null))
      .catch(() => setProduct(null))
  }, [docId])

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [turns])

  async function submit(e) {
    e.preventDefault()
    const q = question.trim()
    if (!q || busy) return
    setBusy(true)
    setQuestion('')
    const pending = { q, pending: true, at: Date.now() }
    setTurns((t) => [...t, pending])
    try {
      const r = await ask(q, docId)
      setTurns((t) => t.map((x) => (x === pending ? { q, ...r } : x)))
    } catch (err) {
      setTurns((t) => t.map((x) => (x === pending ? { q, ok: false, status: 0, error: String(err) } : x)))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="layout">
      <main className="main chat">
        {/* The selected product stays on screen for the whole session. It is the ASKED product,
            and the sources under each answer are the ANSWERED product — the demo's sharpest
            moment is when those two disagree. */}
        <header className="chat-head">
          <Link to="/" className="back">← catalogue</Link>
          <div>
            <span className="asking">Asking about</span>
            <h1>{product?.title ?? docId}</h1>
            <code className="pid">product_id = {docId}</code>
          </div>
        </header>

        <div className="turns">
          {turns.length === 0 && (
            <p className="muted hint">
              Ask the same question in two tabs to watch coalescing. Ask it again to watch Tier 1.
              Reword it to watch Tier 2. Ask it about a <em>different</em> product to watch the
              provenance rule refuse a reuse that similarity alone would have allowed.
            </p>
          )}
          {turns.map((t, i) => <Turn key={i} turn={t} askedProduct={docId} />)}
          <div ref={endRef} />
        </div>

        <form className="composer" onSubmit={submit}>
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. Am I entitled to a full refund 30 days after delivery?"
            autoFocus
          />
          <button disabled={busy || !question.trim()}>{busy ? 'asking…' : 'Ask'}</button>
        </form>
      </main>
      <Counters />
    </div>
  )
}

function Turn({ turn, askedProduct }) {
  if (turn.pending) {
    return (
      <div className="turn">
        <div className="q">{turn.q}</div>
        <div className="a pending">generating… <span className="dots" /></div>
      </div>
    )
  }
  if (turn.error) {
    return (
      <div className="turn">
        <div className="q">{turn.q}</div>
        <div className="a err">request failed — {turn.error}</div>
      </div>
    )
  }

  // A 503 is graceful degradation, not a failure (interfaces.md A). Rendered as its own state so
  // it reads as the gateway working, which under many concurrent tabs is exactly what it is.
  if (turn.status === 503) {
    return (
      <div className="turn">
        <div className="q">{turn.q}</div>
        <div className="a shed">
          <span className="badge b-shed">503 SHED</span>
          <p>
            The generation pool was saturated, so the gateway refused this request instead of
            admitting work that would push the machine into swapping.{' '}
            <b>This is the designed behaviour under overload</b>, not an error.
          </p>
          <code>{turn.body?.reason ?? 'generation_pool_saturated'}</code>
        </div>
      </div>
    )
  }

  const b = turn.body ?? {}
  const badge = BADGE[b.cache] ?? { cls: 'b-miss', label: b.cache ?? '?', hint: '' }
  const sources = b.sources ?? []

  // The trap, made visible. `sources` are the documents that actually grounded this answer; if a
  // product document appears that is NOT the one this page is about, the answer was grounded
  // somewhere the user did not ask about.
  const foreign = sources.filter((s) => s.startsWith('product-') && !s.startsWith(askedProduct + '#'))

  return (
    <div className="turn">
      <div className="q">{turn.q}</div>
      <div className="a">
        <div className="meta">
          <span className={`badge ${badge.cls}`} title={badge.hint}>{badge.label}</span>
          <span className="lat"><b>{b.latency_ms ?? '—'}</b> ms <span className="lat-sub">gateway</span></span>
          <span className="lat dim"><b>{turn.wallMs}</b> ms <span className="lat-sub">browser</span></span>
        </div>

        <p className="answer">{b.answer}</p>

        {/* similarity and source_overlap side by side is the research claim in two numbers:
            a high similarity next to a low overlap is the lookalike the rule exists to catch. */}
        <div className="signals">
          <div><span>similarity</span><b>{fmt(b.similarity)}</b></div>
          <div><span>source_overlap</span><b>{fmt(b.source_overlap)}</b></div>
          <div><span>lane</span><b>{b.lane || '—'}</b></div>
          <div><span>rule</span><b>{b.reuse_rule || '—'}</b></div>
        </div>
        {b.namespace && <div className="ns">namespace <code>{b.namespace}</code></div>}

        {sources.length > 0 && (
          <details className="sources" open={foreign.length > 0}>
            <summary>
              grounded in {sources.length} chunk{sources.length === 1 ? '' : 's'}
              {foreign.length > 0 && <span className="warn"> — {foreign.length} from another product</span>}
            </summary>
            <ul>
              {sources.map((s) => (
                <li key={s} className={foreign.includes(s) ? 'foreign' : ''}>
                  <code>{s}</code>
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </div>
  )
}
