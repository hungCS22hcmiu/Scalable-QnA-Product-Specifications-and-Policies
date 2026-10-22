# Build report — item 3.4 (written by `make workload-build`)

## whole

- records 1274 · K 1274 · capacity 318 · unanswerable 94 · minimal-pair twins 136 · trap fraction 0.2229
- strata {'A': 761, 'B-cross': 22, 'B-within': 272, 'C': 150, 'D': 69}
- probe kinds {'condition-department': 16, 'name-swap': 12, 'name-swap-same': 10, 'natural': 10, 'none': 980, 'policy-condition': 120, 'policy-kind': 9, 'policy-region': 18, 'spec-attribute': 99}
- departments {'electronics': 226, 'furniture': 326, 'laptops': 338, 'phones': 384} · axes {'grade': 46, 'none': 1012, 'packaging': 180, 'region': 36}
- roles {'d': 69, 'natural': 54, 'paraphrase': 555, 'probe': 294, 'seed': 302} · origins {'claude': 871, 'pqa': 309, 'pqa-template': 94}

## validation

- records 622 · K 622 · capacity 156 · unanswerable 40 · minimal-pair twins 56 · trap fraction 0.2074
- strata {'A': 371, 'B-cross': 11, 'B-within': 124, 'C': 83, 'D': 33}
- probe kinds {'condition-department': 16, 'name-swap': 5, 'name-swap-same': 6, 'natural': 4, 'none': 487, 'policy-condition': 40, 'policy-kind': 6, 'policy-region': 6, 'spec-attribute': 52}
- departments {'electronics': 105, 'furniture': 154, 'laptops': 162, 'phones': 201} · axes {'grade': 22, 'none': 506, 'packaging': 82, 'region': 12}
- roles {'d': 33, 'natural': 22, 'paraphrase': 281, 'probe': 135, 'seed': 151} · origins {'claude': 422, 'pqa': 147, 'pqa-template': 53}

## test

- records 652 · K 652 · capacity 163 · unanswerable 54 · minimal-pair twins 80 · trap fraction 0.2377
- strata {'A': 390, 'B-cross': 11, 'B-within': 148, 'C': 67, 'D': 36}
- probe kinds {'name-swap': 7, 'name-swap-same': 4, 'natural': 6, 'none': 493, 'policy-condition': 80, 'policy-kind': 3, 'policy-region': 12, 'spec-attribute': 47}
- departments {'electronics': 121, 'furniture': 172, 'laptops': 176, 'phones': 183} · axes {'grade': 24, 'none': 506, 'packaging': 98, 'region': 24}
- roles {'d': 36, 'natural': 32, 'paraphrase': 274, 'probe': 159, 'seed': 151} · origins {'claude': 449, 'pqa': 162, 'pqa-template': 41}

## validation: what a run sees

- skew 0.8: traffic by stratum {'A': 0.6074, 'B-cross': 0.0154, 'B-within': 0.2038, 'C': 0.1261, 'D': 0.0474}
  by probe kind {'condition-department': 0.0162, 'name-swap': 0.0083, 'name-swap-same': 0.007, 'natural': 0.0067, 'none': 0.7809, 'policy-condition': 0.0546, 'policy-kind': 0.0089, 'policy-region': 0.0453, 'spec-attribute': 0.0721}
  LRU (3000 requests, capacity 156): Tier-1 hit rate 0.542, misses with a cached cluster-mate 521, probe encounters {'condition-department': 9, 'name-swap': 3, 'name-swap-same': 3, 'natural': 4, 'policy-condition': 16, 'policy-kind': 2, 'policy-region': 4, 'spec-attribute': 24}
- skew 1.1: traffic by stratum {'A': 0.6323, 'B-cross': 0.0112, 'B-within': 0.2072, 'C': 0.1114, 'D': 0.0379}
  by probe kind {'condition-department': 0.0091, 'name-swap': 0.0072, 'name-swap-same': 0.004, 'natural': 0.0048, 'none': 0.7816, 'policy-condition': 0.0391, 'policy-kind': 0.0059, 'policy-region': 0.089, 'spec-attribute': 0.0594}
  LRU (3000 requests, capacity 156): Tier-1 hit rate 0.7657, misses with a cached cluster-mate 267, probe encounters {'condition-department': 8, 'name-swap': 3, 'name-swap-same': 1, 'policy-condition': 16, 'policy-kind': 3, 'policy-region': 2, 'spec-attribute': 8}
- skew 1.4: traffic by stratum {'A': 0.674, 'B-cross': 0.0065, 'B-within': 0.2048, 'C': 0.089, 'D': 0.0258}
  by probe kind {'condition-department': 0.0038, 'name-swap': 0.0048, 'name-swap-same': 0.0017, 'natural': 0.0025, 'none': 0.7887, 'policy-condition': 0.0225, 'policy-kind': 0.0029, 'policy-region': 0.1305, 'spec-attribute': 0.0426}
  LRU (3000 requests, capacity 156): Tier-1 hit rate 0.9057, misses with a cached cluster-mate 87, probe encounters {'name-swap': 1, 'name-swap-same': 1, 'policy-condition': 3, 'spec-attribute': 3}

## test: what a run sees

- skew 0.8: traffic by stratum {'A': 0.6083, 'B-cross': 0.0146, 'B-within': 0.2272, 'C': 0.1006, 'D': 0.0493}
  by probe kind {'name-swap': 0.0117, 'name-swap-same': 0.0029, 'natural': 0.0453, 'none': 0.7582, 'policy-condition': 0.0992, 'policy-kind': 0.0026, 'policy-region': 0.0244, 'spec-attribute': 0.0557}
  LRU (3000 requests, capacity 163): Tier-1 hit rate 0.552, misses with a cached cluster-mate 536, probe encounters {'name-swap': 1, 'name-swap-same': 1, 'natural': 2, 'policy-condition': 27, 'policy-kind': 1, 'policy-region': 1, 'spec-attribute': 12}
- skew 1.1: traffic by stratum {'A': 0.6325, 'B-cross': 0.0107, 'B-within': 0.2248, 'C': 0.0927, 'D': 0.0393}
  by probe kind {'name-swap': 0.0093, 'name-swap-same': 0.0013, 'natural': 0.089, 'none': 0.7645, 'policy-condition': 0.0693, 'policy-kind': 0.0013, 'policy-region': 0.0266, 'spec-attribute': 0.0386}
  LRU (3000 requests, capacity 163): Tier-1 hit rate 0.7743, misses with a cached cluster-mate 259, probe encounters {'natural': 2, 'policy-condition': 20, 'policy-kind': 1, 'policy-region': 3, 'spec-attribute': 12}
- skew 1.4: traffic by stratum {'A': 0.6738, 'B-cross': 0.0062, 'B-within': 0.2157, 'C': 0.0776, 'D': 0.0266}
  by probe kind {'name-swap': 0.0058, 'name-swap-same': 0.0005, 'natural': 0.1305, 'none': 0.778, 'policy-condition': 0.0385, 'policy-kind': 0.0005, 'policy-region': 0.0242, 'spec-attribute': 0.0221}
  LRU (3000 requests, capacity 163): Tier-1 hit rate 0.9083, misses with a cached cluster-mate 84, probe encounters {'natural': 1, 'policy-condition': 5, 'policy-region': 1, 'spec-attribute': 4}

## Cosines

- A: nearest foreign cosine min 0.5511 · median 0.7264 · max 0.9669 · ≥ 0.85: 20
- B-within: nearest foreign cosine min 0.5578 · median 0.9442 · max 0.9777 · ≥ 0.85: 159
- B-cross: nearest foreign cosine min 0.6656 · median 0.757 · max 0.8151 · ≥ 0.85: 0
- C: nearest foreign cosine min 0.5647 · median 0.7902 · max 0.9777 · ≥ 0.85: 24
- D: nearest foreign cosine min 0.6529 · median 0.7995 · max 0.9346 · ≥ 0.85: 13
- across the splits: {'same_document_max_cosine': 0.9648, 'd_against_term_max_cosine': 0.9374}

## Drops (rules.md §8)

- lookalike: the blind label disagrees: 17
- name swap: its seed was dropped: 5
- name swap: the partner's record cannot answer it: 47
- natural pair: a blind label disagrees: 10
- natural pair: marked unanswerable: 190
- paraphrase: the blind label disagrees: 2
- spec query dropped with its seed: 40
- spec seed: the blind label disagrees (its cluster and probes go too): 16
- unanswerable query dropped with its seed: 5
- unanswerable seed: the blind label finds an answer: 5
