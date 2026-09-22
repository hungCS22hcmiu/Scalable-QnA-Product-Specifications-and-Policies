// The μ_hit probe — Phase 1 exit criterion.
//
// ⚠️ RUN THIS OFF-BOX, like every other load scenario (proposal §7). A co-hosted
// generator competes for the envelope it is measuring.
//
//   k6 run -e GATEWAY_URL=http://<sut-ip>:8080 -e WORKLOAD=workload.json experiments/k6/mu_hit.js
//
// ## Why this number can change the report
//
// The load-conversion crossover is `h* = μ_hit / (μ_gen + μ_hit)`. `Final_Proposal.md` §3 and the
// submitted pre-thesis report both state the crossover is **computed rather than observed**, on
// the basis that μ_hit sits far above ~16 req/s. If this probe returns **≤ ~16 req/s** that
// reasoning inverts and S1's empirical wording is restored (the falsification trigger).
// So this is measured before anything else depends on it.
//
// ## What makes it a μ_hit measurement rather than a fast load test
//
//   1. **The cache is pre-warmed in setup(), and the warm-up is verified.** setup() is excluded
//      from k6's metrics, so no generation latency reaches the number. A second pass then asserts
//      every query answers from cache: "100 %-hit" is a CHECKED property here, not an assumption.
//   2. **A mid-run MISS fails the probe.** `unexpected_miss` carries a threshold of 0. The usual
//      cause is CACHE_CAPACITY smaller than the probe set, so LRU evicts under the probe's own
//      load — which would quietly mix generation into the hit path and understate μ_hit by orders
//      of magnitude.
//   3. **Tiers are reported separately.** A Tier-1 hit is a hash lookup; a Tier-2 hit pays an
//      embedding round-trip that `interfaces.md` §F says bounds μ_hit. One blended figure would
//      hide exactly that decomposition, and which tier dominates depends on the workload.
//   4. **Saturation is verified, not assumed.** The offered rate is deliberately far above the
//      expected ceiling. If nothing is dropped and nothing is shed, the generator never pushed
//      past capacity and the result is a LOWER BOUND on μ_hit, not μ_hit. The summary says which
//      of the two it got.

import http from 'k6/http';
import { Counter, Rate, Trend } from 'k6/metrics';
import { SharedArray } from 'k6/data';

const GATEWAY = __ENV.GATEWAY_URL || 'http://localhost:8080';
const WORKLOAD = __ENV.WORKLOAD || '';
// Offered rate. The default is deliberately well above any plausible ceiling for a path that is a
// Redis lookup plus (on Tier 2) one embedding call -- the probe is looking for the plateau, so
// under-offering is the one way to get a wrong answer quietly.
const RATE_RPS = parseInt(__ENV.RATE_RPS || '400', 10);
const VUS = parseInt(__ENV.VUS || '100', 10);
const DURATION = __ENV.DURATION || '60s';
const DURATION_S = parseInt(DURATION, 10) * (DURATION.endsWith('m') ? 60 : 1);

// The probe set must be SMALL and must fit inside CACHE_CAPACITY, or the probe evicts its own
// working set (see check 2 above). A few dozen queries is plenty: μ_hit is a service rate, and
// serving the same entry repeatedly is what the load-conversion argument is actually about.
const PROBE_SIZE = parseInt(__ENV.PROBE_SIZE || '20', 10);

// Which tier's ceiling is being measured. They are DIFFERENT numbers and the distinction is the
// whole of interfaces.md §F: a Tier-1 hit is a hash lookup, while a Tier-2 hit pays an embedding
// round-trip -- "this endpoint's latency directly bounds μ_hit". Reporting the Tier-1 figure as
// "μ_hit" would state a ceiling the tiered system never actually reaches.
//
//   MODE=tier1  drive the exact warmed question   -> Tier-1 hits (hash lookup only)
//   MODE=tier2  drive each record's `paraphrase`  -> Tier-2 hits (embed + FLAT search + rule)
const MODE = (__ENV.MODE || 'tier1').toLowerCase();

const queries = new SharedArray('probe', function () {
  if (!WORKLOAD) {
    // Smoke fallback, for shaking the harness out before `v1` exists. NOT a workload.
    //
    // Every paraphrase here was MEASURED against its question with the frozen embedding model on
    // 2026-09-06 and clears tau=0.85 with margin (0.92-0.98). That is not fussiness: a pair below
    // tau MISSES, generates, and contaminates Tier 1 permanently for later probes (see setup()).
    // An earlier fallback used "how long does the EarBuds Pop 3 battery last", which measures
    // 0.84 -- below tau -- and did exactly that.
    return [
      { question: 'what is the battery life of the EarBuds Pop 3',                    // 0.9838
        paraphrase: 'what is the battery life of the EarBuds Pop 3 headphones' },
      { question: 'how long do I have to return an item',                             // 0.9230
        paraphrase: 'how long do I have to return a purchase' },
      { question: 'what does the shipping policy say',                                // 0.9629
        paraphrase: 'what does the shipping policy state' },
      { question: 'how much RAM does the UltraBook Pro 14 have',                      // 0.9666
        paraphrase: 'how much memory does the UltraBook Pro 14 have' },
      { question: 'Am I entitled to a full refund on my headphones 30 days after delivery?',
        paraphrase: 'Is a full refund possible for my headphones 30 days after delivery?' }, // 0.9750
    ];
  }
  return JSON.parse(open(WORKLOAD)).slice(0, PROBE_SIZE);
});

// The text the MEASURED scenario sends. Warm-up always uses `question`; only the driving text
// changes, so both modes measure hits against the same cache contents.
function driveText(q) {
  return MODE === 'tier2' ? (q.paraphrase || q.question) : q.question;
}

// --- Metrics -----------------------------------------------------------------------------------
const hits = new Counter('hit_requests'); // the μ_hit numerator
const tier1 = new Counter('cache_tier1_hit');
const tier2 = new Counter('cache_tier2_hit');
const unexpectedMiss = new Counter('unexpected_miss');
const shedRate = new Rate('shed_rate');
const errorRate = new Rate('error_rate');
const t1Latency = new Trend('tier1_latency_ms', true);
const t2Latency = new Trend('tier2_latency_ms', true);

export const options = {
  scenarios: {
    saturate: {
      executor: 'constant-arrival-rate',
      rate: RATE_RPS,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: VUS,
      maxVUs: VUS * 4,
      gracefulStop: '10s',
    },
  },
  thresholds: {
    // A miss during the probe invalidates it. Failing here is the point: a silently degraded
    // probe would report a μ_hit that is really a generation rate.
    unexpected_miss: ['count==0'],
    error_rate: ['rate<0.01'],
  },
};

// setup() runs once, is EXCLUDED from the metrics, and aborts the whole run if it throws.
export function setup() {
  const warmed = [];
  for (const q of queries) {
    const payload = { question: q.question };
    if (q.product_id) payload.product_id = q.product_id;
    // A cold generation on this envelope takes seconds; that is why warm-up is here and not in
    // the measured scenario.
    const res = http.post(`${GATEWAY}/ask`, JSON.stringify(payload), {
      headers: { 'Content-Type': 'application/json' },
      timeout: '180s',
    });
    if (res.status !== 200) {
      throw new Error(`warm-up failed for ${JSON.stringify(q.question)}: HTTP ${res.status}`);
    }
    warmed.push(q.question);
  }

  // Verification pass, on the text the scenario will actually SEND. Without this the probe would
  // happily measure a cache that never populated -- e.g. a gateway whose write-back is failing,
  // which produces plausible 200s and a μ_hit that is really μ_gen.
  //
  // In tier2 mode the requirement is stricter than "a hit": it must be a TIER2_HIT specifically.
  // A paraphrase that falls below tau MISSES, generates, and is then written into Tier 1 under
  // its own key -- after which every subsequent request is a TIER1_HIT and the probe reports the
  // hash-lookup ceiling while claiming to have measured the embedding-bound one. That failure is
  // completely silent in the numbers, so it is caught here instead.
  const wrong = [];
  for (const q of queries) {
    const payload = { question: driveText(q) };
    if (q.product_id) payload.product_id = q.product_id;
    const res = http.post(`${GATEWAY}/ask`, JSON.stringify(payload), {
      headers: { 'Content-Type': 'application/json' },
      timeout: '180s',
    });
    let body = {};
    try { body = res.json(); } catch (e) { /* handled by the check below */ }

    const ok = MODE === 'tier2'
      ? body.cache === 'TIER2_HIT'
      : body.cache === 'TIER1_HIT' || body.cache === 'TIER2_HIT';
    if (!ok) wrong.push(`${JSON.stringify(driveText(q))} -> ${body.cache || res.status}`);
  }
  if (wrong.length) {
    const why = MODE === 'tier2'
      ? `they must answer TIER2_HIT. A paraphrase below tau generates instead, lands in Tier 1 ` +
        `under its own key, and turns this into a tier1 probe wearing a tier2 label -- and that ` +
        `contamination is STICKY: every later tier2 probe then sees TIER1_HIT for the same ` +
        `paraphrase. Fix: stop the gateway, \`make demo-reset\`, restart, and re-run. If it ` +
        `still fails, the paraphrases genuinely sit below tau -- bring them closer, or lower ` +
        `REUSE_TAU for the probe and record in the manifest that you did.`
      : `this is not a 100 %-hit run. Check CACHE_CAPACITY (>= ${queries.length}) and that ` +
        `write-back succeeds.`;
    throw new Error(
      `${wrong.length}/${queries.length} probe queries answered wrongly in MODE=${MODE}: ` +
      `${why}\n  ${wrong.join('\n  ')}`
    );
  }

  return { warmed: warmed.length, mode: MODE };
}

export default function () {
  const q = queries[Math.floor(Math.random() * queries.length)];
  const payload = { question: driveText(q) };
  if (q.product_id) payload.product_id = q.product_id;

  const res = http.post(`${GATEWAY}/ask`, JSON.stringify(payload), {
    headers: { 'Content-Type': 'application/json' },
    timeout: '30s',
  });

  if (res.status === 503) {
    // A shed on the HIT path would be surprising: hits never acquire a generation permit
    //, and that asymmetry is what lets hit throughput exceed the generation ceiling.
    // Recorded rather than ignored, because if it happens it falsifies that claim.
    shedRate.add(true);
    errorRate.add(false);
    return;
  }
  shedRate.add(false);

  if (res.status !== 200) {
    errorRate.add(true);
    return;
  }
  errorRate.add(false);

  let body;
  try {
    body = res.json();
  } catch (e) {
    errorRate.add(true);
    return;
  }

  if (body.cache === 'TIER1_HIT') {
    tier1.add(1); hits.add(1); t1Latency.add(res.timings.duration);
  } else if (body.cache === 'TIER2_HIT') {
    tier2.add(1); hits.add(1); t2Latency.add(res.timings.duration);
  } else {
    unexpectedMiss.add(1);
  }
}

export function handleSummary(data) {
  const m = data.metrics;
  const val = (name, field) => (m[name] && m[name].values ? m[name].values[field] : 0);

  const served = val('hit_requests', 'count');
  const dropped = val('dropped_iterations', 'count');
  const shed = val('shed_rate', 'passes');
  const muHit = served / DURATION_S;

  // Saturation check -- see point 4 in the header. Offered load must have EXCEEDED capacity, or
  // the plateau was never reached and this is a floor rather than a ceiling.
  const saturated = dropped > 0 || shed > 0;
  const verdict = served === 0
    // setup() threw, so the scenario never ran. Say so: "LOWER BOUND 0.0 req/s" would read as a
    // measured ceiling of zero, which is the opposite of what happened.
    ? 'NO MEASUREMENT -- the scenario never ran. setup() aborted; read the error above it.'
    : saturated
      ? `mu_hit ~= ${muHit.toFixed(1)} req/s  (offered ${RATE_RPS}/s, generator saturated the target)`
      : `LOWER BOUND ${muHit.toFixed(1)} req/s -- nothing dropped, nothing shed, so the offered ` +
        `rate of ${RATE_RPS}/s never reached the ceiling. Re-run with a higher RATE_RPS.`;

  // the falsification trigger, evaluated here so it cannot be forgotten later.
  const trigger = !saturated
    ? '  (undetermined -- the probe did not saturate)'
    : muHit <= 16
      ? '  ⚠️ mu_hit <= ~16 req/s: the crossover IS reachable in a non-degenerate sweep.\n' +
        '     the capacity ratio requires S1\'s EMPIRICAL wording to be restored, and Final_Proposal.md §3 /\n' +
        '     the evaluation to be revised before anything further depends on them.'
      : '  mu_hit > ~16 req/s: the capacity ratio\'s restated S1 stands -- the crossover is computed rather\n' +
        '     than observed, and the finding is "generation-bound throughout the operating range".';

  const lines = [
    '',
    `=== mu_hit probe, MODE=${MODE} ===`,
    `  ${verdict}`,
    MODE === 'tier1'
      ? '  NOTE: this is the TIER-1 ceiling -- a hash lookup, no embedding call. The tiered\n' +
        '        system\'s hit path is bounded by Tier 2 (interfaces.md §F). Run MODE=tier2 for\n' +
        '        the figure h* should be computed from.'
      : '  This is the TIER-2 ceiling: embed round-trip + FLAT search + the reuse rule, which is\n' +
        '        what interfaces.md §F says bounds mu_hit.',
    '',
    `  hits served             ${served} over ${DURATION_S}s`,
    `  TIER1 / TIER2           ${val('cache_tier1_hit', 'count')} / ${val('cache_tier2_hit', 'count')}`,
    `  TIER1 p95 / TIER2 p95   ${val('tier1_latency_ms', 'p(95)').toFixed(1)} / ${val('tier2_latency_ms', 'p(95)').toFixed(1)} ms`,
    `  dropped iterations      ${dropped}   <- offered-minus-served; >0 means the target saturated`,
    `  sheds                   ${shed}   <- should be 0: hits take no generation permit`,
    `  unexpected misses       ${val('unexpected_miss', 'count')}   <- any non-zero INVALIDATES the probe`,
    '',
    '=== the capacity ratio falsification trigger ===',
    trigger,
    '',
    '=== for manifest.yaml ===',
    `  mu_hit_probe_rps: ${muHit.toFixed(1)}`,
    `  k6_scenario: { rate_rps: ${RATE_RPS}, duration: "${DURATION}", probe_set: ${queries.length} }`,
    '',
    '  ⚠️ Record memory_pressure.min_zone from the SUT. A run that left green is INVALID and is',
    '     repeated at lower load (proposal §7), whatever these numbers say.',
    '',
  ].join('\n');

  return { stdout: lines };
}
