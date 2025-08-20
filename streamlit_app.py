import base64, json, hmac, hashlib, time
import streamlit as st

st.set_page_config(page_title="Mini Clicker", page_icon="🖱️", layout="centered")

# Секреты в Streamlit (Manage app → Settings → Secrets)
BOT_USERNAME = st.secrets.get("put_in_coin_bot")  # например: put_in_coin_bot
BOT_TOKEN    = st.secrets.get("8344313198:AAHRR7gjXU7KDlg5ZzMyATMxvp2bHr1pT9k")              # для валидации initData (опционально)

# --- 1) Сначала пробуем прочитать user прямо из query (бот его туда положил) ---
params = st.experimental_get_query_params()
user_from_bot = {
    "id": int(params["id"][0]) if "id" in params else None,
    "first_name": params.get("first_name", [None])[0],
    "last_name": params.get("last_name", [None])[0],
    "username": params.get("username", [None])[0],
    "photo_url": None,  # фото пока нет (см. примечание ниже)
}

# --- 2) Затем пробуем добрать user/initData через Telegram WebApp SDK (если доступен в WebView) ---
js_bootstrap = """
<script>
(function(){
  // Подключим официальный SDK (на случай отсутствия)
  if (!window.Telegram || !window.Telegram.WebApp) {
    var s = document.createElement('script');
    s.src = "https://telegram.org/js/telegram-web-app.js";
    document.head.appendChild(s);
  }

  let tries = 0;
  function getWebApp(){
    return (window.Telegram && window.Telegram.WebApp) ||
           (window.parent && window.parent.Telegram && window.parent.Telegram.WebApp) ||
           (window.top && window.top.Telegram && window.top.Telegram.WebApp) || null;
  }
  function init(){
    tries++;
    const W = getWebApp();
    if (!W || !W.initDataUnsafe) {
      if (tries < 100) return setTimeout(init, 100); // ждём до ~10 сек
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

# Читаем то, что дополнительно мог положить JS
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

# Выбираем источник user: JS > бот > None
tg_user = tg_user_js or (user_from_bot if user_from_bot["id"] else None)

# --- UI ---
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
            if tg_user.get("photo_url"):
                st.markdown(f'<img src="{tg_user["photo_url"]}" style="width:72px;height:72px;border-radius:50%;object-fit:cover"/>', unsafe_allow_html=True)
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

# Отправка результата боту
payload = {
    "type": "clicker_result",
    "score": st.session_state.score,
    "user_id": tg_user.get("id") if tg_user else None,
    "ts": int(time.time())
}
payload_str = json.dumps(payload).replace("'", "\\'")

send_js = f"""
<script>
(function(){{
  function getWebApp(){{
    return (window.Telegram && window.Telegram.WebApp) ||
           (window.parent && window.parent.Telegram && window.parent.Telegram.WebApp) ||
           (window.top && window.top.Telegram && window.top.Telegram.WebApp) || null;
  }}
  const send = () => {{
    const W = getWebApp();
    if (!W || !W.sendData) return alert("Откройте внутри Telegram, чтобы отправить результат.");
    W.sendData('{payload_str}');
    try {{ W.close(); }} catch(e) {{}}
  }};
  const hook = () => {{
    const btn = document.getElementById("sendToTelegramBtn");
    if (btn && !btn.__hooked) {{ btn.__hooked = true; btn.addEventListener("click", send); }}
    else setTimeout(hook, 300);
  }};
  hook();
}})();
</script>
"""
st.divider()
st.write("Готово? Отправьте результат боту:")
st.markdown('<button id="sendToTelegramBtn" style="padding:.7rem 1.2rem;border-radius:.7rem;border:1px solid #ddd;cursor:pointer;">Отправить в Telegram</button>', unsafe_allow_html=True)
st.components.v1.html(send_js, height=0)

# Примечание: аватар
# Чтобы безопасно показывать аватар, лучше получить его на стороне бота (getUserProfilePhotos + getFile),
# скачать байты и отдать с вашего бэкенда/прокси (без токена в URL). Для MVP оставили инициалы.
