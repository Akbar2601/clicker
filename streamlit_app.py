import base64, json, hmac, hashlib, time, urllib.request, urllib.parse
import streamlit as st

st.set_page_config(page_title="Mini Clicker", page_icon="🖱️", layout="centered")

# === Секреты (Streamlit: Manage app → Settings → Secrets) ===
BOT_USERNAME = st.secrets.get("put_in_coin_bots")  # напр.: put_in_coin_bot (без @)
BOT_TOKEN    = st.secrets.get("8344313198:AAHRR7gjXU7KDlg5ZzMyATMxvp2bHr1pT9k")              # обязателен для аватара и отправки результата

# ============ 1) user из query (бот добавляет ?id&first_name&last_name&username) ============
params = st.experimental_get_query_params()
user_from_bot = {
    "id": int(params["id"][0]) if "id" in params and params["id"][0].isdigit() else None,
    "first_name": params.get("first_name", [None])[0],
    "last_name":  params.get("last_name",  [None])[0],
    "username":   params.get("username",   [None])[0],
    "photo_url":  None,
}

# ============ 2) пробуем достать user через Telegram WebApp SDK (если доступен) ============
js_bootstrap = """
<script>
(function(){
  if (!window.Telegram || !window.Telegram.WebApp) {
    var s = document.createElement('script');
    s.src = "https://telegram.org/js/telegram-web-app.js";
    document.head.appendChild(s);
  }
  function getW(){
    return (window.Telegram && window.Telegram.WebApp) ||
           (window.parent && window.parent.Telegram && window.parent.Telegram.WebApp) ||
           (window.top && window.top.Telegram && window.top.Telegram.WebApp) || null;
  }
  let tries = 0;
  function init(){
    tries++;
    const W = getW();
    if (!W || !W.initDataUnsafe) {
      if (tries < 100) return setTimeout(init, 100);
      return;
    }
    try {
      if (typeof W.ready === "function") W.ready();
      const url = new URL(window.location.href);
      if (!url.searchParams.get("tg_user_b64")) {
        const u = W.initDataUnsafe.user || null;
        if (u) {
          const payload = {
            id: u.id, first_name: u.first_name || null, last_name: u.last_name || null,
            username: u.username || null, language_code: u.language_code || null,
            is_premium: u.is_premium || null, photo_url: u.photo_url || null
          };
          const enc = btoa(unescape(encodeURIComponent(JSON.stringify(payload))));
          url.searchParams.set("tg_user_b64", enc);
        }
      }
      if (!url.searchParams.get("tg_init") && W.initData) {
        url.searchParams.set("tg_init", W.initData);
      }
      if (!sessionStorage.getItem("miniapp_init_done")) {
        sessionStorage.setItem("miniapp_init_done", "1");
        history.replaceState(null, "", url.toString());
        location.reload();
      }
    } catch(e) { console.log("bootstrap error:", e); }
  }
  init();
})();
</script>
"""
st.components.v1.html(js_bootstrap, height=0)

# читаем то, что мог положить JS
params = st.experimental_get_query_params()
user_b64 = (params.get("tg_user_b64") or [None])[0]
tg_init  = (params.get("tg_init") or [None])[0]

def parse_tg_user_b64(b64):
    if not b64: return None
    try:
        return json.loads(base64.b64decode(b64).decode("utf-8"))
    except Exception:
        return None

def validate_init_data(init_data: str) -> bool:
    if not (init_data and BOT_TOKEN): return False
    try:
        items = sorted([kv for kv in init_data.split("&") if not kv.startswith("hash=")])
        data_check_string = "\n".join(items)
        secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
        h = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        supplied_hash = dict([kv.split("=",1) for kv in init_data.split("&")]).get("hash", "")
        return h == supplied_hash
    except Exception:
        return False

tg_user_js = parse_tg_user_b64(user_b64)
is_valid   = validate_init_data(tg_init)

# итоговый пользователь
tg_user = tg_user_js or (user_from_bot if user_from_bot["id"] else None)

# ============ 3) аватар через Bot API ============
def fetch_avatar_data_url(user_id: int) -> str | None:
    if not (BOT_TOKEN and user_id): 
        return None
    try:
        # 3.1 getUserProfilePhotos
        api = f"https://api.telegram.org/bot{BOT_TOKEN}/getUserProfilePhotos?user_id={user_id}&limit=1"
        with urllib.request.urlopen(api, timeout=8) as r:
            info = json.loads(r.read().decode("utf-8"))
        if not info.get("ok") or info.get("result", {}).get("total_count", 0) == 0:
            return None
        photos = info["result"]["photos"][0]
        best = max(photos, key=lambda p: p.get("file_size", 0))
        file_id = best["file_id"]

        # 3.2 getFile
        api2 = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={urllib.parse.quote(file_id)}"
        with urllib.request.urlopen(api2, timeout=8) as r2:
            finfo = json.loads(r2.read().decode("utf-8"))
        if not finfo.get("ok"):
            return None
        file_path = finfo["result"]["file_path"]

        # 3.3 download
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        with urllib.request.urlopen(file_url, timeout=12) as img:
            data = img.read()
        b64 = base64.b64encode(data).decode("ascii")
        mime = "image/jpeg"
        if file_path.lower().endswith(".png"): mime = "image/png"
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None

avatar_data_url = None
if tg_user and not tg_user.get("photo_url"):
    avatar_data_url = fetch_avatar_data_url(tg_user.get("id"))

# ============ 4) DEBUG-панель (помогает сразу понять проблему) ============
with st.sidebar:
    st.write("**Debug**")
    st.write("has_token:", bool(BOT_TOKEN))
    st.write("user_from_bot:", bool(user_from_bot["id"]))
    st.write("user_from_js:", bool(tg_user_js))
    st.write("avatar_fetched:", bool(avatar_data_url))

# ============ 5) UI ============
st.title("Mini Clicker 🖱️")
st.caption("Streamlit MiniApp для Telegram")

if not tg_user:
    st.warning("Похоже, вы открыли приложение не из Telegram. Откройте бота и нажмите кнопку «Открыть кликер».")
    if BOT_USERNAME:
        st.link_button("Открыть в Telegram", f"https://t.me/{BOT_USERNAME}")
else:
    with st.container(border=True):
        st.subheader("Ваш профиль")
        col1, col2 = st.columns([1,4], vertical_alignment="center")
        with col1:
            pic = tg_user.get("photo_url") or avatar_data_url
            if pic:
                st.markdown(f'<img src="{pic}" style="width:72px;height:72px;border-radius:50%;object-fit:cover"/>', unsafe_allow_html=True)
            else:
                initials = (tg_user.get("first_name") or "?")[:1]
                st.markdown(f'''
                  <div style="width:72px;height:72px;border-radius:50%;background:#EEE;display:flex;align-items:center;justify-content:center;font-weight:700">{initials}</div>
                ''', unsafe_allow_html=True)
        with col2:
            full_name = " ".join(filter(None, [tg_user.get("first_name"), tg_user.get("last_name")])) or "Гость"
            st.write(f"**{full_name}**")
            if tg_user.get("username"): st.write(f"@{tg_user['username']}")
            st.write(f"ID: `{tg_user.get('id')}`")
            if BOT_TOKEN:
                st.write("Проверка подписи:", "✅ корректна" if is_valid else "⚠️ не проверено")

# Кликер
if "score" not in st.session_state: st.session_state.score = 0
colA, colB = st.columns(2)
with colA:
    if st.button("Клик!"): st.session_state.score += 1
with colB:
    if st.button("Сброс"): st.session_state.score = 0
st.metric("Счёт", st.session_state.score)

# ============ 6) Отправка результата через Bot API ============
payload = {
    "type": "clicker_result",
    "score": st.session_state.score,
    "user_id": tg_user.get("id") if tg_user else None,
    "ts": int(time.time())
}
st.divider()
if st.button("Отправить результат боту"):
    if not BOT_TOKEN:
        st.error("В Secrets нет BOT_TOKEN. Задай в Settings → Secrets.")
    elif not tg_user or not tg_user.get("id"):
        st.error("Нет chat_id. Открой MiniApp из бота (кнопкой).")
    else:
        try:
            text = json.dumps(payload, ensure_ascii=False)
            api = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            data = urllib.parse.urlencode({"chat_id": tg_user["id"], "text": text}).encode("utf-8")
            with urllib.request.urlopen(urllib.request.Request(api, data=data), timeout=8) as r:
                r.read()
            st.success("✅ Отправлено сообщением боту")
        except Exception as e:
            st.error(f"Не удалось отправить: {e}")
