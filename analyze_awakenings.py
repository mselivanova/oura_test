"""What happens before night-time awakenings, based on data/ from export.py.

Usage:
    python3 analyze_awakenings.py
"""
import json
import statistics as st
from collections import Counter
from datetime import date, datetime, timedelta

from oura import ROOT

DATA_DIR = ROOT / "data"
EPOCH = 30   # seconds per sleep_phase_30_sec / movement_30_sec item
BIN = 300    # seconds per heart_rate / hrv item
MIN_AWAKE_EPOCHS = 2  # an awakening must last at least 1 minute
PHASES = {"1": "dyp", "2": "lett", "3": "REM", "4": "våken"}


def load(name):
    return json.loads((DATA_DIR / f"{name}.json").read_text())


def by_day(name):
    return {d["day"]: d for d in load(name)}


def awakenings(phases):
    """Return (start, end) epoch indices of awake runs between sleep onset and final wake-up."""
    sleep = [i for i, p in enumerate(phases) if p != "4"]
    if not sleep:
        return []
    runs, i = [], sleep[0]
    while i <= sleep[-1]:
        if phases[i] == "4":
            j = i
            while phases[j] == "4":
                j += 1
            if j - i >= MIN_AWAKE_EPOCHS:
                runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def mean(values):
    values = [v for v in values if v is not None]
    return st.mean(values) if values else None


def spearman(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    if len(pairs) < 8:
        return None, len(pairs)

    def ranks(vals):
        order = sorted(range(len(vals)), key=vals.__getitem__)
        r = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r

    rx, ry = ranks([p[0] for p in pairs]), ranks([p[1] for p in pairs])
    mx, my = st.mean(rx), st.mean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    var = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return (cov / var if var else None), len(pairs)


def night_profiles(night):
    """Per-awakening deltas of movement, HR and HRV relative to the night's calm-sleep baseline."""
    phases = night["sleep_phase_30_sec"]
    movement = [int(c) for c in night["movement_30_sec"]]
    hr, hrv = night["heart_rate"]["items"], night["hrv"]["items"]
    runs = awakenings(phases)

    # Baseline: sleep epochs at least 20 min away from any awakening.
    near = set()
    for a, b in runs:
        near.update(range(a - 40, b + 40))
    calm = [i for i, p in enumerate(phases) if p != "4" and i not in near]
    calm_bins = {i * EPOCH // BIN for i in calm}
    base = {
        "move": mean(movement[i] for i in calm if i < len(movement)),
        "hr": mean(hr[b] for b in calm_bins if b < len(hr)),
        "hrv": mean(hrv[b] for b in calm_bins if b < len(hrv)),
    }

    events = []
    for a, b in runs:
        start_bin = a * EPOCH // BIN
        ev = {
            "prev_phase": next((phases[i] for i in range(a - 1, -1, -1) if phases[i] != "4"), None),
            "hours_in": (a - next(i for i, p in enumerate(phases) if p != "4")) * EPOCH / 3600,
            "minutes": (b - a) * EPOCH / 60,
            # movement per minute, offsets -20..-1 min before the awakening
            "move": {m: mean(movement[i] - base["move"] for i in (a + 2 * m, a + 2 * m + 1)
                             if 0 <= i < len(movement)) for m in range(-20, 0)},
            # HR/HRV per 5-min bin, offsets -4..-1 bins (bin -1 = the 5 minutes before)
            "hr": {k: (hr[start_bin + k] - base["hr"]) if 0 <= start_bin + k < len(hr)
                   and hr[start_bin + k] is not None and base["hr"] else None for k in range(-4, 0)},
            "hrv": {k: (hrv[start_bin + k] - base["hrv"]) if 0 <= start_bin + k < len(hrv)
                    and hrv[start_bin + k] is not None and base["hrv"] else None for k in range(-4, 0)},
        }
        events.append(ev)
    return runs, base, events


def main():
    nights = sorted((s for s in load("sleep") if s["type"] == "long_sleep"),
                    key=lambda s: s["bedtime_start"])
    activity, readiness, stress = by_day("daily_activity"), by_day("daily_readiness"), by_day("daily_stress")
    workouts = load("workout")

    all_events, rows = [], []
    phase_time = Counter()
    for night in nights:
        runs, base, events = night_profiles(night)
        all_events += events
        phases = night["sleep_phase_30_sec"]
        phase_time.update(p for p in phases if p != "4")

        app_phases = night.get("app_sleep_phase_5_min") or night["sleep_phase_5_min"]
        prev_day = (date.fromisoformat(night["day"]) - timedelta(days=1)).isoformat()
        bedtime = datetime.fromisoformat(night["bedtime_start"])
        late_workout = sum(
            (datetime.fromisoformat(w["end_datetime"]) - datetime.fromisoformat(w["start_datetime"])).seconds / 60
            for w in workouts
            if timedelta(0) <= bedtime - datetime.fromisoformat(w["end_datetime"]) <= timedelta(hours=3)
        )
        act, rdy, strs = activity.get(prev_day, {}), readiness.get(night["day"], {}), stress.get(prev_day, {})
        rows.append({
            "day": night["day"],
            "awakenings": len(runs),
            "app_awakenings": sum(1 for _ in awakenings_5min(app_phases)),
            "awake_min": sum(b - a for a, b in runs) * EPOCH / 60,
            "Skritt i løpet av dagen": act.get("steps"),
            "Aktiv tid (min)": ((act.get("medium_activity_time") or 0) + (act.get("high_activity_time") or 0)) / 60 if act else None,
            "Trening 3 t før leggetid (min)": late_workout,
            "Leggetid (t)": bedtime.hour + bedtime.minute / 60 + (24 if bedtime.hour < 12 else 0),
            "Stress i løpet av dagen (min)": (strs.get("stress_high") or 0) / 60 if strs else None,
            "Temperaturavvik": rdy.get("temperature_deviation"),
            "Gjennomsnittspuls om natten": night.get("average_heart_rate"),
            "Laveste puls": night.get("lowest_heart_rate"),
            "Gjennomsnittlig HRV om natten": night.get("average_hrv"),
            "Pustefrekvens": night.get("average_breath"),
            "Innsovningstid (min)": (night.get("latency") or 0) / 60,
        })

    n = len(all_events)
    print(f"Netter: {len(nights)}, oppvåkninger (≥1 min): {n}, "
          f"i snitt {n / len(nights):.1f} per natt")
    print(f"Varighet på oppvåkning: median {st.median(e['minutes'] for e in all_events):.1f} min")
    print(f"Etter appens 5-minutters inndeling: i snitt "
          f"{st.mean(r['app_awakenings'] for r in rows):.1f} oppvåkninger per natt")

    print("\n== Hva skjer FØR en oppvåkning (avvik fra rolig søvn samme natt) ==")
    print("\nBevegelse (1 = ingen bevegelse … 4 = aktiv), per minutt før oppvåkning:")
    for m in range(-20, 0, 2):
        d = [e["move"][m] for e in all_events if e["move"][m] is not None]
        print(f"  {m:>4} min: {st.mean(d):+.2f}   (over normalen i {sum(x > 0 for x in d) / len(d):.0%})")
    for key, label in (("hr", "Puls, slag/min"), ("hrv", "HRV, ms")):
        print(f"\n{label}, per 5-minutters intervall før oppvåkning:")
        for k in range(-4, 0):
            d = [e[key][k] for e in all_events if e[key][k] is not None]
            if d:
                print(f"  {k * 5:>4}…{(k + 1) * 5:>3} min: {st.mean(d):+.1f}   "
                      f"(over normalen i {sum(x > 0 for x in d) / len(d):.0%}, n={len(d)})")

    print("\nSøvnfase rett før oppvåkning  vs  andel av denne fasen i all søvn:")
    prev = Counter(e["prev_phase"] for e in all_events)
    total = sum(phase_time.values())
    for p in "123":
        print(f"  {PHASES[p]:>9}: {prev[p] / n:5.0%} av oppvåkningene   vs   {phase_time[p] / total:5.0%} av søvntiden")

    print("\nNår oppvåkningene skjer (timer etter innsovning):")
    hours = Counter(int(e["hours_in"]) for e in all_events)
    for h in sorted(hours):
        print(f"  {h}–{h + 1} t: {'#' * hours[h]} {hours[h]}")

    print("\n== Netter med mange oppvåkninger: sammenheng med dag- og nattverdier ==")
    print("(Spearman-korrelasjon: fra -1 til +1; |r| < 0.3 – praktisk talt ingen sammenheng)")
    ys = [r["awakenings"] for r in rows]
    results = []
    for key in rows[0]:
        if key in ("day", "awakenings", "app_awakenings", "awake_min"):
            continue
        r, k = spearman([row[key] for row in rows], ys)
        if r is not None:
            results.append((r, key, k))
    for r, key, k in sorted(results, key=lambda x: -abs(x[0])):
        print(f"  {key:<32} r = {r:+.2f}  (n={k})")


def awakenings_5min(phases):
    """Awake runs in the 5-minute app hypnogram (any length) between sleep onset and final wake-up."""
    sleep = [i for i, p in enumerate(phases) if p != "4"]
    i = sleep[0] if sleep else 0
    while sleep and i <= sleep[-1]:
        if phases[i] == "4":
            j = i
            while phases[j] == "4":
                j += 1
            yield i, j
            i = j
        else:
            i += 1


if __name__ == "__main__":
    main()
