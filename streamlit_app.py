import base64, json, hmac, hashlib, time
import streamlit as st

st.set_page_config(page_title="Mini Clicker", page_icon="🖱️", layout="centered")

# Читаем секреты из Streamlit (Settings → Secrets)
BOT_USERNAME = st.secrets.get("put_in_coin_bot")  # например: put_in_coin_bot (без @)
BOT_TOKEN    = st.secrets.get("8344313198:AAHRR7gjXU7KDlg5ZzMyATMxvp2bHr1pT9k")              # для валидации initData (опционально)

# --- JS: подключаем Telegram WebApp SDK + ищем API в window / parent / top (из-за iframe) ---
js_bootstrap = """
<script>
(function(){
  // 1) Подключаем официальный SDK, если его ещё нет
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
      console.log("Telegram WebApp API не найден");
      return;
    }

    try {
      if (typeof W.ready === "function") W.ready();

      const url = new URL(window.location.href);

      // Кладём данные пользователя
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

      // Кладём сырое initData (для серверной валидации)
      if (!url.searchParams.get("tg_init") && W.initData) {
        url.searchParams.set("tg_init", W.initData);
      }

      // Обновляем URL один раз, чтобы Streamlit увидел параметры
      if (!sessionStorage.getItem("miniapp_init_done")) {
        sessionStorage.setItem("miniapp_init_done", "1");
        history.replaceState(null, "", url.toString());
        location.reload();
      }
    } catch (e) {
      console.log("MiniApp bootstrap error:", e);
    }
  }
  init();
})();
</script>
"""
st.components.v1.html(js_bootstrap, height=0)

# --- Читаем query-параметры, которые заполнил JS ---
params = st.experimental_get_query_params()
user_b64 = (params.get("tg_user_b64") or [None])[0]
tg_init  = (params.get("tg_init") or [None])[0]

def parse_user():
  if not user_b64:
    return None
  try:
    return json.loads(base64.b64decode(user_b64).decode("utf-8"))
  except Exception:
    return None

def validate_init_data(init_data: str) -> bool:
  if not (init_data and BOT_TOKEN):
    return False
  try:
    items = sorted([kv for kv in init_data.split("&") if not kv.startswith("hash=")])
    data_check_string = "\n".join(items)
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    h = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    supplied_hash = dict([kv.split("=",1) for kv in init_data.split("&")]).get("hash", "")
    return h == supplied_hash
  except Exception:
    return False

tg_user = parse_user()
is_valid = validate_init_data(tg_init)

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

# Состояние кликера
if "score" not in st.session_state: st.session_state.score = 0
colA, colB = st.columns(2)
with colA:
  if st.button("Клик!"): st.session_state.score += 1
with colB:
  if st.button("Сброс"): st.session_state.score = 0
st.metric("Счёт", st.session_state.score)

# Отправка результата в Telegram (ищем API где угодно)
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
