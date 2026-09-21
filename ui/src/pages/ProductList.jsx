import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchProducts } from '../api.js'
import Counters from '../Counters.jsx'

export default function ProductList() {
  const [products, setProducts] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    fetchProducts().then(setProducts).catch((e) => setErr(e.message))
  }, [])

  const byCategory = (products ?? []).reduce((acc, p) => {
    ;(acc[p.category || 'uncategorised'] ??= []).push(p)
    return acc
  }, {})

  return (
    <div className="layout">
      <main className="main">
        <header className="page-head">
          <h1>Product catalogue</h1>
          <p className="sub">
            Pick a product to open its assistant. The product you pick is sent as{' '}
            <code>product_id</code> — the page already knows which product the question is about,
            which is how a production assistant is actually invoked.
          </p>
        </header>

        {err && <div className="error">Could not load the catalogue — {err}</div>}
        {!products && !err && <div className="muted">Loading…</div>}
        {products?.length === 0 && (
          <div className="error">
            The corpus index is empty. Run <code>make ingest</code> (or <code>make demo-reset</code>).
          </div>
        )}

        {Object.entries(byCategory).sort().map(([category, items]) => (
          <section key={category} className="category">
            <h2>{category} <span className="count">{items.length}</span></h2>
            <div className="grid">
              {items.map((p) => (
                <Link key={p.doc_id} to={`/p/${encodeURIComponent(p.doc_id)}`} className="card">
                  <span className="card-title">{p.title || p.doc_id}</span>
                  <span className="card-id">{p.doc_id}</span>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </main>
      <Counters />
    </div>
  )
}
