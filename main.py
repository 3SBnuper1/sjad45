# ============================================================
# بوت تنظيف الميديا + مانع +18 بالكامل
# ذكاء اصطناعي محلي + فحص فيديو فريم فريم + تشغيل/اطفاء
# ============================================================
import os, json, datetime, io, tempfile, cv2
from PIL import Image
import torch
from transformers import pipeline

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ============ الاعدادات - غيرها هنا ============
TOKEN = "9035064383:AAH61Rzyg92Vu814MXEHQkxi2G7ZC1NgfZM"
ADMIN_ID = 6871060318  # ايدي الادمن الرئيسي
DEVELOPER_USERNAME = "ziocw"  # يوزر المطور بدون @
DB_FILE = "db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {"users": {}, "groups": {}, "assistants": [], "force_sub": None}
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

db = load_db()

# ============ الذكاء الاصطناعي ============
print("جار تحميل موديل الذكاء الاصطناعي...")
nsfw_pipe = pipeline("image-classification", model="Falconsai/nsfw_image_detection", device=0 if torch.cuda.is_available() else -1)
print("تم تحميل الموديل ✅")

def check_media_ai(file_bytes):
    """فحص صورة واحدة - يرجع (True/False, السبب)"""
    try:
        img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        res = nsfw_pipe(img, top_k=5)
        scores = {r['label'].lower(): r['score'] for r in res}
        print("NSFW:", scores)
        if scores.get('porn', 0) > 0.55: return True, "porn"
        if scores.get('hentai', 0) > 0.55: return True, "hentai"
        if scores.get('sexy', 0) > 0.82: return True, "sexy"
        if scores.get('sexy', 0) > 0.6 and scores.get('porn', 0) > 0.3: return True, "sexy+porn"
        return False, "clean"
    except Exception as e:
        print("AI Error:", e)
        return False, "error"

def check_video_ai(file_path, max_frames=15, interval_sec=1):
    """فحص الفيديو فريم فريم - بداية + وسط + نهاية"""
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        return False, "cannot_open", 0
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total_frames / fps if fps else 0
    print(f"Video: {duration:.1f}s, {total_frames} frames")

    # نختار فريمات ذكية: بداية + وسط + نهاية + كل ثانية
    # اذا الفيديو طويل، ناخذ عينات من كل اجزاءه
    positions = []
    step = int(fps * interval_sec)
    if step < 1: step = 30

    # كل ثانية
    for idx in range(0, total_frames, step):
        positions.append(idx)
    # نضيف الوسط والنهاية للتأكيد
    if total_frames > 0:
        positions.append(total_frames // 2)
        positions.append(max(0, total_frames - 5))
    positions = sorted(list(set(positions)))
    # نقلل العدد اذا كان كبير جدا - نوزعها بالتساوي
    if len(positions) > max_frames:
        # ناخذ عينات متساوية من كل الفيديو
        import numpy as np
        idxs = np.linspace(0, len(positions)-1, max_frames).astype(int)
        positions = [positions[i] for i in idxs]

    for i, pos in enumerate(positions):
        cap.set(cv2.CAP_PROP_POS_FRAMES, pos)
        ret, frame = cap.read()
        if not ret: continue
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=85)
        is_bad, reason = check_media_ai(buf.getvalue())
        sec = pos / fps if fps else 0
        print(f"Frame {i+1}/{len(positions)} sec={sec:.1f} -> {reason} bad={is_bad}")
        if is_bad:
            cap.release()
            return True, f"{reason} - الثانية {sec:.1f}", i+1
    cap.release()
    return False, "clean", 0

async def is_admin_or_assistant(user_id):
    return user_id == ADMIN_ID or user_id in db["assistants"]

def is_group_enabled(chat_id):
    g = db["groups"].get(str(chat_id))
    if not g: return True
    return g.get("ai_enabled", True)

async def check_force_sub(user_id, context):
    ch = db.get("force_sub")
    if not ch: return True
    try:
        m = await context.bot.get_chat_member(ch, user_id)
        return m.status in ["member", "administrator", "creator"]
    except: return False

# ============ /start ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    is_new = uid not in db["users"]
    db["users"][uid] = {"name": user.full_name, "username": user.username, "id": user.id}
    save_db(db)
    if is_new:
        try:
            await context.bot.send_message(ADMIN_ID, f"👤 دخل مستخدم جديد\n• الاسم: {user.full_name}\n• اليوزر: @{user.username or 'لا يوجد'}\n• الايدي: `{user.id}`\n• عدد المستخدمين الكلي: {len(db['users'])}")
        except: pass
    if not await check_force_sub(user.id, context):
        ch = db["force_sub"]
        kb = [[InlineKeyboardButton("📢 اشترك بالقناة", url=f"https://t.me/{ch.replace('@','')}")],
              [InlineKeyboardButton("✅ تحققت، اشتركت", callback_data="check_sub")]]
        await update.message.reply_text("⚠️ يجب الاشتراك بالقناة اولا لاستخدام البوت", reply_markup=InlineKeyboardMarkup(kb))
        return
    text = "هلا بيك 👋\n\n• انا بـوت تنظيف الميديا + مانـع الـ +18 بالكامل\n• ضيفني لمجـموعتك ودز الاوامر\n\nلتجربة الكاشف دز ‹ صـورة - ملصق - Gif › وراح افحصها"
    kb = [
        [InlineKeyboardButton("➕ اضفني لمجموعتك", url=f"https://t.me/{context.bot.username}?startgroup=new")],
        [InlineKeyboardButton("👨‍💻 المطور", url=f"https://t.me/{DEVELOPER_USERNAME}")],
    ]
    if await is_admin_or_assistant(user.id):
        kb.append([InlineKeyboardButton("⚙️ لوحة التحكم", callback_data="panel")])
    kb.append([InlineKeyboardButton("🛡️ اضافة مشرف", callback_data="add_admin_menu")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))

# ============ اوامر التشغيل / الاطفاء ============
async def toggle_ai_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text("❌ هذا الامر يعمل داخل المجموعة فقط")
        return
    is_allowed = False
    if user.id == ADMIN_ID or user.id in db["assistants"]:
        is_allowed = True
    else:
        try:
            member = await context.bot.get_chat_member(chat.id, user.id)
            if member.status == "creator": is_allowed = True
        except: pass
    if not is_allowed:
        await update.message.reply_text("❌ هذا الامر للادمن فقط")
        return
    gid = str(chat.id)
    if gid not in db["groups"]:
        db["groups"][gid] = {"title": chat.title, "owner_id": user.id, "ai_enabled": True}
    cmd = update.message.text.split()[0].lower()
    if cmd == "/on":
        db["groups"][gid]["ai_enabled"] = True
        msg = "✅ تم تشغيل كاشف الذكاء الاصطناعي في هذه المجموعة"
    elif cmd == "/off":
        db["groups"][gid]["ai_enabled"] = False
        msg = "⛔ تم اطفاء كاشف الذكاء الاصطناعي في هذه المجموعة"
    else:
        cur = db["groups"][gid].get("ai_enabled", True)
        db["groups"][gid]["ai_enabled"] = not cur
        msg = "✅ تم التشغيل" if not cur else "⛔ تم الاطفاء"
    save_db(db)
    await update.message.reply_text(msg)

async def status_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    enabled = is_group_enabled(chat.id)
    await update.message.reply_text(f"🤖 حالة الكاشف: {'✅ شغال' if enabled else '⛔ مطفي'}\n\nللادمن فقط:\n/on - تشغيل\n/off - اطفاء\n/toggle - تبديل")

# ============ لوحة التحكم ============
async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user = q.from_user
    if not await is_admin_or_assistant(user.id):
        await q.answer("هذا الزر للادمن فقط", show_alert=True); return
    is_main = user.id == ADMIN_ID
    kb = [
        [InlineKeyboardButton("📊 الاحصائيات", callback_data="stats")],
        [InlineKeyboardButton("👥 المجموعات", callback_data="groups")],
        [InlineKeyboardButton("🤖 تشغيل / اطفاء الكاشف", callback_data="ai_toggle_menu")],
    ]
    if is_main:
        kb.append([InlineKeyboardButton("📢 الاشتراك الاجباري", callback_data="force_sub_menu")])
        kb.append([InlineKeyboardButton("➕ اضافة مساعد", callback_data="add_assistant")])
    kb.append([InlineKeyboardButton("🛡️ اضافة مشرف", callback_data="add_admin_menu")])
    await q.edit_message_text("⚙️ لوحة تحكم الادمن:", reply_markup=InlineKeyboardMarkup(kb))

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    user = q.from_user
    if data == "panel": await panel(update, context); return
    if data == "check_sub":
        if await check_force_sub(user.id, context):
            try: await context.bot.send_message(ADMIN_ID, f"✅ اشترك بالقناة الاجبارية\n• الاسم: {user.full_name}\n• اليوزر: @{user.username or 'لا يوجد'}\n• الايدي: `{user.id}`\n• القناة: {db.get('force_sub')}")
            except: pass
            await q.answer("تم التحقق ✅", show_alert=True)
            await q.message.delete()
            await start(update, context)
        else: await q.answer("❌ لم تشترك بعد!", show_alert=True)
        return
    if data == "stats":
        await q.edit_message_text(f"📊 الاحصائيات:\n\n• عدد المستخدمين: {len(db['users'])}\n• عدد المجموعات: {len(db['groups'])}\n• عدد المساعدين: {len(db['assistants'])}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="panel")]])); return
    if data == "groups":
        if not db["groups"]:
            await q.edit_message_text("لا توجد مجموعات", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="panel")]])); return
        kb = []
        for gid, info in db["groups"].items():
            status = "✅" if info.get("ai_enabled", True) else "⛔"
            kb.append([InlineKeyboardButton(f"{status} {info['title']}", callback_data="noop"),
                       InlineKeyboardButton("🤖 تشغيل/اطفاء", callback_data=f"toggle_{gid}"),
                       InlineKeyboardButton("🚪 مغادرة", callback_data=f"leave_{gid}")])
        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="panel")])
        await q.edit_message_text("👥 المجموعات المتواجد فيها البوت:", reply_markup=InlineKeyboardMarkup(kb)); return
    if data.startswith("toggle_"):
        gid = data.replace("toggle_", "")
        if gid in db["groups"]:
            cur = db["groups"][gid].get("ai_enabled", True)
            db["groups"][gid]["ai_enabled"] = not cur
            save_db(db)
            await q.answer(f"{'تم التشغيل ✅' if not cur else 'تم الاطفاء ⛔'}")
            q.data = "groups"; await callbacks(update, context)
        return
    if data == "ai_toggle_menu":
        if not db["groups"]:
            await q.edit_message_text("لا توجد مجموعات", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="panel")]])); return
        kb = []
        for gid, info in db["groups"].items():
            status = "✅ شغال" if info.get("ai_enabled", True) else "⛔ مطفي"
            kb.append([InlineKeyboardButton(f"{info['title']} - {status}", callback_data=f"toggle_{gid}")])
        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="panel")])
        await q.edit_message_text("🤖 اختر مجموعة لتشغيل / اطفاء الكاشف (للادمن فقط):", reply_markup=InlineKeyboardMarkup(kb)); return
    if data.startswith("leave_"):
        gid = data.split("_")[1]
        try: await context.bot.leave_chat(int(gid))
        except: pass
        db["groups"].pop(gid, None); save_db(db)
        await q.answer("تمت المغادرة"); await panel(update, context); return
    if data == "force_sub_menu":
        await q.edit_message_text(f"📢 القناة الحالية: {db.get('force_sub') or 'لا توجد'}\n\nارسل يوزر القناة مثل: @channel\nاو ارسل /off للالغاء", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="panel")]]))
        context.user_data["waiting"] = "force_sub"; return
    if data == "add_assistant":
        if user.id != ADMIN_ID: await q.answer("للمالك فقط", show_alert=True); return
        await q.edit_message_text("ارسل يوزر او ايدي المساعد الجديد:")
        context.user_data["waiting"] = "add_assistant"; return
    if data == "add_admin_menu":
        my_groups = []
        if user.id == ADMIN_ID or user.id in db["assistants"]:
            my_groups = list(db["groups"].items())
        else:
            for gid, info in db["groups"].items():
                if info.get("owner_id") == user.id: my_groups.append((gid, info))
        if not my_groups: await q.answer("ليس لديك اي مجموعة تديرها", show_alert=True); return
        kb = [[InlineKeyboardButton(f"🛡️ {info['title']}", callback_data=f"pick_group_{gid}")] for gid, info in my_groups]
        await q.edit_message_text("اختر المجموعة لاضافة مشرف فيها:", reply_markup=InlineKeyboardMarkup(kb)); return
    if data.startswith("pick_group_"):
        gid = data.split("_")[2]
        context.user_data["target_group"] = gid
        context.user_data["waiting"] = "add_group_admin"
        await q.edit_message_text("ارسل يوزر المستخدم داخل المجموعة لرفعه مشرف:\nمثال: @username"); return

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    waiting = context.user_data.get("waiting")
    text = update.message.text.strip()
    if not waiting: return
    if waiting == "force_sub" and user.id == ADMIN_ID:
        db["force_sub"] = None if text == "/off" else (text if text.startswith("@") else f"@{text}")
        save_db(db); context.user_data["waiting"] = None
        await update.message.reply_text(f"✅ تم تحديث الاشتراك الاجباري: {db['force_sub']}"); return
    if waiting == "add_assistant" and user.id == ADMIN_ID:
        try:
            target = await context.bot.get_chat(text)
            if target.id not in db["assistants"]:
                db["assistants"].append(target.id); save_db(db)
            context.user_data["waiting"] = None
            await update.message.reply_text(f"✅ تم اضافة المساعد: {target.full_name}\nيظهر له فقط خيار اضف مشرف")
        except: await update.message.reply_text("❌ لم اجد المستخدم")
        return
    if waiting == "add_group_admin":
        gid = context.user_data.get("target_group")
        info = db["groups"].get(str(gid))
        allowed = (user.id == ADMIN_ID or user.id in db["assistants"] or (info and info.get("owner_id") == user.id))
        if not allowed: await update.message.reply_text("❌ ليس لديك صلاحية"); return
        try:
            target = await context.bot.get_chat(text)
            await context.bot.promote_chat_member(int(gid), target.id, can_send_messages=True, can_delete_messages=True, can_restrict_members=False, can_promote_members=False, can_change_info=False, can_invite_users=False, can_pin_messages=False)
            context.user_data["waiting"] = None
            await update.message.reply_text(f"✅ تم رفع {target.full_name} مشرف في {info['title']}")
        except Exception as e: await update.message.reply_text(f"❌ فشل الرفع، تأكد ان المستخدم في المجموعة والبوت مشرف.\n{e}")
        return

async def new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            chat = update.effective_chat
            owner_id = None
            try:
                admins = await context.bot.get_chat_administrators(chat.id)
                for a in admins:
                    if a.status == "creator": owner_id = a.user.id
            except: pass
            db["groups"][str(chat.id)] = {"title": chat.title, "link": chat.invite_link or f"@{chat.username or 'private'}", "owner_id": owner_id, "ai_enabled": True}
            save_db(db)
            try: await context.bot.send_message(ADMIN_ID, f"➕ تم اضافة البوت الى مجموعة\n• الاسم: {chat.title}\n• الرابط: {chat.invite_link or 'خاص'}\n• الوقت: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n• الكاشف: ✅ شغال افتراضيا")
            except: pass

# ============ فحص الميديا - صور + ملصقات + GIF + فيديو ============
async def check_group_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg: return
    if msg.chat.type in ["group", "supergroup"] and not is_group_enabled(msg.chat.id):
        return
    file_id = None
    file_type = "photo"
    if msg.photo:
        file_id = msg.photo[-1].file_id; file_type = "photo"
    elif msg.sticker:
        file_id = msg.sticker.file_id; file_type = "sticker"
    elif msg.animation:
        file_id = msg.animation.file_id; file_type = "gif"
    elif msg.video:
        file_id = msg.video.file_id; file_type = "video"
    elif msg.video_note:
        file_id = msg.video_note.file_id; file_type = "video"
    elif msg.document and msg.document.mime_type and "video" in msg.document.mime_type:
        file_id = msg.document.file_id; file_type = "video"
    if not file_id: return

    f = await context.bot.get_file(file_id)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
        tmp_path = tmp.name
    await f.download_to_drive(tmp_path)

    is_bad = False
    reason = "clean"
    try:
        if file_type in ["video", "gif"]:
            max_f = 15 if file_type == "video" else 10
            is_bad, reason, _ = check_video_ai(tmp_path, max_frames=max_f, interval_sec=1)
            if not is_bad:
                with open(tmp_path, "rb") as fh:
                    is_bad, reason = check_media_ai(fh.read())
        else:
            # صورة / ملصق
            try:
                is_bad, reason, _ = check_video_ai(tmp_path, max_frames=5, interval_sec=1)
            except: is_bad = False
            if not is_bad:
                with open(tmp_path, "rb") as fh:
                    is_bad, reason = check_media_ai(fh.read())
    finally:
        try: os.remove(tmp_path)
        except: pass

    if msg.chat.type == "private":
        if file_type in ["video", "gif"]:
            await msg.reply_text(f"🚨 فيديو +18 / عنف\nالسبب: {reason}" if is_bad else "✅ الفيديو نظيف - تم فحص كل الفريمات بالذكاء الاصطناعي")
        else:
            await msg.reply_text(f"🚨 +18 / عنف - السبب: {reason}" if is_bad else "✅ المحتوى نظيف - الذكاء الاصطناعي")
        return
    if not is_bad: return

    user = msg.from_user; chat = msg.chat
    try: await msg.delete()
    except: pass
    try:
        member = await context.bot.get_chat_member(chat.id, user.id)
        if member.status == "administrator":
            await context.bot.promote_chat_member(chat.id, user.id, can_send_messages=False, can_delete_messages=False, can_restrict_members=False, can_promote_members=False, can_change_info=False, can_invite_users=False, can_pin_messages=False)
    except: pass
    try: await context.bot.restrict_chat_member(chat.id, user.id, ChatPermissions(can_send_messages=False))
    except: pass
    group_info = db["groups"].get(str(chat.id), {})
    owner_id = group_info.get("owner_id")
    time_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    notif = f"🚨 تحذير +18 (ذكاء اصطناعي - فحص فيديو)\n• المستخدم: {user.full_name}\n• اليوزر: @{user.username or 'لا يوجد'}\n• الوقت: {time_now}\n• المجموعة: {chat.title}\n• النوع: {file_type}\n• السبب: {reason}\nتم الحذف والتقييد وازالته من المشرفين"
    if owner_id:
        try: await context.bot.send_message(owner_id, notif)
        except: pass
    try: await context.bot.send_message(ADMIN_ID, notif)
    except: pass
    try: await context.bot.send_message(chat.id, f"🚫 تم حذف محتوى +18 من {user.full_name} وتقييده - {reason}")
    except: pass

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["on", "off", "toggle"], toggle_ai_cmd))
    app.add_handler(CommandHandler("status", status_ai))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_members))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Sticker.ALL | filters.ANIMATION | filters.VIDEO | filters.VIDEO_NOTE | filters.Document.VIDEO, check_group_media))
    print("Bot Running with AI + Video Check...")
    app.run_polling()

if __name__ == "__main__":
    main()
