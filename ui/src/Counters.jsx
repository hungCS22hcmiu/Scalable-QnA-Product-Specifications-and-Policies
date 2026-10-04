import { useEffect, useState } from 'react'
import { fetchStats } from './api.js'

// The counters sidebar is REQUIRED by the demo UI contract, not optional:
//
//   "running counters: total requests, hit rate, and generations avoided. Not optional.
//    Generations avoided is the load-conversion ratio (§3) rendered as a single live number,
//    which makes it the cheapest scalability evidence available and the only one visible
//    during steps 1-5."
//
// It polls the GATEWAY rather than counting locally, because the demo drives the system from
// several tabs at once and a per-tab counter would show each tab its own slice. Polling is a
// deliberate non-choice: server-sent events were out of scope, and one small GET a
// second is invisible next to a generation.
export default function Counters({ intervalMs = 1000 }) {
  const [stats, setStats] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let alive = true
    const tick = () =>
      fetchStats()
        .then((s) => alive && (setStats(s), setErr(null)))
        .catch((e) => alive && setErr(e.message))
    tick()
    const id = setInterval(tick, intervalMs)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [intervalMs])

  if (err) return <aside className="counters"><div className="counters-err">stats unavailable — {err}</div></aside>
  if (!stats) return <aside className="counters"><div className="counters-err">…</div></aside>

  return (
    <aside className="counters">
      <h2>Counters <span className="counters-scope">gateway-wide, all tabs</span></h2>

      <div className="counter big">
        <span className="counter-value">{stats.generations_avoided}</span>
        <span className="counter-label">generations avoided</span>
      </div>

      <div className="counter big">
        <span className="counter-value">{(stats.hit_rate * 100).toFixed(1)}%</span>
        <span className="counter-label">hit rate</span>
      </div>

      <div className="counter-grid">
        <div><b>{stats.requests}</b><span>requests</span></div>
        <div><b>{stats.generations_run}</b><span>model runs</span></div>
        <div><b>{stats.tier1_hits}</b><span>TIER 1</span></div>
        <div><b>{stats.tier2_hits}</b><span>TIER 2</span></div>
        <div><b>{stats.misses}</b><span>miss</span></div>
        <div className={stats.coalesced > 0 ? 'lit' : ''}><b>{stats.coalesced}</b><span>coalesced</span></div>
        <div className={stats.shed > 0 ? 'shed' : ''}><b>{stats.shed}</b><span>shed 503</span></div>
      </div>

      <p className="counters-note">
        <b>coalesced</b> — duplicates that arrived while an identical question was still
        generating, and were served its result. <b>shed</b> — refused with{' '}
        <code>503 busy, retry</code> rather than queued invisibly behind the model's one generation slot.
      </p>
    </aside>
  )
}
