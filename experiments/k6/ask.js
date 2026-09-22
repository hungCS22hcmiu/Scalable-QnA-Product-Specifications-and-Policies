// k6 load scenario for POST /ask.
//
// ⚠️ RUN THIS OFF-BOX. the off-box measurement rule and proposal §7: the load generator must not be co-hosted with the
// system under test. On a 16 GB machine whose thesis is that generation is memory-bound, a k6
// process on the same host competes for the envelope it is measuring, and a run taken that way is
// invalid rather than merely noisy.
//
//   k6 run -e GATEWAY_URL=http://<sut-ip>:8080 -e WORKLOAD=workload.json experiments/k6/ask.js
//
// What this script is careful about, in order of how badly getting it wrong would hurt:
//
//   1. A 503 is NOT a failure. interfaces.md §A's shed is a graceful-degradation event and
//      the evaluation counts it separately from goodput. If k6's default checks marked
//      it failed, an overloaded run would report an error rate instead of a shed rate -- and
//      proposal §3's S2 would look violated exactly where the gateway behaved correctly.
//   2. Goodput excludes sheds. Throughput here counts only answered requests, because otherwise
//      S2 (stability) is satisfiable at S1's (capacity) expense by shedding everything.
//   3. The workload's REDUNDANCY is the independent variable (proposal §9.1), so query
//      selection is Zipf with a swept skew -- never uniform, which would make the cache look
//      useless, and never a fixed cycle, which would make it look perfect.

import http from 'k6/http';
import { Counter, Rate, Trend } from 'k6/metrics';
import { SharedArray } from 'k6/data';

const GATEWAY = __ENV.GATEWAY_URL || 'http://localhost:8080';
const WORKLOAD = __ENV.WORKLOAD || '';
const ZIPF_SKEW = parseFloat(__ENV.ZIPF_SKEW || '1.1');   // manifest: zipf_skew
const RATE_RPS = parseInt(__ENV.RATE_RPS || '10', 10);
const VUS = parseInt(__ENV.VUS || '20', 10);
const DURATION = __ENV.DURATION || '2m';

// The workload file is the frozen query set (data-card.md §3). Each record needs at least
// `question`; `stratum` and `product_id` are passed through when present.
//
// SharedArray parses once for all VUs instead of once per VU -- with a few thousand queries the
// per-VU copy is what makes a load generator run out of memory before the target does.
const queries = new SharedArray('queries', function () {
  if (!WORKLOAD) {
    // Smoke fallback so the harness is runnable before `v1` is frozen. NOT a workload: it has no
    // strata, no redundancy structure, and nothing measured on it may be reported.
    return [
      { question: 'what is the battery life of the EarBuds Pop 3' },
      { question: 'how long do I have to return an item' },
      { question: 'what is the warranty period' },
      { question: 'what is the battery life of the EarBuds Pop 3 and how long do I have to return it' },
      { question: 'how much RAM does the UltraBook Pro 14 have' },
    ];
  }
  return JSON.parse(open(WORKLOAD));
});

// --- Zipf sampling -----------------------------------------------------------------------------
// Precomputed CDF over ranks 1..N with P(rank) proportional to 1/rank^s. Built once per VU;
// sampling is then a binary search rather than a sum per request, so the generator does not become
// the bottleneck at high rates.
const zipfCDF = (function () {
  const n = queries.length;
  const cdf = new Array(n);
  let total = 0;
  for (let i = 0; i < n; i++) {
    total += 1 / Math.pow(i + 1, ZIPF_SKEW);
    cdf[i] = total;
  }
  for (let i = 0; i < n; i++) cdf[i] /= total;
  return cdf;
})();

function sampleZipf() {
  const u = Math.random();
  let lo = 0, hi = zipfCDF.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (zipfCDF[mid] < u) lo = mid + 1; else hi = mid;
  }
  return queries[lo];
}

// --- Metrics -----------------------------------------------------------------------------------
// Reported per the evaluation. Sheds and goodput are separate by construction.
const goodput = new Counter('goodput_requests');       // answered; excludes sheds
const shedRate = new Rate('shed_rate');                // 503 / all admitted attempts
const errorRate = new Rate('error_rate');              // genuine failures only -- never a 503
const tier1 = new Counter('cache_tier1_hit');
const tier2 = new Counter('cache_tier2_hit');
const miss = new Counter('cache_miss');
const answeredLatency = new Trend('answered_latency_ms', true);
const shedLatency = new Trend('shed_latency_ms', true);

export const options = {
  scenarios: {
    constant_rate: {
      executor: 'constant-arrival-rate',
      // Arrival rate, NOT closed-loop VUs. A closed loop cannot overload the target -- each VU
      // waits for its own response -- so it can never produce the saturation point S1 is about.
      rate: RATE_RPS,
      timeUnit: '1s',
      duration: DURATION,
      preAllocatedVUs: VUS,
      maxVUs: VUS * 4,
    },
  },
  // No global thresholds on http_req_failed: a 503 is expected behaviour here, and a threshold on
  // it would abort a run that is demonstrating exactly what the gateway is for.
  thresholds: {
    error_rate: ['rate<0.01'],
  },
};

export default function () {
  const q = sampleZipf();
  const payload = { question: q.question };
  if (q.product_id) payload.product_id = q.product_id;

  const headers = { 'Content-Type': 'application/json' };
  // interfaces.md §H carries `stratum`; §A deliberately does not, so it travels as a header
  //. Absent, the label joins offline on query_normalized.
  if (q.stratum) headers['X-Thesis-Stratum'] = q.stratum;

  const res = http.post(`${GATEWAY}/ask`, JSON.stringify(payload), {
    headers,
    // Long enough for a cold generation on this envelope; a timeout here would be recorded as an
    // error and mis-attributed to the gateway.
    timeout: '120s',
  });

  if (res.status === 503) {
    shedRate.add(true);
    errorRate.add(false);
    shedLatency.add(res.timings.duration);
    return;
  }
  shedRate.add(false);

  if (res.status !== 200) {
    errorRate.add(true);
    return;
  }
  errorRate.add(false);
  goodput.add(1);
  answeredLatency.add(res.timings.duration);

  let body;
  try {
    body = res.json();
  } catch (e) {
    errorRate.add(true);
    return;
  }
  if (body.cache === 'TIER1_HIT') tier1.add(1);
  else if (body.cache === 'TIER2_HIT') tier2.add(1);
  else miss.add(1);
}

export function handleSummary(data) {
  // Printed so the operator can paste the numbers straight into manifest.yaml. The manifest is
  // required and a run without one is invalid (the evaluation).
  const m = data.metrics;
  const val = (name, field) => (m[name] && m[name].values ? m[name].values[field] : 0);
  const answered = val('goodput_requests', 'count');
  const t1 = val('cache_tier1_hit', 'count');
  const t2 = val('cache_tier2_hit', 'count');
  const ms = val('cache_miss', 'count');
  const hitRate = answered ? (t1 + t2) / answered : 0;

  const lines = [
    '',
    '=== for manifest.yaml (the evaluation) ===',
    `  zipf_skew: ${ZIPF_SKEW}`,
    `  k6_scenario: { vus: ${VUS}, rate_rps: ${RATE_RPS}, duration: "${DURATION}" }`,
    '',
    '=== outcomes (the evaluation) ===',
    `  goodput (answered)      ${answered}`,
    `  shed rate               ${(val('shed_rate', 'rate') * 100).toFixed(2)} %   <- graceful degradation, NOT errors`,
    `  error rate              ${(val('error_rate', 'rate') * 100).toFixed(2)} %`,
    `  TIER1 / TIER2 / MISS    ${t1} / ${t2} / ${ms}`,
    `  hit rate                ${(hitRate * 100).toFixed(2)} %`,
    `  answered p95            ${val('answered_latency_ms', 'p(95)').toFixed(1)} ms`,
    '',
    '  ⚠️ Record memory_pressure.min_zone from the SUT. A run that left green is INVALID and is',
    '     repeated at lower load (proposal §7), whatever these numbers say.',
    '',
  ].join('\n');

  return { stdout: lines };
}
