"""Telegram Bot API yardımcıları (yalnızca standart kütüphane)."""
import json, os, time, urllib.request, urllib.parse

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}/"
LIMIT = 3900  # Telegram sınırı 4096; HTML etiketleri için pay


def call(method, **params):
    if not TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN tanımlı değil (deponun Actions secret'larına ekleyin).")
    data = urllib.parse.urlencode({k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                                   for k, v in params.items() if v is not None}).encode()
    for attempt in range(3):
        try:
            with urllib.request.urlopen(API + method, data=data, timeout=70) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = json.loads(e.read() or b"{}")
            if e.code == 429:  # hız sınırı
                time.sleep(body.get("parameters", {}).get("retry_after", 3) + 1); continue
            return body
        except Exception:
            time.sleep(2)
    return {"ok": False}


def chunks(text):
    """Uzun mesajı satır sınırlarından böler."""
    out, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > LIMIT:
            out.append(cur); cur = ""
        cur += line + "\n"
    if cur.strip():
        out.append(cur)
    return out


def send(chat_id, text, silent=False):
    """Mesaj gönderir. Kullanıcı botu engellediyse False döner."""
    ok = True
    for part in chunks(text):
        r = call("sendMessage", chat_id=chat_id, text=part, parse_mode="HTML",
                 disable_web_page_preview="true", disable_notification="true" if silent else None)
        if not r.get("ok"):
            desc = (r.get("description") or "").lower()
            print("Telegram gönderilemedi:", chat_id, r.get("description"))
            if "blocked" in desc or "chat not found" in desc or "deactivated" in desc:
                return False
            ok = False
        time.sleep(0.05)
    return ok


def updates(offset, wait=0):
    r = call("getUpdates", offset=offset, timeout=wait, allowed_updates=["message"])
    return r.get("result", []) if r.get("ok") else []


def set_commands(cmds):
    call("setMyCommands", commands=[{"command": c, "description": d} for c, d in cmds])


def send_photo(chat_id, png, caption=None, silent=False):
    """PNG gönderir (multipart/form-data)."""
    import uuid
    if not TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN tanımlı değil.")
    b = uuid.uuid4().hex
    parts = []
    def field(name, value):
        parts.append(f"--{b}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    field("chat_id", chat_id)
    if caption:
        field("caption", caption[:1000]); field("parse_mode", "HTML")
    if silent:
        field("disable_notification", "true")
    parts.append(f"--{b}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"kart.png\"\r\nContent-Type: image/png\r\n\r\n".encode() + png + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    req = urllib.request.Request(API + "sendPhoto", data=b"".join(parts), headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=70) as r:
                return json.loads(r.read()).get("ok", False)
        except urllib.error.HTTPError as e:
            body = json.loads(e.read() or b"{}")
            if e.code == 429:
                time.sleep(body.get("parameters", {}).get("retry_after", 3) + 1); continue
            print("Fotoğraf gönderilemedi:", chat_id, body.get("description")); return False
        except Exception:
            time.sleep(2)
    return False
