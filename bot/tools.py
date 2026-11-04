"""Kupon araçları: /sistem (sistem kupon hesabı), /kuponyap (hedef orana göre kupon önerisi) ve maç önü kısa yorum."""
import itertools, math, re
import core, extra
from core import e, nm, pct, odds_fmt, ko_local

SYS_HELP = ("🧮 <b>Sistem kupon hesabı</b>\n"
            "İlk satıra sistemi, altına maçları yaz (takım, seçim, oran):\n"
            "<code>/sistem 3/5\ngalatasaray 1 1.85\nbarcelona 1 2.5 üst 2.40\narsenal kg 1.70\nmilan 2.5 alt 1.90\nlakers 2 1.95</code>\n"
            "Sistemi yazmazsan tüm sistemler karşılaştırılır. Her kupona 1 birim yatırıldığı varsayılır.\n"
            "Bot her maçın olasılığını bulur; kaç maç tutarsa ne kadar alacağını, kâr ihtimalini ve beklenen getiriyi hesaplar.")


def _legs(data, basket, lines):
    legs, errs, seen = [], [], set()
    for raw in lines[:10]:
        pl = extra.parse_line(raw)
        if not pl or not pl["odds"]:
            errs.append(f"❓ <i>{e(raw)}</i> — seçim ya da oran anlaşılamadı"); continue
        m, kind = extra.find_match(data, basket, pl["team"])
        if not m:
            errs.append(f"❓ <i>{e(raw)}</i> — maç bulunamadı"); continue
        pr, lbl = extra.sel_prob(m, kind, pl["sel"])
        if pr is None:
            errs.append(f"❓ <i>{e(raw)}</i> — {e(lbl)}"); continue
        dup = m["id"] in seen; seen.add(m["id"])
        legs.append(dict(title=f"{nm(m['home'])} – {nm(m['away'])}", sel=lbl, p=pr, odds=pl["odds"], dup=dup))
    return legs, errs


def system_table(ps, odds, k):
    """k/n sistem: [(tutan sayısı, olasılık, geri dönen)], kupon sayısı, beklenen getiri, kâr olasılığı."""
    n = len(ps); combos = list(itertools.combinations(range(n), k)); stake = len(combos)
    dist = {}
    for outcome in itertools.product((0, 1), repeat=n):
        pr = 1.0
        for i, w in enumerate(outcome):
            pr *= ps[i] if w else 1 - ps[i]
        ret = sum(math.prod(odds[i] for i in c) for c in combos if all(outcome[i] for i in c))
        w = sum(outcome); d = dist.setdefault(w, [0.0, 0.0]); d[0] += pr; d[1] += pr * ret
    rows = [(w, d[0], d[1] / d[0] if d[0] else 0.0) for w, d in sorted(dist.items())]
    ev = sum(p * r for _, p, r in rows) / stake - 1
    pprofit = sum(p for _, p, r in rows if r > stake)
    return rows, stake, ev, pprofit


def system_message(data, basket, arg):
    lines = [l.strip() for l in (arg or "").strip().splitlines() if l.strip()]
    if not lines:
        return SYS_HELP
    k = None
    m = re.match(r"^(\d+)\s*/\s*(\d+)$", lines[0])
    if m:
        k = int(m.group(1)); lines = lines[1:]
    legs, errs = _legs(data, basket, lines)
    out = ["🧮 <b>Sistem kupon hesabı</b>"]
    if errs:
        out += errs
    n = len(legs)
    if n < 3:
        return "\n".join(out + ["\nEn az 3 maç gerekli (en fazla 10)."]) if errs else SYS_HELP
    if k is not None and not (2 <= k < n):
        return "\n".join(out + [f"\n{k}/{n} sistem olmaz: 2 ile {n - 1} arası seç."])
    for g in legs:
        ev = g["p"] * g["odds"] - 1
        out.append(f"• {e(g['title'])} · {e(g['sel'])} @ {odds_fmt(g['odds'])} · olasılık {pct(g['p'])} "
                   + ("✅" if ev > 0.03 else ("➖" if ev >= -0.03 else "❌")))
    if any(g["dup"] for g in legs):
        out.append("⚠️ Aynı maç iki kez var; seçimler birbirine bağlı olduğu için hesap yanıltıcı olur.")
    ps = [g["p"] for g in legs]; od = [g["odds"] for g in legs]
    ks = [k] if k else list(range(2, n))
    if len(ks) > 1:
        out.append("\n<b>Sistemlerin karşılaştırması</b> (her kupona 1 birim)")
        for kk in ks:
            rows, stake, ev, pp = system_table(ps, od, kk)
            out.append(f"{kk}/{n}: {stake} kupon · kâr ihtimali {pct(pp)} · beklenen getiri {'+' if ev >= 0 else ''}{round(ev * 100)}%")
        out.append("\nAyrıntı için ilk satıra sistemi yaz, ör. <code>/sistem 3/%d</code>" % n)
    else:
        rows, stake, ev, pp = system_table(ps, od, k)
        out.append(f"\n<b>{k}/{n} sistem</b>: {stake} kupon, toplam {stake} birim")
        for w, p_, r in rows:
            if w < k:
                continue
            out.append(f"{w} tutarsa ({pct(p_)}): {_n(r)} birim geri → {'+' if r - stake >= 0 else ''}{_n(r - stake)}")
        lose = sum(p_ for w, p_, _ in rows if w < k)
        out.append(f"{k}'ten az tutarsa ({pct(lose)}): hepsi kaybedilir → -{stake}")
        out.append(f"\n<b>Kâr ihtimali {pct(pp)}</b> · beklenen getiri {'+' if ev >= 0 else ''}{round(ev * 100)}%")
    out.append("<i>Sistem kupon kazanma şansını artırmaz, riski dağıtır. Oranlar botun olasılığına göre düşükse "
               "beklenen getiri negatiftir.</i>")
    return "\n".join(out)


def _n(x):
    return f"{x:.1f}".replace(".", ",")


# ---------- kupon kurucu ----------
BUILD_HELP = ("🧩 <b>Kupon kurucu</b>\n"
              "Hedef toplam oranı yaz, bot günün test edilmiş seçimlerinden en az maçla o orana ulaşan kuponu önerir:\n"
              "<code>/kuponyap 3</code> · <code>/kuponyap 2.5</code>\n"
              "Toplam oran yükseldikçe tutma ihtimali düşer: 3,00 oranlı bir kupon ancak ~3'te 1 tutar.")


def _cands(data, day):
    """Günün test edilmiş seçimleri, maç başına en olası olanı: (maç, etiket, olasılık, kaynak)."""
    best = {}
    for m in core.day_matches(data, day):
        opts = []
        g = core.grade(m)
        if g and g["tier"] >= 2:
            opts.append((g["label"], g["prob"], {3: "Güçlü", 2: "Orta"}[g["tier"]]))
        x = core.extra_pick(m)
        if x:
            opts.append((x["label"], x["prob"], "Ek"))
        r = core.risky_pick(m)
        if r:
            opts.append((r["label"], r["prob"], "Riskli"))
        for lab, p, src in opts:
            if m["id"] not in best or p > best[m["id"]][2]:
                best[m["id"]] = (m, lab, p, src)
    return list(best.values())


def build_message(data, day, arg):
    try:
        target = float((arg or "").strip().replace(",", "."))
    except ValueError:
        return BUILD_HELP
    if not 1.3 <= target <= 30:
        return BUILD_HELP + "\n\nHedef oran 1,30 ile 30 arasında olmalı."
    cs = sorted(_cands(data, day), key=lambda c: -c[2])[:24]
    best = None
    for n in range(1, 5):  # en az maç: her maç büro payını katlar
        for combo in itertools.combinations(cs, n):
            fo = math.prod(1 / c[2] for c in combo)  # adil toplam oran
            if fo < target or fo > target * 1.35:
                continue
            tested = sum(1 for c in combo if c[3] in ("Güçlü", "Orta"))
            key = (n, -tested, fo)
            if best is None or key < best[0]:
                best = (key, combo, fo)
        if best:
            break
    if not best:
        return f"🧩 Bugün kalan maçlarla adil toplam oranı {odds_fmt(target)} civarında olan bir kupon kurulamadı. Başka bir hedef dene."
    _, combo, fo = best
    p = math.prod(c[2] for c in combo)
    out = [f"🧩 <b>Kupon önerisi · hedef oran {odds_fmt(target)}</b>"]
    for m, lab, pr, src in sorted(combo, key=lambda c: c[0]["ko"]):
        out.append(f"{ko_local(m).strftime('%H:%M')} · <b>{e(nm(m['home']))} – {e(nm(m['away']))}</b> <i>({e(m['lgName'])})</i>\n"
                   f"   👉 {e(lab.upper())} · %{round(pr * 100)} · iddaa en az {odds_fmt(1.03 / pr)} · {src}")
    out.append(f"\n<b>Kuponun tutma ihtimali {pct(p)}</b> (yaklaşık {max(1, round(1 / p))} kuponda 1)")
    out.append(f"Değmesi için iddaa'da toplam oran en az <b>{odds_fmt(1.03 ** len(combo) * fo)}</b> olmalı.")
    out.append("<i>Aynı toplam oranlı her kuponun tutma ihtimali yaklaşık aynıdır; fark, maç sayısı azaldıkça büro payının azalmasıdır. "
               "Bu yüzden en az maçlı kupon seçildi.</i>")
    return "\n".join(out)


# ---------- maç önü kısa yorum ----------
def comment(m):
    """2–3 cümlelik özet: favori, gol beklentisi, ilk yarı."""
    p = m["p"]; h, a = nm(m["home"]), nm(m["away"])
    s = []
    fav, pf = ("1", p["1"]) if p["1"] >= p["2"] else ("2", p["2"])
    who = h if fav == "1" else a; where = "evinde" if fav == "1" else "deplasmanda"
    if pf >= 0.70:
        s.append(f"{who} {where} açık favori (%{round(pf * 100)}).")
    elif pf >= 0.50:
        s.append(f"{who} {where} favori (%{round(pf * 100)}), ama beraberlik ihtimali %{round(p['X'] * 100)}.")
    else:
        s.append(f"Dengeli maç: {h} %{round(p['1'] * 100)}, beraberlik %{round(p['X'] * 100)}, {a} %{round(p['2'] * 100)}.")
    lam = m.get("lam") or [None, None]
    if lam[0] is not None:
        tot = lam[0] + lam[1]
        level = "yüksek" if tot >= 3.0 else ("orta" if tot >= 2.4 else "düşük")
        s.append(f"Gol beklentisi {level} (toplam {tot:.1f}".replace(".", ",") + f"): 2,5 Üst %{round(p['O25'] * 100)}, KG Var %{round(p['BTTS'] * 100)}.")
    if "HTO05" in p:
        s.append(f"İlk yarının golsüz geçme ihtimali %{round((1 - p['HTO05']) * 100)}.")
    if m.get("src") != "piyasa":
        s.append("Piyasa oranı yok; tahmin yalnızca modelden, düşük güven.")
    return " ".join(s)
