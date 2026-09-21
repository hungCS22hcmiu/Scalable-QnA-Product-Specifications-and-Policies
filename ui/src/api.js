// One place for every call to the gateway. Same-origin in both dev (Vite proxy) and production
// (the gateway serves the bundle), so no base URL and no CORS.

export async function fetchProducts() {
  const res = await fetch('/products')
  if (!res.ok) throw new Error(`/products returned ${res.status}`)
  return res.json()
}

export async function fetchStats() {
  const res = await fetch('/stats')
  if (!res.ok) throw new Error(`/stats returned ${res.status}`)
  return res.json()
}

// ask returns { ok, status, body, wallMs }.
//
// A 503 is NOT an error here, and separating `ok` from `status` is the whole point.
// interfaces.md A's shed is designed behaviour: under enough concurrent tabs the gateway refuses
// work rather than swapping, and a UI that rendered that as a failure would show the opposite of
// what happened.
//
// wallMs is measured in the BROWSER and is kept deliberately separate from the gateway's own
// latency_ms. With several tabs open the two diverge -- the gap is queueing plus browser
// scheduling -- and showing both is more honest than picking one.
export async function ask(question, productId) {
  const started = performance.now()
  const res = await fetch('/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(productId ? { question, product_id: productId } : { question }),
  })
  const wallMs = Math.round(performance.now() - started)
  let body = null
  try {
    body = await res.json()
  } catch {
    // A shed with an empty body, or a gateway restart mid-request. Leave body null; the caller
    // renders the status instead.
  }
  return { ok: res.ok, status: res.status, body, wallMs }
}
