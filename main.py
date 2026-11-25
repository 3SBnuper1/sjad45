import asyncio, json, os, random, datetime, logging, sys, types

############################################
# ترقيع (shim) لوحدة imghdr المحذوفة من بايثون 3.13+
# pyrogram يحتاجها بالخلفية، وبدون هذا الترقيع الكود يطيح فوراً
# بخطأ ModuleNotFoundError قبل لا يوصل لأي طباعة أو تشغيل فعلي.
############################################
if "imghdr" not in sys.modules:
    try:
        import imghdr  # noqa: F401  (موجودة فعلاً - ما نحتاج الترقيع)
    except ModuleNotFoundError:
        _imghdr_shim = types.ModuleType("imghdr")

        def _what(file, h=None):
            return None

        _imghdr_shim.what = _what
        sys.modules["imghdr"] = _imghdr_shim

from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup as Markup,
    InlineKeyboardButton as IButton
)
from pyrogram.errors import (
    FloodWait,
    UserDeactivated,
    AuthKeyUnregistered,
    SessionRevoked,
    SessionPasswordNeeded,
    PhoneCodeInvalid,
    UserAlreadyParticipant,
    UserNotParticipant,
    ChatWriteForbidden,
    UserBannedInChannel,
    ChannelPrivate,
    PeerIdInvalid,
    UserKicked
)

# أخطاء تعني فعلاً إن الحساب انطرد/انحظر من المجموعة (وليس أي خطأ عابر فيه كلمة "403")
BAN_LIKE_ERRORS = (ChatWriteForbidden, UserBannedInChannel, ChannelPrivate, PeerIdInvalid, UserKicked, UserNotParticipant)

############################################
# عدّل القيم الأربعة هذي بس، وخل الباقي زي ما هو
############################################
API_ID = 9661697                                                          # رقم API_ID من my.telegram.org
API_HASH = "4ae76784fdfecd5df142004955bb8393"                            # API_HASH من my.telegram.org
BOT_TOKEN = "9277873259:AAGFetmQuOavf11wc0OVYATMnxoftpbH8A8"             # توكن البوت من @BotFather
ADMIN_ID = 5723475089                                                     # آيديك انت (المالك)
DEV = "@i999l9"                                                           # يوزرك اللي يطلع للمستخدمين كـ"راسل المطور"
############################################
DATA_FILE = "data.json"
logging.basicConfig(level=logging.WARNING)


def load():
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "accounts": {}, "groups": {}, "vip": {}, "settings": {}, "blocked": {}, "force_stopped": [], "subscribed": [], "referrals": {}}
    with open(DATA_FILE, encoding="utf-8") as f:
        d = json.load(f)
    for k, v in {"blocked": {}, "force_stopped": [], "subscribed": [], "referrals": {}}.items():
        if k not in d:
            d[k] = v
    if "ALL" in d["force_stopped"]:
        d["force_stopped"].remove("ALL")
    return d


def save():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


db = load()


def clean_ch(raw):
    if not raw: return None
    t = raw.strip()
    if t.lower() in ["الغاء", "cancel", "none", "-"]: return None
    if t.startswith("-100") and t[1:].isdigit(): return t
    t = t.replace("https://", "").replace("http://", "").replace("t.me/", "").replace("telegram.me/", "").replace("@", "").split("/")[0].split("?")[0].strip()
    if not t: return None
    if t.startswith("+") or "joinchat" in t: return "NEED_FORWARD"
    return "@" + t


def get_settings(uid):
    uid = str(uid)
    if uid not in db["settings"]:
        db["settings"][uid] = {"caption": "اهلا بكم 🔥", "captions": ["اهلا بكم 🔥"], "caption_mode": "single", "delay": 60, "delay_min": 60, "delay_max": 120, "media_enabled": False, "protect_enabled": True, "report_enabled": True, "random_enabled": False, "stealth_enabled": False, "media_file": None, "media_type": None, "forced_channel": None}
        save()
    s = db["settings"][uid]
    if "captions" not in s: s["captions"] = [s.get("caption", "اهلا بكم 🔥")]
    if "caption_mode" not in s: s["caption_mode"] = "single"
    if "stealth_enabled" not in s: s["stealth_enabled"] = False
    return s


def get_forced():
    s = db["settings"].get(str(ADMIN_ID), {}); ch = s.get("forced_channel")
    if not ch: return None
    if ch == "NEED_FORWARD": return "NEED_FORWARD"
    if str(ch).startswith("-100"): return str(ch)
    return clean_ch(ch)


def is_admin(uid): return uid == ADMIN_ID


def is_vip(uid):
    if is_admin(uid): return True
    v = db["vip"].get(str(uid))
    if not v: return False
    if v.get("expire") == "lifetime": return True
    try:
        exp = datetime.datetime.fromisoformat(v["expire"])
        if datetime.datetime.now() > exp: del db["vip"][str(uid)]; save(); return False
        return True
    except Exception: return False


def vip_left(uid):
    v = db["vip"].get(str(uid))
    if not v: return None
    if v.get("expire") == "lifetime": return "مدى الحياة"
    exp = datetime.datetime.fromisoformat(v["expire"]); left = exp - datetime.datetime.now()
    return f"{left.days} يوم - {exp.strftime('%Y-%m-%d')}"


def is_force(acc): return acc in db.get("force_stopped", [])


def force_acc(acc):
    if acc not in db["force_stopped"]: db["force_stopped"].append(acc); save()


def unforce_acc(acc):
    if acc in db["force_stopped"]: db["force_stopped"].remove(acc); save(); return True
    return False


def bkey(a, g): return f"{a}__{g}"


def is_blocked(a, g): return bkey(a, g) in db.get("blocked", {})


def force_block(uid, a, g, reason="انطرد"):
    db.setdefault("blocked", {})
    db["blocked"][bkey(a, g)] = {"owner": uid, "acc": a, "grp": g, "reason": reason, "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}; save()


def t(v): return "✅ مفعل" if v else "❌ معطل"


def main_kb(uid):
    r = [[IButton("📁 الحسابات", callback_data="accounts")]]
    r.append([IButton("🚀 النشر", callback_data="posting"), IButton("👥 المجموعات", callback_data="groups")])
    r.append([IButton("👥 احالتي 🎁", callback_data="my_ref"), IButton("🥷 التخفي", callback_data="stealth_info")])
    r.append([IButton("ℹ️ معلومات حول البوت", callback_data="about_bot")])
    if is_admin(uid): r.append([IButton("📊 احصائيات", callback_data="stats"), IButton("👑 VIP", callback_data="vip_admin")])
    r.append([IButton("👑 اشتراكي", callback_data="check_my_vip"), IButton("🔍 فحص", callback_data="check_acc")])
    return r


def back_kb(): return [[IButton("🔙 رجوع", callback_data="main")]]


def kb(rows):
    """يحول قائمة صفوف الأزرار (نفس شكل Button.inline بتليثون) الى InlineKeyboardMarkup."""
    return Markup(rows) if rows else None


bot = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
posting_tasks = {}; stats_today = {"count": 0}; login_tmp = {}; account_clients = {}; tasks_started = False
user_state = {}; stealth_counter = {}


async def notify_admin(kind, uid):
    try:
        sender = await bot.get_users(uid)
        full = f"{sender.first_name or ''} {sender.last_name or ''}".strip() or "بدون اسم"
        username = f"@{sender.username}" if sender.username else "بدون يوزر"
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if kind == "new":
            msg = f"🔔 دخل مستخدم جديد للبوت\n\n👤 الاسم: {full}\n🔗 اليوزر: {username}\n🆔 الايدي: `{uid}`\n🕐 الوقت: {now}\n👥 عدد المستخدمين الكلي: {len(db.get('users', {}))}"
        else:
            msg = f"🔔 اشتراك جديد بقناة البوت\n\nقام {full}\n🔗 اليوزر: {username}\n🆔 الايدي: `{uid}`\n🕐 الوقت: {now}\nبالاشتراك بقناة البوت\n\n👥 عدد المشتركين الكلي: {len(db.get('subscribed', []))}"
        await bot.send_message(ADMIN_ID, msg)
    except Exception as ex: print("notify error:", ex)


account_locks = {}


async def get_client(acc_key):
    """
    قفل لكل حساب يمنع فتح أكثر من اتصال بنفس الوقت لنفس الجلسة.
    بدون هذا القفل، لما عدة مجموعات لنفس الحساب تبدأ النشر بنفس اللحظة،
    كل مهمة كانت تفتح Client جديد منفصل بنفس الجلسة في نفس الوقت،
    وهذا يسبب "تعارض جلسات" يخلي تيليجرام يحط قيد مؤقت يشبه الحظر على الحساب.
    """
    lock = account_locks.setdefault(acc_key, asyncio.Lock())
    async with lock:
        if acc_key in account_clients:
            try:
                c = account_clients[acc_key]
                await c.get_me(); return c
            except Exception:
                try: await account_clients[acc_key].stop()
                except Exception: pass
                account_clients.pop(acc_key, None)
        acc = db["accounts"].get(acc_key)
        if not acc: return None
        client = Client(f"acc_{acc_key}", api_id=API_ID, api_hash=API_HASH, session_string=acc["session"], in_memory=True)
        await client.start()
        account_clients[acc_key] = client; return client


async def resolve_gid(client, link_or_id):
    if isinstance(link_or_id, str) and "t.me" in link_or_id:
        link = link_or_id.strip()
        try:
            chat = await client.get_chat(link)
            return str(chat.id)
        except Exception as e:
            print(e); return None
    return link_or_id


async def leave_real(client, gid):
    try:
        await client.leave_chat(int(gid)); return True
    except Exception:
        return False


async def check_forced(uid):
    ch = get_forced()
    if not ch or ch == "NEED_FORWARD": return True
    if is_admin(uid): return True
    chat_id = str(ch)
    try:
        import urllib.request, json as js
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember?chat_id={chat_id}&user_id={uid}"

        def _req():
            with urllib.request.urlopen(url, timeout=10) as r: return js.loads(r.read().decode())
        data = await asyncio.to_thread(_req)
        if not data.get("ok"): return False
        return data["result"]["status"] in ["creator", "administrator", "member", "restricted"]
    except Exception:
        try:
            target = int(ch) if str(ch).startswith("-100") else ch
            await bot.get_chat_member(target, uid); return True
        except Exception: return False


async def check_gate(message, uid):
    if is_admin(uid): return True
    if not await check_forced(uid):
        ch = get_forced()
        if str(ch).startswith("-100"):
            await message.reply(f"⚠️ الاشتراك الاجباري\nاشترك بالقناة الخاصة اولاً.\nراسل المطور:\n{DEV}", reply_markup=kb([[IButton("📩 راسل المطور", url=f"https://t.me/{DEV.replace('@', '')}")], [IButton("✅ تحققت", callback_data="check_forced")]]))
        else:
            await message.reply(f"⚠️ الاشتراك الاجباري\nاشترك بالقناة اولاً:\n{ch}", reply_markup=kb([[IButton("📢 اشترك", url=f"https://t.me/{str(ch).replace('@', '')}")], [IButton("✅ تحققت", callback_data="check_forced")]]))
        return False
    if not is_vip(uid):
        await message.reply(f"❌ غير مشترك VIP\nراسل المطور:\n{DEV}", reply_markup=kb([[IButton("📩 راسل المطور", url=f"https://t.me/{DEV.replace('@', '')}")]])); return False
    return True


def forced_btns():
    ch = get_forced()
    if str(ch).startswith("-100"): return [[IButton("📩 راسل المطور", url=f"https://t.me/{DEV.replace('@', '')}")], [IButton("✅ تحققت", callback_data="check_forced")]]
    return [[IButton("📢 اشترك", url=f"https://t.me/{str(ch).replace('@', '')}")], [IButton("✅ تحققت", callback_data="check_forced")]]


async def send_one(uid, acc_key, grp_id):
    s = get_settings(uid); acc = db["accounts"].get(acc_key)
    if not acc: return False
    if is_force(acc_key): return False
    if is_blocked(acc_key, grp_id): return False
    try:
        client = await get_client(acc_key)
        try:
            await client.get_me()
        except Exception:
            raise AuthKeyUnregistered("جلسة منتهية")
        real_id = grp_id
        if isinstance(grp_id, str) and ("t.me" in grp_id or "http" in grp_id):
            real_id = await resolve_gid(client, grp_id)
            if real_id and real_id != grp_id and grp_id in db["groups"]:
                db["groups"][real_id] = db["groups"].pop(grp_id); save()
            if not real_id:
                await bot.send_message(uid, f"⚠️ ما كدرت احول الرابط: {grp_id}"); return False
        if s.get("caption_mode") == "multi" and s.get("captions"):
            caption_to_send = random.choice(s["captions"])
        else:
            caption_to_send = s.get("caption", "اهلا بكم 🔥")
        is_reply = False
        if s.get("stealth_enabled"):
            ck = f"{acc_key}_{real_id}"; c = stealth_counter.get(ck, 0)
            if c % 3 == 2: is_reply = True
            stealth_counter[ck] = c + 1
        if is_reply:
            try:
                msgs = [m async for m in client.get_chat_history(int(real_id), limit=20)]
                me = await client.get_me()
                cand = [m for m in msgs if m and m.text and not m.outgoing and m.from_user and m.from_user.id != me.id]
                if cand:
                    target = random.choice(cand)
                    if s["media_enabled"] and s["media_file"] and os.path.exists(s["media_file"]):
                        if s.get("media_type") == "video":
                            await client.send_video(int(real_id), s["media_file"], caption=caption_to_send, reply_to_message_id=target.id)
                        else:
                            await client.send_photo(int(real_id), s["media_file"], caption=caption_to_send, reply_to_message_id=target.id)
                    else:
                        await client.send_message(int(real_id), caption_to_send, reply_to_message_id=target.id)
                    stats_today["count"] += 1; return True
                raise Exception("ماكو رسالة للرد")
            except Exception:
                pass
        if s["media_enabled"] and s["media_file"] and os.path.exists(s["media_file"]):
            if s.get("media_type") == "video":
                await client.send_video(int(real_id), s["media_file"], caption=caption_to_send)
            else:
                await client.send_photo(int(real_id), s["media_file"], caption=caption_to_send)
        else:
            await client.send_message(int(real_id), caption_to_send)
        stats_today["count"] += 1; return True
    except FloodWait as e:
        if s["protect_enabled"]: await bot.send_message(ADMIN_ID, f"🛡️ FloodWait {e.value} للحساب {acc_key}"); return False
        await asyncio.sleep(e.value); return await send_one(uid, acc_key, grp_id)
    except (UserDeactivated, AuthKeyUnregistered, SessionRevoked) as e:
        acc["status"] = "معطل"; acc["reason"] = str(e); save()
        if s["protect_enabled"]: await bot.send_message(uid, f"⚠️ حساب {acc_key} تعطل: {e}")
        return False
    except BAN_LIKE_ERRORS as e:
        force_block(uid, acc_key, grp_id, f"انطرد: {e}"); stop_post(uid, acc_key, grp_id)
        try:
            t2 = db["groups"].get(str(grp_id), {}).get("title", grp_id)
            await bot.send_message(uid, f"⛔ طرد تلقائي\nالحساب {acc.get('phone')} انطرد من:\n{t2}\nتم ايقاف النشر لهاي المجموعة فقط.")
        except Exception: pass
        return False
    except Exception as e:
        msg = str(e)
        if any(x in msg for x in ["USER_NOT_PARTICIPANT", "UserNotParticipant", "CHAT_WRITE_FORBIDDEN", "ChatWriteForbidden", "USER_KICKED", "kicked", "not participant", "PEER_ID_INVALID"]):
            force_block(uid, acc_key, grp_id, f"انطرد: {e}"); stop_post(uid, acc_key, grp_id)
            try:
                t2 = db["groups"].get(str(grp_id), {}).get("title", grp_id)
                await bot.send_message(uid, f"⛔ طرد تلقائي\nالحساب {acc.get('phone')} انطرد من:\n{t2}\nتم ايقاف النشر لهاي المجموعة فقط.")
            except Exception: pass
            return False
        print(f"خطأ نشر: {e}")
        if s["protect_enabled"]: await bot.send_message(uid, f"⚠️ خطأ نشر {acc_key}: {e}")
        return False


async def posting_loop(uid, acc_key, grp_id):
    s = get_settings(uid)
    await asyncio.sleep(random.uniform(1, 8))  # فاصل بسيط عشوائي حتى ما تبدأ كل مجموعات نفس الحساب بنفس اللحظة
    while True:
        try:
            if is_force(acc_key): break
            if is_blocked(acc_key, grp_id): break
            await send_one(uid, acc_key, grp_id)
            delay = random.randint(s["delay_min"], s["delay_max"]) if s["random_enabled"] else s["delay"]
            await asyncio.sleep(delay)
        except asyncio.CancelledError: break
        except Exception as e: print(e); await asyncio.sleep(10)


def start_post(uid, acc_key, grp_id):
    if is_force(acc_key): return "force_stopped"
    if is_blocked(acc_key, grp_id): return "blocked"
    key = f"{uid}_{acc_key}_{grp_id}"
    if key in posting_tasks: return False
    posting_tasks[key] = asyncio.create_task(posting_loop(uid, acc_key, grp_id)); return True


def stop_post(uid, acc_key, grp_id):
    key = f"{uid}_{acc_key}_{grp_id}"
    if key in posting_tasks: posting_tasks[key].cancel(); del posting_tasks[key]; return True
    return False


def stop_all_acc(uid, acc_key):
    cnt = 0
    for k in list(posting_tasks.keys()):
        if k.startswith(f"{uid}_{acc_key}_"): posting_tasks[k].cancel(); del posting_tasks[k]; cnt += 1
    return cnt


async def vip_checker():
    while True:
        now = datetime.datetime.now()
        for uid, v in list(db["vip"].items()):
            if v.get("expire") == "lifetime": continue
            try:
                exp = datetime.datetime.fromisoformat(v["expire"])
                if (exp - now).total_seconds() <= 86400 and not v.get("notified"):
                    v["notified"] = True; save()
                    try: await bot.send_message(int(uid), "⚠️ اشتراكك VIP راح يخلص باجر!")
                    except Exception: pass
                if now > exp:
                    del db["vip"][uid]; save()
                    try: await bot.send_message(int(uid), "❌ انتهى اشتراكك VIP")
                    except Exception: pass
            except Exception: pass
        await asyncio.sleep(3600)


async def daily_report():
    while True:
        now = datetime.datetime.now(); target = now.replace(hour=23, minute=59, second=0)
        if target < now: target += datetime.timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        for uid, s in list(db["settings"].items()):
            if s.get("report_enabled"):
                try: await bot.send_message(int(uid), f"📊 تقرير يومي\nنشرت اليوم: {stats_today['count']}")
                except Exception: pass
        stats_today["count"] = 0


@bot.on_message(filters.command("start") & filters.private)
async def start(_: Client, message: Message):
    uid = message.from_user.id; sender = message.from_user
    ref_code = None
    if message.text and len(message.text.split()) > 1:
        arg = message.text.split()[1]
        if arg.startswith("ref_"): ref_code = arg.replace("ref_", "")
    is_new = str(uid) not in db["users"]
    db["users"][str(uid)] = {"name": sender.first_name or "", "username": sender.username or "", "id": uid, "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}; save()
    if is_new and uid != ADMIN_ID:
        await notify_admin("new", uid)
        if ref_code and ref_code != str(uid) and ref_code in db["users"]:
            db.setdefault("referrals", {})
            if ref_code not in db["referrals"]: db["referrals"][ref_code] = {"invited": [], "rewarded": False}
            if uid not in db["referrals"][ref_code]["invited"]:
                db["referrals"][ref_code]["invited"].append(uid); save()
                cnt = len(db["referrals"][ref_code]["invited"])
                try: await bot.send_message(int(ref_code), f"👥 احالة جديدة!\nواحد دخل من رابطك، صار عندك {cnt}/3\nاذا وصلت 3 تاخذ يوم VIP مجاني 🎁")
                except: pass
                if cnt >= 3 and not db["referrals"][ref_code].get("rewarded"):
                    db["referrals"][ref_code] = {"invited": [], "rewarded": False}
                    old = db["vip"].get(ref_code)
                    if old and old.get("expire") != "lifetime":
                        try: new_exp = datetime.datetime.fromisoformat(old["expire"]) + datetime.timedelta(days=1)
                        except: new_exp = datetime.datetime.now() + datetime.timedelta(days=1)
                    else: new_exp = datetime.datetime.now() + datetime.timedelta(days=1)
                    db["vip"][ref_code] = {"expire": new_exp.isoformat(), "notified": False}; save()
                    try: await bot.send_message(int(ref_code), "🎁 مبروك! جبت 3 احالات\nحصلت على يوم VIP مجاني 👑")
                    except: pass
    if not await check_gate(message, uid): return
    await message.reply("🤖 بوت النشر\nاهلا بك", reply_markup=kb(main_kb(uid)))


@bot.on_callback_query()
async def cb(_: Client, e: CallbackQuery):
    uid = e.from_user.id; data = e.data
    if data == "check_forced":
        await asyncio.sleep(2)
        if await check_forced(uid):
            if not is_vip(uid) and not is_admin(uid):
                await e.edit_message_text(f"❌ غير VIP\nراسل المطور:\n{DEV}", reply_markup=kb([[IButton("📩 راسل المطور", url=f"https://t.me/{DEV.replace('@', '')}")]])); return
            if uid != ADMIN_ID:
                if "subscribed" not in db: db["subscribed"] = []
                if uid not in db["subscribed"]:
                    db["subscribed"].append(uid); save(); await notify_admin("sub", uid)
            await e.edit_message_text("🤖 بوت النشر\nاهلا بك", reply_markup=kb(main_kb(uid)))
        else:
            ch = get_forced()
            if str(ch).startswith("-100"): await e.edit_message_text("⚠️ ما اشتركت بعد!\nالقناة خاصة، اشترك برابط الدعوة", reply_markup=kb(forced_btns()))
            else: await e.edit_message_text(f"⚠️ ما اشتركت بعد!\nاشترك:\n{ch}", reply_markup=kb(forced_btns()))
        return
    if not is_admin(uid):
        if not await check_forced(uid):
            ch = get_forced()
            if str(ch).startswith("-100"): await e.edit_message_text("⚠️ الاشتراك الاجباري\nاشترك بالقناة الخاصة اولاً", reply_markup=kb(forced_btns()))
            else: await e.edit_message_text(f"⚠️ الاشتراك الاجباري\nاشترك:\n{ch}", reply_markup=kb(forced_btns()))
            return
    if not is_admin(uid) and not is_vip(uid):
        if data not in ["check_my_vip", "main", "about_bot", "my_ref"]: await e.answer("❌ غير VIP", show_alert=True); return
    await e.answer(); s = get_settings(uid)
    if data == "about_bot":
        txt = """ℹ️ معلومات حول البوت - شنو يسوي بالتفصيل؟

🚀 النشر:
- تضيف حساباتك التليجرام للبوت
- تضيف المجموعات اللي تريد تنشر بيها
- تكتب كليشة النشر (نص + صورة او فيديو اختياري) - كليشة وحدة او عدة كلايش
- البوت ينشر الكليشة بكل المجموعات تلقائياً

🛡️ الحماية:
1. فارق زمني بين الحسابات
2. استراحة كل 50 نشرة
3. تأخير عشوائي 60-120 ثانية
4. ايقاف تلقائي اذا انحظر او انطرد
5. ايقاف اجباري طوارئ

🥷 وضع التخفي:
- النشرة 1 و 2: نشر عادي
- النشرة 3: رد على رسالة موجودة بنفس نص النشر

👥 الاحالة: كل 3 يدخلون من رابطك = يوم VIP مجاني
👑 VIP: نشر اسرع، حسابات اكثر
"""
        await e.edit_message_text(txt, reply_markup=kb([[IButton("🔙 رجوع", callback_data="main")]])); return
    if data == "my_ref":
        me = await bot.get_me(); link = f"https://t.me/{me.username}?start=ref_{uid}"
        cnt = len(db.get("referrals", {}).get(str(uid), {"invited": []}).get("invited", []))
        await e.edit_message_text(f"👥 نظام الاحالة 🎁\n\n🔗 رابطك:\n{link}\n\n👥 جبت: {cnt}/3\n🎁 كل 3 اشخاص يدخلون من رابطك تاخذ يوم VIP مجاني!", reply_markup=kb([[IButton("🔙 رجوع", callback_data="main")]])); return
    if data == "stealth_info":
        cur = s.get("stealth_enabled", False)
        txt2 = f"""🥷 وضع التخفي
اذا شغلته:
النشر الاول والثاني: ينشر عادي
النشر الثالث: يرد على رسالة موجودة بالكروب بنفس نص النشر بالضبط
الحالة الحالية: {'✅ شغال' if cur else '❌ مطفي'}
"""
        btns = [[IButton("✅ شغل التخفي" if not cur else "❌ طفي التخفي", callback_data="toggle_stealth")], [IButton("🔙 رجوع", callback_data="main")]]
        await e.edit_message_text(txt2, reply_markup=kb(btns)); return
    if data.startswith("join_prompt_"):
        key = data.replace("join_prompt_", "")
        grps = [(k, v) for k, v in db["groups"].items() if v.get("owner") == uid or is_admin(uid)]
        if not grps: await e.edit_message_text("⚠️ ماكو مجموعات محفوظة بالبوت", reply_markup=kb(back_kb())); return
        btns = []
        for gid, g in grps:
            title = g.get("title", gid) if isinstance(g, dict) else str(g)
            btns.append([IButton(f"➕ انضمام | {title[:30]}", callback_data=f"do_join_{key}_{gid}")])
        btns.append([IButton("✅ تم", callback_data="main")])
        await e.edit_message_text("📋 اختر المجموعات اللي تريد الحساب ينضم الها:", reply_markup=kb(btns)); return
    if data.startswith("do_join_"):
        try: _, key, gid = data.split("_", 2)
        except: await e.answer("خطأ", show_alert=True); return
        acc = db["accounts"].get(key)
        if not acc: await e.answer("الحساب مو موجود", show_alert=True); return
        g = db["groups"].get(gid); link = g.get("link") if isinstance(g, dict) else g
        try:
            client = await get_client(key)
            target = link if (isinstance(link, str) and "t.me" in link) else int(gid)
            try:
                await client.join_chat(target)
            except UserAlreadyParticipant:
                pass
            await e.answer("تم الانضمام ✅", show_alert=False)
            btns = []
            for gid2, g2 in db["groups"].items():
                if g2.get("owner") != uid and not is_admin(uid): continue
                title2 = g2.get("title", gid2) if isinstance(g2, dict) else str(g2)
                if gid2 == gid: btns.append([IButton(f"✅ انضم | {title2[:30]}", callback_data=f"done_{key}_{gid2}")])
                else: btns.append([IButton(f"➕ انضمام | {title2[:30]}", callback_data=f"do_join_{key}_{gid2}")])
            btns.append([IButton("✅ تم", callback_data="main")])
            await e.edit_message_text("📋 اختر المجموعات اللي تريد الحساب ينضم الها:", reply_markup=kb(btns))
        except Exception as ex: await e.answer(f"فشل: {ex}", show_alert=True)
        return
    if data == "main": await e.edit_message_text("🤖 بوت النشر\nاهلا بك", reply_markup=kb(main_kb(uid))); return
    if data == "accounts":
        accs = [(k, v) for k, v in db["accounts"].items() if v["owner"] == uid or is_admin(uid)]
        txt = "📁 الحسابات\n\n"
        for k, v in accs: txt += f"{v.get('phone', k)} - {v.get('status', '🟢')}{' ⛔ ايقاف' if is_force(k) else ''}\n"
        if not accs: txt += "لا توجد حسابات"
        btns = []
        for k, v in accs: btns.append([IButton(f"{v.get('phone', k)}", callback_data="noop"), IButton("🗑 حذف", callback_data=f"del_acc_{k}")])
        btns.append([IButton("➕ اضافة", callback_data="add_acc")]); btns.append([IButton("🔙 رجوع", callback_data="main")]); await e.edit_message_text(txt, reply_markup=kb(btns)); return
    if data == "add_acc": user_state[uid] = "wait_phone"; await e.edit_message_text("📱 دز رقمك مع + \nمثال: +964770...", reply_markup=kb(back_kb())); return
    if data.startswith("del_acc_"):
        k = data.replace("del_acc_", "")
        if k in account_clients:
            try: await account_clients[k].stop()
            except Exception: pass
            del account_clients[k]
        db["accounts"].pop(k, None); save(); await e.edit_message_text("تم حذف الحساب ✅", reply_markup=kb(back_kb())); return
    if data == "groups":
        grps = [(k, v) for k, v in db["groups"].items() if v["owner"] == uid or is_admin(uid)]
        txt = "👥 المجموعات\n\n"
        for k, v in grps: txt += f"{v.get('title', k)}\n"
        if not grps: txt += "لا توجد مجموعات"
        btns = []
        for k, v in grps: btns.append([IButton(v.get('title', k)[:30], callback_data="noop"), IButton("🚪 حذف + مغادرة", callback_data=f"del_grp_{k}")])
        btns.append([IButton("➕ اضافة مجموعة", callback_data="add_grp_choose_acc")]); btns.append([IButton("🔙 رجوع", callback_data="main")]); await e.edit_message_text(txt, reply_markup=kb(btns)); return
    if data.startswith("del_grp_"):
        grp_id = data.replace("del_grp_", ""); grp_title = db["groups"].get(grp_id, {}).get("title", grp_id)[:30]
        accs = [k for k, v in db["accounts"].items() if v["owner"] == uid]
        btns = [[IButton("🚪 مغادرة بكل الحسابات", callback_data=f"leave_grp_{grp_id}__ALL")]]
        for k in accs: btns.append([IButton(f"🚪 مغادرة {db['accounts'][k].get('phone', k)}", callback_data=f"leave_grp_{grp_id}__{k}")])
        btns.append([IButton("🗑 حذف من البوت فقط", callback_data=f"del_only_{grp_id}")]); btns.append([IButton("🔙 رجوع", callback_data="groups")])
        await e.edit_message_text(f"🚪 حذف:\n{grp_title}\nالحساب يغادر فعلاً؟", reply_markup=kb(btns)); return
    if data.startswith("leave_grp_"):
        rest = data.replace("leave_grp_", ""); grp_id, acc_part = rest.split("__", 1) if "__" in rest else (rest, "ALL")
        accs = [k for k, v in db["accounts"].items() if v["owner"] == uid] if acc_part == "ALL" else [acc_part]
        grp_title = db["groups"].get(grp_id, {}).get("title", grp_id); ok = 0; fail = 0
        for a in accs:
            try:
                client = await get_client(a); stop_post(uid, a, grp_id)
                if await leave_real(client, grp_id): ok += 1
                else: fail += 1
            except Exception: fail += 1
        db["groups"].pop(grp_id, None); save(); await e.edit_message_text(f"تم ✅\n🚪 غادر: {ok}\n❌ فشل: {fail}\n{grp_title}", reply_markup=kb(back_kb())); return
    if data.startswith("del_only_"):
        grp_id = data.replace("del_only_", ""); db["groups"].pop(grp_id, None); save(); await e.edit_message_text("تم حذف من البوت فقط ✅", reply_markup=kb(back_kb())); return
    if data == "add_grp_choose_acc":
        accs = [k for k, v in db["accounts"].items() if v["owner"] == uid]
        if not accs: await e.edit_message_text("اضف حساب اولا", reply_markup=kb(back_kb())); return
        btns = [[IButton("كل الحسابات", callback_data="add_grp_all")]]
        for k in accs: btns.append([IButton(db["accounts"][k].get("phone", k), callback_data=f"add_grp_acc_{k}")])
        btns.append([IButton("🔙 رجوع", callback_data="main")]); await e.edit_message_text("اختر الحساب:", reply_markup=kb(btns)); return
    if data.startswith("add_grp_acc_") or data == "add_grp_all":
        user_state[uid] = f"wait_grp_{data}"; await e.edit_message_text("ارسل رابط الكروب كامل:", reply_markup=kb(back_kb())); return
    if data == "posting":
        btns = [[IButton("▶️ بدء", callback_data="start_post"), IButton("⏹️ ايقاف", callback_data="stop_post")], [IButton("📝 الكليشة", callback_data="set_caption")], [IButton("⏱️ المدة", callback_data="set_delay")], [IButton("⚙️ اعدادات", callback_data="auto_settings")], [IButton("🔙 رجوع", callback_data="main")]]
        await e.edit_message_text("🚀 النشر", reply_markup=kb(btns)); return
    if data == "stop_post":
        btns = [[IButton("⏹️ عادي", callback_data="stop_post_normal")], [IButton("⛔ اجباري طوارئ", callback_data="stop_post_force")], [IButton("✅ الغاء الاجباري", callback_data="unblock_list")], [IButton("🔙 رجوع", callback_data="posting")]]
        await e.edit_message_text("⏹️ ايقاف النشر", reply_markup=kb(btns)); return
    if data == "unblock_list":
        forced = [a for a in db.get("force_stopped", []) if a in db["accounts"] and (db["accounts"][a]["owner"] == uid or is_admin(uid))]
        blocked = [(k, v) for k, v in db.get("blocked", {}).items() if v.get("owner") == uid or is_admin(uid)]
        txt = "⛔ الايقاف الاجباري:\n\n"; btns = []
        for acc_key in forced:
            phone = db["accounts"].get(acc_key, {}).get("phone", acc_key); txt += f"{phone} ⛔\n"
            btns.append([IButton(f"✅ الغاء + شغل: {phone}", callback_data=f"unforce_and_start_{acc_key}")]); btns.append([IButton(f"✅ الغاء فقط: {phone}", callback_data=f"unforce_{acc_key}")])
        for k, v in blocked:
            ap = db["accounts"].get(v.get("acc"), {}).get("phone", v.get("acc")); gt = db["groups"].get(v.get("grp"), {}).get("title", v.get("grp"))[:20]; txt += f"{ap} - {gt}\n"
            btns.append([IButton(f"✅ الغاء حظر: {ap} - {gt}", callback_data=f"unblock_{v.get('acc')}__{v.get('grp')}")])
        if not forced and not blocked: await e.edit_message_text("ما عندك ايقاف ✅", reply_markup=kb(back_kb())); return
        btns.append([IButton("🔙 رجوع", callback_data="posting")]); await e.edit_message_text(txt, reply_markup=kb(btns)); return
    if data.startswith("unforce_and_start_") or data.startswith("unforce_"):
        acc_key = data.replace("unforce_and_start_", "").replace("unforce_", "")
        if unforce_acc(acc_key):
            phone = db["accounts"].get(acc_key, {}).get("phone", acc_key)
            await e.edit_message_text(f"✅ تم الغاء الايقاف {phone}\nهسه رجع طبيعي.", reply_markup=kb([[IButton("▶️ بدء النشر", callback_data="start_post")], [IButton("🔙 رجوع", callback_data="main")]]))
        else: await e.edit_message_text("مو موجود", reply_markup=kb(back_kb()))
        return
    if data.startswith("unblock_"):
        rest = data.replace("unblock_", "")
        if "__" in rest:
            ak, gid = rest.split("__", 1)
            if bkey(ak, gid) in db.get("blocked", {}): del db["blocked"][bkey(ak, gid)]; save(); await e.edit_message_text("✅ تم الغاء الحظر", reply_markup=kb(back_kb()))
            else: await e.edit_message_text("مو موجود", reply_markup=kb(back_kb()))
        return
    if data in ["start_post", "stop_post_normal"]:
        mode = "start" if data == "start_post" else "stop"
        accs = [k for k, v in db["accounts"].items() if v["owner"] == uid]
        if not accs: await e.edit_message_text("ما عندك حساب", reply_markup=kb(back_kb())); return
        btns = [[IButton("كل الحسابات", callback_data=f"{mode}_post_ALL")]]
        for k in accs:
            label = db["accounts"][k].get("phone", k)
            if is_force(k): btns.append([IButton(label + " ⛔ موقوف - الغاء", callback_data=f"unforce_{k}")])
            else: btns.append([IButton(label, callback_data=f"{mode}_post_ACC_{k}")])
        btns.append([IButton("🔙 رجوع", callback_data="posting")]); await e.edit_message_text("اختر الحساب:", reply_markup=kb(btns)); return
    if data == "stop_post_force":
        accs = [k for k, v in db["accounts"].items() if v["owner"] == uid]
        if not accs: await e.edit_message_text("ما عندك حساب", reply_markup=kb(back_kb())); return
        btns = [[IButton("⛔ ايقاف لكل الحسابات", callback_data="force_ALL")]]
        for k in accs:
            label = db["accounts"][k].get("phone", k)
            if is_force(k): label += " ⛔ موقوف"
            btns.append([IButton(f"⛔ ايقاف: {label}", callback_data=f"force_{k}")])
        btns.append([IButton("🔙 رجوع", callback_data="posting")]); await e.edit_message_text("⛔ ايقاف اجباري طوارئ", reply_markup=kb(btns)); return
    if data.startswith("force_"):
        acc_key = data.replace("force_", "")
        if acc_key == "ALL":
            for k in [kk for kk, v in db["accounts"].items() if v["owner"] == uid]: stop_all_acc(uid, k); force_acc(k)
            await e.edit_message_text("⛔ تم ايقاف كل الحسابات ✅", reply_markup=kb([[IButton("✅ الغاء الايقاف", callback_data="unblock_list")], [IButton("🔙 رجوع", callback_data="main")]])); return
        cnt = stop_all_acc(uid, acc_key); force_acc(acc_key); phone = db["accounts"].get(acc_key, {}).get("phone", acc_key)
        await e.edit_message_text(f"⛔ تم ايقاف {phone} ✅\nتم ايقاف {cnt} نشر.", reply_markup=kb([[IButton("✅ الغاء الايقاف", callback_data="unblock_list")], [IButton("🔙 رجوع", callback_data="main")]])); return
    if data.startswith("start_post_ACC_") or data.startswith("stop_post_ACC_") or data in ["start_post_ALL", "stop_post_ALL"]:
        mode = "start" if data.startswith("start") else "stop"
        acc_part = "ALL" if data.endswith("_ALL") else data.replace(f"{mode}_post_ACC_", "")
        if mode == "start" and acc_part != "ALL" and is_force(acc_part):
            phone = db["accounts"].get(acc_part, {}).get("phone", acc_part)
            await e.edit_message_text(f"⛔ {phone} موقوف اجبارياً", reply_markup=kb([[IButton("✅ الغاء + شغل", callback_data=f"unforce_and_start_{acc_part}")], [IButton("🔙 رجوع", callback_data="posting")]])); return
        grps = [(k, v) for k, v in db["groups"].items() if v["owner"] == uid]
        if not grps: await e.edit_message_text("ما عندك مجموعة", reply_markup=kb(back_kb())); return
        btns = [[IButton("كل المجموعات", callback_data=f"{mode}_GRP_ALL__{acc_part}")]]
        for k, v in grps:
            label = v.get('title', k)[:30]
            if acc_part != "ALL" and is_blocked(acc_part, k): label += " ⛔ انطرد"
            btns.append([IButton(label, callback_data=f"{mode}_GRP_{k}__{acc_part}")])
        btns.append([IButton("🔙 رجوع", callback_data="posting")]); await e.edit_message_text("اختر المجموعة:", reply_markup=kb(btns)); return
    if data.startswith("start_GRP_") or data.startswith("stop_GRP_"):
        mode = "start" if data.startswith("start") else "stop"
        rest = data.replace(f"{mode}_GRP_", ""); grp_id, acc_part = rest.split("__", 1) if "__" in rest else (rest, "ALL")
        accs = [k for k, v in db["accounts"].items() if v["owner"] == uid] if acc_part == "ALL" else [acc_part]
        grps = list(db["groups"].keys()) if grp_id == "ALL" else [grp_id]
        cnt = 0; already = 0; blocked_cnt = 0; force_cnt = 0; force_accs = []
        for a in accs:
            for g in grps:
                real_g = g
                if isinstance(g, str) and "t.me" in g:
                    cl = await get_client(a); real_g = await resolve_gid(cl, g) or g
                    if real_g != g and g in db["groups"]: db["groups"][real_g] = db["groups"].pop(g); save()
                if mode == "start":
                    res = start_post(uid, a, real_g)
                    if res is True: cnt += 1
                    elif res == "blocked": blocked_cnt += 1
                    elif res == "force_stopped": force_cnt += 1; force_accs.append(a) if a not in force_accs else None
                    else: already += 1
                else:
                    if stop_post(uid, a, real_g): cnt += 1
                    else: already += 1
        if mode == "start":
            if force_cnt > 0 and cnt == 0:
                btns = []
                for fa in force_accs:
                    phone = db["accounts"].get(fa, {}).get("phone", fa); btns.append([IButton(f"✅ الغاء: {phone}", callback_data=f"unforce_and_start_{fa}")])
                btns.append([IButton("🔙 رجوع", callback_data="posting")]); await e.edit_message_text("⛔ موقوف اجبارياً", reply_markup=kb(btns)); return
            msg = ""
            if cnt > 0:
                caps = s.get("captions", [s.get("caption", "")])
                msg += f"✅ بدء النشر {cnt} 🔁\nالوضع: {'عدة كلايش (' + str(len(caps)) + ') 🎲' if s.get('caption_mode') == 'multi' else 'كليشة وحدة 📝'}\nالكليشة: {s.get('caption', '')[:100]}\n"
            if already > 0: msg += f"\n⚠️ شغال: {already}\n"
            if blocked_cnt > 0: msg += f"\n⛔ انطرد: {blocked_cnt}\n"
            if force_cnt > 0: msg += f"\n⛔ موقوف: {force_cnt}\n"
            await e.edit_message_text(msg or "تم", reply_markup=kb(back_kb()))
        else:
            if cnt > 0: await e.edit_message_text(f"⏹️ تم ايقاف {cnt} ✅", reply_markup=kb(back_kb()))
            else: await e.edit_message_text("⚠️ متوقف اصلاً", reply_markup=kb(back_kb()))
        return
    if data == "set_caption":
        cur_mode = s.get("caption_mode", "single"); cur_count = len(s.get("captions", []))
        btns = [[IButton("📝 كليشة وحدة", callback_data="caption_single")], [IButton("📝 عدة كلايش", callback_data="caption_multi")], [IButton("📋 عرض الكلايش الحالية", callback_data="caption_show")], [IButton("🔙 رجوع", callback_data="posting")]]
        await e.edit_message_text(f"📝 الكليشة\n\nالوضع الحالي: {'عدة كلايش' if cur_mode == 'multi' else 'كليشة وحدة'}\nعدد الكلايش: {cur_count}\n\nشلون تريد تنشر؟", reply_markup=kb(btns)); return
    if data == "caption_single":
        user_state[uid] = "wait_caption_single"
        await e.edit_message_text("📝 دز الكليشة الوحدة:\nمثال: اهلا بكم 🔥", reply_markup=kb(back_kb())); return
    if data == "caption_multi":
        user_state[uid] = "wait_caption_multi"
        await e.edit_message_text("📝 دز عدة كلايش، كل كليشة بسطر:\n\nمثال:\nاهلا بكم 🔥\nعرض اليوم خصم 50%\nتوصيل لكل المحافظات 🚀\n\nالبوت كل نشرة راح يختار وحدة عشوائياً", reply_markup=kb(back_kb())); return
    if data == "caption_show":
        caps = s.get("captions", [])
        txt = "📋 الكلايش الحالية:\n\n"
        for i, c in enumerate(caps, 1): txt += f"{i}. {c}\n---\n"
        if not caps: txt += "ماكو كلايش"
        await e.edit_message_text(txt, reply_markup=kb([[IButton("🔙 رجوع", callback_data="posting")]])); return
    if data == "set_delay":
        if s["random_enabled"]: user_state[uid] = "wait_delay_random"; await e.edit_message_text("ارسل هكذا: 60-120", reply_markup=kb(back_kb()))
        else: user_state[uid] = "wait_delay"; await e.edit_message_text("ارسل المدة بالثواني.", reply_markup=kb(back_kb()))
        return
    if data == "auto_settings":
        btns = [[IButton(f"🖼️ صور: {t(s['media_enabled'])}", callback_data="toggle_media")], [IButton(f"🛡️ حماية: {t(s['protect_enabled'])}", callback_data="toggle_protect")], [IButton(f"📊 تقرير: {t(s['report_enabled'])}", callback_data="toggle_report")], [IButton(f"🎲 عشوائي: {t(s['random_enabled'])}", callback_data="toggle_random")], [IButton(f"🥷 تخفي: {t(s['stealth_enabled'])}", callback_data="toggle_stealth")], [IButton("🔙 رجوع", callback_data="posting")]]
        await e.edit_message_text("⚙️ اعدادات", reply_markup=kb(btns)); return
    if data.startswith("toggle_"):
        key = {"toggle_media": "media_enabled", "toggle_protect": "protect_enabled", "toggle_report": "report_enabled", "toggle_random": "random_enabled", "toggle_stealth": "stealth_enabled"}[data]
        s[key] = not s[key]; save()
        if key == "media_enabled" and s[key]: user_state[uid] = "wait_media"; await e.edit_message_text("ارسل الصورة:", reply_markup=kb(back_kb())); return
        if key == "stealth_enabled":
            await e.edit_message_text(f"{'✅ تم تشغيل وضع التخفي 🥷' + chr(10) + 'هسه كل 3 نشرات، الثالثة راح تكون رد بنفس نص النشر.' if s[key] else '❌ تم اطفاء وضع التخفي'}", reply_markup=kb([[IButton("🔙 رجوع", callback_data="auto_settings")]])); return
        await e.edit_message_text("تم ✅", reply_markup=kb([[IButton("🔙 رجوع", callback_data="auto_settings")]])); return
    if data == "stats":
        if not is_admin(uid): await e.edit_message_text("للادمن فقط", reply_markup=kb(back_kb())); return
        ch = get_forced() or "مو مفعل"; ct = "خاصة" if str(ch).startswith("-100") else ("عامة" if ch != "مو مفعل" else "")
        await e.edit_message_text(f"📊 احصائيات\nالمستخدمين: {len(db['users'])}\nالحسابات: {len(db['accounts'])}\nالمجموعات: {len(db['groups'])}\nشغال: {len(posting_tasks)}\nاليوم: {stats_today['count']}\n📢 اجباري: {ch} {ct}", reply_markup=kb(back_kb())); return
    if data == "vip_admin":
        if not is_admin(uid): await e.edit_message_text("للادمن فقط", reply_markup=kb(back_kb())); return
        btns = [[IButton("➕ تفعيل VIP", callback_data="vip_add")], [IButton("➖ الغاء VIP", callback_data="vip_del")], [IButton("📋 قائمة VIP", callback_data="vip_list")], [IButton("📢 اشتراك اجباري", callback_data="vip_forced")], [IButton("🔙 رجوع", callback_data="main")]]
        await e.edit_message_text("👑 VIP", reply_markup=kb(btns)); return
    if data == "vip_add": user_state[uid] = "wait_vip_id"; await e.edit_message_text("ارسل ايدي المستخدم:", reply_markup=kb(back_kb())); return
    if data == "vip_del": user_state[uid] = "wait_vip_del"; await e.edit_message_text("ارسل ايدي المستخدم للالغاء:", reply_markup=kb(back_kb())); return
    if data == "vip_list":
        txt = "📋 VIP:\n\n"
        for k, v in db["vip"].items(): txt += f"{k} - {vip_left(int(k)) if k.isdigit() else v}\n"
        if not db["vip"]: txt += "لا يوجد"
        await e.edit_message_text(txt, reply_markup=kb(back_kb())); return
    if data == "vip_forced":
        cur = get_forced() or "مو مفعل"; ct = "خاصة" if str(cur).startswith("-100") else ("عامة" if cur != "مو مفعل" else "")
        user_state[uid] = "wait_forced"
        if cur != "مو مفعل":
            btns = [[IButton("🗑 حذف القناة", callback_data="vip_forced_del")], [IButton("🔙 رجوع", callback_data="main")]]
            await e.edit_message_text(f"📢 القناة الحالية:\n{cur} {ct}\n\nاذا تريد تغيرها، دز رابط جديد او حوّل رسالة من قناة جديدة\nاذا تريد تحذفها دوس زر الحذف جوة\n\n1️⃣ عامة: دز https://t.me/xxx\n2️⃣ خاصة: حوّل رسالة من القناة\n⚠️ البوت لازم ادمن", reply_markup=kb(btns)); return
        else: await e.edit_message_text(f"📢 ماكو قناة حالياً\n\n1️⃣ عامة: دز https://t.me/xxx\n2️⃣ خاصة: حوّل رسالة من القناة\nاو ارسل 'الغاء'\n⚠️ البوت لازم ادمن", reply_markup=kb(back_kb())); return
    if data == "vip_forced_del":
        s2 = get_settings(ADMIN_ID); s2["forced_channel"] = None; save()
        await e.edit_message_text("✅ تم حذف قناة الاشتراك الاجباري\nهسه البوت بدون اشتراك اجباري", reply_markup=kb([[IButton("🔙 رجوع", callback_data="vip_admin")]])); return
    if data.startswith("vip_dur_"):
        p = data.split("_", 3); dur = p[2]; target = p[3]
        if dur == "lifetime": exp = "lifetime"
        else: exp = (datetime.datetime.now() + datetime.timedelta(days={"day": 1, "week": 7, "month": 30}[dur])).isoformat()
        db["vip"][target] = {"expire": exp, "notified": False}; save(); await e.edit_message_text(f"تم تفعيل VIP {target} ✅", reply_markup=kb(back_kb())); return
    if data == "check_my_vip":
        if is_vip(uid): await e.edit_message_text(f"VIP ✅\n{vip_left(uid)}", reply_markup=kb(back_kb()))
        else: await e.edit_message_text(f"عادي ❌\nراسل: {DEV}", reply_markup=kb([[IButton("📩 راسل", url=f"https://t.me/{DEV.replace('@', '')}")]]))
        return
    if data == "check_acc":
        txt = "🔍 فحص:\n\n"
        for k, v in db["accounts"].items():
            if v["owner"] != uid and not is_admin(uid): continue
            running = any(k in kk for kk in posting_tasks.keys())
            txt += f"{v.get('phone', k)} - {'شغال ✅' if running else 'متوقف ⏹️'}{' ⛔ ايقاف' if is_force(k) else ''}\n"
        await e.edit_message_text(txt, reply_markup=kb(back_kb())); return


@bot.on_message(filters.private, group=1)
async def on_msg(_: Client, e: Message):
    uid = e.from_user.id; st = user_state.get(uid)
    if not st: return
    if e.text and e.text.startswith("/"): return
    if not is_admin(uid) and not is_vip(uid): await e.reply(f"❌ غير VIP\nراسل: {DEV}"); return
    s = get_settings(uid); txt = (e.text or "").strip()
    if st == "wait_forced":
        fwd = e.forward_from_chat
        if fwd is not None:
            ch_id = fwd.id
            if ch_id:
                full_id = str(ch_id) if str(ch_id).startswith("-100") else f"-100{ch_id}"
                s["forced_channel"] = full_id; save(); user_state.pop(uid, None)
                await e.reply(f"تم ✅ قناة خاصة\n🆔 {full_id}\n⚠️ البوت لازم ادمن", reply_markup=kb(main_kb(uid))); return
            await e.reply("⚠️ مو من قناة، حوّل من القناة نفسها"); return
        if txt.lower() in ["الغاء", "cancel", "none", "-", "ايقاف", "تعطيل"]:
            s["forced_channel"] = None; save(); user_state.pop(uid, None); await e.reply("تم تعطيل الاجباري ✅", reply_markup=kb(main_kb(uid))); return
        cleaned = clean_ch(txt)
        if cleaned == "NEED_FORWARD": await e.reply("⚠️ رابط خاص t.me/+ ما ينفع، حوّل رسالة من القناة"); return
        if cleaned: s["forced_channel"] = cleaned; save(); user_state.pop(uid, None); await e.reply(f"تم ✅ اجباري = {cleaned}\nعامة 🌐", reply_markup=kb(main_kb(uid))); return
        await e.reply("دز رابط عامة او حوّل من خاصة"); return
    if st == "wait_phone":
        if not txt.startswith("+"): await e.reply("دز الرقم مع +"); return
        try:
            client = Client(f"tmp_{uid}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
            await client.connect()
            sent = await client.send_code(txt)
            login_tmp[uid] = {"phone": txt, "hash": sent.phone_code_hash, "client": client}; user_state[uid] = "wait_code"; await e.reply(f"تم ارسال الكود الى {txt}\nدز الكود:")
        except Exception as ex: await e.reply(f"خطأ: {ex}")
        return
    if st == "wait_code":
        tmp = login_tmp.get(uid)
        if not tmp: await e.reply("دز الرقم من جديد"); user_state[uid] = "wait_phone"; return
        try:
            await tmp["client"].sign_in(tmp["phone"], tmp["hash"], txt)
            sess = await tmp["client"].export_session_string(); key = f"acc_{int(datetime.datetime.now().timestamp())}_{random.randint(100, 999)}"
            db["accounts"][key] = {"owner": uid, "session": sess, "phone": tmp["phone"], "status": "🟢 موجود", "reason": "-"}; save(); account_clients[key] = tmp["client"]
            login_tmp.pop(uid, None); user_state.pop(uid, None)
            kb_ = [[IButton("✅ اي نعم", callback_data="join_prompt_" + key)], [IButton("❌ لا، بعدين", callback_data="main")]]
            await e.reply(f"تم اضافة ✅ {tmp['phone']}\n\nهل تريد انضمام الحساب للمجموعات؟", reply_markup=kb(kb_))
        except SessionPasswordNeeded: user_state[uid] = "wait_2fa"; await e.reply("🔐 تحقق بخطوتين\nدز كلمة المرور:")
        except PhoneCodeInvalid: await e.reply("الكود غلط:")
        except Exception as ex: await e.reply(f"خطأ: {ex}")
        return
    if st == "wait_2fa":
        tmp = login_tmp.get(uid)
        if txt == "ماعندي": await e.reply("لازم تدز كلمة المرور"); return
        try:
            await tmp["client"].check_password(txt)
            sess = await tmp["client"].export_session_string(); key = f"acc_{int(datetime.datetime.now().timestamp())}_{random.randint(100, 999)}"
            db["accounts"][key] = {"owner": uid, "session": sess, "phone": tmp["phone"], "status": "🟢 موجود", "reason": "-"}; save(); account_clients[key] = tmp["client"]
            login_tmp.pop(uid, None); user_state.pop(uid, None)
            kb_ = [[IButton("✅ اي نعم", callback_data="join_prompt_" + key)], [IButton("❌ لا، بعدين", callback_data="main")]]
            await e.reply(f"تم ✅ {tmp['phone']}\n\nهل تريد انضمام الحساب للمجموعات؟", reply_markup=kb(kb_))
        except Exception as ex: await e.reply(f"غلط: {ex}")
        return
    if st.startswith("wait_grp_"):
        link = txt.strip(); chosen = st.replace("wait_grp_", "")
        if chosen.startswith("add_grp_acc_"):
            ak = chosen.replace("add_grp_acc_", "")
            if ak in db["accounts"] and db["accounts"][ak]["owner"] == uid: accs = [(ak, db["accounts"][ak])]
            else: await e.reply("الحساب مو موجود"); user_state.pop(uid, None); return
            mode_txt = f"للحساب {db['accounts'][ak].get('phone')}"
        else: accs = [(k, v) for k, v in db["accounts"].items() if v["owner"] == uid]; mode_txt = "لجميع الحسابات"
        if not accs: await e.reply("ما عندك حساب"); user_state.pop(uid, None); return
        await e.reply(f"جاري دخول {mode_txt} ... ⏳")
        joined = 0; skipped = 0; failed = ""; gid_final = None
        for ak, acc in accs:
            try:
                client = await get_client(ak)
                try:
                    chat = await client.join_chat(link); gid_final = str(chat.id); joined += 1
                except UserAlreadyParticipant:
                    skipped += 1
                    try:
                        chat = await client.get_chat(link); gid_final = str(chat.id)
                    except Exception: pass
            except FloodWait:
                failed += f"\n{acc.get('phone')}: Flood"
            except Exception as ex:
                msg = str(ex)
                if "already" in msg.lower() or "participant" in msg.lower():
                    skipped += 1
                    try:
                        chat = await client.get_chat(link); gid_final = str(chat.id)
                    except Exception: pass
                elif "INVITE_HASH_EXPIRED" in msg: failed += f"\n{acc.get('phone')}: رابط منتهي"
                elif "INVITE_HASH_INVALID" in msg: failed += f"\n{acc.get('phone')}: رابط غلط"
                else: failed += f"\n{acc.get('phone')}: {ex}"
        if not gid_final: user_state.pop(uid, None); await e.reply(f"❌ فشل\n{failed}", reply_markup=kb(main_kb(uid))); return
        db["groups"][gid_final] = {"owner": uid, "title": link, "link": link}; save(); user_state.pop(uid, None)
        await e.reply(f"تم ✅ ({mode_txt})\n✅ دخل: {joined}\n⏭️ موجود: {skipped}\n🆔 {gid_final}\n{failed}", reply_markup=kb(main_kb(uid))); return
    if st == "wait_caption_single":
        s["caption"] = txt; s["captions"] = [txt]; s["caption_mode"] = "single"; save(); user_state.pop(uid, None)
        await e.reply(f"✅ تم حفظ كليشة وحدة:\n{txt}\n\nهسه النشر راح يكون بنفس الكليشة دائماً", reply_markup=kb(main_kb(uid))); return
    if st == "wait_caption_multi":
        lines = [l.strip() for l in (e.text or "").split("\n") if l.strip()]
        if len(lines) < 2:
            await e.reply("⚠️ لازم تدز كليشتين على الاقل، كل وحدة بسطر\nجرب مرة ثانية:"); return
        s["captions"] = lines; s["caption"] = lines[0]; s["caption_mode"] = "multi"; save(); user_state.pop(uid, None)
        txt2 = "✅ تم حفظ عدة كلايش:\n\n"
        for i, c in enumerate(lines, 1): txt2 += f"{i}. {c}\n"
        txt2 += "\n🎲 البوت كل نشرة راح يختار وحدة عشوائياً"
        await e.reply(txt2, reply_markup=kb(main_kb(uid))); return
    if st == "wait_caption":
        s["caption"] = txt; s["captions"] = [txt]; s["caption_mode"] = "single"; save(); user_state.pop(uid, None); await e.reply("تم حفظ الكليشة ✅", reply_markup=kb(main_kb(uid))); return
    if st == "wait_delay":
        try:
            d = int(txt)
            if d < 60: await e.reply(f"⚠️ {d} ثانية خطر، دز 'اي' للتأكيد"); user_state[uid] = "wait_delay_confirm"; return
            s["delay"] = d; save(); user_state.pop(uid, None); await e.reply(f"تم: {d} ثانية ✅", reply_markup=kb(main_kb(uid))); return
        except Exception: await e.reply("ارسل رقم"); return
    if st == "wait_delay_confirm":
        if txt == "اي": s["delay"] = 30; save(); user_state.pop(uid, None); await e.reply("تم 30 ثانية ⚠️", reply_markup=kb(main_kb(uid))); return
        try: s["delay"] = int(txt); save(); user_state.pop(uid, None); await e.reply("تم ✅", reply_markup=kb(main_kb(uid))); return
        except Exception: await e.reply("دز رقم"); return
    if st == "wait_delay_random":
        try: a, b = txt.split("-"); s["delay_min"] = int(a); s["delay_max"] = int(b); save(); user_state.pop(uid, None); await e.reply(f"تم: {a}-{b} 🎲", reply_markup=kb(main_kb(uid))); return
        except Exception: await e.reply("ارسل 60-120"); return
    if st == "wait_media":
        if e.photo or e.video:
            path = f"media_{uid}.jpg"; await e.download(file_name=path); s["media_file"] = path; s["media_type"] = "photo" if e.photo else "video"; save(); user_state.pop(uid, None)
            await e.reply("تم حفظ ✅", reply_markup=kb(main_kb(uid))); return
        await e.reply("ارسل صورة"); return
    if st == "wait_vip_id": target = txt; user_state[uid] = f"wait_vip_dur_{target}"; await e.reply("اختر المدة:", reply_markup=kb([[IButton("📅 يوم", callback_data="vip_dur_day_" + target), IButton("📅 اسبوع", callback_data="vip_dur_week_" + target)], [IButton("📅 شهر", callback_data="vip_dur_month_" + target), IButton("♾️ مدى", callback_data="vip_dur_lifetime_" + target)]])); return
    if st == "wait_vip_del": db["vip"].pop(txt, None); save(); user_state.pop(uid, None); await e.reply("تم الغاء VIP ✅", reply_markup=kb(main_kb(uid))); return


async def main():
    global tasks_started
    print("جاري الاتصال بتيليجرام...", flush=True)
    await bot.start()
    if not tasks_started:
        asyncio.create_task(vip_checker()); asyncio.create_task(daily_report()); tasks_started = True
    print("Bot Running...", flush=True)
    await idle()
    await bot.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        import traceback
        print("====== حدث خطأ أوقف البوت ======", flush=True)
        traceback.print_exc()
        raise
