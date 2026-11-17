#!/usr/bin/env python3
"""GTA VI launch-day Twitch CCU forecaster (make.fun gta6-twitch-ccu-forecast-01).

Strategy
--------
Forecast Twitch viewers for the "Grand Theft Auto VI" category, hours 2-24 of
launch day, as five quantiles (5/25/50/75/95%) per hour.

The single most informative signal is the hour-1 print (p1): across the 38
comparable launches shipped with each case, the launch-day curve shape depends
massively on hour-1 scale. Small launches (h1 ~ 1k) rise up to ~100x by the
US-evening peak; huge launches (h1 ~ 900k) stay roughly flat (~0.9-1.3x).
In log-log space the relationship between log(h1) and the log-ratio
log(viewers_h / p1) is CONCAVE: steep for small h1, flattening for big h1
(a global straight line badly under-predicts big launches, e.g. it predicts
0.29x at hour 20 for an 875k launch whose actual ratio is 0.90x).

So, for each hour h = 2..24, we fit a piecewise-linear regression of the
log-ratio on log(h1) over the case's own comparables, with the knot at the
median log(h1):

    lr_h = a + b1 * x + b2 * max(0, x - x_median),   x = log(h1)

The second segment's slope is gentle (about -0.17 to -0.28), so the model
extrapolates sanely even if GTA VI's hour-1 print exceeds every comparable.

Quantiles come from the empirical distribution of the fit residuals
(5/25/75/95% quantiles around the fitted median), which captures the true
skewed, heavy-tailed uncertainty better than a normal spread.

Fallbacks: if fewer than 4 usable comparable curves exist, we fall back to
the house baseline shape (p1 * exp(z_tau * 0.15 * sqrt(h-1))).

Deterministic: pure stdlib, no network, no wall clock, no files outside the
case input directory. Same input -> byte-identical output.
"""

import json
import math
import os
import sys

TAUS = (0.05, 0.25, 0.50, 0.75, 0.95)
# House baseline z-scores, used only for the fallback path.
Z = (-1.645, -0.674, 0.0, 0.674, 1.645)
MIN_CURVES = 4


def launch_curve(comp):
    """Return the 24 hourly viewer counts of a comparable's launch day.

    The launch day is the UTC date of ``day_start``; hour 0 of that day is
    the first hour of the launch (the same convention as the case's hour-1
    print). Returns None if the day is incomplete or hour 0 is not positive.
    """
    day = comp["day_start"][:10]
    pts = {}
    for h in comp["hourly"]:
        if h["from"].startswith(day):
            try:
                pts[int(h["from"][11:13])] = h["viewers"]
            except (KeyError, ValueError):
                continue
    if len(pts) < 24 or pts.get(0, 0) <= 0:
        return None
    return [pts[h] for h in range(24)]


def comparable_curves(case):
    """List of (log_h1, [log-ratio hour 0..23]) for usable comparables."""
    curves = []
    for comp in case.get("comparables", []):
        pts = launch_curve(comp)
        if pts is None:
            continue
        h1 = pts[0]
        lr = [math.log(max(1, v) / h1) for v in pts]
        curves.append((math.log(h1), lr))
    return curves


def solve3(a, v):
    """Solve a 3x3 linear system by Gaussian elimination with pivoting."""
    m = [row[:] + [v[i]] for i, row in enumerate(a)]
    for col in range(3):
        piv = max(range(col, 3), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        d = m[col][col]
        if d == 0.0:
            return None
        for r in range(3):
            if r != col:
                f = m[r][col] / d
                for cc in range(4):
                    m[r][cc] -= f * m[col][cc]
    return [m[i][3] / m[i][i] for i in range(3)]


def quantile(sorted_vals, tau):
    """Type-7 style empirical quantile (linear interpolation)."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return sorted_vals[0]
    pos = tau * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def fit_piecewise(xs, ys):
    """Fit lr = a + b1*x + b2*max(0, x - median(x)) by least squares.

    Returns (fit_fn, residuals) or None if the system is singular.
    """
    sx = sorted(xs)
    xm = sx[len(sx) // 2]
    design = [[1.0, x, max(0.0, x - xm)] for x in xs]
    n = 3
    ata = [[sum(d[r] * d[c] for d in design) for c in range(n)] for r in range(n)]
    aty = [sum(d[r] * y for d, y in zip(design, ys)) for r in range(n)]
    coef = solve3(ata, aty)
    if coef is None:
        return None
    a, b1, b2 = coef

    def fit(x):
        return a + b1 * x + b2 * max(0.0, x - xm)

    resid = sorted(y - fit(x) for x, y in zip(xs, ys))
    return fit, resid


def forecast_case(case):
    """Return the output dict {"hours": [{"hour": h, "q": [...]} x 23]}."""
    p1 = 1
    for k in case.get("known", []):
        if k.get("hour") == 1 and k.get("viewers"):
            p1 = max(1, int(k["viewers"]))
            break
    log_p1 = math.log(p1)
    curves = comparable_curves(case)

    hours = []
    for h in range(2, 25):
        if len(curves) >= MIN_CURVES:
            xs = [c[0] for c in curves]
            ys = [c[1][h - 1] for c in curves]
            fitted = fit_piecewise(xs, ys)
        else:
            fitted = None
        if fitted is not None:
            fit, resid = fitted
            med = fit(log_p1)
            vals = [med + quantile(resid, tau) for tau in TAUS]
        else:
            # House baseline shape (fallback when too few comparables).
            vals = [z * 0.15 * math.sqrt(h - 1) for z in Z]
            vals[2] = 0.0
        q = []
        for v in vals:
            qv = p1 * math.exp(v)
            if not math.isfinite(qv):
                qv = float(p1)
            qv = min(max(qv, 1.0), 1e9)
            q.append(round(qv, 2))
        for i in range(1, 5):
            if q[i] < q[i - 1]:
                q[i] = q[i - 1]
        hours.append({"hour": h, "q": q})
    return {"hours": hours}


def main():
    input_dir = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
    output_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(output_dir, exist_ok=True)
    names = sorted(
        f for f in os.listdir(input_dir) if f.endswith(".in")
    )
    for name in names:
        with open(os.path.join(input_dir, name), "r", encoding="utf-8") as fh:
            case = json.load(fh)
        out = forecast_case(case)
        case_id = str(case.get("id") or os.path.splitext(name)[0])
        dest = os.path.join(output_dir, case_id + ".out")
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(out, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
