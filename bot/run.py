"""GitHub Actions giriş noktası.

  python bot/run.py daily     # sabah: tarama + dünün karnesi + günün önerileri
  python bot/run.py live      # canlı döngü: 5 dakikada bir kontrol, maç kalmayınca biter
  python bot/run.py commands  # bekleyen bot komutlarını cevaplar

Ortam değişkenleri:
  TELEGRAM_TOKEN   (secret)  bot token'ı
  TELEGRAM_CHAT_ID (isteğe bağlı) virgülle ayrılmış ek alıcılar, örn. bir kanal: @kanaladi
  SITE_URL         (isteğe bağlı) GitHub Pages adresi
  SITE_DIR         gh-pages çalışma kopyası (varsayılan ./site-out)
  STATE_DIR        bot durumu (abone listesi vb., Actions önbelleğinde tutulur; varsayılan ./state)
  FD_DIR           football-data önbelleği (varsayılan ./fd)
"""
import json, os, subprocess, sys, time, traceback
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "engine"), os.path.join(ROOT, "bot")]
import tg, core, extra, visual  # noqa: E402

SITE = os.environ.get("SITE_DIR", os.path.join(ROOT, "site-out"))
STATE_DIR = os.environ.get("STATE_DIR", os.path.join(ROOT, "state"))
FD = os.environ.get("FD_DIR", os.path.join(ROOT, "fd"))
SUBS_FILE = os.path.join(STATE_DIR, "subs", "subs.json")   # yalnızca komut işi yazar
RUN_FILE = os.path.join(STATE_DIR, "run", "run.json")      # sabah ve canlı işleri yazar
CMD_SECONDS = int(os.environ.get("CMD_SECONDS", "560"))
EXTRA = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]
LOOP_EVERY = int(os.environ.get("LIVE_EVERY_SEC", "300"))
MAX_LOOP = int(os.environ.get("LIVE_MAX_SEC", str(5 * 3600 + 40 * 60)))


# ---------- durum ----------
def _load(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default


def _save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"; json.dump(obj, open(tmp, "w")); os.replace(tmp, path)


def load_state():
    """Abone listesi (salt okunur kopya) + bu işin kendi durumu."""
    st = _load(RUN_FILE, {"sent": {}, "moves": {}})
    st.setdefault("sent", {}); st.setdefault("moves", {})
    st["subs"] = _load(SUBS_FILE, {}).get("subs", {})
    return st


def save_state(st):
    _save(RUN_FILE, {k: v for k, v in st.items() if k != "subs"})


def recipients(st):
    return [c for c, v in st["subs"].items() if v.get("on", True)] + EXTRA


def broadcast(st, text, silent=False):
    for c in recipients(st):
        tg.send(c, text, silent=silent)


def broadcast_photos(st, pngs, caption=None, silent=False):
    for c in recipients(st):
        tg.send_album(c, pngs, caption=caption, silent=silent)


def imgs_or(fn, *a):
    """Görsel üretir; hata olursa boş liste döner (o zaman yazılı mesaj gider)."""
    try:
        return fn(*a) or []
    except Exception:
        traceback.print_exc(); return []


def reply(chat, pngs, text, caption=None):
    if pngs and tg.send_album(chat, pngs, caption=caption):
        return
    tg.send(chat, text)


def broadcast_rich(st, pngs, text, caption=None, silent=False):
    if pngs:
        broadcast_photos(st, pngs, caption=caption, silent=silent)
    elif text:
        broadcast(st, text, silent=silent)


def jload(name, default=None):
    try:
        return json.load(open(os.path.join(SITE, name)))
    except Exception:
        return default


def now_ist():
    return datetime.now(core.IST)


# ---------- site (gh-pages) ----------
SITE_FILES_DAILY = ["index.html", "backtest.json", ".nojekyll", "config.json", "data.json", "history.json", "basket.json"]


def publish(msg, files):
    """Yalnızca bu işin dosyalarını gh-pages'in en güncel hâlinin üstüne yazar (diğer işin dosyaları korunur).
    Dal her zaman tek commit'tir; geçmiş birikmez."""
    if not os.path.isdir(os.path.join(SITE, ".git")):
        print("SITE_DIR bir git kopyası değil; yayın atlandı."); return
    g = lambda *a: subprocess.run(["git", "-C", SITE, *a], check=False, capture_output=True, text=True)
    mine = {}
    for f in files:
        p = os.path.join(SITE, f)
        if os.path.exists(p):
            mine[f] = open(p, "rb").read()
    for attempt in range(4):
        base = None
        if g("fetch", "-q", "--depth", "1", "origin", "gh-pages").returncode == 0:
            base = g("rev-parse", "FETCH_HEAD").stdout.strip()
            g("reset", "-q", "--hard", "FETCH_HEAD")
        for f, b in mine.items():
            open(os.path.join(SITE, f), "wb").write(b)
        g("checkout", "-q", "--orphan", "tmp-publish"); g("add", "-A")
        c = g("-c", "user.name=skor-bot", "-c", "user.email=skor-bot@users.noreply.github.com", "commit", "-q", "-m", msg)
        if c.returncode != 0 and "nothing to commit" in (c.stdout + c.stderr):
            g("checkout", "-q", "-f", "gh-pages"); g("branch", "-D", "tmp-publish"); return
        lease = f"--force-with-lease=gh-pages:{base}" if base else "--force"
        p = g("push", "-q", lease, "origin", "HEAD:gh-pages")
        g("branch", "-D", "gh-pages"); g("branch", "-m", "gh-pages")
        if p.returncode == 0:
            print("yayın:", msg, "ok"); return
        print("yayın çakıştı, tekrar deneniyor:", p.stderr[-200:]); time.sleep(3 + attempt * 3)
    print("yayın başarısız:", msg)


# ---------- tarama ----------
def scan():
    import scan as S
    S.main(FD, os.path.join(SITE, "data.json"), prev=os.path.join(SITE, "data.json"),
           histpath=os.path.join(SITE, "history.json"))


# ---------- komutlar ----------
def handle_commands(st, wait=0):
    ups = tg.updates(st.get("offset", 0), wait)
    if not ups:
        return False
    data = jload("data.json", {"matches": []}); hist = jload("history.json", {"matches": []}); basket = jload("basket.json", {})
    for u in ups:
        st["offset"] = u["update_id"] + 1
        msg = u.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id", "")); text = (msg.get("text") or "").strip()
        if not chat or not text.startswith("/"):
            continue
        parts = text.split(None, 1); cmd = parts[0].split("@")[0].lower(); arg = parts[1] if len(parts) > 1 else ""
        today = now_ist().date()
        try:
            if cmd == "/start":
                st["subs"][chat] = {"on": True, "since": datetime.now(timezone.utc).isoformat()}
                tg.send(chat, "✅ Bildirimler açıldı.\n\n" + core.HELP)
            elif cmd in ("/dur", "/stop"):
                st["subs"].setdefault(chat, {})["on"] = False
                tg.send(chat, "🔕 Bildirimler kapatıldı. Tekrar açmak için /start.")
            elif cmd in ("/nasil", "/nasıl"):
                tg.send(chat, visual.how_to())
            elif cmd == "/secimler":
                reply(chat, imgs_or(visual.daily_images, data, basket, today),
                      visual.daily_text(data, basket, today), caption=visual.how_to())
            elif cmd == "/bugun":
                reply(chat, imgs_or(visual.all_matches_images, data, basket, today), core.all_matches_message(data, today),
                      caption="Bugünün tüm maçları. Ayrıntı için /mac takım")
            elif cmd == "/guclu":
                reply(chat, imgs_or(visual.daily_images, {"matches": [m for m in data["matches"] if (core.grade(m) or {}).get("tier") == 3]}, {}, today),
                      core.tier_list_message(data, today, 3))
            elif cmd == "/orta":
                reply(chat, imgs_or(visual.daily_images, {"matches": [m for m in data["matches"] if (core.grade(m) or {}).get("tier") == 2]}, {}, today),
                      core.tier_list_message(data, today, 2))
            elif cmd == "/canli":
                lv = jload("live.json")
                imgs = imgs_or(visual.live_list_images, lv)
                if imgs: tg.send_album(chat, imgs)
                else: tg.send(chat, core.live_list_message(lv))
            elif cmd == "/mac":
                if not arg.strip():
                    tg.send(chat, "Kullanım: /mac galatasaray")
                else:
                    png = imgs_or(lambda: [visual.match_image(data, arg.strip())] if visual.match_image(data, arg.strip()) else [])
                    r = core.match_message(data, arg.strip())
                    if png:
                        tg.send_photo(chat, png[0])
                    else:
                        bimg = imgs_or(visual.basket_match_images, basket, arg.strip())
                        if bimg:
                            tg.send_album(chat, bimg)
                        else:
                            if "bulunamadı" in r:
                                r = extra.basket_match(basket, arg.strip()) or r
                            tg.send(chat, r)
            elif cmd == "/basket":
                reply(chat, imgs_or(visual.all_matches_images, {"matches": []}, basket, today), extra.basket_message(basket))
            elif cmd == "/kupon":
                if not arg.strip():
                    tg.send(chat, extra.COUPON_HELP)
                else:
                    reply(chat, imgs_or(visual.coupon_images, data, basket, arg), extra.coupon_message(data, basket, arg))
            elif cmd == "/karne":
                y = today - timedelta(days=1)
                reply(chat, imgs_or(visual.report_images, hist["matches"], y),
                      core.report_message(hist["matches"], y) or "Dün için sonuçlanmış öneri yok.")
            else:
                tg.send(chat, core.HELP)
        except Exception:
            traceback.print_exc()
            tg.send(chat, "Bir hata oluştu, biraz sonra tekrar dene.")
    return True


# ---------- modlar ----------
def daily():
    st = load_state(); daily_body(st); save_state(st)


def daily_body(st):
    tg.set_commands(core.COMMANDS)
    me = tg.call("getMe")
    if me.get("ok"):
        json.dump({"bot": me["result"].get("username")}, open(os.path.join(SITE, "config.json"), "w"))
    scan()
    publish("Sabah taraması", SITE_FILES_DAILY)
    today = now_ist().date()
    hist = jload("history.json", {"matches": []})
    if st["sent"].get("report") != str(today - timedelta(days=1)):
        y = today - timedelta(days=1)
        broadcast_rich(st, imgs_or(visual.report_images, hist["matches"], y), core.report_message(hist["matches"], y), silent=True)
        st["sent"]["report"] = str(today - timedelta(days=1))
    if st["sent"].get("daily") != str(today):
        data = jload("data.json"); basket = jload("basket.json", {})
        broadcast_rich(st, imgs_or(visual.daily_images, data, basket, today),
                       visual.daily_text(data, basket, today) + core.FOOTER, caption=visual.how_to())
        broadcast_rich(st, imgs_or(visual.all_matches_images, data, basket, today), "",
                       caption="Bugünün tüm maçları (futbol + basketbol). Ayrıntı için /mac takım", silent=True)
        st["sent"]["daily"] = str(today)
    check_moves(st)


def check_moves(st):
    seen = st.setdefault("moves", {})
    cutoff = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    for k in [k for k, v in seen.items() if v < cutoff]:
        del seen[k]
    items = extra.move_alerts(jload("data.json", {"matches": []}), jload("basket.json", {}), seen)
    if items:
        broadcast_rich(st, imgs_or(visual.move_images, items[:10]), extra.move_message(items[:10]))


def upcoming_soon(data, minutes=25):
    now = datetime.now(timezone.utc)
    return any(now - timedelta(minutes=110) < datetime.fromisoformat(m["ko"]) < now + timedelta(minutes=minutes)
               for m in data.get("matches", []))


def live_tick(st):
    """Bir canlı kontrol: canlı analiz, uyarılar, live.json yayını. Dönüş: canlı maç sayısı."""
    import live as L
    lj = os.path.join(SITE, "live.json")
    L.main(os.path.join(SITE, "data.json"), lj, lj if os.path.exists(lj) else None)
    lv = jload("live.json", {"matches": [], "alerts": []})
    by_id = {m["id"]: m for m in lv["matches"]}
    alerts = []
    for a in lv.get("alerts", []):
        m = by_id.get(a["id"])
        pk = next((p for p in (m or {}).get("picks", []) if p["k"] == a["k"]), None)
        if m and pk: alerts.append((m, pk))
    if alerts:
        broadcast_rich(st, imgs_or(visual.live_images, alerts[:8]), core.live_alert_message(alerts[:8]))
    publish("Canlı güncelleme", ["live.json"])
    return len(lv["matches"])


def live():
    import live as L
    st = load_state(); start = time.time(); last_scan = 0
    while True:
        t0 = time.time()
        rescanned = False
        try:
            data = jload("data.json", {"matches": []})
            gen = datetime.fromisoformat(data["generated"]) if data.get("generated") else None
            if not gen or datetime.now(timezone.utc) - gen > timedelta(hours=2):
                if time.time() - last_scan > 3600:
                    scan(); last_scan = time.time(); data = jload("data.json", {"matches": []}); rescanned = True
                    check_moves(st)
            lj = os.path.join(SITE, "live.json")
            L.main(os.path.join(SITE, "data.json"), lj, lj if os.path.exists(lj) else None)
            lv = jload("live.json", {"matches": [], "alerts": []})
            by_id = {m["id"]: m for m in lv["matches"]}
            alerts = []
            for a in lv.get("alerts", []):
                m = by_id.get(a["id"])
                pk = next((p for p in (m or {}).get("picks", []) if p["k"] == a["k"]), None)
                if m and pk: alerts.append((m, pk))
            if alerts:
                broadcast_rich(st, imgs_or(visual.live_images, alerts[:8]), core.live_alert_message(alerts[:8]))
            publish("Canlı güncelleme", ["live.json"] + (SITE_FILES_DAILY if rescanned else []))
            save_state(st)
            n_live = len(lv["matches"])
        except Exception:
            traceback.print_exc(); n_live = 1
        elapsed = time.time() - start
        if (n_live == 0 and not upcoming_soon(jload("data.json", {"matches": []}))) or elapsed > MAX_LOOP:
            print(f"Döngü bitti: canlı maç {n_live}, süre {elapsed/60:.0f} dk"); break
        time.sleep(max(10, LOOP_EVERY - (time.time() - t0)))
    save_state(st)


def refresh_site():
    """Komut işinin sayfa verisi kopyasını gh-pages'ten tazeler."""
    g = lambda *a: subprocess.run(["git", "-C", SITE, *a], check=False, capture_output=True, text=True)
    if g("fetch", "-q", "--depth", "1", "origin", "gh-pages").returncode == 0:
        g("reset", "-q", "--hard", "FETCH_HEAD")


def commands():
    """~10 dakika boyunca Telegram'ı dinler; komutlara birkaç saniyede cevap verir."""
    subs = _load(SUBS_FILE, {"offset": 0, "subs": {}})
    subs.setdefault("offset", 0); subs.setdefault("subs", {})
    start = time.time(); last_refresh = start
    while time.time() - start < CMD_SECONDS:
        left = CMD_SECONDS - (time.time() - start)
        if time.time() - last_refresh > 180:
            refresh_site(); last_refresh = time.time()
        if handle_commands(subs, wait=int(max(1, min(50, left - 5)))):
            _save(SUBS_FILE, subs)
    _save(SUBS_FILE, subs)


BOT_SECONDS = int(os.environ.get("BOT_SECONDS", "3300"))
MORNING = (9, 30)


def bot():
    """Tek sürekli iş: komutları dinler, maç varken 5 dakikada bir canlı kontrol yapar, sabah taramasını
    zamanında çalıştırır, gün içinde 2 saatte bir verileri tazeler. ~55 dakika sonra biter; iş akışı
    bir sonrakini kendisi başlatır."""
    subs = _load(SUBS_FILE, {"offset": 0, "subs": {}}); subs.setdefault("offset", 0); subs.setdefault("subs", {})
    st = load_state(); st["subs"] = subs["subs"]  # yeni aboneler hemen bildirim alır
    start = time.time(); last_live = 0.0; live_active = True
    while time.time() - start < BOT_SECONDS:
        try:
            now = now_ist(); today = now.date()
            data = jload("data.json", {"matches": []})
            gen = datetime.fromisoformat(data["generated"]) if data.get("generated") else None
            if (now.hour, now.minute) >= MORNING and st["sent"].get("daily") != str(today):
                daily_body(st); save_state(st)
            elif not gen or datetime.now(timezone.utc) - gen > timedelta(hours=2):
                scan(); publish("Veri tazeleme", SITE_FILES_DAILY); check_moves(st); save_state(st)
            if time.time() - last_live >= LOOP_EVERY:
                last_live = time.time()
                if live_active or upcoming_soon(jload("data.json", {"matches": []})):
                    live_active = live_tick(st) > 0
                    save_state(st)
        except Exception:
            traceback.print_exc()
        left = BOT_SECONDS - (time.time() - start)
        wait = int(max(1, min(50, LOOP_EVERY - (time.time() - last_live), left - 5)))
        try:
            if handle_commands(subs, wait=wait):
                _save(SUBS_FILE, subs)
        except Exception:
            traceback.print_exc(); time.sleep(5)
    _save(SUBS_FILE, subs); save_state(st)
    out = os.environ.get("GITHUB_OUTPUT")
    if out and time.time() - start > 120:
        open(out, "a").write("long=1\n")


if __name__ == "__main__":
    {"daily": daily, "live": live, "commands": commands, "bot": bot}[sys.argv[1]]()
