"""Canlı korner modeli testi (live_events.py verisiyle).
Kalan süredeki korner ~ Poisson( kalan_pay * [(1-w)*maç_öncesi_beklenti + w*maç_içi_tempo] * skor_durumu * kırmızı_kart ).
Maç öncesi beklenti: takımların bu maçtan ÖNCEKİ maçlardaki korner ortalamaları (lig ortalamasına çekilmiş).
Parametreler 2023-25 maçlarıyla öğrenilir, 2025-26 ve sonrasında denenir (ileriye dönük).
Seçim kuralı canlı goldeki gibi: %70–88 arası olasılık, maç başına en olası tek seçim.
Kullanım: python -I backtest/live_corner_test.py <events.pkl>"""
import sys, pickle, math, collections
import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

R = pickle.load(open(sys.argv[1], "rb"))
R.sort(key=lambda m: m["date"])
SPLIT = "2025-08-01"
MINS = (30, 45, 60, 75)

# ---- maç öncesi beklenti (yalnızca geçmiş maçlar) ----
team = collections.defaultdict(lambda: [0.0, 0.0, 0.0])  # üstel ağırlıklı: kazanılan, verilen, ağırlık
lgs = collections.defaultdict(lambda: [0.0, 0.0, 0])      # lig: ev korner, dep korner, maç
DECAY, K0 = 0.97, 6.0
for m in R:
    L = lgs[m["lg"]]
    if L[2] >= 30:
        lh, la = L[0] / L[2], L[1] / L[2]
    else:
        lh, la = 5.4, 4.4
    def est(t, base_for, base_against):
        f, a, w = team[(m["lg"], t)]
        sh = w / (w + K0)
        return (sh * f / w + (1 - sh) * base_for if w else base_for), (sh * a / w + (1 - sh) * base_against if w else base_against)
    hf, ha = est(m["home"], (lh + la) / 2, (lh + la) / 2)
    af, aa = est(m["away"], (lh + la) / 2, (lh + la) / 2)
    avg = (lh + la) / 2
    m["Eh"] = lh * (hf / avg) * (aa / avg); m["Ea"] = la * (af / avg) * (ha / avg)
    m["Lh"], m["La"] = lh, la
    for t, cf_, ca_ in ((m["home"], m["ch"], m["ca"]), (m["away"], m["ca"], m["ch"])):
        s = team[(m["lg"], t)]
        s[0] = s[0] * DECAY + cf_; s[1] = s[1] * DECAY + ca_; s[2] = s[2] * DECAY + 1
    L[0] += m["ch"]; L[1] += m["ca"]; L[2] += 1


def snap(m, t):
    ch = sum(1 for mn, s in m["corners"] if mn <= t and s == "h"); ca = sum(1 for mn, s in m["corners"] if mn <= t and s == "a")
    gh = sum(1 for mn, s in m["goals"] if mn <= t and s == "h"); ga = sum(1 for mn, s in m["goals"] if mn <= t and s == "a")
    rh = sum(1 for mn, s in m["reds"] if mn <= t and s == "h"); ra = sum(1 for mn, s in m["reds"] if mn <= t and s == "a")
    return ch, ca, gh - ga, rh, ra


S = []  # (maç, dakika, durum, kalan ev, kalan dep)
for m in R:
    for t in MINS:
        ch, ca, d, rh, ra = snap(m, t)
        S.append((m, t, ch, ca, d, rh, ra, m["ch"] - ch, m["ca"] - ca))
train = [s for s in S if s[0]["date"] < SPLIT]; test = [s for s in S if s[0]["date"] >= SPLIT]


def arr(X):
    t = np.array([s[1] for s in X], float)
    return dict(t=t, ch=np.array([s[2] for s in X], float), ca=np.array([s[3] for s in X], float),
                d=np.array([s[4] for s in X], float), rh=np.array([s[5] for s in X], float), ra=np.array([s[6] for s in X], float),
                yh=np.array([s[7] for s in X], float), ya=np.array([s[8] for s in X], float),
                Eh=np.array([s[0]["Eh"] for s in X]), Ea=np.array([s[0]["Ea"] for s in X]),
                Lh=np.array([s[0]["Lh"] for s in X]), La=np.array([s[0]["La"] for s in X]))


def mus(x, A, kind):
    rem = np.clip((90 - A["t"]) / 90, 0, 1) * x[0]
    if kind == "lig":
        return rem * A["Lh"], rem * A["La"]
    w = x[1] * A["t"] / 90
    ph, pa = A["ch"] / (A["t"] / 90), A["ca"] / (A["t"] / 90)
    bh = (1 - w) * A["Eh"] + w * ph; ba = (1 - w) * A["Ea"] + w * pa
    dh = np.clip(A["d"], -2, 2)
    sh = np.exp(x[2] * np.clip(-dh, 0, 2) + x[3] * np.clip(dh, 0, 2))   # geride / önde
    sa = np.exp(x[2] * np.clip(dh, 0, 2) + x[3] * np.clip(-dh, 0, 2))
    redh = np.exp(x[4] * A["rh"] + x[5] * A["ra"]); reda = np.exp(x[4] * A["ra"] + x[5] * A["rh"])
    return rem * bh * sh * redh, rem * ba * sa * reda


def nll(x, A, kind):
    mh, ma = mus(x, A, kind); mh = np.maximum(mh, 1e-6); ma = np.maximum(ma, 1e-6)
    return float(np.sum(mh - A["yh"] * np.log(mh)) + np.sum(ma - A["ya"] * np.log(ma)))


TR, TE = arr(train), arr(test)
fits = {}
for kind, x0 in (("lig", [1.0]), ("model", [1.0, 0.4, 0.1, -0.1, -0.2, 0.2])):
    r = minimize(nll, x0, args=(TR, kind), method="Nelder-Mead", options={"maxiter": 4000, "xatol": 1e-4, "fatol": 1e-4})
    fits[kind] = r.x
print(f"Doğrulanmış maç {len(R)} (öğrenme {len({id(s[0]) for s in train})}, test {len({id(s[0]) for s in test})}), "
      f"ligler {dict(collections.Counter(m['lg'] for m in R))}")
x = fits["model"]
print(f"Model: zaman payı {x[0]:.3f}, tempo ağırlığı (90'da) {x[1]:.2f}, geride {math.exp(x[2]):.2f}x, önde {math.exp(x[3]):.2f}x, "
      f"kendi kırmızısı {math.exp(x[4]):.2f}x, rakip kırmızısı {math.exp(x[5]):.2f}x")
for kind in fits:
    print(f"  test log-kayıp/anlık ({kind}): {nll(fits[kind], TE, kind) / len(test):.4f}")


def picks(mt, cur):
    """Toplam korner çizgileri: mevcut+0,5 ... mevcut+6,5; %70–88 arası en olası seçim."""
    best = None
    for k in range(0, 7):
        line = cur + k + 0.5; need = k + 1   # üst: kalan korner ≥ need
        po = 1 - poisson.cdf(need - 1, mt)
        for lab, pr in ((f"{line:.1f} Üst", po), (f"{line:.1f} Alt", 1 - po)):
            if 0.70 <= pr <= 0.88 and (best is None or pr > best[1]):
                best = (lab, pr, line)
    return best


print("\nTEST (2025-26+), seçim: en olası korner alt/üst, %70–88")
for kind in ("lig", "model"):
    mh, ma = mus(fits[kind], TE, kind)
    by = collections.defaultdict(lambda: [0, 0, 0.0]); cal = collections.defaultdict(lambda: [0, 0, 0.0])
    for i, s in enumerate(test):
        cur = s[2] + s[3]; mt = mh[i] + ma[i]
        p = picks(mt, cur)
        if not p: continue
        fin = s[0]["ch"] + s[0]["ca"]
        w = fin > p[2] if "Üst" in p[0] else fin < p[2]
        for key in (s[1], "TOPLAM", "Üst" if "Üst" in p[0] else "Alt"):
            c = by[key]; c[0] += 1; c[1] += w; c[2] += p[1]
        # genel kalibrasyon: mevcut+1,5 üst
        po = 1 - poisson.cdf(1, mt); b = min(int(po * 10) / 10, .9)
        c = cal[b]; c[0] += 1; c[1] += (fin - cur) >= 2; c[2] += po
    print(f" {kind}:")
    for key in list(MINS) + ["Üst", "Alt", "TOPLAM"]:
        c = by.get(key)
        if c and c[0]:
            name = f"{key}. dakika" if isinstance(key, int) else key
            print(f"   {name:10s} {c[1]:5d} / {c[0]:5d}  %{100*c[1]/c[0]:.1f}  (beklenen %{100*c[2]/c[0]:.1f})")
    print("   kalibrasyon (en az 2 korner daha):", "  ".join(f"%{int(b*100)}+: {100*c[1]/c[0]:.0f}/{100*c[2]/c[0]:.0f}" for b, c in sorted(cal.items()) if c[0] >= 100))
