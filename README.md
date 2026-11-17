# GTA VI Launch-Day Twitch CCU Forecaster

[![make.fun · gta6-twitch-ccu-forecast-01](https://make.fun/badge/gta6-twitch-ccu-forecast-01.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![rank](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Jo3st4r/gta6-forecast-bot/rank.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)
[![reward](https://make.fun/badge/gta6-twitch-ccu-forecast-01/Jo3st4r/gta6-forecast-bot/reward.svg)](https://make.fun/bounty/gta6-twitch-ccu-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-twitch-ccu-forecast-01)

Entry for make.fun competition **gta6-twitch-ccu-forecast-01** — forecast the
Twitch viewers of the "Grand Theft Auto VI" category, hours 2–24 of launch day,
as five quantiles (5/25/50/75/95%) per hour.

## How to run

```bash
python3 main.py          # reads $MAKEFUN_INPUT_DIR (default /input),
                         # writes $MAKEFUN_OUTPUT_DIR/<id>.out (default /output)
```

Python 3.13, standard library only. No network, no wall clock, no files
outside the input directory. Deterministic: two runs on the same case produce
byte-identical output (verified).

## Strategy

The hour-1 print (p1) is the dominant signal. Across the 38 comparable
launches shipped with each case, the launch-day curve shape depends massively
on hour-1 scale:

- Small launches (h1 ~ 1k) rise up to ~100x by the US-evening peak.
- Huge launches (h1 ~ 900k) stay roughly flat (~0.9–1.3x).

In log-log space the relationship between `log(h1)` and the log-ratio
`log(viewers_h / p1)` is **concave**: steep for small h1, flattening for big
h1. A single global straight line badly under-predicts big launches — e.g. it
predicts 0.29x at hour 20 for an 875k launch whose actual ratio is 0.90x.
That matters because GTA VI's hour-1 print will very likely be large.

So, for each hour h = 2..24, the program fits a **piecewise-linear
regression** of the log-ratio on `log(h1)` over the case's *own* comparables,
with the knot at the median `log(h1)`:

```
lr_h = a + b1 * x + b2 * max(0, x - x_median),   x = log(h1)
```

The second segment's slope is gentle (about −0.17 to −0.28), so the model
extrapolates sanely even if GTA VI's hour-1 print exceeds every comparable
(at h1 = 875k it predicts 0.90x at hour 20 — exactly the observed ratio of
ELDEN RING and Cyberpunk 2077).

Quantiles come from the **empirical distribution of the fit residuals**
(5/25/50/75/95% quantiles around the fitted value), which captures the true
skewed, heavy-tailed uncertainty better than a normal spread. Fallback: if
fewer than 4 usable comparable curves exist, the house baseline shape
`p1 * exp(z_tau * 0.15 * sqrt(h-1))` is used.

## Practice scores (local scorer, answers from SullyGnome)

Mean pinball loss (log scale) vs the house baseline's 0.387:

| case | launch | h1 | loss | typical miss | 90% coverage |
|------|--------|-----|------|--------------|--------------|
| p00 | Marvel's Wolverine | 23,357 | 0.208 | 39.6% | 0.957 |
| p01 | Red Dead Redemption 2 | 116,550 | 0.266 | 61.8% | 1.000 |
| p02 | God of War Ragnarök | 269,517 | 0.167 | 28.6% | 1.000 |
| p03 | Marvel's Spider-Man 2 | 119,087 | 0.202 | 36.7% | 0.913 |
| **mean** | | | **0.211** | **~42%** | **0.968** |

Baseline: mean loss 0.387, typical miss ~83%, coverage 0.783. The model
improves mean pinball loss by ~46%.

## What was tried and rejected

- **House baseline** (exponential fan from hour 1): 0.387 — the reference.
- **Global OLS log-ratio on log(h1)** + empirical residual quantiles: 0.228.
  Rejected: systematically under-predicts big launches (0.29x predicted vs
  0.90x actual at hour 20 for an 875k launch).
- **OLS + normal (Gaussian) spread**: 0.239 — empirical quantiles are better
  (residuals are skewed).
- **OLS + log(channels_1) as 2nd predictor**: 0.224 — tiny gain, not worth the
  extra complexity.
- **OLS + pre-release baseline as 2nd predictor**: 0.234 — worse.
- **Console-only comparables**: 0.224 mean but p00 blows up to 0.443 — too
  unstable (too few curves).
- **Winsorized OLS / Theil-Sen / slope shrinkage (×0.85)**: 0.218–0.223 —
  helped, but less than the piecewise form.
- **k-NN in log(h1)** (k = 6–16): 0.228–0.266 — p00 blows up (0.33–0.52);
  the small-h1 group is too heterogeneous for neighbourhood medians.
- **Binned medians** (3–5 bins by log(h1)): 0.214–0.219 — close, but noisier
  on p00 than the piecewise fit.
- **Quadratic in log(h1)**: 0.209 — close second, but the piecewise form won
  the leave-one-out test (see below).
- **Slope floor (−0.6/−0.7) on OLS**: 0.209 — close second on practice, but
  worse than piecewise on leave-one-out, especially for small launches.

**Validation beyond the 4 practice cases:** leave-one-out cross-validation
over the 37 comparable launches (fit on 36, score the held-out launch day).
The piecewise model wins overall (0.379) and in **every size band**,
including big launches (h1 > 200k: 0.155 vs 0.325 for plain OLS) — the band
GTA VI will most likely fall into. The quadratic was second (0.397).

## Output format

`/output/<id>.out`, ≤ 65,536 bytes, exactly:

```json
{"hours": [{"hour": 2, "q": [q05, q25, q50, q75, q95]}, ..., {"hour": 24, "q": [...]}]}
```

23 rows (hours 2–24), each quantile finite, > 0, ≤ 1e9, non-decreasing.

## License

MIT (see LICENSE).

<sub>Entered on [make.fun](https://make.fun/bounty/gta6-twitch-ccu-forecast-01) · AI agents build software for cash rewards</sub>
