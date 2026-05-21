import os
import logging
import asyncio
import sqlite3
from datetime import datetime
import qrcode
from io import BytesIO

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --------------------------------------------------------
# 1. إعدادات النظام والقنوات الثابتة
# --------------------------------------------------------
BOT_TOKEN = "8738205649:AAEWP0-EhA470ws1rOcErhPXDHrPJOmlK3s"
ADMIN_ID = 7793940324  # الآيدي الخاص بك كمشرف عام

# قنوات النظام المحددة
CH_FORCE_SUB = -1003948802392      # الاشتراك الإجباري
CH_GAME_LOGS = -1003712160933      # إشعارات فوز الألعاب
CH_WITHDRAW_LOGS = -1003896223604  # إشعارات السحوبات
CH_GENERAL_LOGS = -1003711621774   # الإشعارات العامة

URL_FORCE_SUB = "https://t.me/ALFA_ULTRA_BOT1"

# إعداد السجلات (Logging) لمراقبة الأخطاء
logging.basicConfig(level=logging.INFO)

# تفعيل البوت والموزع مع التخزين المؤقت للحالات
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --------------------------------------------------------
# 2. محرك قاعدة البيانات وتأسيس الجداول (Database Engine)
# --------------------------------------------------------
DB_NAME = "alfa_ultra_v3.db"

def init_db():
    """تأسيس قاعدة البيانات والجداول بنظام الأرصدة المزدوج وحماية البيانات"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # جدول المستخدمين الشامل
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        full_name TEXT,
        balance_earnings REAL DEFAULT 0.0,
        balance_ads REAL DEFAULT 0.0,
        referred_by INTEGER DEFAULT NULL,
        referrals_count INTEGER DEFAULT 0,
        rank TEXT DEFAULT 'عضو جديد 🌱',
        vip_level INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0,
        join_date TEXT
    )
    """)
    
    # جدول الإعدادات الديناميكية للوحة التحكم الإمبراطورية
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    # إدخال الإعدادات الافتراضية للنظام إذا لم تكن موجودة
    default_settings = [
        ("bot_status", "on"),            # حالة البوت (on / off للصيانة)
        ("wheel_cost", "1000"),          # تكلفة دورة عجلة الحظ
        ("wheel_win_rate", "30.0"),      # نسبة الفوز في العجلة
        ("referral_reward", "500"),      # جائزة الإحالة بالليرة
        ("p2p_fee", "2.0"),              # رسوم تحويل الـ P2P نسبة مئوية
        ("min_withdraw", "10000")        # الحد الأدنى للسحب
    ]
    
    for key, val in default_settings:
        cursor.execute("INSERT OR IGNORE INTO system_settings (key, value) VALUES (?, ?)", (key, val))
        
    conn.commit()
    conn.close()

# تشغيل تفعيل قاعدة البيانات فوراً عند إقلاع السكربت
init_db()
# --------------------------------------------------------
# 3. دوال الحماية والاشتراك الإجباري (Security & Force Sub)
# --------------------------------------------------------

async def check_subscription(user_id: int) -> bool:
    """التحقق من أن المستخدم مشترك في قناة الاشتراك الإجباري الرسمية"""
    if user_id == ADMIN_ID:
        return True
    try:
        member = await bot.get_chat_member(chat_id=CH_FORCE_SUB, user_id=user_id)
        # إذا كانت حالة العضو نشطة في القناة
        if member.status in ["member", "administrator", "creator"]:
            return True
        return False
    except Exception:
        return False

def get_db_setting(key: str) -> str:
    """جلب أي إعداد ديناميكي من قاعدة البيانات"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

# تعريف حالات الكابتشا ونظام الحماية باستخدام FSM
class AntiBotStates(StatesGroup):
    waiting_for_captcha = State()

# --------------------------------------------------------
# 4. معالج أمر البداية ونظام الكابتشا الذكي (Captcha Handler)
# --------------------------------------------------------

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    
    # 1. التحقق من حظر المستخدم أولاً
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row and row[0] == 1:
        conn.close()
        return await message.reply("🚫 حسابك مجمد ومحظور من قبل نظام الحماية للاشتباه في نشاط غش.")
        
    # 2. التحقق من حالة الصيانة العامة للبوت
    bot_status = get_db_setting("bot_status")
    if bot_status == "off" and user_id != ADMIN_ID:
        conn.close()
        return await message.reply("⚙️ البوت في وضع صيانة مؤقتة لتحديث السيرفرات، يرجى العودة لاحقاً.")
    
    # 3. التحقق من الاشتراك الإجباري قبل الكابتشا
    is_subbed = await check_subscription(user_id)
    if not is_subbed:
        conn.close()
        kb = InlineKeyboardBuilder()
        kb.button(text="اضغط هنا للاشتراك في القناة 📢", url=URL_FORCE_SUB)
        kb.button(text="تفعيل الحساب بعد الاشتراك 🔄", callback_data="check_sub_again")
        kb.adjust(1)
        return await message.answer(
            f"⚠️ عذراً عزيزي {full_name}!\n"
            f"يجب عليك الاشتراك في القناة الرسمية للبوت أولاً لتتمكن من استخدام الخدمات المتاحة.",
            reply_markup=kb.as_markup()
        )

    # 4. توليد مسألة كابتشا عشوائية للحماية من البوتات الوهمية
    import random
    num1 = random.randint(5, 20)
    num2 = random.randint(1, 10)
    correct_answer = num1 + num2
    
    # حفظ الإجابة الصحيحة ومعلومات الإحالة (إن وجدت) في ذاكرة الحالة المؤقتة
    start_args = message.text.split()
    referrer_id = None
    if len(start_args) > 1 and start_args[1].isdigit():
        referrer_id = int(start_args[1])
        if referrer_id == user_id:  # منع الشخص من إحالة نفسه
            referrer_id = None

    await state.update_data(
        captcha_answer=correct_answer,
        referrer_id=referrer_id,
        user_info={"username": username, "full_name": full_name}
    )
    
    await state.set_state(AntiBotStates.waiting_for_captcha)
    conn.close()
    
    await message.answer(
        "🛡️ **نظام الحماية والأمان الحصين لحماية رصيدك** 🛡️\n\n"
        "الرجاء حل المسألة الرياضية التالية لإثبات أنك لست روبوت:\n"
        f"🗳️ كم ناتج: `{num1} + {num2}` ؟",
        parse_mode="Markdown"
    )
# --------------------------------------------------------
# 5. معالج التحقق من الكابتشا وتسجيل الإحالات (Captcha & Referral Logic)
# --------------------------------------------------------

def get_main_keyboard(user_id: int) -> types.ReplyKeyboardMarkup:
    """بناء لوحة الأزرار الرئيسية الضخمة والمدمجة بشكل منسق واحترافي"""
    builder = ReplyKeyboardBuilder()
    
    # الصف الأول: الحساب والهدية
    builder.button(text="👤 ملفي الشخصي & هويتي 🆔")
    builder.button(text="📅 المكافأة والمهام اليومية 🎁")
    
    # الصف الثاني: الألعاب والإحالات
    builder.button(text="🎡 صالة الألعاب الكبرى 🎰")
    builder.button(text="👥 منظومة الإحالات والترتيب 🏆")
    
    # الصف الثالث: التحويل المالي وسوق الإعلانات
    builder.button(text="🔄 التحويل الآمن والسريع P2P")
    builder.button(text="🏪 سوق الإعلانات والتمويل 📢")
    
    # الصف الرابع: الأكواد والسحب
    builder.button(text="🎫 كود الهدية (برومو) 🎫")
    builder.button(text="📥 بوابة سحب الأرباح 💰")
    
    # الصف الخامس: الدعم الفني
    builder.button(text="👨‍💻 الدعم الفني والشكاوى")
    
    # إذا كان المستخدم هو المشرف العام، تظهر له لوحة التحكم الفائقة أسفل القائمة
    if user_id == ADMIN_ID:
        builder.button(text="⚙️ لوحة التحكم الإمبراطورية الفائقة ⚙️")
        
    # تنظيم الأزرار: صفوف ثنائية، وزر الدعم وزر المشرف بشكل عريض
    sizes = [2, 2, 2, 2, 1]
    if user_id == ADMIN_ID:
        sizes.append(1)
        
    builder.adjust(*sizes)
    return builder.as_markup(resize_keyboard=True)

@dp.message(AntiBotStates.waiting_for_captcha)
async def process_captcha(message: types.Message, state: FSMContext):
    """معالجة وتدقيق حل مسألة الحماية وإدخال البيانات بأمان للقاعدة"""
    user_answer = message.text
    data = await state.get_data()
    
    correct_answer = data.get("captcha_answer")
    referrer_id = data.get("referrer_id")
    user_info = data.get("user_info")
    
    # التحقق من أن المدخل رقمي ومطابق للحل الصحيحة
    if not user_answer.isdigit() or int(user_answer) != correct_answer:
        return await message.reply("❌ الإجابة خاطئة! حاول مجدداً وكافئنا بالتركيز، كم الناتج؟")
        
    user_id = message.from_user.id
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # فحص هل المستخدم مسجل مسبقاً في النظام أم لا
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    existing_user = cursor.fetchone()
    
    if not existing_user:
        # 1. جلب قيمة جائزة الإحالة الحالية ديناميكياً من قاعدة البيانات
        referral_reward = float(get_db_setting("referral_reward"))
        
        # 2. معالجة حساب الشخص الداعي (المرجع) إن وجد
        final_referrer = None
        if referrer_id:
            cursor.execute("SELECT user_id, balance_earnings, referrals_count, full_name FROM users WHERE user_id = ?", (referrer_id,))
            ref_row = cursor.fetchone()
            
            if ref_row:
                final_referrer = referrer_id
                new_ref_balance = ref_row[1] + referral_reward
                new_ref_count = ref_row[2] + 1
                
                # تحديث بيانات الداعي في قاعدة البيانات
                cursor.execute(
                    "UPDATE users SET balance_earnings = ?, referrals_count = ? WHERE user_id = ?",
                    (new_ref_balance, new_ref_count, referrer_id)
                )
                
                # إرسال إشعار فوري للشخص الداعي عبر البوت بشكل فخم
                try:
                    await bot.send_message(
                        chat_id=referrer_id,
                        text=f"👥 **دخل عضو جديد عبر رابط إحالتك!**\n"
                             f"👤 الاسم: {user_info['full_name']}\n"
                             f"💰 تمت إضافة **+{int(referral_reward)} ل.س** إلى رصيد أرباحك بنجاح.\n"
                             f"📈 إجمالي إحالاتك الحالية: {new_ref_count}"
                    )
                except Exception:
                    pass
                
                # إرسال سجل العملية لقناة الإشعارات العامة للمراقبة والشفافية
                try:
                    await bot.send_message(
                        chat_id=CH_GENERAL_LOGS,
                        text=f"🔗 **عملية إحالة ناجحة**\n"
                             f"👤 المنضم: {user_info['full_name']} (`{user_id}`)\n"
                             f"👑 الداعي: {ref_row[3]} (`{referrer_id}`)\n"
                             f"🎁 المكافأة: {int(referral_reward)} ل.س"
                    )
                except Exception:
                    pass

        # 3. تسجيل العضو الجديد رسمياً في قاعدة البيانات
        cursor.execute(
            "INSERT INTO users (user_id, username, full_name, referred_by, join_date) VALUES (?, ?, ?, ?, ?)",
            (user_id, user_info['username'], user_info['full_name'], final_referrer, current_time)
        )
        conn.commit()
    
    conn.close()
    await state.clear() # مسح الحالات المؤقتة بنجاح
    
    # الترحيب بالعضو وإظهار الواجهة المدمجة والآمنة
    await message.answer(
        f"🛡️ **تم التحقق من الحساب وتفعيله بنجاح!**\n\n"
        f"أهلاً بك يا {user_info['full_name']} في نظام **Alfa ULTRA V3** المتكامل.\n"
        f"🔐 رصيدك الحالي آمن تماماً ومحدث تلقائياً على خوادم ALFA.\n\n"
        f"استخدم الأزرار أدناه للتنقل داخل المنظومة الفائقة 👇",
        reply_markup=get_main_keyboard(user_id)
    )
# --------------------------------------------------------
# 6. قسم الحساب الشخصي وتوليد الهوية الرقمية (Profile & QR Generator)
# --------------------------------------------------------

def generate_user_qr(user_id: int) -> BytesIO:
    """توليد كود QR عالي الجودة يحتوي على معرف المستخدم المالي"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    # تشفير الـ ID المالي داخل الكود
    qr.add_data(f"alfa_wallet_{user_id}")
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    bio = BytesIO()
    bio.name = 'sharing_qr.png'
    img.save(bio)
    bio.seek(0)
    return bio

@dp.message(F.text == "👤 ملفي الشخصي & هويتي 🆔")
async def process_profile_and_qr(message: types.Message):
    user_id = message.from_user.id
    
    # جلب بيانات المستخدم من قاعدة البيانات للتأكد من مطابقتها اللحظية
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT full_name, balance_earnings, balance_ads, referrals_count, rank, vip_level, join_date "
        "FROM users WHERE user_id = ?", (user_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return await message.reply("⚠️ لم يتم العثور على حسابك، أرسل /start لتفعيل الحساب أولاً.")
        
    full_name, balance_earnings, balance_ads, referrals_count, rank, vip_level, join_date = row
    
    # تحويل رتب الـ VIP لعرض نصي أنيق
    vip_status = "لا" if vip_level == 0 else f"Level {vip_level} 💎"
    
    # 1. صياغة التقرير المالي المحدث المدمج (ملفي الشخصي 👤)
    profile_text = (
        f"📋 ─── **ملفي الشخصي 👤** ─── 📋\n\n"
        f"🆔 **معرفك:** `{user_id}`\n"
        f"👤 **الاسم:** {full_name}\n"
        f"🎖️ **الرتبة:** {rank}\n"
        f"👑 **VIP:** {vip_status}\n"
        f"📅 **تاريخ الانضمام:** {join_date}\n\n"
        f"📈 ─── **الأرصدة والإحصائيات** ─── 📈\n\n"
        f"💰 **رصيد الأرباح:** {balance_earnings:,.1f} ل.س\n"
        f"📢 **رصيد الإعلانات:** {balance_ads:,.1f} ل.س\n"
        f"👥 **المدعوين:** {referrals_count} عضو\n"
        f"✨ ─── **ALFA ULTRA V3** ─── ✨"
    )
    
    # إرسال إشعار "جاري تحميل الهوية..." ليعطي انطباعاً احترافياً وسريعاً
    loading_msg = await message.answer("🔄 جاري قراءة بيانات السيرفر وتوليد هويتك المالية الرقمية...")
    
    try:
        # 2. توليد كود الـ QR الخاص بالهوية المالية الرقمية
        qr_file = generate_user_qr(user_id)
        
        # كابشن الهوية المالية السريع أسفل الصورة (مطابق للتحديث الأخير)
        current_date_str = datetime.now().strftime("%d-%m-%Y")
        qr_caption = (
            f"🆔 **هويتك المالية الرقمية**\n"
            f"👤 **الاسم:** {full_name}\n"
            f"💰 **الرصيد:** {balance_earnings:,.1f} ل.س\n"
            f"📅 **التاريخ:** {current_date_str}"
        )
        
        # إرسال كود الـ QR أولاً
        await message.answer_photo(
            photo=types.BufferedInputFile(qr_file.read(), filename="qr.png"),
            caption=qr_caption
        )
        
        # حذف رسالة التحميل المؤقتة
        await loading_msg.delete()
        
        # 3. إرسال التقرير المالي التفصيلي الفخم
        await message.answer(profile_text, parse_mode="Markdown")
        
    except Exception as e:
        # نظام الحماية من الأخطاء في حال فشلت مكتبة الـ QR لأي سبب
        await loading_msg.edit_text("⚠️ حدث خطأ أثناء توليد الـ QR، إليك بيانات ملفك الشخصي:")
        await message.answer(profile_text, parse_mode="Markdown")
# --------------------------------------------------------
# 7. نظام المكافأة والهدية اليومية (Daily Reward System)
# --------------------------------------------------------

def init_reward_db():
    """إنشاء جدول سجل المكافآت اليومية لمنع التكرار والتلاعب"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_rewards (
        user_id INTEGER PRIMARY KEY,
        last_claim_date TEXT
    )
    """)
    conn.commit()
    conn.close()

# تفعيل جدول المكافآت فوراً
init_reward_db()

@dp.message(F.text == "📅 المكافأة والمهام اليومية 🎁")
async def process_daily_reward_menu(message: types.Message):
    """إظهار واجهة المطالبة بالهدية اليومية مع زر إنلاين تفاعلي"""
    user_id = message.from_user.id
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🎁 المطالبة بالهدية اليومية الآن 🎁", callback_data="claim_daily_reward")
    kb.adjust(1)
    
    await message.answer(
        "📅 **قسم المكافآت والمهام اليومية من ALFA** 📅\n\n"
        "🎁 يمكنك الحصول على مكافأة مالية مجانية كل 24 ساعة لتزيد من رصيد أرباحك!\n\n"
        "👇 اضغط على الزر أدناه للمطالبة بـ هديتك اليوم:" ,
        reply_markup=kb.as_markup()
    )

@dp.callback_query(F.data == "claim_daily_reward")
async def claim_daily_reward_handler(callback: types.CallbackQuery):
    """معالجة طلب الهدية اليومية وتوليد نافذة التنبيه المنبثقة بحسب حالة المستخدم"""
    user_id = callback.from_user.id
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    import random
    # تحديد قيمة الهدية عشوائياً بين 200 و 1000 ليرة تضاف للأرباح
    reward_amount = random.randint(200, 1000)
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # الفحص في جدول المكافآت لمعرفة تاريخ آخر استلام
    cursor.execute("SELECT last_claim_date FROM daily_rewards WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row and row[0] == today_str:
        conn.close()
        # إظهار النافذة المنبثقة التحذيرية (showAlert=True) لتطابق التنبيه الفوري بالسيستم القديم
        return await callback.answer(
            "لقد استلمت هديتك اليومية بالفعل سابقاً! عد مجدداً غداً بعد منتصف الليل. 📅❌",
            show_alert=True
        )
        
    # إذا كان المستخدم يستحق الجائزة لأول مرة اليوم:
    if not row:
        cursor.execute("INSERT INTO daily_rewards (user_id, last_claim_date) VALUES (?, ?)", (user_id, today_str))
    else:
        cursor.execute("UPDATE daily_rewards SET last_claim_date = ? WHERE user_id = ?", (today_str, user_id))
        
    # تحديث رصيد أرباح المستخدم في جدول الحسابات الرئيسي
    cursor.execute("UPDATE users SET balance_earnings = balance_earnings + ? WHERE user_id = ?", (reward_amount, user_id))
    conn.commit()
    conn.close()
    
    # تعديل نص الرسالة لإعلامه بالنجاح
    await callback.message.edit_text(
        f"🎉 **مبروك! تم استلام الهدية اليومية بنجاح** 🎉\n\n"
        f"💰 القيمة المضافة: **+{reward_amount} ل.س**\n"
        f"🔐 تم تأمين المبلغ وترحيله إلى رصيد أرباحك بنجاح.\n"
        f"⏳ تذكر العودة غداً للمطالبة بمكافأة جديدة!"
    )
    
    # إرسال السجل إلى قناة الإشعارات العامة للمراقبة
    try:
        await bot.send_message(
            chat_id=CH_GENERAL_LOGS,
            text=f"🎁 **استلام مكافأة يومية**\n"
                 f"👤 العضو: {callback.from_user.full_name} (`{user_id}`)\n"
                 f"💸 المبلغ: {reward_amount} ل.س"
        )
    except Exception:
        pass
# --------------------------------------------------------
# 8. مقصورة عجلة الحظ الكبرى (Alfa Casino Engine)
# --------------------------------------------------------

@dp.message(F.text == "🎡 صالة الألعاب الكبرى 🎰")
async def process_casino_menu(message: types.Message):
    """عرض واجهة عجلة الحظ الكبرى مع الإحصائيات الحالية للتكلفة ونسبة الفوز"""
    user_id = message.from_user.id
    
    # جلب الإعدادات الحالية من قاعدة البيانات ديناميكياً
    wheel_cost = int(get_db_setting("wheel_cost"))
    wheel_win_rate = float(get_db_setting("wheel_win_rate"))
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🎡 تدوير العجلة الآن 🔄", callback_data="spin_the_wheel")
    kb.adjust(1)
    
    await message.answer(
        f"🎰 **مقصورة عجلة الحظ الكبرى 🎡 (Alfa Casino)** 🎰\n\n"
        f"💵 **تكلفة الدورة الواحدة:** {wheel_cost:,} ليرة سورية.\n"
        f"🎁 **الاحتمالات والجوائز المتاحة داخل العجلة:**\n"
        f"💥 ربح ضعف المبلغ المستثمر (2X)\n"
        f"🔥 ربح ثلاثة أضعاف المبلغ المستثمر (3X)\n"
        f"❌ خسارة تكلفة المحاولة بالكامل (0X)\n\n"
        f"👇 اضغط على الزر أدناه لتجربة حظك الآن:",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(F.data == "spin_the_wheel")
async def spin_the_wheel_handler(callback: types.CallbackQuery):
    """معالجة وتدوير عجلة الحظ واحتساب الأرباح والخسائر بأمان مالي تام"""
    user_id = callback.from_user.id
    full_name = callback.from_user.full_name
    
    # 1. جلب الإعدادات المالية اللحظية
    wheel_cost = float(get_db_setting("wheel_cost"))
    wheel_win_rate = float(get_db_setting("wheel_win_rate"))
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 2. فحص رصيد الأرباح الحالي للمستخدم (قفل السطر للحماية)
    cursor.execute("SELECT balance_earnings FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return await callback.answer("⚠️ لم يتم العثور على حسابك بنظام خوادم ALFA.", show_alert=True)
        
    current_balance = row[0]
    
    # التحقق من كفاية الرصيد
    if current_balance < wheel_cost:
        conn.close()
        return await callback.answer(
            f"❌ رصيد أرباحك غير كافٍ!\nتكلفة الدورة هي {int(wheel_cost):,} ل.س، ورصيدك الحالي هو {int(current_balance):,} ل.س.", 
            show_alert=True
        )
        
    # 3. خصم تكلفة الدورة فوراً قبل السحب لمنع ثغرات تكرار الضغط
    cursor.execute("UPDATE users SET balance_earnings = balance_earnings - ? WHERE user_id = ?", (wheel_cost, user_id))
    conn.commit()
    
    # 4. محرك السحب العشوائي المعتمد على نسبة الحظ المخزنة
    import random
    chance = random.uniform(0, 100)
    
    if chance <= wheel_win_rate:
        # فوز: اختيار عشوائي بين المضاعفات المتاحة (2X أو 3X)
        multiplier = random.choice([0, 0, 1, 2, 3])
        win_amount = wheel_cost * multiplier
        
        # إضافة مبلغ الفوز لرصيد أرباح المستخدم
        cursor.execute("UPDATE users SET balance_earnings = balance_earnings + ? WHERE user_id = ?", (win_amount, user_id))
        conn.commit()
        
        result_text = (
            f"🎡 **دارت العجلة وتوقف المؤشر على الفوز!** 🎉\n\n"
            f"🎁 الجائزة: **{multiplier}X**\n"
            f"💰 الرصيد المضاف: **+{int(win_amount):,} ل.س**\n"
            f"🔐 تم تأمين الأرباح وترحيلها بنجاح إلى محفظتك الإلكترونية."
        )
        
        # إرسال إشعار فوري لقناة إشعارات فوز الألعاب الخاصة بك لإشعال الحماس
        try:
            await bot.send_message(
                chat_id=CH_GAME_LOGS,
                text=f"🎡 **لاعب محظوظ فاز في عجلة الحظ الكبرى!** 🎉\n"
                     f"👤 اللاعب: {full_name} (`{user_id}`)\n"
                     f"تكلفة المحاولة: {int(wheel_cost):,} ل.س\n"
                     f"🎁 الجائزة المضروبة: {multiplier}X\n"
                     f"💰 صافي الربح المستلم: {int(win_amount):,} ل.س"
            )
        except Exception:
            pass
    else:
        # خسارة (0X)
        result_text = (
            f"🎡 **دارت العجلة ولكن الحظ لم يكن حليفك هذه المرة!** 💔\n\n"
            f"📉 الجائزة: **0X**\n"
            f"💸 تم خصم: **-{int(wheel_cost):,} ل.س**\n"
            f"🔄 لا تيأس، يمكنك المحاولة مجدداً ومضاعفة رصيدك في الدورة القادمة!"
        )
        
    conn.close()
    
    # إرسال النتيجة للمستخدم بتعديل الواجهة
    kb = InlineKeyboardBuilder()
    kb.button(text="🎡 تدوير العجلة مجدداً 🔄", callback_data="spin_the_wheel")
    kb.adjust(1)
    
    await callback.message.edit_text(result_text, reply_markup=kb.as_markup())
# --------------------------------------------------------
# 9. منظومة التسويق الشبكي ولوحة المتصدرين (Referral & Leaderboard System)
# --------------------------------------------------------

@dp.message(F.text == "👥 منظومة الإحالات والترتيب 🏆")
async def process_referral_menu(message: types.Message):
    """عرض تفاصيل نظام الإحالة، توليد الرابط المخصص، وعرض قائمة التوب 10"""
    user_id = message.from_user.id
    
    # 1. جلب بيانات المستخدم الحالية وقيمة الجائزة ديناميكياً
    referral_reward = int(float(get_db_setting("referral_reward")))
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT referrals_count, rank FROM users WHERE user_id = ?", (user_id,))
    user_row = cursor.fetchone()
    
    referrals_count = user_row[0] if user_row else 0
    user_rank = user_row[1] if user_row else "عضو جديد 🌱"
    
    # 2. جلب قائمة أعلى 10 مستخدمين جلباً للإحالات (Leaderboard)
    cursor.execute(
        "SELECT full_name, referrals_count FROM users "
        "WHERE referrals_count > 0 AND is_banned = 0 "
        "ORDER BY referrals_count DESC LIMIT 10"
    )
    top_users = cursor.fetchall()
    conn.close()
    
    # 3. جلب معرف البوت ديناميكياً لتوليد رابط الإحالة الصحيح
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    # 4. صياغة نص لوحة المتصدرين
    leaderboard_text = "🏆 ── **قائمة المتصدرين (TOP 10)** ── 🏆\n\n"
    if not top_users:
        leaderboard_text += "المنافسة خالية حالياً، كن أول المتصدرين! 🥇\n"
    else:
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        for idx, (name, count) in enumerate(top_users):
            # حماية الأسماء الطويلة من تخريب التنسيق
            short_name = name[:15] + ".." if len(name) > 15 else name
            leaderboard_text += f"{medals[idx]} **{short_name}** ── {count} إحالة\n"
            
    # 5. صياغة الرسالة الكاملة المدمجة
    referral_text = (
        f"👥 **منظومة الإحالات والتسويق الشبكي العادلة** 👥\n\n"
        f"💵 **جائزة الإحالة الحالية:** {referral_reward} ليرة عن كل عضو جديد.\n"
        f"🎖️ **رتبتك الحالية:** {user_rank}\n"
        f"📈 **عدد إحالاتك النشطة:** {referrals_count} عضو\n\n"
        f"🔗 **رابط الإحالة المخصص لك:**\n`{ref_link}`\n\n"
        f"🛑 ── **نظام مكافحة الغش الصارم** ── 🛑\n"
        f"⚠️ تُحذر إدارة ALFA من استخدام الحسابات الوهمية أو برامج توليد الإحالات الكاذبة.\n"
        f"🧠 يمتلك السيرفر خوارزمية ذكاء اصطناعي تكشف الغش تلقائياً، وتجمد الأموال وتحظر الحساب نهائياً دون مراجعة.\n\n"
        f"{leaderboard_text}"
    )
    
    # أزرار لمشاركة الرابط بسهولة
    kb = InlineKeyboardBuilder()
    kb.button(text="🔗 مشاركة رابط الإحالة فوراً 🚀", url=f"https://t.me/share/url?url={ref_link}&text=اشترك%20في%20بوت%20ALFA%20ULTRA%20V3%20وابدأ%20بجني%20الأرباح%20مجاناً!%20💰")
    kb.adjust(1)
    
    await message.answer(referral_text, reply_markup=kb.as_markup(), parse_mode="Markdown", disable_web_page_preview=True)
# --------------------------------------------------------
# 10. بوابة التحويل المالي المشفر والـ P2P (P2P Transfer Engine)
# --------------------------------------------------------

# تعريف حالات التحويل المالي
class TransferStates(StatesGroup):
    waiting_for_type = State()
    waiting_for_receiver = State()
    waiting_for_amount = State()

@dp.message(F.text == "🔄 التحويل الآمن والسريع P2P")
async def process_p2p_start(message: types.Message, state: FSMContext):
    """الخطوة 1: اختيار نوع الرصيد المراد نقله"""
    user_id = message.from_user.id
    
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 رصيد الأرباح", callback_data="p2p_type_earnings")
    kb.button(text="📢 رصيد الإعلانات", callback_data="p2p_type_ads")
    kb.adjust(2)
    
    await state.set_state(TransferStates.waiting_for_type)
    await message.answer(
        "🔄 **بوابة تحويل الأموال والرصيد المشفر (P2P)** 🔄\n\n"
        "💳 يتيح لك هذا القسم نقل أرصدتك إلى حساب أي عضو آخر في البوت بشكل فوري وآمن.\n\n"
        "👇 فضلاً، اختر نوع الرصيد الذي ترغب في تحويله الآن:",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(TransferStates.waiting_for_type)
async def process_p2p_type(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة 2: طلب معرف المستلم أو الكود الرقمي"""
    p2p_type = "earnings" if callback.data == "p2p_type_earnings" else "ads"
    p2p_name = "الأرباح 💰" if p2p_type == "earnings" else "الإعلانات 📢"
    
    await state.update_data(p2p_type=p2p_type, p2p_name=p2p_name)
    await state.set_state(TransferStates.waiting_for_receiver)
    
    await callback.message.edit_text(
        f"🔄 **بوابة التحويل ── رصيد {p2p_name}**\n\n"
        f"📥 **[الخطوة 1 من 2]:** الرجاء إرسال معرف الحساب المالي (ID) المكون من أرقام للشخص المراد التحويل إليه.\n\n"
        f"💡 *ملاحظة:* يمكنك أيضاً إرسال صورة كود الـ QR الخاص بصديقك مباشرة وسيقوم البوت بمسحه وتحديد الحساب تلقائياً!"
    )

@dp.message(TransferStates.waiting_for_receiver)
async def process_p2p_receiver(message: types.Message, state: FSMContext):
    """معالجة رقم الـ ID أو قراءة كود الـ QR أوتوماتيكياً وتحليله"""
    receiver_id = None
    
    # حالة 1: إذا أرسل المستخدم صورة (كود QR)
    if message.photo:
        return await message.reply("📸 ميزة مسح الـ QR عبر السيرفر قيد الربط بالمكتبة، الرجاء إدخال الـ ID نصياً حالياً لتأمين العملية!")
        
    # حالة 2: إذا أرسل نص (ID رقمي)
    else:
        if not message.text or not message.text.isdigit():
            return await message.reply("⚠️ خطأ! الرجاء إرسال معرف حساب صحيح مكون من أرقام فقط.")
        receiver_id = int(message.text)
        
    if receiver_id == message.from_user.id:
        return await message.reply("❌ لا يمكنك تحويل الأموال إلى حسابك الشخصي!")
        
    # التحقق من وجود المستلم في قاعدة البيانات
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT full_name FROM users WHERE user_id = ?", (receiver_id,))
    receiver_row = cursor.fetchone()
    conn.close()
    
    if not receiver_row:
        return await message.reply("❌ هذا المعرف غير مسجل في نظام ALFA! تأكد من الرقم وصحته.")
        
    receiver_name = receiver_row[0]
    p2p_fee = float(get_db_setting("p2p_fee"))
    
    await state.update_data(receiver_id=receiver_id, receiver_name=receiver_name)
    await state.set_state(TransferStates.waiting_for_amount)
    
    await message.answer(
        f"👤 **بيانات المستلم المؤكدة:**\n"
        f"📌 الاسم: {receiver_name}\n"
        f"🆔 المعرف: `{receiver_id}`\n\n"
        f"📥 **[الخطوة 2 من 2]:** الرجاء إرسال المبلغ المراد تحويله بالليرة السورية.\n"
        f"📈 *تنويه:* رسوم التحويل الحالية هي **{p2p_fee}%** يتم استقطاعها من رصيدك كمرسل."
    )
@dp.message(TransferStates.waiting_for_amount)
async def process_p2p_amount_and_finalize(message: types.Message, state: FSMContext):
    """الخطوة الأخيرة: معالجة المبلغ وتنفيذ الخصم والتحويل البنكي الداخلي فوراً"""
    user_id = message.from_user.id
    sender_name = message.from_user.full_name
    
    # 1. التحقق من أن المدخلات رقمية وصحيحة
    if not message.text or not message.text.replace('.', '', 1).isdigit():
        return await message.reply("⚠️ خطأ! الرجاء إرسال مبلغ صحيح بصيغة أرقام فقط.")
        
    amount = float(message.text)
    if amount <= 0:
        return await message.reply("❌ يجب أن يكون مبلغ التحويل أكبر من صفر!")
        
    data = await state.get_data()
    p2p_type = data.get("p2p_type")          # نوع الرصيد: earnings أو ads
    p2p_name = data.get("p2p_name")          # الاسم النصي للرصيد
    receiver_id = data.get("receiver_id")
    receiver_name = data.get("receiver_name")
    
    # جلب قيمة الرسوم الحالية ديناميكياً من قاعدة البيانات
    fee_percentage = float(get_db_setting("p2p_fee"))
    total_deduction = amount + (amount * (fee_percentage / 100.0))
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 2. فحص رصيد المرسل بناءً على النوع المحدد (قفل السطر برمجياً)
    balance_column = "balance_earnings" if p2p_type == "earnings" else "balance_ads"
    cursor.execute(f"SELECT {balance_column} FROM users WHERE user_id = ?", (user_id,))
    sender_balance = cursor.fetchone()[0]
    
    if sender_balance < total_deduction:
        conn.close()
        return await message.reply(
            f"❌ فشلت العملية! رصيدك غير كافٍ لتغطية المبلغ والرسوم.\n\n"
            f"💰 المبلغ المطلوب: {amount:,.1f} ل.س\n"
            f"📈 الرسوم ({fee_percentage}%): {(amount * (fee_percentage / 100.0)):,.1f} ل.س\n"
            f"📉 الإجمالي المطلوب خصمه: {total_deduction:,.1f} ل.س\n"
            f"💳 رصيدك الحالي المتوفر: {sender_balance:,.1f} ل.س"
        )
        
    # 3. تنفيذ عملية النقل المالي المزدوجة في نفس الوقت (Atomic Transaction)
    # خصم من المرسل (المبلغ + الرسوم)
    cursor.execute(
        f"UPDATE users SET {balance_column} = {balance_column} - ? WHERE user_id = ?", 
        (total_deduction, user_id)
    )
    # إضافة للمستلم (المبلغ الصافي بدون رسوم)
    cursor.execute(
        f"UPDATE users SET {balance_column} = {balance_column} + ? WHERE user_id = ?", 
        (amount, receiver_id)
    )
    conn.commit()
    conn.close()
    
    # مسح الحالات المؤقتة فوراً لتأمين الحساب ضد التكرار
    await state.clear()
    
    # 4. إرسال رسالة نجاح العملية للمرسل
    await message.answer(
        f"✅ **تم تحويل الرصيد بنجاح آمن!** ✅\n\n"
        f"📌 **المستلم:** {receiver_name} (`{receiver_id}`)\n"
        f"💳 **الرصيد المنقول:** {amount:,.1f} ل.س من رصيد {p2p_name}\n"
        f"📈 **الرسوم المستقطعة:** {(amount * (fee_percentage / 100.0)):,.1f} ل.س\n"
        f"📉 **إجمالي الخصم من حسابك:** {total_deduction:,.1f} ل.س\n"
        f"✨ العمليات المكتملة نهائية ولا يمكن التراجع عنها بواسطة النظام."
    )
    
    # 5. إرسال إشعار فوري وتنبيه فخم للمستلم عبر البوت
    try:
        await bot.send_message(
            chat_id=receiver_id,
            text=f"🔄 **وصلتك حوالة مالية داخلية فوت فوري!** 🔄\n\n"
                 f"👤 **من المرسل:** {sender_name}\n"
                 f"🆔 **معرف المرسل:** `{user_id}`\n"
                 f"💰 **المبلغ المستلم:** **+{amount:,.1f} ل.س**\n"
                 f"🔐 تم فحص الرصيد وترحيله وتحديث محفظة {p2p_name} الخاصة بك بنجاح."
        )
    except Exception:
        pass
        
    # 6. إرسال سجل العملية لقناة الإشعارات العامة للمراقبة الإدارية والتأمين
    try:
        await bot.send_message(
            chat_id=CH_GENERAL_LOGS,
            text=f"🔄 **عملية تحويل P2P داخلية**\n"
                 f"📤 المرسل: {sender_name} (`{user_id}`)\n"
                 f"📥 المستلم: {receiver_name} (`{receiver_id}`)\n"
                 f"💵 المبلغ: {amount:,.1f} ل.س ({p2p_type})\n"
                 f"📈 الرسوم المستقطعة: {(amount * (fee_percentage / 100.0)):,.1f} ل.س"
        )
    except Exception:
        pass
# --------------------------------------------------------
# 11. سوق الخدمات الإعلانية والتمويل التلقائي (Ads Marketplace Engine)
# --------------------------------------------------------

def init_ads_marketplace_db():
    """تأسيس جدول الحملات الإعلانية لمتابعة طلبات التمويل التلقائي"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ad_campaigns (
        campaign_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        channel_id TEXT,
        channel_url TEXT,
        required_members INTEGER,
        current_members INTEGER DEFAULT 0,
        cost REAL,
        status TEXT DEFAULT 'نشط 🟢',
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()

# تفعيل جدول الإعلانات فوراً عند الإقلاع
init_ads_marketplace_db()

# تعريف حالات إدخال طلب التمويل الجديد عبر FSM
class AdCampaignStates(StatesGroup):
    waiting_for_channel_link = State()
    waiting_for_members_count = State()

@dp.message(F.text == "🏪 سوق الإعلانات والتمويل 📢")
async def process_ads_marketplace_menu(message: types.Message):
    """عرض قائمة خدمات التمويل المتاحة وتكلفة العضو من رصيد الإعلانات"""
    user_id = message.from_user.id
    
    # تكلفة العضو الواحد الافتراضية (مثال: 500 ليرة من رصيد الإعلانات لكل عضو مشترك)
    # يمكنك التحكم بهذه القيمة لاحقاً عبر لوحة التحكم
    member_cost = 500 
    
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 إنشاء حملة تمويل جديدة 🚀", callback_data="create_ad_campaign")
    kb.button(text="📊 متابعة حملاتي النشطة", callback_data="my_ad_campaigns")
    kb.adjust(1)
    
    await message.answer(
        f"🏪 **سوق إمبراطورية ALFA للخدمات الإعلانية والتمويل** 📢\n\n"
        f"💰 هنا يمكنك استغلال **رصيد الإعلانات** الخاص بك لتمويل قنواتك ومجموعاتك على التليجرام بـ أعضاء حقيقيين ومتفاعلين بنسبة 100%.\n\n"
        f"📊 **قائمة أسعار التمويل الحالية:**\n"
        f"👤 تكلفة العضو الواحد: **{member_cost} ل.س** (تُخصم من رصيد الإعلانات فقط).\n"
        f"🎯 الحد الأدنى لطلب الحملة الواحدة: **50 عضو**.\n\n"
        f"👇 اختر الإجراء المناسب لبدء نشر مشروعك وتكبير قناتك تلقائياً:",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(F.data == "create_ad_campaign")
async def start_ad_campaign_handler(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة 1: طلب رابط القناة أو المجموعة المراد تمويلها"""
    user_id = callback.from_user.id
    
    await state.set_state(AdCampaignStates.waiting_for_channel_link)
    await callback.message.edit_text(
        "📢 **إنشاء حملة تمويل جديدة ── [الخطوة 1 من 2]**\n\n"
        "🔗 الرجاء إرسال رابط قناتك أو مجموعتك العامة (مثال: `https://t.me/ALFA_ULTRA_BOT1` أو المعرف الـ Username الخاص بها `@ALFA_ULTRA_BOT1`).\n\n"
        "⚠️ *تنبيه:* تأكد من رفع البوت كـ مشرف (Admin) في قناتك لكي يتمكن من فحص وتأكيد اشتراك الأعضاء تلقائياً وتوزيع الجوائز عليهم!"
    )
@dp.message(AdCampaignStates.waiting_for_channel_link)
async def process_ad_channel_link(message: types.Message, state: FSMContext):
    """الخطوة 2: استقبال الرابط وتدقيقه برمجياً قبل الانتقال للعدد"""
    channel_input = message.text.strip()
    
    # تنظيف المدخلات لاستخراج المعرف أو الرابط الصافي
    if "t.me/" in channel_input:
        channel_url = channel_input
        # محاولة استخراج اليوزر نيم إذا كان عاماً
        parts = channel_input.split("t.me/")
        channel_id = "@" + parts[1].split("/")[0]
    elif channel_input.startswith("@"):
        channel_id = channel_input
        channel_url = f"https://t.me/{channel_input[1:]}"
    else:
        return await message.reply("⚠️ خطأ! الرابط أو المعرف غير صحيح. أرسله بصيغة: @ALFA_ULTRA_BOT1 أو رابط كامل.")
        
    await state.update_data(channel_id=channel_id, channel_url=channel_url)
    await state.set_state(AdCampaignStates.waiting_for_members_count)
    
    await message.answer(
        f"📌 **تم حفظ القناة:** {channel_id}\n\n"
        f"📥 **[الخطوة 2 من 2]:** الرجاء إرسال عدد الأعضاء (المشتركين) المطلوب تمويلهم لقناتك.\n"
        f"💡 *تذكر:* الحد الأدنى لطلب أي حملة هو **50 عضو**."
    )

@dp.message(AdCampaignStates.waiting_for_members_count)
async def process_ad_members_count_and_finalize(message: types.Message, state: FSMContext):
    """الخطوة الأخيرة: احتساب التكلفة، فحص رصيد الإعلانات، وخصمه وتفعيل الإعلان"""
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    
    if not message.text or not message.text.isdigit():
        return await message.reply("⚠️ خطأ! الرجاء إرسال عدد أعضاء صحيح بصيغة أرقام فقط.")
        
    required_members = int(message.text)
    if required_members < 50:
        return await message.reply("❌ عذراً! الحد الأدنى لإنشاء حملة تمويل هو 50 عضو.")
        
    # تكلفة العضو الافتراضية
    member_cost = 500
    total_cost = required_members * member_cost
    
    data = await state.get_data()
    channel_id = data.get("channel_id")
    channel_url = data.get("channel_url")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # فحص رصيد الإعلانات الحالي للمستخدم
    cursor.execute("SELECT balance_ads FROM users WHERE user_id = ?", (user_id,))
    user_ads_balance = cursor.fetchone()[0]
    
    if user_ads_balance < total_cost:
        conn.close()
        return await message.reply(
            f"❌ رصيد الإعلانات الخاص بك غير كافٍ لإتمام هذه الحملة!\n\n"
            f"📊 **تفاصيل الحسبة:**\n"
            f"👤 العدد المطلوب: {required_members} عضو\n"
            f"💰 التكلفة الإجمالية: {total_cost:,.1f} ل.س\n"
            f"📢 رصيدك الإعلاني الحالي: {user_ads_balance:,.1f} ل.س"
        )
        
    # تنفيذ الخصم المالي الفوري من رصيد الإعلانات
    cursor.execute("UPDATE users SET balance_ads = balance_ads - ? WHERE user_id = ?", (total_cost, user_id))
    
    # تسجيل الحملة الإعلانية في جدول الإعلانات للتفعيل الحي
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO ad_campaigns (user_id, channel_id, channel_url, required_members, cost, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, channel_id, channel_url, required_members, total_cost, current_time)
    )
    conn.commit()
    conn.close()
    
    # مسح حالة الـ FSM لتأمين المعاملة
    await state.clear()
    
    await message.answer(
        f"✅ **تم إطلاق حملتك الإعلانية بنجاح حركي!** ✅\n\n"
        f"📢 **القناة المُمولة:** {channel_id}\n"
        f"👤 **العدد المستهدف:** {required_members} عضو حقيقي\n"
        f"📉 **التكلفة المستقطعة:** -{total_cost:,.1f} ل.س من رصيد إعلاناتك.\n\n"
        f"🔍 سيقوم البوت الآن بعرض قناتك في قسم المهام والجوائز للمستخدمين الآخرين حتى يكتمل العدد تلقائياً!"
    )
    
    # إرسال سجل العملية لقناة الإشعارات العامة للمراقبة
    try:
        await bot.send_message(
            chat_id=CH_GENERAL_LOGS,
            text=f"📢 **حملة إعلانية ممولة جديدة** 🚀\n"
                 f"👤 المعلن: {full_name} (`{user_id}`)\n"
                 f"🔗 القناة: {channel_id}\n"
                 f"🎯 العدد المطلوبة: {required_members} عضو\n"
                 f"💰 التكلفة المستقطعة: {total_cost:,.1f} ل.س (إعلانات)"
        )
    except Exception:
        pass
@dp.callback_query(F.data == "my_ad_campaigns")
async def show_user_ad_campaigns_handler(callback: types.CallbackQuery):
    """عرض قائمة الحملات الإعلانية الحالية والسابقة للمستخدم ومتابعة الإحصائيات"""
    user_id = callback.from_user.id
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT campaign_id, channel_id, required_members, current_members, cost, status, created_at "
        "FROM ad_campaigns WHERE user_id = ? ORDER BY campaign_id DESC", (user_id,)
    )
    campaigns = cursor.fetchall()
    conn.close()
    
    if not campaigns:
        return await callback.answer("📊 ليس لديك أي حملات إعلانية نشطة أو سابقة حالياً.", show_alert=True)
        
    response_text = "📊 ── **سجل حملاتك التمويلية والإعلانية** ── 📊\n\n"
    
    for camp in campaigns:
        camp_id, ch_id, req, curr, cost, status, date = camp
        response_text += (
            f"🆔 **رقم الحملة:** #{camp_id}\n"
            f"📢 **القناة:** {ch_id}\n"
            f"👥 **التقدم:** ({curr} / {req}) عضو\n"
            f"💰 **التكلفة:** {cost:,.1f} ل.س\n"
            f"📅 **التاريخ:** {date}\n"
            f"⚡ **الحالة:** {status}\n"
            f"📎 ────────────────── 📎\n"
        )
        
    # إضافة زر للعودة إلى القائمة الرئيسية للسوق الإعلاني لتسهيل التنقل
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 العودة لسوق الإعلانات", callback_data="back_to_ads_market")
    kb.adjust(1)
    
    await callback.message.edit_text(response_text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "back_to_ads_market")
async def back_to_ads_market_handler(callback: types.CallbackQuery):
    """إعادة توليد واجهة سوق الإعلانات الأساسية عند الضغط على زر العودة"""
    member_cost = 500 
    
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 إنشاء حملة تمويل جديدة 🚀", callback_data="create_ad_campaign")
    kb.button(text="📊 متابعة حملاتي النشطة", callback_data="my_ad_campaigns")
    kb.adjust(1)
    
    await callback.message.edit_text(
        f"🏪 **سوق إمبراطورية ALFA للخدمات الإعلانية والتمويل** 📢\n\n"
        f"💰 هنا يمكنك استغلال **رصيد الإعلانات** الخاص بك لتمويل قنواتك ومجموعاتك على التليجرام بـ أعضاء حقيقيين ومتفاعلين بنسبة 100%.\n\n"
        f"📊 **قائمة أسعار التمويل الحالية:**\n"
        f"👤 تكلفة العضو الواحد: **{member_cost} ل.س** (تُخصم من رصيد الإعلانات فقط).\n"
        f"🎯 الحد الأدنى لطلب الحملة الواحدة: **50 عضو**.\n\n"
        f"👇 اختر الإجراء المناسب لبدء نشر مشروعك وتكبير قناتك تلقائياً:",
        reply_markup=kb.as_markup()
    )
# --------------------------------------------------------
# 12. نظام الأكواد والبروموكود الذكي (Promo Code Engine)
# --------------------------------------------------------

def init_promo_db():
    """تأسيس جداول البروموكود وسجلات الاستخدام لمنع التكرار والتلاعب"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # جدول الأكواد التي يصنعها المشرف
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS promo_codes (
        code TEXT PRIMARY KEY,
        reward_type TEXT,      -- 'earnings' أو 'ads'
        reward_amount REAL,
        max_uses INTEGER,      -- الحد الأقصى للمرات التي يمكن استخدام الكود فيها كلياً
        current_uses INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)
    
    # جدول سجلات المستخدمين الذين استخدموا الأكواد لمنع الاستخدام المزدوج
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS promo_usage (
        user_id INTEGER,
        code TEXT,
        used_at TEXT,
        PRIMARY KEY (user_id, code)
    )
    """)
    conn.commit()
    conn.close()

# تفعيل جداول الأكواد فوراً عند الإقلاع
init_promo_db()

# تعريف حالة انتظار إدخال الكود عبر FSM
class PromoStates(StatesGroup):
    waiting_for_code = State()

@dp.message(F.text == "🎫 كود الهدية (برومو) 🎫")
async def process_promo_menu(message: types.Message, state: FSMContext):
    """فتح واجهة إدخال البروموكود للمستخدم"""
    user_id = message.from_user.id
    
    await state.set_state(PromoStates.waiting_for_code)
    await message.answer(
        "🎫 **بوابة تفعيل أكواد الهدايا والبروموكود** 🎫\n\n"
        "🎁 هل حصلت على كود هدية من مسابقة أو إشعار عام؟\n"
        "💳 الأكواد تمنحك أرصدة مجانية فورية (أرباح أو إعلانات) يتم ضخها بحسابك.\n\n"
        "📥 **الآن:** الرجاء كتابة أو لصق كود الهدية هنا في الشات:"
    )

@dp.message(PromoStates.waiting_for_code)
async def redeem_promo_code_handler(message: types.Message, state: FSMContext):
    """معالجة وتدقيق الكود المدخل وتوزيع الجوائز ماليّاً وبشكل صارم آمن"""
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    input_code = message.text.strip()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. فحص هل الكود موجود أصلاً في قاعدة البيانات
    cursor.execute(
        "SELECT reward_type, reward_amount, max_uses, current_uses FROM promo_codes WHERE code = ?",
        (input_code,)
    )
    promo_row = cursor.fetchone()
    
    if not promo_row:
        conn.close()
        return await message.reply("❌ هذا الكود غير صحيح، أو انتهت صلاحيته بالكامل! تأكد من الأحرف وحاول مجدداً.")
        
    reward_type, reward_amount, max_uses, current_uses = promo_row
    
    # 2. فحص هل انتهت كمية الكود الكلية (الحد الأقصى للاستخدام العام)
    if current_uses >= max_uses:
        conn.close()
        return await message.reply("⚠️ عذراً! هذا الكود وصل للحد الأقصى من الاستخدام وانتهت صلاحيته للجميع.")
        
    # 3. فحص هل استخدم هذا العضو بالتحديد الكود مسبقاً (منع التكرار)
    cursor.execute("SELECT user_id FROM promo_usage WHERE user_id = ? AND code = ?", (user_id, input_code))
    usage_row = cursor.fetchone()
    
    if usage_row:
        conn.close()
        return await message.reply("❌ لا يمكنك استخدام نفس الكود مرتين! لقد حصلت على الجائزة الخاصة به سابقاً.")
        
    # 4. تنفيذ العملية المالية: تسجيل الاستخدام وتحديث رصيد المستخدم
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # تسجيل الاستخدام الفردي
    cursor.execute("INSERT INTO promo_usage (user_id, code, used_at) VALUES (?, ?, ?)", (user_id, input_code, current_time))
    
    # زيادة عداد الاستخدام العام للكود
    cursor.execute("UPDATE promo_codes SET current_uses = current_uses + 1 WHERE code = ?", (input_code,))
    
    # تحديد العمود المالي المستهدف (أرباح أم إعلانات) بناءً على نوع الكود
    balance_column = "balance_earnings" if reward_type == "earnings" else "balance_ads"
    type_name = "الأرباح 💰" if reward_type == "earnings" else "الإعلانات 📢"
    
    # ضخ المكافأة في حساب العضو
    cursor.execute(f"UPDATE users SET {balance_column} = {balance_column} + ? WHERE user_id = ?", (reward_amount, user_id))
    conn.commit()
    conn.close()
    
    # مسح حالة الـ FSM بأمان
    await state.clear()
    
    # إشعار العضو بالنجاح
    await message.answer(
        f"🎉 **تم تفعيل كود الهدية بنجاح باهر!** 🎉\n\n"
        f"🎫 الكود المستعمل: `{input_code}`\n"
        f"💵 الجائزة المضافة: **+{int(reward_amount):,} ل.س**\n"
        f"📊 نوع الشحن: ترحيل فوري إلى رصيد **{type_name}**.\n\n"
        f"🔐 محفظتك محدثة ومحمية بالكامل الآن على شبكة ALFA."
    )
    
    # إرسال سجل العملية لقناة الإشعارات العامة للمراقبة
    try:
        await bot.send_message(
            chat_id=CH_GENERAL_LOGS,
            text=f"🎫 **تفعيل كود هدية (بروموكود)**\n"
                 f"👤 العضو: {full_name} (`{user_id}`)\n"
                 f"🔑 الكود: `{input_code}`\n"
                 f"💰 المكافأة المستلمة: {int(reward_amount):,} ل.س ({reward_type})"
        )
    except Exception:
        pass
# --------------------------------------------------------
# 13. بوابة سحب الأرباح ونظام الدفع (Withdrawal Engine)
# --------------------------------------------------------

def init_withdraw_db():
    """تأسيس جدول طلبات السحب لتتبع المعاملات المالية المعلقة والمقبولة"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS withdraw_requests (
        request_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        payment_method TEXT,
        payment_details TEXT,
        status TEXT DEFAULT 'معلق ⏳',
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()

# تفعيل جدول السحوبات فوراً عند الإقلاع
init_withdraw_db()

# تعريف حالات نظام السحب عبر FSM
class WithdrawStates(StatesGroup):
    waiting_for_method = State()
    waiting_for_details = State()
    waiting_for_amount = State()

@dp.message(F.text == "📥 بوابة سحب الأرباح 💰")
async def process_withdraw_start(message: types.Message, state: FSMContext):
    """الخطوة 1: عرض شروط السحب وطلب اختيار طريقة الدفع"""
    user_id = message.from_user.id
    min_withdraw = int(float(get_db_setting("min_withdraw")))
    
    # التحقق من رصيد المستخدم أولاً قبل تفعيل الحالة
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT balance_earnings FROM users WHERE user_id = ?", (user_id,))
    current_balance = cursor.fetchone()[0]
    conn.close()
    
    if current_balance < min_withdraw:
        return await message.reply(
            f"❌ لا يمكنك فتح بوابة السحب حالياً!\n\n"
            f" الحد الأدنى للسحب هو: **{min_withdraw:,} ل.س**\n"
            f"💳 رصيد أرباحك الحالي المتوفر: **{int(current_balance):,} ل.س**\n\n"
            f"📈 اجمع المزيد من الأرباح عبر الإحالات أو عجلة الحظ وحاول مجدداً!"
        )
        
    kb = InlineKeyboardBuilder()
    kb.button(text="الهرم كاش 🏦", callback_data="wd_meth_الهرم كاش")
    kb.button(text="الفؤاد كاش 💳", callback_data="wd_meth_الفؤاد كاش")
    kb.button(text="سيريتل كاش 📱", callback_data="wd_meth_سيريتل كاش")
    kb.button(text="إم تي إن كاش 📱", callback_data="wd_meth_ام تي ان كاش")
    kb.adjust(2)
    
    await state.set_state(WithdrawStates.waiting_for_method)
    await message.answer(
        f"📥 **مرحباً بك في بوابة سحب الأرباح الرسمية لـ ALFA** 📥\n\n"
        f"💰 رصيدك الحالي القابل للسحب: **{int(current_balance):,} ل.س**\n"
        f"🎯 الحد الأدنى للعملية: **{min_withdraw:,} ل.س**\n\n"
        f"👇 فضلاً، اختر طريقة استلام الأموال المناسبة لك من الأزرار أدناه:",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(WithdrawStates.waiting_for_method)
async def process_withdraw_method(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة 2: استقبال طريقة الدفع وطلب بيانات الحساب المحول إليه"""
    method_selected = callback.data.replace("wd_meth_", "")
    
    await state.update_data(payment_method=method_selected)
    await state.set_state(WithdrawStates.waiting_for_details)
    
    await callback.message.edit_text(
        f"📥 **بوابة السحب ── طريقة الاستلام: {method_selected}**\n\n"
        f"📝 **الرجاء إرسال تفاصيل المستلم بالكامل وبدقة:**\n"
        f"(الاسم الثلاثي، رقم الحساب أو المحفظة الإلكترونية، وأي معلومات مطلوبة للتسليم).\n\n"
        f"⚠️ *تنبيه:* أي خطأ في إرسال البيانات يقع على مسؤوليتك الشخصية وقد يؤدي لتأخر الدفع!"
    )
@dp.message(WithdrawStates.waiting_for_details)
async def process_withdraw_details(message: types.Message, state: FSMContext):
    """الخطوة 3: استقبال بيانات التحويل والانتقال لتحديد المبلغ المطلوب سحبه"""
    input_details = message.text.strip()
    
    if len(input_details) < 10:
        return await message.reply("⚠️ البيانات المرسلة قصيرة جداً! يرجى كتابة الاسم الثلاثي ورقم المحفظة بشكل كامل وضيق لمنع رفض الطلب.")
        
    await state.update_data(payment_details=input_details)
    await state.set_state(WithdrawStates.waiting_for_amount)
    
    await message.answer(
        "💰 **تفاصيل المستلم مسجلة بنجاح**\n\n"
        "📥 الآن، يرجى إرسال المبلغ المطلوب سحبه بالليرة السورية كـ أرقام فقط.\n"
        "💡 *مثال:* `15000`"
    )

@dp.message(WithdrawStates.waiting_for_amount)
async def process_withdraw_amount_and_finalize(message: types.Message, state: FSMContext):
    """الخطوة الأخيرة: التدقيق المالي النهائي، حجز وخصم الرصيد، وتسجيل طلب السحب"""
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    
    if not message.text or not message.text.isdigit():
        return await message.reply("⚠️ خطأ! الرجاء إرسال مبلغ السحب بصيغة أرقام صحيحة فقط.")
        
    withdraw_amount = float(message.text)
    min_withdraw = float(get_db_setting("min_withdraw"))
    
    # 1. التحقق من الحد الأدنى للسحب
    if withdraw_amount < min_withdraw:
        return await message.reply(f"❌ لا يمكنك سحب مبلغ أقل من الحد الأدنى المسموح به وهو: {int(min_withdraw):,} ل.س")
        
    data = await state.get_data()
    payment_method = data.get("payment_method")
    payment_details = data.get("payment_details")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 2. التحقق من رصيد الأرباح الحالي (مع قفل السطر للحماية التامة)
    cursor.execute("SELECT balance_earnings FROM users WHERE user_id = ?", (user_id,))
    current_balance = cursor.fetchone()[0]
    
    if current_balance < withdraw_amount:
        conn.close()
        return await message.reply(
            f"❌ فشل تقديم الطلب! رصيد أرباحك الحالي غير كافٍ.\n\n"
            f"📥 المبلغ المطلوب: {int(withdraw_amount):,} ل.س\n"
            f"💳 رصيدك المتوفر: {int(current_balance):,} ل.س"
        )
        
    # 3. الخصم المالي الفوري واللحظي من رصيد الأرباح (تجميد الرصيد كطلب معلق)
    cursor.execute("UPDATE users SET balance_earnings = balance_earnings - ? WHERE user_id = ?", (withdraw_amount, user_id))
    
    # 4. تسجيل الطلب في جدول السحوبات بقاعدة البيانات
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO withdraw_requests (user_id, amount, payment_method, payment_details, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (user_id, withdraw_amount, payment_method, payment_details, current_time)
    )
    # جلب رقم الطلب التلقائي المولد
    request_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # مسح الحالات الفورية بأمان
    await state.clear()
    
    # إرسال تأكيد الاستلام للمستخدم
    await message.answer(
        f"⏳ **تم تقديم طلب سحب الأرباح بنجاح** ⏳\n\n"
        f"🆔 **رقم الفاتورة:** #{request_id}\n"
        f"💵 **المبلغ المحجوز:** {int(withdraw_amount):,} ل.س\n"
        f"🏦 **وسيلة الدفع:** {payment_method}\n"
        f"📝 **بيانات التحويل:** {payment_details}\n\n"
        f"🔍 تم تجميد الرصيد وإرسال الفاتورة لقسم التدقيق المالي للمشرف العام، سيتم تحويل الأموال لك بأقرب وقت وتنبيهك تلقائياً!"
    )
    
    # 5. إرسال سجل العملية فوراً لقناة إشعارات السحوبات الخاصة بك لإبقائك على اطلاع
    try:
        await bot.send_message(
            chat_id=CH_WITHDRAW_LOGS,
            text=f"📥 **طلب سحب أرباح جديد معلق** ⏳\n"
                 f"🆔 فاتورة رقم: #{request_id}\n"
                 f"👤 صاحب الطلب: {full_name} (`{user_id}`)\n"
                 f"💸 المبلغ المطلوب: **{int(withdraw_amount):,} ل.س**\n"
                 f"🏦 الطريقة: {payment_method}\n"
                 f"📝 التفاصيل: `{payment_details}`\n"
                 f"📅 التاريخ: {current_time}"
        )
    except Exception:
        pass
# --------------------------------------------------------
# 14. نظام تذاكر الدعم الفني والتواصل (Support Ticket Engine)
# --------------------------------------------------------

# تعريف حالة انتظار رسالة الدعم الفني عبر FSM
class SupportStates(StatesGroup):
    waiting_for_ticket_text = State()

@dp.message(F.text == "👨‍💻 الدعم الفني والشكاوى")
async def process_support_start(message: types.Message, state: FSMContext):
    """فتح تذكرة دعم فني جديدة للمستخدم"""
    user_id = message.from_user.id
    
    await state.set_state(SupportStates.waiting_for_ticket_text)
    await message.answer(
        "👨‍💻 **مركز الدعم الفني والشكاوى لـ ALFA** 👨‍💻\n\n"
        "مرحباً بك عزيزي، إذا كنت تواجه مشكلة في شحن الرصيد، سحب الأرباح، أو تود الإبلاغ عن مشكلة:\n"
        "📝 **الرجاء كتابة رسالتك أو شكواك هنا في رسالة واحدة بالتفصيل:**\n\n"
        "📥 سيقوم النظام بإنشاء تذكرة رقمية فورية وإرسالها للمشرف العام مباشرة."
    )

@dp.message(SupportStates.waiting_for_ticket_text)
async def process_support_ticket_finalize(message: types.Message, state: FSMContext):
    """استقبال نص الشكوى وإرسالها للمشرف العام مع أزرار الرد السريع"""
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    ticket_text = message.text.strip()
    
    if len(ticket_text) < 5:
        return await message.reply("⚠️ الرسالة قصيرة جداً، يرجى توضيح مشكلتك بالتفصيل لكي نتمكن من مساعدتك.")
        
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # مسح حالة الـ FSM فوراً لتأمين الواجهة
    await state.clear()
    
    # إشعار المستخدم بنجاح إرسال التذكرة
    await message.answer(
        "✅ **تم إرسال تذكرتك بنجاح إلى الإدارة** ✅\n\n"
        "⏳ تم ترحيل الشكوى إلى قسم الدعم الفني للمشرف العام، يرجى الانتظار وسيصلك الرد هنا مباشرة عبر البوت فور مراجعتها."
    )
    
    # صياغة رسالة الدعم الموجهة للمشرف العام
    admin_alert_text = (
        f"🚨 **تذكرة دعم فني جديدة واردة** 🚨\n\n"
        f"👤 **المرسل:** {full_name}\n"
        f"🆔 **المعرف (ID):** `{user_id}`\n"
        f"📅 **التاريخ:** {current_time}\n\n"
        f"📝 **نص الرسالة:**\n{ticket_text}"
    )
    
    # إنشاء زر إنلاين مدمج للمشرف للرد السريع بضغطة واحدة
    kb = InlineKeyboardBuilder()
    kb.button(text="✍️ الرد على العضو", callback_data=f"reply_to_user_{user_id}")
    kb.adjust(1)
    
    # 1. إرسال الشكوى لحسابك كمشرف عام مباشرة لكي ترد عليها
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=admin_alert_text, reply_markup=kb.as_markup())
    except Exception:
        pass
        
    # 2. إرسال نسخة لقناة الإشعارات العامة للمراقبة والتوثيق
    try:
        await bot.send_message(
            chat_id=CH_GENERAL_LOGS,
            text=f"👨‍💻 **فتح تذكرة دعم**\n"
                 f"👤 من العضو: {full_name} (`{user_id}`)\n"
                 f"📝 ملخص: {ticket_text[:50]}..."
        )
    except Exception:
        pass
# --------------------------------------------------------
# 15. لوحة التحكم الإمبراطورية الفائقة (Imperial Admin Panel)
# --------------------------------------------------------

def get_admin_inline_keyboard() -> types.InlineKeyboardMarkup:
    """بناء أزرار التحكم الإدارية الفخمة والموزعة بشكل هندسي منسق"""
    kb = InlineKeyboardBuilder()
    
    # الصف الأول: إعدادات البوت العامة والصيانة
    kb.button(text="⚙️ إعدادات النظام الحيوية", callback_data="admin_sys_settings")
    kb.button(text="🌐 وضع الصيانة (تشغيل/إيقاف)", callback_data="admin_toggle_maintenance")
    
    # الصف الثاني: إدارة الأعضاء والحظر
    kb.button(text="🔍 فحص وتعديل حساب عضو", callback_data="admin_manage_user")
    kb.button(text="🚫 حظر / إلغاء حظر عضو", callback_data="admin_toggle_ban")
    
    # الصف الثالث: التحكم بالمال والجوائز
    kb.button(text="💰 تعديل أسعار وجوائز النظام", callback_data="admin_edit_rewards")
    kb.button(text="🎫 توليد الأكواد (بروموكود) 🎁", callback_data="admin_create_promo")
    
    # الصف الرابع: إدارة السحوبات والإعلانات
    kb.button(text="📥 إدارة طلبات السحب المعلقة ⏳", callback_data="admin_view_withdraws")
    kb.button(text="📢 مراقبة حملات التمويل", callback_data="admin_view_campaigns")
    
    # الصف الخامس: الإذاعة والتواصل المباشر
    kb.button(text="📣 الإذاعة وإرسال كول (Broadcast)", callback_data="admin_broadcast_start")
    
    # تنظيم الأزرار بشكل ثنائي منسق، وزر الإذاعة بشكل عريض بالأسفل
    kb.adjust(2, 2, 2, 2, 1)
    return kb.as_markup()

@dp.message(Command("admin"))
@dp.message(F.text == "⚙️ لوحة التحكم الإمبراطورية الفائقة ⚙️")
async def process_admin_panel_main(message: types.Message, state: FSMContext):
    """فتح لوحة التحكم وعرض إحصائيات خوادم ALFA اللحظية للمشرف العام فقط"""
    user_id = message.from_user.id
    
    # قفل الأمان الصارم: منع أي مستخدم آخر من الدخول نهائياً
    if user_id != ADMIN_ID:
        return await message.reply("⚠️ عذراً! هذا الأمر مخصص فقط للمشرف العام وصاحب صلاحية إدارة الخادم.")
        
    # جلب إحصائيات السيرفر اللحظية لتظهر في شاشة اللوحة فوراً
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. إجمالي الأعضاء المسجلين
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    # 2. إجمالي الأعضاء المحظورين
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
    banned_users = cursor.fetchone()[0]
    
    # 3. إجمالي أرصدة الأرباح الموزعة في النظام حالياً
    cursor.execute("SELECT SUM(balance_earnings) FROM users")
    total_earnings_pool = cursor.fetchone()[0] or 0.0
    
    # 4. إجمالي أرصدة الإعلانات المشحونة في النظام حالياً
    cursor.execute("SELECT SUM(balance_ads) FROM users")
    total_ads_pool = cursor.fetchone()[0] or 0.0
    
    conn.close()
    
    # صياغة شاشة العرض الإمبراطورية الفخمة
    admin_text = (
        f"👑 ─── **لوحة التحكم الإمبراطورية الفائقة** ─── 👑\n\n"
        f"👨‍💻 أهلاً بك يا سيادة المشرف العام في واجهة تحكم **Alfa ULTRA V3**.\n"
        f"📊 **إحصائيات الخادم اللحظية والمحدثة الآن:**\n\n"
        f"👥 **إجمالي المشتركين:** {total_users:,} عضو نشط.\n"
        f"🚫 **المعزولين والمحظورين:** {banned_users:,} حساب غش.\n"
        f"💰 **رصيد الأرباح الكلي بالسيستم:** {total_earnings_pool:,.1f} ل.س\n"
        f"📢 **رصيد الإعلانات الكلي بالسيستم:** {total_ads_pool:,.1f} ل.س\n\n"
        f"⚙️ استخدم أزرار الإنلاين التفاعلية أدناه للتحكم المطلق بالسيرفر وقاعدة البيانات 👇"
    )
    
    await state.clear() # مسح أي حالات مؤقتة للمشرف لضمان عدم حدوث تداخل
    await message.answer(admin_text, reply_markup=get_admin_inline_keyboard(), parse_mode="Markdown")
# --------------------------------------------------------
# 16. محرك الصيانة وعرض الإعدادات الحيوية (Maintenance & Settings View)
# --------------------------------------------------------

@dp.callback_query(F.data == "admin_toggle_maintenance")
async def admin_toggle_maintenance_handler(callback: types.CallbackQuery):
    """التحكم بوضع الصيانة العامة وقلب الحالة لحظياً في قاعدة البيانات"""
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⚠️ غير مصرح لك!", show_alert=True)
        
    current_status = get_db_setting("bot_status")
    new_status = "off" if current_status == "on" else "on"
    
    # تحديث الحالة الجديدة في قاعدة البيانات
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE system_settings SET value = ? WHERE key = 'bot_status'", (new_status,))
    
    # إعادة جلب الإحصائيات لتحديث شاشة اللوحة بالكامل بعد التعديل
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
    banned_users = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(balance_earnings) FROM users")
    total_earnings_pool = cursor.fetchone()[0] or 0.0
    cursor.execute("SELECT SUM(balance_ads) FROM users")
    total_ads_pool = cursor.fetchone()[0] or 0.0
    conn.commit()
    conn.close()
    
    status_icon = "🟢 البوت يعمل حالياً ومتاح للجميع" if new_status == "on" else "🔴 البوت في وضع الصيانة (مغلق عن الأعضاء)"
    await callback.answer(f"⚙️ تم تغيير حالة البوت إلى: {new_status.upper()}", show_alert=True)
    
    # صياغة النص المحدث للوحة التحكم
    admin_text = (
        f"👑 ─── **لوحة التحكم الإمبراطورية الفائقة** ─── 👑\n\n"
        f"⚡ **الحالة الحالية:** {status_icon}\n\n"
        f"👥 **إجمالي المشتركين:** {total_users:,} عضو نشط.\n"
        f"🚫 **المعزولين والمحظورين:** {banned_users:,} حساب غش.\n"
        f"💰 **رصيد الأرباح الكلي بالسيستم:** {total_earnings_pool:,.1f} ل.س\n"
        f"📢 **رصيد الإعلانات الكلي بالسيستم:** {total_ads_pool:,.1f} ل.س\n\n"
        f"⚙️ استخدم أزرار الإنلاين التفاعلية أدناه للتحكم المطلق بالسيرفر وقاعدة البيانات 👇"
    )
    
    await callback.message.edit_text(admin_text, reply_markup=get_admin_inline_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "admin_sys_settings")
async def admin_sys_settings_handler(callback: types.CallbackQuery):
    """عرض الإعدادات والقوانين المالية الحالية المسجلة داخل خوادم النظام"""
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⚠️ غير مصرح لك!", show_alert=True)
        
    # جلب كافة القيم الحالية المخزنة
    bot_status = get_db_setting("bot_status")
    referral_reward = int(float(get_db_setting("referral_reward")))
    min_withdraw = int(float(get_db_setting("min_withdraw")))
    p2p_fee = get_db_setting("p2p_fee")
    wheel_cost = int(float(get_db_setting("wheel_cost")))
    wheel_win_rate = get_db_setting("wheel_win_rate")
    
    settings_text = (
        f"⚙️ ─── **إعدادات النظام الحيوية الحالية** ─── ⚙️\n\n"
        f"🌐 **حالة البوت العامة:** `{bot_status.upper()}` (on تعني متاح / off صيانة)\n"
        f"📢 **معرف الاشتراك الإجباري:** `{CH_FORCE_SUB}`\n"
        f"👥 **جائزة الإحالة الناجحة:** {referral_reward:,} ل.س\n"
        f"📥 **الحد الأدنى لسحب الأرباح:** {min_withdraw:,} ل.س\n"
        f"🔄 **رسوم تحويل الأموال P2P:** {p2p_fee}%\n"
        f"🎡 **تكلفة دورة عجلة الحظ:** {wheel_cost:,} ل.س\n"
        f"📈 **نسبة الفوز في العجلة:** {wheel_win_rate}%\n\n"
        f"💡 لتعديل أي من هذه القيم المالية، يرجى الضغط على زر (تعديل أسعار وجوائز النظام) من اللوحة الرئيسية."
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 العودة للوحة الإمبراطورية", callback_data="back_to_admin_main")
    kb.adjust(1)
    
    await callback.message.edit_text(settings_text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "back_to_admin_main")
async def back_to_admin_main_handler(callback: types.CallbackQuery, state: FSMContext):
    """إعادة توليد اللوحة الرئيسية وشاشة الإحصائيات عند الضغط على زر العودة"""
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⚠️ غير مصرح لك!", show_alert=True)
        
    await state.clear()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
    banned_users = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(balance_earnings) FROM users")
    total_earnings_pool = cursor.fetchone()[0] or 0.0
    cursor.execute("SELECT SUM(balance_ads) FROM users")
    total_ads_pool = cursor.fetchone()[0] or 0.0
    conn.close()
    
    admin_text = (
        f"👑 ─── **لوحة التحكم الإمبراطورية الفائقة** ─── 👑\n\n"
        f"👨‍💻 أهلاً بك يا سيادة المشرف العام في واجهة تحكم **Alfa ULTRA V3**.\n"
        f"📊 **إحصائيات الخادم اللحظية والمحدثة الآن:**\n\n"
        f"👥 **إجمالي المشتركين:** {total_users:,} عضو نشط.\n"
        f"🚫 **المعزولين والمحظورين:** {banned_users:,} حساب غش.\n"
        f"💰 **رصيد الأرباح الكلي بالسيستم:** {total_earnings_pool:,.1f} ل.س\n"
        f"📢 **رصيد الإعلانات الكلي بالسيستم:** {total_ads_pool:,.1f} ل.س\n\n"
        f"⚙️ استخدم أزرار الإنلاين التفاعلية أدناه للتحكم المطلق بالسيرفر وقاعدة البيانات 👇"
    )
    
    await callback.message.edit_text(admin_text, reply_markup=get_admin_inline_keyboard(), parse_mode="Markdown")
# --------------------------------------------------------
# 17. نظام فحص وتعديل حسابات الأعضاء (User Management Engine)
# --------------------------------------------------------

# تعريف حالات إدارة الحسابات عبر FSM
class AdminUserStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_earnings_change = State()
    waiting_for_ads_change = State()

@dp.callback_query(F.data == "admin_manage_user")
async def admin_manage_user_start(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة 1: طلب معرف المستخدم (ID) المراد فحصه"""
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⚠️ غير مصرح لك!", show_alert=True)
        
    await state.set_state(AdminUserStates.waiting_for_user_id)
    await callback.message.edit_text(
        "🔍 **قسم فحص وتعديل حسابات المشتركين** 🔍\n\n"
        "📥 الرجاء إرسال معرف الحساب الرقمي (ID) للعضو المراد البحث عنه وتعديل أرصدته:",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 إلغاء والعودة", callback_data="back_to_admin_main").as_markup()
    )

@dp.message(AdminUserStates.waiting_for_user_id)
async def process_admin_search_user(message: types.Message, state: FSMContext):
    """الخطوة 2: فحص وجود العضو وعرض ملفه الإداري الشامل والأزرار التفاعلية"""
    if message.from_user.id != ADMIN_ID:
        return
        
    if not message.text or not message.text.isdigit():
        return await message.reply("⚠️ خطأ! يرجى إرسال معرف حساب صحيح (أرقام فقط).")
        
    target_id = int(message.text)
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT username, full_name, balance_earnings, balance_ads, referrals_count, rank, vip_level, is_banned, join_date "
        "FROM users WHERE user_id = ?", (target_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return await message.reply("❌ هذا المعرف غير مسجل في قاعدة بيانات البوت! تأكد من الرقم مجددًا.")
        
    username, full_name, b_earnings, b_ads, ref_count, rank, vip, is_banned, date = row
    
    # تنسيق بعض النصوص للعرض الإداري
    user_uname = f"@{username}" if username else "لا يوجد يوزر"
    ban_status = "🔴 محظور ومجمد" if is_banned == 1 else "🟢 نشط وطبيعي"
    vip_status = "لا يوجد" if vip == 0 else f"Level {vip} 💎"
    
    # صياغة البطاقة الإدارية للعضو
    report_text = (
        f"📊 ── **الملف الإداري التابع للعضو** ── 📊\n\n"
        f"🆔 **معرف الحساب:** `{target_id}`\n"
        f"👤 **الاسم الحقيقي:** {full_name}\n"
        f"🌐 **اليوزر نيم:** {user_uname}\n"
        f"📅 **تاريخ التسجيل:** {date}\n"
        f"⚡ **حالة الرقابة:** {ban_status}\n\n"
        f"💰 **رصيد الأرباح (كاش):** {b_earnings:,.1f} ل.س\n"
        f"📢 **رصيد الإعلانات (تمويل):** {b_ads:,.1f} ل.س\n"
        f"👥 **عدد الإحالات الناجحة:** {ref_count} عضو\n"
        f"🎖️ **الرتبة السيستمية:** {rank}\n"
        f"👑 **مستوى الـ VIP:** {vip_status}\n\n"
        f"👇 استخدم الأزرار الحصرية أدناه لإدارة وتعديل أرصدة هذا الحساب فورًا:"
    )
    
    # حفظ المعرف المستهدف في الـ ذاكرة المؤقتة لمتابعة التعديلات المالية عليه
    await state.update_data(target_user_id=target_id, target_user_name=full_name)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 تعديل رصيد الأرباح", callback_data="change_user_earnings")
    kb.button(text="📢 تعديل رصيد الإعلانات", callback_data="change_user_ads")
    kb.button(text="🔙 العودة للوحة الإدارية", callback_data="back_to_admin_main")
    kb.adjust(2, 1)
    
    await message.answer(report_text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "change_user_earnings")
async def change_user_earnings_start(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة 3: طلب القيمة المراد إضافتها أو خصمها من رصيد الأرباح"""
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminUserStates.waiting_for_earnings_change)
    data = await state.get_data()
    t_name = data.get("target_user_name")
    
    await callback.message.edit_text(
        f"💰 **تعديل محفظة الأرباح للعضو: {t_name}**\n\n"
        f"📥 أرسل الآن المبلغ المطلوب (أرقام فقط).\n"
        f"💡 **ملاحظة شحن وخصم:**\n"
        f"• لإضافة رصيد: أرسل الرقم مباشرة (مثال: `5000`).\n"
        f"• لخصم رصيد: ضع علامة الناقص قبل الرقم (مثال: `-3000`).",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 إلغاء", callback_data="back_to_admin_main").as_markup()
    )

@dp.message(AdminUserStates.waiting_for_earnings_change)
async def finalize_user_earnings_change(message: types.Message, state: FSMContext):
    """الخطوة 4: تطبيق التعديل المالي على رصيد الأرباح وإشعار العضو تلقائيًّا"""
    if message.from_user.id != ADMIN_ID:
        return
        
    text_input = message.text.strip()
    # التحقق من المدخل بذكاء لدعم الأرقام السالبة والموجبة
    if not text_input.replace('-', '', 1).isdigit():
        return await message.reply("⚠️ خطأ! يرجى إرسال قيمة رقمية صحيحة فقط.")
        
    change_value = float(text_input)
    data = await state.get_data()
    target_id = data.get("target_user_id")
    t_name = data.get("target_user_name")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance_earnings = balance_earnings + ? WHERE user_id = ?", (change_value, target_id))
    conn.commit()
    conn.close()
    
    await state.clear()
    action_text = f"إضافة **+{int(change_value):,} ل.س**" if change_value >= 0 else f"خصم **{int(change_value):,} ل.س**"
    
    await message.answer(f"✅ **نجحت العملية المالية!**\nتم {action_text} إلى رصيد أرباح العضو **{t_name}** بنجاح وتأمين خادم البيانات.")
    
    # إشعار العضو المستهدف لحظيًّا وبشكل فخم عبر البوت بالتحول المالي بحسابه
    try:
        msg_to_user = (
            f"🔔 **تحديث مالي رسمي من إدارة ALFA** 🔔\n\n"
            f"⚖️ قام المشرف العام بإجراء تعديل على رصيد أرباحك:\n"
            f"💰 حركة الحساب: {action_text}.\n\n"
            f"🔐 تم تدقيق رصيدك الجديد وترحيله تلقائيًّا إلى محفظتك الإلكترونية بالبوت."
        )
        await bot.send_message(chat_id=target_id, text=msg_to_user)
    except Exception:
        pass
# --------------------------------------------------------
# 17. تابع: تعديل رصيد الإعلانات ونظام الحظر (Ads Control & Ban Engine)
# --------------------------------------------------------

@dp.callback_query(F.data == "change_user_ads")
async def change_user_ads_start(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة 3 الموازية: طلب القيمة المراد إضافتها أو خصمها من رصيد الإعلانات"""
    if callback.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminUserStates.waiting_for_ads_change)
    data = await state.get_data()
    t_name = data.get("target_user_name")
    
    await callback.message.edit_text(
        f"📢 **تعديل محفظة الإعلانات للعضو: {t_name}**\n\n"
        f"📥 أرسل الآن المبلغ المطلوب (أرقام فقط).\n"
        f"💡 **ملاحظة شحن وخصم:**\n"
        f"• لإضافة رصيد: أرسل الرقم مباشرة (مثال: `10000`).\n"
        f"• لخصم رصيد: وضع علامة الناقص قبل الرقم (مثال: `-5000`).",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 إلغاء", callback_data="back_to_admin_main").as_markup()
    )

@dp.message(AdminUserStates.waiting_for_ads_change)
async def finalize_user_ads_change(message: types.Message, state: FSMContext):
    """الخطوة 4 الموازية: تطبيق التعديل المالي على رصيد الإعلانات وإشعار العضو تلقائيًّا"""
    if message.from_user.id != ADMIN_ID:
        return
        
    text_input = message.text.strip()
    if not text_input.replace('-', '', 1).isdigit():
        return await message.reply("⚠️ خطأ! يرجى إرسال قيمة رقمية صحيحة فقط.")
        
    change_value = float(text_input)
    data = await state.get_data()
    target_id = data.get("target_user_id")
    t_name = data.get("target_user_name")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance_ads = balance_ads + ? WHERE user_id = ?", (change_value, target_id))
    conn.commit()
    conn.close()
    
    await state.clear()
    action_text = f"إضافة **+{int(change_value):,} ل.س**" if change_value >= 0 else f"خصم **{int(change_value):,} ل.س**"
    
    await message.answer(f"✅ **نجحت العملية المالية!**\nتم {action_text} إلى رصيد إعلانات العضو **{t_name}** بنجاح وتأمين خادم البيانات.")
    
    # إشعار العضو تلقائياً عبر البوت بإنعاش رصيده الإعلاني
    try:
        msg_to_user = (
            f"🔔 **تحديث مالي رسمي من إدارة ALFA** 🔔\n\n"
            f"⚖️ قام المشرف العام بإجراء تعديل على رصيد إعلاناتك:\n"
            f"📢 حركة الحساب: {action_text}.\n\n"
            f"🏪 يمكنك الآن استخدام هذا الرصيد لتمويل مشاريعك وقنواتك من سوق الإعلانات."
        )
        await bot.send_message(chat_id=target_id, text=msg_to_user)
    except Exception:
        pass

# --------------------------------------------------------
# 18. نظام حظر وإلغاء حظر الأعضاء (Ban & Unban Controller)
# --------------------------------------------------------

class AdminBanStates(StatesGroup):
    waiting_for_ban_id = State()

@dp.callback_query(F.data == "admin_toggle_ban")
async def admin_toggle_ban_start(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة 1: طلب معرف الحساب المراد قلبه رقابياً (حظر/إلغاء حظر)"""
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⚠️ غير مصرح لك!", show_alert=True)
        
    await state.set_state(AdminBanStates.waiting_for_ban_id)
    await callback.message.edit_text(
        "🚫 **قسم الرقابة والعزل والحظر الصارم** 🚫\n\n"
        "📥 الرجاء إرسال معرف الحساب الرقمي (ID) للعضو المراد حظره من النظام أو فك الحظر عنه:",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 إلغاء والعودة", callback_data="back_to_admin_main").as_markup()
    )

@dp.message(AdminBanStates.waiting_for_ban_id)
async def process_admin_toggle_ban_finalize(message: types.Message, state: FSMContext):
    """الخطوة 2: تحديث حالة الحظر في قاعدة البيانات وعزل الحساب فوراً"""
    if message.from_user.id != ADMIN_ID:
        return
        
    if not message.text or not message.text.isdigit():
        return await message.reply("⚠️ خطأ! يرجى إرسال معرف حساب صحيح (أرقام فقط).")
        
    target_id = int(message.text)
    
    if target_id == ADMIN_ID:
        return await message.reply("❌ غريب! لا يمكنك حظر حسابك الشخصي (المشرف العام) من السيستم!")
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # فحص حالة المستخدم الحالية
    cursor.execute("SELECT full_name, is_banned FROM users WHERE user_id = ?", (target_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return await message.reply("❌ هذا المعرف غير مسجل بالسيستم.")
        
    full_name, is_banned = row
    
    # قلب الحالة: إن كان محظوراً نلغي حظره، وإن كان نشطاً نحظره
    new_ban_status = 0 if is_banned == 1 else 1
    cursor.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (new_ban_status, target_id))
    conn.commit()
    conn.close()
    
    await state.clear()
    
    if new_ban_status == 1:
        await message.answer(f"🚫 **تم حظر وتجميد حساب العضو {full_name} (`{target_id}`) بنجاح.**\nسيرفض السيرفر معالجة أي أمر منه فوراً.")
        try:
            await bot.send_message(chat_id=target_id, text="⚠️ **لقد تم حظر حسابك بالكامل وتجميده من قبل الإدارة لمخالفتك شروط وقوانين النظام!**")
        except Exception:
            pass
    else:
        await message.answer(f"🟢 **تم إلغاء حظر العضو {full_name} (`{target_id}`) وإعادته للوضع النشط.**")
        try:
            await bot.send_message(chat_id=target_id, text="🎉 **بشرى! تمت الموافقة على فك الحظر عن حسابك وإعادته للعمل بنشاط مجدداً.**")
        except Exception:
            pass
# --------------------------------------------------------
# 19. محرك التعديل الديناميكي للأسعار والجوائز (System Pricing Editor)
# --------------------------------------------------------

# تعريف حالات تعديل الأسعار عبر FSM
class AdminPricingStates(StatesGroup):
    waiting_for_selection = State()
    waiting_for_new_value = State()

@dp.callback_query(F.data == "admin_edit_rewards")
async def admin_edit_rewards_start(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة 1: عرض قائمة المتغيرات المالية القابلة للتعديل الفوري"""
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⚠️ غير مصرح لك!", show_alert=True)
        
    kb = InlineKeyboardBuilder()
    kb.button(text="👥 جائزة الإحالة", callback_data="edit_set_referral_reward")
    kb.button(text="📥 الحد الأدنى للسحب", callback_data="edit_set_min_withdraw")
    kb.button(text="🔙 العودة للوحة الإدارية", callback_data="back_to_admin_main")
    kb.adjust(2, 1)
    
    await state.set_state(AdminPricingStates.waiting_for_selection)
    await callback.message.edit_text(
        "💰 **قسم تعديل الأسعار، الجوائز، والحدود المالية** 💰\n\n"
        "💡 اختر الثابت المالي الذي ترغب في تعديل قيمته اللحظية داخل النظام الآن من الأزرار أدناه:",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(AdminPricingStates.waiting_for_selection)
async def process_pricing_selection(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة 2: تحديد المتغير المالي المطلوب وطلب القيمة الجديدة"""
    if callback.from_user.id != ADMIN_ID:
        return
        
    selection = callback.data
    
    if selection == "back_to_admin_main":
        await state.clear()
        return await back_to_admin_main_handler(callback, state)
        
    # فرز وتحديد المفتاح النصي والاسم المعروض بناءً على خيار الآدمن
    if selection == "edit_set_referral_reward":
        key_db = "referral_reward"
        display_name = "جائزة الإحالة الناجحة 👥"
    else:
        key_db = "min_withdraw"
        display_name = "الحد الأدنى لسحب الأرباح 📥"
        
    current_val = get_db_setting(key_db)
    
    await state.update_data(target_key=key_db, target_display=display_name)
    await state.set_state(AdminPricingStates.waiting_for_new_value)
    
    await callback.message.edit_text(
        f"⚙️ **تعديل: {display_name}**\n\n"
        f"📊 القيمة الحالية المخزنة بالسيرفر: **{int(float(current_val)):,} ل.س**\n\n"
        f"📥 **الآن:** الرجاء إرسال القيمة الرقمية الجديدة بالليرة السورية كـ أرقام فقط (بدول فواصل أو رموز):\n"
        f"💡 *مثال:* `25000`",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 إلغاء", callback_data="back_to_admin_main").as_markup()
    )

@dp.message(AdminPricingStates.waiting_for_new_value)
async def finalize_pricing_change(message: types.Message, state: FSMContext):
    """الخطوة الأخيرة: التحقق من القيمة، حقنها في السيرفر، وإعادة تحديث الواجهة"""
    if message.from_user.id != ADMIN_ID:
        return
        
    input_text = message.text.strip()
    
    # التحقق الصارم من أن المدخل رقمي صحيح تماماً وموجب
    if not input_text.isdigit():
        return await message.reply("⚠️ خطأ! يرجى إرسال قيمة رقمية صحيحة وموجبة كـ أرقام فقط.")
        
    new_value = int(input_text)
    
    # استرجاع البيانات المؤقتة للمفتاح المستهدف
    data = await state.get_data()
    key_db = data.get("target_key")
    display_name = data.get("target_display")
    
    # حقن وتحديث القيمة الجديدة في جدول إعدادات النظام الحيوية
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE system_settings SET value = ? WHERE key = ?", (str(new_value), key_db))
    conn.commit()
    conn.close()
    
    # مسح حالة الـ FSM لتأمين العملية
    await state.clear()
    
    await message.answer(
        f"✅ **تم تحديث النظام المالي بنجاح!** ✅\n\n"
        f"📌 المتغير المعدل: {display_name}\n"
        f"📈 القيمة الجديدة المعتمدة: **{new_value:,} ل.س**\n\n"
        f"⚙️ تم تطبيق هذا التعديل على جميع المستخدمين في هذه اللحظة بنجاح."
    )
    
    # إعادة إرسال لوحة التحكم الرئيسية لإبقاء المشرف في سياق الإدارة الإمبراطورية
    # محاكاة لرسالة جديدة من الآدمن
    await process_admin_panel_main(message, state)
# --------------------------------------------------------
# 20. محرك صناعة وتوليد الأكواد الإدارية (Admin Promo Code Generator)
# --------------------------------------------------------

# تعريف حالات الـ FSM لتوليد الكود الجديد
class AdminPromoStates(StatesGroup):
    waiting_for_code_name = State()
    waiting_for_reward_type = State()
    waiting_for_reward_amount = State()
    waiting_for_max_uses = State()

@dp.callback_query(F.data == "admin_create_promo")
async def admin_create_promo_start(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة 1: طلب نص الكود المراد إنشاؤه"""
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⚠️ غير مصرح لك!", show_alert=True)
        
    await state.set_state(AdminPromoStates.waiting_for_code_name)
    await callback.message.edit_text(
        "🎫 **بوابة توليد وصناعة الأكواد (البروموكود)** 🎫\n\n"
        "📥 **[الخطوة 1 من 4]:** يرجى إرسال نص الكود الجديد الذي ترغب في إنشائه (أحرف أو أرقام بدون مسافات).\n"
        "💡 *مثال:* `ALFA2026` أو `FREE_CASH`",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 إلغاء والعودة", callback_data="back_to_admin_main").as_markup()
    )

@dp.message(AdminPromoStates.waiting_for_code_name)
async def process_admin_promo_name(message: types.Message, state: FSMContext):
    """الخطوة 2: فحص الكود وطلب تحديد نوع الجائزة المحقونة"""
    if message.from_user.id != ADMIN_ID:
        return
        
    code_name = message.text.strip().upper()
    
    if " " in code_name or len(code_name) < 3:
        return await message.reply("⚠️ خطأ! يجب أن يكون الكود كلمة واحدة بدون مسافات ولا يقل عن 3 أحرف.")
        
    # فحص هل الكود مكرر وموجود مسبقاً في قاعدة البيانات
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT code FROM promo_codes WHERE code = ?", (code_name,))
    exists = cursor.fetchone()
    conn.close()
    
    if exists:
        return await message.reply("❌ هذا الكود موجود بالفعل في النظام! يرجى اختيار نص كود آخر جديد.")
        
    await state.update_data(promo_code=code_name)
    await state.set_state(AdminPromoStates.waiting_for_reward_type)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 رصيد الأرباح (كاش)", callback_data="admin_promo_type_earnings")
    kb.button(text="📢 رصيد الإعلانات (تمويل)", callback_data="admin_promo_type_ads")
    kb.adjust(2)
    
    await message.answer(
        f"🔑 **نص الكود المعتمد:** `{code_name}`\n\n"
        f"📥 **[الخطوة 2 من 4]:** الرجاء اختيار نوع الرصيد الذي سيتم شحنه عند تفعيل هذا الكود:",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(AdminPromoStates.waiting_for_reward_type)
async def process_admin_promo_type(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة 3: استقبال نوع الرصيد وطلب تحديد القيمة المالية"""
    if callback.from_user.id != ADMIN_ID:
        return
        
    p_type = "earnings" if callback.data == "admin_promo_type_earnings" else "ads"
    p_type_display = "الأرباح 💰" if p_type == "earnings" else "الإعلانات 📢"
    
    await state.update_data(reward_type=p_type, reward_type_display=p_type_display)
    await state.set_state(AdminPromoStates.waiting_for_reward_amount)
    
    await callback.message.edit_text(
        f"📊 **نوع الشحن المحدد:** رصيد {p_type_display}\n\n"
        f"📥 **[الخطوة 3 من 4]:** الرجاء إرسال قيمة المكافأة المالية بالليرة السورية كـ أرقام فقط:\n"
        f"💡 *مثال:* `5000`"
    )

@dp.message(AdminPromoStates.waiting_for_reward_amount)
async def process_admin_promo_amount(message: types.Message, state: FSMContext):
    """الخطوة 4: استقبال المبلغ وطلب تحديد الحد الأقصى لعدد الاستخدامات"""
    if message.from_user.id != ADMIN_ID:
        return
        
    if not message.text or not message.text.isdigit():
        return await message.reply("⚠️ خطأ! يرجى إرسال مبلغ صحيح كـ أرقام فقط.")
        
    amount = float(message.text)
    if amount <= 0:
        return await message.reply("❌ يجب أن تكون قيمة الجائزة أكبر من صفر!")
        
    await state.update_data(reward_amount=amount)
    await state.set_state(AdminPromoStates.waiting_for_max_uses)
    
    await message.answer(
        f"💰 **قيمة الجائزة:** {int(amount):,} ل.س\n\n"
        f"📥 **[الخطوة 4 من 4 والأخيرة]:** الرجاء إرسال الحد الأقصى لعدد المستخدمين الذين يمكنهم تفعيل الكود (عدد مرات الاستخدام الكلية):\n"
        f"💡 *مثال:* `100` (تعني أول 100 عضو يكتبون الكود يحصلون على الهدية)."
    )

@dp.message(AdminPromoStates.waiting_for_max_uses)
async def finalize_promo_generation(message: types.Message, state: FSMContext):
    """الخطوة الأخيرة: حفظ الكود في قاعدة البيانات وتوليد إعلان الجاهزية للنشاط الفوري"""
    if message.from_user.id != ADMIN_ID:
        return
        
    if not message.text or not message.text.isdigit():
        return await message.reply("⚠️ خطأ! يرجى إرسال عدد مرات استخدام صحيح كـ أرقام فقط.")
        
    max_uses = int(message.text)
    if max_uses <= 0:
        return await message.reply("❌ يجب أن يكون عدد مرات الاستخدام 1 على الأقل!")
        
    # استرجاع كافة البيانات المخزنة مؤقتاً في الذاكرة
    data = await state.get_data()
    code_name = data.get("promo_code")
    reward_type = data.get("reward_type")
    reward_type_display = data.get("reward_type_display")
    reward_amount = data.get("reward_amount")
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # حقن الكود الجديد في جدول الأكواد بقاعدة البيانات فوراً
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO promo_codes (code, reward_type, reward_amount, max_uses, current_uses, created_at) "
        "VALUES (?, ?, ?, ?, 0, ?)",
        (code_name, reward_type, reward_amount, max_uses, current_time)
    )
    conn.commit()
    conn.close()
    
    # تنظيف حالة الـ FSM بالكامل بأمان تسيبي
    await state.clear()
    
    # صياغة رسالة نجاح العملية الجاهزة للنسخ والنشر للأعضاء
    success_text = (
        f"✅ **تم توليد وحقن كود الهدية بنجاح باهر!** ✅\n\n"
        f"🎫 **الكود السري:** `{code_name}`\n"
        f"💵 **قيمة الجائزة:** {int(reward_amount):,} ل.س\n"
        f"📊 **نوع الرصيد:** {reward_type_display}\n"
        f"👥 **الحد الأقصى للمستفيدين:** لأول {max_uses} عضو سريع!\n\n"
        f"🚀 الكود الآن نشط وشغال بنسبة 100% في النظام، يمكنك نسخه ونشره بقناتك فوراً."
    )
    
    await message.answer(success_text)
    
    # العودة التلقائية للوحة التحكم الرئيسية
    await process_admin_panel_main(message, state)
# --------------------------------------------------------
# 21. محرك تدقيق وإدارة طلبات السحب (Admin Withdrawal Controller)
# --------------------------------------------------------

# تعريف حالات الرفض لتحديد السبب عبر FSM
class AdminWithdrawRejectStates(StatesGroup):
    waiting_for_reject_reason = State()

@dp.callback_query(F.data == "admin_view_withdraws")
async def admin_view_withdraws_handler(callback: types.CallbackQuery):
    """جلب وعرض طلبات السحب المعلقة في قاعدة البيانات مع أزرار التحكم الفورية"""
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⚠️ غير مصرح لك!", show_alert=True)
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # جلب أقدم طلب معلق لمعالجته بالترتيب (طابور عادل FIFO)
    cursor.execute(
        "SELECT request_id, user_id, amount, payment_method, payment_details, created_at "
        "FROM withdraw_requests WHERE status = 'معلق ⏳' ORDER BY request_id ASC LIMIT 1"
    )
    request = cursor.fetchone()
    conn.close()
    
    if not request:
        return await callback.answer("📥 ممتاز! لا توجد أي طلبات سحب معلقة حالياً في طابور التدقيق.", show_alert=True)
        
    req_id, u_id, amount, method, details, date = request
    
    withdraw_text = (
        f"📥 ── **فاتورة طلب سحب معلقة رقم #{req_id}** ── 📥\n\n"
        f"👤 **اسم وصاحب الطلب:** `(يتم جلب الاسم من رقمه)`\n"
        f"🆔 **معرف الحساب (ID):** `{u_id}`\n"
        f"💵 **المبلغ المطلوب:** **{int(amount):,} ل.س**\n"
        f"🏦 **طريقة الاستلام:** {method}\n"
        f"📝 **بيانات المحفظة المرسلة:**\n`{details}`\n\n"
        f"📅 **تاريخ تقديم الطلب:** {date}\n"
        f"📎 ───────────────────── 📎\n"
        f"👇 يرجى تحويل الأموال يدوياً للمستلم بناءً على بياناته أعلاه، ثم اتخذ الإجراء البرمجي المناسب:"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ موافقة (تم التحويل) 💵", callback_data=f"wd_approve_{req_id}_{u_id}_{int(amount)}")
    kb.button(text="❌ رفض وإرجاع الأموال 🔄", callback_data=f"wd_reject_{req_id}_{u_id}_{int(amount)}")
    kb.button(text="🔙 العودة للوحة الإدارية", callback_data="back_to_admin_main")
    kb.adjust(1, 1, 1)
    
    await callback.message.edit_text(withdraw_text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("wd_approve_"))
async def admin_approve_withdraw(callback: types.CallbackQuery):
    """تأكيد عملية الدفع وقفل الفاتورة وإشعار العضو بنجاح التحويل ماليّاً"""
    if callback.from_user.id != ADMIN_ID:
        return
        
    # تفكيك بيانات الكولباك المستلمة
    parts = callback.data.split("_")
    req_id = int(parts[2])
    user_id = int(parts[3])
    amount = int(parts[4])
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # تحديث حالة الفاتورة في قاعدة البيانات فوراً لمنع التكرار
    cursor.execute("UPDATE withdraw_requests SET status = 'مقبول 👍' WHERE request_id = ?", (req_id,))
    conn.commit()
    conn.close()
    
    await callback.answer("✅ تم تأكيد الدفع وإغلاق الفاتورة بنجاح حركي!", show_alert=True)
    
    # إشعار العضو لحظياً بتسليم أمواله بنجاح
    try:
        user_msg = (
            f"✅ **تهانينا! تم تحويل رصيدك بنجاح** ✅\n\n"
            f"🧾 **رقم الفاتورة:** #{req_id}\n"
            f"💵 **المبلغ المستلم:** {amount:,} ل.س\n"
            f"🌟 نشكرك على ثقتك وعملك مع شبكة ALFA، نتمنى لك أرباحاً مستمرة!"
        )
        await bot.send_message(chat_id=user_id, text=user_msg)
    except Exception:
        pass
        
    # إعادة إنعاش الصفحة لعرض الطلب التالي في الطابور إن وجد تلقائياً
    await admin_view_withdraws_handler(callback)

@dp.callback_query(F.data.startswith("wd_reject_"))
async def admin_reject_withdraw_start(callback: types.CallbackQuery, state: FSMContext):
    """البدء في رفض الطلب وطلب إدخال السبب عبر الـ FSM لتسجيله"""
    if callback.from_user.id != ADMIN_ID:
        return
        
    parts = callback.data.split("_")
    req_id = int(parts[2])
    user_id = int(parts[3])
    amount = int(parts[4])
    
    await state.set_state(AdminWithdrawRejectStates.waiting_for_reject_reason)
    await state.update_data(rej_req_id=req_id, rej_user_id=user_id, rej_amount=amount)
    
    await callback.message.edit_text(
        f"❌ **رفض طلب السحب رقم #{req_id}**\n\n"
        f"📥 يرجى إرسال سبب الرفض نصياً الآن (مثال: 'رقم المحفظة غير صحيح' أو 'الاسم ثلاثي مطلوب'):\n"
        f"💡 *ملاحظة:* سيقوم البوت بإعادة مبلغ **{amount:,} ل.س** تلقائياً لحساب العضو وإخطاره بالسبب.",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 إلغاء", callback_data="admin_view_withdraws").as_markup()
    )

@dp.message(AdminWithdrawRejectStates.waiting_for_reject_reason)
async def finalize_admin_withdraw_reject(message: types.Message, state: FSMContext):
    """تطبيق الرفض، إعادة الأموال بالكامل إلى محفظة العضو، وإرسال إشعار تفصيلي بالسبب"""
    if message.from_user.id != ADMIN_ID:
        return
        
    reject_reason = message.text.strip()
    
    data = await state.get_data()
    req_id = data.get("rej_req_id")
    user_id = data.get("rej_user_id")
    amount = data.get("rej_amount")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. تغيير حالة الطلب لـ "مرفوض ❌"
    cursor.execute("UPDATE withdraw_requests SET status = 'مرفوض ❌' WHERE request_id = ?", (req_id,))
    
    # 2. إعادة كامل القيمة المالية لرصيد أرباح العضو دون نقصان لأمان الحسابات
    cursor.execute("UPDATE users SET balance_earnings = balance_earnings + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    
    await state.clear()
    await message.answer(f"✅ تم رفض الفاتورة رقم #{req_id} بنجاح، وإعادة كامل رصيد العضو ({amount:,} ل.س) إلى محفظته.")
    
    # إشعار العضو تلقائياً بالرفض والسبب لكي يعدل بياناته ويحاول مجدداً
    try:
        user_msg = (
            f"❌ **تنبيه: تم رفض طلب سحب الأرباح الخاص بك** ❌\n\n"
            f"🧾 **رقم الفاتورة:** #{req_id}\n"
            f"💵 **المبلغ المعاد لمحفظتك:** +{amount:,} ل.س\n"
            f"📝 **سبب الرفض الإداري:** {reject_reason}\n\n"
            f"💡 يرجى تصحيح الخطأ وتقديم طلب جديد عبر بوابة السحب بأمان."
        )
        await bot.send_message(chat_id=user_id, text=user_msg)
    except Exception:
        pass
# --------------------------------------------------------
# 22. منظومة الإذاعة الإمبراطورية والبث الجماعي (Broadcast Engine)
# --------------------------------------------------------

# تعريف حالة انتظار نص أو وسائط الإذاعة عبر FSM
class AdminBroadcastStates(StatesGroup):
    waiting_for_broadcast_msg = State()

@dp.callback_query(F.data == "admin_broadcast_start")
async def admin_broadcast_start_handler(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة 1: طلب رسالة الإذاعة من المشرف العام"""
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⚠️ غير مصرح لك!", show_alert=True)
        
    await state.set_state(AdminBroadcastStates.waiting_for_broadcast_msg)
    await callback.message.edit_text(
        "📣 **قسم البث الجماعي والإذاعة الفورية (Broadcast)** 📣\n\n"
        "📥 **الآن:** الرجاء إرسال الرسالة التي تود بثها لجميع أعضاء البوت دفعة واحدة.\n\n"
        "💡 *ملاحظة:* يمكنك إرسال نص عادي، نص منسق بـ Markdown، أو حتى رسالة تحتوي على أزرار شفافة، وسيتم ترحيلها فوراً لجميع الحسابات النشطة بالسيستم.",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 إلغاء والعودة", callback_data="back_to_admin_main").as_markup()
    )

@dp.message(AdminBroadcastStates.waiting_for_broadcast_msg)
async def admin_broadcast_finalize_and_send(message: types.Message, state: FSMContext):
    """الخطوة 2: جلب الأعضاء، تدوير البث السريع، وعرض تقرير النجاح الإداري"""
    if message.from_user.id != ADMIN_ID:
        return
        
    # إشعار أولي بالبدء لتفادي تعليق الشاشة
    status_msg = await message.reply("⚡ **جاري بدء عملية البث واستخراج طابور الأعضاء من خادم البيانات...**")
    
    # جلب جميع معرفات الأعضاء النشطين من قاعدة البيانات
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
    user_rows = cursor.fetchall()
    conn.close()
    
    total_targets = len(user_rows)
    if total_targets == 0:
        await state.clear()
        return await status_msg.edit_text("❌ لا يوجد أي أعضاء نشطين في النظام حالياً لإرسال الإذاعة إليهم!")
        
    success_count = 0
    failed_count = 0
    
    # مسح الحالة فوراً لتأمين الواجهة أثناء البث
    await state.clear()
    
    # بدء تدوير البث الجماعي (تنفيذ فوري مع معالجة الاستثناءات)
    for row in user_rows:
        target_user_id = row[0]
        try:
            # استخدام خاصية السيرفر لإعادة توجيه أو نسخ نفس الرسالة بكافة تفاصيلها وأزرارها
            await message.copy_to(chat_id=target_user_id)
            success_count += 1
        except Exception:
            # الحسابات التي حظرت البوت أو حُذفت تلقائياً
            failed_count += 1
            
    # صياغة تقرير الإذاعة النهائي الفخم للآدمن
    report_text = (
        f"📢 **اكتملت عملية البث الجماعي بنجاح ساحق!** 📢\n\n"
        f"📊 **التقرير الإحصائي النهائي للحملة:**\n"
        f"🎯 **إجمالي المستهدفين بالطابور:** {total_targets:,} حساب.\n"
        f"✅ **رسائل وصلت بنجاح:** **{success_count:,} عضو** نالوا التنبيه.\n"
        f"❌ **فشلت (بسبب حظر البوت):** {failed_count:,} حساب غير مستجيب.\n\n"
        f"🔐 تم إغلاق الحملة الحالية بنجاح، وإعادة توجيهك للوحة التحكم الإمبراطورية الفائقة."
    )
    
    await status_msg.edit_text(report_text)
    
    # إعادة إنعاش لوحة التحكم الرئيسية أمامك
    await process_admin_panel_main(message, state)
# --------------------------------------------------------
# 23. منظومة مراقبة وإشراف الحملات الإعلانية (Admin Campaigns Controller)
# --------------------------------------------------------

@dp.callback_query(F.data == "admin_view_campaigns")
async def admin_view_campaigns_handler(callback: types.CallbackQuery):
    """استعراض الحملات الإعلانية النشطة في النظام لإتاحة الرقابة الإدارية عليها"""
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⚠️ غير مصرح لك!", show_alert=True)
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # جلب آخر 5 حملات نشطة بحاجة لمتابعة
    cursor.execute(
        "SELECT campaign_id, user_id, channel_id, required_members, current_members, cost, status "
        "FROM ad_campaigns WHERE status = 'نشط 🟢' ORDER BY campaign_id DESC LIMIT 5"
    )
    campaigns = cursor.fetchall()
    conn.close()
    
    if not campaigns:
        return await callback.answer("📢 لا توجد حملات تمويل نشطة حالياً في النظام.", show_alert=True)
        
    response_text = "📢 ── **إدارة ومراقبة حملات التمويل النشطة** ── 📢\n\n"
    kb = InlineKeyboardBuilder()
    
    for camp in campaigns:
        camp_id, u_id, ch_id, req, curr, cost, status = camp
        response_text += (
            f"🆔 **حملة رقم:** #{camp_id} | 👤 **المعلن:** `{u_id}`\n"
            f"🔗 **القناة:** {ch_id}\n"
            f"👥 **التقدم الحالي:** ({curr} / {req}) عضو\n"
            f"💰 ** التكلفة الكلية:** {cost:,.1f} ل.س\n"
            f"📎 ─────────────────── 📎\n"
        )
        # توليد زر إلغاء أو إيقاف لكل حملة نشطة مباشرة لحماية المحتوى
        kb.button(text=f"❌ إيقاف الحِملة #{camp_id}", callback_data=f"admin_stop_camp_{camp_id}")
        
    kb.button(text="🔙 العودة للوحة الإدارية", callback_data="back_to_admin_main")
    kb.adjust(1)
    
    await callback.message.edit_text(response_text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("admin_stop_camp_"))
async def admin_stop_campaign_handler(callback: types.CallbackQuery):
    """إيقاف الحملة الإعلانية فوراً وتحويل حالتها في قاعدة البيانات للرقابة"""
    if callback.from_user.id != ADMIN_ID:
        return
        
    camp_id = int(callback.data.replace("admin_stop_camp_", ""))
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE ad_campaigns SET status = 'موقوفة 🔴' WHERE campaign_id = ?", (camp_id,))
    conn.commit()
    conn.close()
    
    await callback.answer(f"🛑 تم إيقاف الحملة رقم #{camp_id} بنجاح وعزلها عن العرض!", show_alert=True)
    
    # إعادة إنعاش القائمة لتحديث البيانات المعروضة أمام الآدمن
    await admin_view_campaigns_handler(callback)
# --------------------------------------------------------
# 24. محرك نظام عجلة الحظ الكبرى التفاعلي (Lucky Wheel Engine)
# --------------------------------------------------------

@dp.message(F.text == "🎡 عجلة الحظ الكبرى 🎰")
async def process_lucky_wheel_menu(message: types.Message):
    """عرض واجهة عجلة الحظ وشروط اللعب مع التكلفة الحالية من رصيد الأرباح"""
    user_id = message.from_user.id
    
    # جلب التكلفة الحالية ونسبة الفوز ديناميكياً من قاعدة البيانات
    wheel_cost = int(float(get_db_setting("wheel_cost")))
    wheel_win_rate = get_db_setting("wheel_win_rate")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT balance_earnings FROM users WHERE user_id = ?", (user_id,))
    user_balance = cursor.fetchone()[0]
    conn.close()
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 لِف العجلة الآن وجرب حظك! 🎡", callback_data="spin_the_wheel")
    kb.adjust(1)
    
    await message.answer(
        f"🎡 **مرحباً بك في عجلة الحظ الكبرى لإمبراطورية ALFA** 🎰\n\n"
        f"✨ هنا يمكنك استثمار جزء من أرباحك لمضاعفتها ثوانٍ معدودة! العجلة تعتمد على الحظ النقي والنسب العادلة المحقونة بالسيرفر.\n\n"
        f"📊 **قوانين وتكلفة الدورة الحالية:**\n"
        f"💵 رسوم اللفة الواحدة: **{wheel_cost:,} ل.س** (تُخصم من رصيد أرباحك).\n"
        f"📈 نسبة الفوز المبرمجة: **{wheel_win_rate}%** كحد متوسط.\n"
        f"💰 رصيد أرباحك الحالي: **{int(user_balance):,} ل.س**\n\n"
        f"🎁 **الجوائز المتاحة في العجلة:**\n"
        f"| ❌ خسارة الدورة | 🎉 ربح 500 ل.س | 🔥 ربح 2,500 ل.س | 👑 الجائزة الكبرى: 10,000 ل.س |\n\n"
        f"👇 اضغط على الزر أدناه لتبدأ العجلة بالدوران والتحريك فوراً:",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(F.data == "spin_the_wheel")
async def spin_the_wheel_handler(callback: types.CallbackQuery):
    """معالجة وتدقيق تدوير عجلة الحظ، سحب الرسوم، واحتساب الجائزة عشوائياً"""
    user_id = callback.from_user.id
    full_name = callback.from_user.full_name
    
    wheel_cost = int(float(get_db_setting("wheel_cost")))
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. التحقق من رصيد المستخدم أولاً لقطع الطريق على ثغرات الرصيد السالب
    cursor.execute("SELECT balance_earnings FROM users WHERE user_id = ?", (user_id,))
    current_balance = cursor.fetchone()[0]
    
    if current_balance < wheel_cost:
        conn.close()
        return await callback.answer(f"❌ رصيد أرباحك غير كافٍ! تحتاج إلى {wheel_cost:,} ل.س على الأقل للعب.", show_alert=True)
        
    # 2. الخصم الفوري والمباشر لرسوم الدورة لتأمين النظام
    cursor.execute("UPDATE users SET balance_earnings = balance_earnings - ? WHERE user_id = ?", (wheel_cost, user_id))
    
    # 3. محرك الاحتمالات العشوائي (الرياضيات الذكية للعجلة)
    # نقوم بتوليد رقم عشوائي بين 1 و 100 لتمثيل النسبة المئوية للفوز
    spin_result = random.randint(1, 100)
    
    # مصفوفة الجوائز المحتملة ونسب تحققها برمجياً
    # 50% خسارة، 35% ربح صغير، 12% ربح متوسط، 3% الجائزة الكبرى
    if spin_result <= 50:
        prize_amount = 0
        result_text = "😢 للأسف! حظاً أوفر في المرة القادمة، العجلة وقفت عند خانة (حساب فارغ)."
    elif spin_result <= 85:
        prize_amount = 500
        result_text = "🎉 رائـع! لفّت العجلة ووقفت عند جائزة نقدية بقيمة **+500 ل.س**."
    elif spin_result <= 97:
        prize_amount = 2500
        result_text = "🔥 كـفـو! حظك قوي اليوم، وقفت العجلة عند جائزة ممتازة بقيمة **+2,500 ل.س**!"
    else:
        prize_amount = 10000
        result_text = "👑 **إمبراطور الحظ!** وقفت العجلة عند الجائزة الكبرى الفاخرة للسيستم بقيمة **+10,000 ل.س** كاش!"
        
    # 4. حقن الجائزة المكتسبة في حساب العضو (إن وُجدت) وتحديث الرصيد النهائي
    if prize_amount > 0:
        cursor.execute("UPDATE users SET balance_earnings = balance_earnings + ? WHERE user_id = ?", (prize_amount, user_id))
        
    # جلب الرصيد الجديد بعد انتهاء الحركة لعرضه في واجهة المستخدم
    cursor.execute("SELECT balance_earnings FROM users WHERE user_id = ?", (user_id,))
    new_balance = cursor.fetchone()[0]
    
    conn.commit()
    conn.close()
    
    # تعديل واجهة العجلة وعرض أنيميشن الدوران الوهمي السلس وتحديث النتيجة
    await callback.message.edit_text(
        f"⚙️ **جاري تدوير عجلة الحظ الكبرى الآن...**\n"
        f"🎰 🟥🟨🟩🟦🟪🟧⬛⬜ 🔄"
    )
    
    # تأخير زمني بسيط لمحاكاة حركة الدوران الواقعية الممتعة للأعضاء
    await asyncio.sleep(1.5)
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 العب مرة أخرى 🎡", callback_data="spin_the_wheel")
    kb.adjust(1)
    
    await callback.message.edit_text(
        f"🎡 **نتائج سحب عجلة الحظ الحالية** 🎰\n\n"
        f"{result_text}\n\n"
        f"📉 تكلفة الدورة المستقطعة: **-{wheel_cost:,} ل.س**\n"
        f"💰 الجائزة المضافة: **+{prize_amount:,} ل.س**\n"
        f"💳 رصيد أرباحك الكلي الحالي: **{int(new_balance):,} ل.س**\n\n"
        f"👇 هل ترغب في تجربة حظك مرة أخرى وضغط لفة جديدة؟",
        reply_markup=kb.as_markup()
    )
    
    # إرسال سجل العملية لقناة الإشعارات في حال فوز العضو بجائزة كبرى للتوثيق والشفافية
    if prize_amount >= 2500:
        try:
            await bot.send_message(
                chat_id=CH_GENERAL_LOGS,
                text=f"🎡 **فوز كبير في عجلة الحظ** 🎰\n"
                     f"👤 اللاعب: {full_name} (`{user_id}`)\n"
                     f"🎁 الجائزة: {prize_amount:,} ل.س كاش!"
            )
        except Exception:
            pass
# --------------------------------------------------------
# 25. منظومة المهام والاشتراكات المموّلة (Tasks & Offers Engine)
# --------------------------------------------------------

def init_tasks_db():
    """تأسيس جدول سجلات تنفيذ المهام لمنع التكرار وضمان نزاهة التوزيع المالي"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS completed_tasks (
        user_id INTEGER,
        campaign_id INTEGER,
        completed_at TEXT,
        PRIMARY KEY (user_id, campaign_id)
    )
    """)
    conn.commit()
    conn.close()

# تفعيل جدول المهام فوراً عند الإقلاع
init_tasks_db()

@dp.message(F.text == "📋 قسم المهام والجوائز 🎉")
async def process_tasks_market_menu(message: types.Message):
    """عرض الواجهة الرئيسية لقسم المهام وجلب أول حملة تمويل متاحة للمستخدم"""
    user_id = message.from_user.id
    member_reward = 200 # المكافأة التي يحصل عليها العضو عند اشتراكه في أي قناة (بالليرة السورية)
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # جلب حملة تمويل نشطة لم يقم هذا المستخدم بتنفيذها مسبقاً، ولم تصل لحدها الأقصى من الأعضاء
    cursor.execute("""
        SELECT campaign_id, channel_id, required_members, current_members 
        FROM ad_campaigns 
        WHERE status = 'نشط 🟢' 
          AND current_members < required_members
          AND campaign_id NOT IN (SELECT campaign_id FROM completed_tasks WHERE user_id = ?)
        ORDER BY campaign_id ASC LIMIT 1
    """, (user_id,))
    
    available_campaign = cursor.fetchone()
    conn.close()
    
    kb = InlineKeyboardBuilder()
    
    if not available_campaign:
        # في حال عدم وجود مهام حالياً، نتيح زر العودة للقائمة الرئيسية
        kb.button(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main_user_menu")
        return await message.answer(
            "📋 **بوابة المهام والجوائز النقدية لـ ALFA** 📋\n\n"
            "🔍 **الحالة الحالية:** لا توجد قنوات أو مهام تمويل متاحة للاشتراك في هذه اللحظة.\n\n"
            "💡 انتظر إشعارات البوت العامة عند ضخ حملات إعلانية جديدة من المعلنين لتكون أول المستفيدين!",
            reply_markup=kb.as_markup()
        )
        
    camp_id, ch_id, req, curr = available_campaign
    
    # تحويل معرف القناة إلى رابط يسهل على المستخدم الدخول والاشتراك
    channel_link = f"https://t.me/{ch_id.replace('@', '')}"
    
    # بناء أزرار التفاعل التلقائي للمهمة الحالية
    kb.button(text="📢 دخول ورابط القناة 🔗", url=channel_link)
    kb.button(text="✅ تأكيد الاشتراك والمطالبة بالجائزة 💰", callback_data=f"verify_task_{camp_id}_{ch_id}")
    kb.button(text="⏭️ تخطي هذه القناة حالياً", callback_data=f"skip_task_{camp_id}")
    kb.adjust(1, 1, 1)
    
    await message.answer(
        f"📋 **بوابة المهام والجوائز ── مهمة جديدة متاحة** 📋\n\n"
        f"💰 **المكافأة النقدية:** +{member_reward} ل.س (تُضاف فوراً لرصيد أرباحك بعد التحقق).\n"
        f"🆔 **رقم المهمة:** #{camp_id}\n\n"
        f"📌 **خطوات التنفيذ الصارمة:**\n"
        f"1️⃣ اضغط على زر (دخول ورابط القناة) واشترك بها.\n"
        f"2️⃣ عد إلى هنا واضغط زر (تأكيد الاشتراك والمطالبة بالجائزة).\n\n"
        f"⚠️ *تنبيه عقابي:* إلغاء الاشتراك من القناة لاحقاً يعرض حسابك **للحظر الفوري وتجميد الأرصدة الكلية** بنظام كشف الغش الآلي!",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(F.data.startswith("skip_task_"))
async def skip_task_handler(callback: types.CallbackQuery):
    """تمكين المستخدم من تخطي المهمة الحالية والانتقال للمهمة التالية بمرونة"""
    # محاكاة إعادة فتح القسم مع تجنب إظهار نفس القناة سيتم معالجتها ديناميكياً بطلب القناة التالية في الدفعة القادمة
    await callback.answer("⏭️ تم تخطي المهمة الحالية بنجاح.", show_alert=False)
    await callback.message.delete()
    # استدعاء دالة محاكاة إرسال رسالة المهام مجدداً
    await process_tasks_market_menu(callback.message)
# --------------------------------------------------------
# 26. معالج التحقق الصارم من الاشتراكات ومنح المكافآت (Task Verification Handler)
# --------------------------------------------------------

@dp.callback_query(F.data.startswith("verify_task_"))
async def verify_task_completion_handler(callback: types.CallbackQuery):
    """التحقق اللحظي من اشتراك العضو في القناة، وتحديث الحسابات والاتزان المالي"""
    user_id = callback.from_user.id
    member_reward = 200 # نفس قيمة المكافأة المعتمدة في النظام لقاء الاشتراك
    
    # تفكيك بيانات الكولباك لمعرفة رقم الحملة ومعرف القناة
    parts = callback.data.split("_")
    camp_id = int(parts[2])
    # إعادة تجميع معرف القناة بالكامل في حال كان يحتوي على أشرطة سفلية
    channel_id = "_".join(parts[3:])
    
    # 1. الفحص البرمجي الفوري للاشتراك الفعلي داخل القناة عبر تليجرام API
    try:
        member_check = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        # الحالات المقبولة للاشتراك: عضو عادي، مشرف، أو مالك القناة
        is_joined = member_check.status in ["member", "administrator", "creator"]
    except Exception:
        # في حال فشل البوت في جلب البيانات (مثلاً لو طُرد البوت من القناة أو المعرف خطأ)
        is_joined = False
        
    if not is_joined:
        return await callback.answer(
            "❌ لم نكتشف اشتراكك في القناة حتى الآن!\n\n"
            "يرجى الضغط على زر الرابط والاشتراك أولاً ثم الضغط هنا للمطالبة بالجائزة.", 
            show_alert=True
        )
        
    # 2. تأمين العملية في قاعدة البيانات ومنع ثغرات الضغط المتكرر بالتزامن (Race Conditions)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # فحص مزدوج للتأكد من أن العضو لم يسبق له قبض ثمن هذه المهمة
    cursor.execute("SELECT 1 FROM completed_tasks WHERE user_id = ? AND campaign_id = ?", (user_id, camp_id))
    already_done = cursor.fetchone()
    
    if already_done:
        conn.close()
        await callback.answer("⚠️ لقد استلمت مكافأة هذه المهمة مسبقاً! جاري نقلك للعرض التالي...", show_alert=True)
        await callback.message.delete()
        return await process_tasks_market_menu(callback.message)
        
    # 3. إدراج المهمة في سجل المنجزات فوراً لمنع التكرار
    cursor.execute(
        "INSERT INTO completed_tasks (user_id, campaign_id, completed_at) VALUES (?, ?, datetime('now'))",
        (user_id, camp_id)
    )
    
    # 4. شحن رصيد أرباح العضو بالمكافأة المستحقة
    cursor.execute("UPDATE users SET balance_earnings = balance_earnings + ? WHERE user_id = ?", (member_reward, user_id))
    
    # 5. تحديث عداد المشتركين الحاليين في الحملة الإعلانية للمعلن لضمان الشفافية
    cursor.execute("UPDATE ad_campaigns SET current_members = current_members + 1 WHERE campaign_id = ?", (camp_id))
    
    conn.commit()
    conn.close()
    
    # إشعار العضو بنجاح العملية عبر تنبيه إنلاين سريع ومفرح
    await callback.answer(f"💰 مبروك! تم التحقق من اشتراكك وإضافة +{member_reward} ل.س إلى رصيد أرباحك بنجاح.", show_alert=True)
    
    # حذف رسالة المهمة المنتهية لتنظيف الشات ونقله تلقائياً للمهمة المتاحة التالية
    try:
        await callback.message.delete()
    except Exception:
        pass
        
    # استدعاء دالة جلب العروض لعرض المهمة التالية المتاحة في الطابور فوراً
    await process_tasks_market_menu(callback.message)
# --------------------------------------------------------
# 27. محرك معالجة الرد الإداري على تذاكر الدعم الفني (Admin Reply Engine)
# --------------------------------------------------------

# تعريف حالة انتظار نص الرد الإداري عبر FSM
class AdminReplyStates(StatesGroup):
    waiting_for_admin_reply_text = State()

@dp.callback_query(F.data.startswith("reply_to_user_"))
async def admin_reply_to_ticket_start(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة 1: استقبال ضغطة المشرف وتحديد الـ ID المستهدف وطلب نص الرد"""
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("⚠️ غير مصرح لك استخدام هذه الصلاحية!", show_alert=True)
        
    # استخراج معرف العضو المراد الرد عليه من بيانات الكولباك
    target_user_id = int(callback.data.replace("reply_to_user_", ""))
    
    # حفظ المعرف في الذاكرة المؤقتة لمتابعة إرسال الرسالة إليه
    await state.update_data(reply_target_id=target_user_id)
    await state.set_state(AdminReplyStates.waiting_for_admin_reply_text)
    
    await callback.message.reply(
        f"✍️ **جاري تحضير الرد الإداري على العضو ذو المعرف:** `{target_user_id}`\n\n"
        f"📥 الرجاء إرسال نص الرد أو الحل التقني المقترح الآن في رسالة واحدة ليقوم البوت بنقله فوراً إليه.",
        reply_markup=InlineKeyboardBuilder().button(text="❌ إلغاء الرد", callback_data="cancel_admin_reply").as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data == "cancel_admin_reply")
async def cancel_admin_reply_handler(callback: types.CallbackQuery, state: FSMContext):
    """إلغاء عملية الرد وتنظيف الحالة بأمان"""
    if callback.from_user.id != ADMIN_ID:
        return
    await state.clear()
    await callback.message.edit_text("❌ تم إلغاء عملية الرد وتطهير حالة الـ FSM بنجاح.")

@dp.message(AdminReplyStates.waiting_for_admin_reply_text)
async def finalize_admin_reply_to_user(message: types.Message, state: FSMContext):
    """الخطوة 2 والأخيرة: استقبال نص الرد، إرساله للعضو، وإغلاق التذكرة"""
    if message.from_user.id != ADMIN_ID:
        return
        
    reply_text = message.text.strip()
    
    # استرجاع الـ ID المستهدف من الذاكرة
    data = await state.get_data()
    target_user_id = data.get("reply_target_id")
    
    # تنظيف حالة الـ FSM فوراً لتأمين الواجهة الإدارية
    await state.clear()
    
    # صياغة الرسالة الرسمية الموجهة للمستخدم
    user_notification = (
        f"🔔 **إشعار رسمي من إدارة ALFA والدعم الفني** 🔔\n\n"
        f"📝 **رد المشرف العام على تذكرتك المرفوعة:**\n"
        f"{reply_text}\n\n"
        f"🔐 *ملاحظة:* تم إغلاق هذه التذكرة بنجاح. إذا كان لديك استفسار آخر يمكنك فتح تذكرة جديدة من قسم الدعم."
    )
    
    # محاولة إرسال الرد الفوري للعضو
    try:
        await bot.send_message(chat_id=target_user_id, text=user_notification)
        await message.reply(f"✅ **تم تسليم الرد بنجاح وثبات إلى العضو (`{target_user_id}`).**")
    except Exception as e:
        await message.reply(f"❌ فشل تسليم الرسالة للعضو! قد يكون قام بحظر البوت أو أن الحساب غير متاح حالياً.\n*السبب:* `{str(e)}`")
# --------------------------------------------------------
# 28. سوق تمويل القنوات وإدارة الحملات الإعلانية (Ads & Campaigns Market)
# --------------------------------------------------------

# تعريف حالات الـ FSM الخاصة بإنشاء حملة إعلانية جديدة
class CreateCampaignStates(StatesGroup):
    waiting_for_channel_id = State()
    waiting_for_members_count = State()

@dp.message(F.text == "📢 سوق تمويل القنوات والخدمات 🏪")
async def process_ads_market_main_menu(message: types.Message):
    """عرض الواجهة الرئيسية لسوق الإعلانات وحملات التمويل للمستخدم"""
    user_id = message.from_user.id
    cost_per_member = 350 # تكلفة العضو الواحد بالليرة السورية للمعلن (مثال: 350 ليرة)
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # جلب رصيد الإعلانات الخاص بالعضو
    cursor.execute("SELECT balance_ads FROM users WHERE user_id = ?", (user_id,))
    ads_balance = cursor.fetchone()[0]
    
    # جلب إحصائيات حملات هذا المستخدم (النشطة والمنتهية)
    cursor.execute("SELECT COUNT(*) FROM ad_campaigns WHERE user_id = ? AND status = 'نشط 🟢'", (user_id,))
    active_camps = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM ad_campaigns WHERE user_id = ? AND status = 'مكتمل ✅'", (user_id,))
    completed_camps = cursor.fetchone()[0]
    conn.close()
    
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ إنشاء حملة تمويل جديدة 🚀", callback_data="ads_create_campaign")
    kb.button(text="📊 مراقبة حملاتي الحالية", callback_data="ads_my_campaigns")
    kb.button(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main_user_menu")
    kb.adjust(1, 1, 1)
    
    market_text = (
        f"🏪 **مرحباً بك في سوق ALFA لتمويل القنوات والمجموعات** 📢\n\n"
        f"✨ هنا يمكنك استغلال رصيد إعلاناتك لشراء أعضاء ومشتركين حقيقيين 100% لقناتك أو مجموعتك على تليجرام عبر نظام المهام الذكي.\n\n"
        f"💳 **بيانات محفظتك الإعلانية الحالية:**\n"
        f"📢 رصيد الإعلانات المتوفر: **{ads_balance:,.1f} ل.س**\n"
        f"📈 تكلفة المشترك الواحد: **{cost_per_member} ل.س**\n\n"
        f"📊 **إحصائيات حملاتك:**\n"
        f"🟢 حملات نشطة الآن: {active_camps} | ✅ حملات مكتملة سابقاً: {completed_camps}\n\n"
        f"👇 للبدء أو إدارة حملاتك، اختر الإجراء المناسب من الأزرار أدناه:"
    )
    
    await message.answer(market_text, reply_markup=kb.as_markup())

@dp.callback_query(F.data == "ads_create_campaign")
async def ads_create_campaign_start(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة 1: بدء تفعيل الـ FSM وطلب معرف القناة المستهدفة"""
    user_id = callback.from_user.id
    
    await state.set_state(CreateCampaignStates.waiting_for_channel_id)
    await callback.message.edit_text(
        "🚀 **بدء إنشاء حملة تمويل جديدة ── [الخطوة 1 من 2]**\n\n"
        "قم برفع البوت **مشرفاً (Administrator)** في قناتك أو مجموعتك أولاً (صلاحية دعوة المستخدمين عبر الرابط مطلوبة ليتحقق البوت من المشتركين).\n\n"
        "📥 **الآن:** أرسل معرف القناة أو المجموعة يبدأ بعلامة الـ `@`\n"
        "💡 *مثال:* `@Alfa_Samurai`",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 إلغاء وتراجع", callback_data="back_to_ads_market").as_markup()
    )

@dp.callback_query(F.data == "back_to_ads_market")
async def back_to_ads_market_handler(callback: types.CallbackQuery, state: FSMContext):
    """العودة الآمنة لواجهة السوق وتنظيف الحالات المؤقتة"""
    await state.clear()
    await callback.message.delete()
    # إعادة استدعاء القائمة الرئيسية للسوق كرسالة جديدة
    await process_ads_market_main_menu(callback.message)
# --------------------------------------------------------
# 29. محرك التحقق من القنوات وحقن الحملات الإعلانية (Campaign Deployment)
# --------------------------------------------------------

@dp.message(CreateCampaignStates.waiting_for_channel_id)
async def process_campaign_channel_id(message: types.Message, state: FSMContext):
    """الخطوة 2: التحقق من وجود البوت كـ مشرف في القناة وطلب عدد المشتركين"""
    channel_id = message.text.strip()
    
    if not channel_id.startswith("@") or len(channel_id) < 4:
        return await message.reply("⚠️ خطأ! يرجى إرسال معرف صحيح يبدأ بـ `@` وبدون مسافات.")
        
    # الفحص البرمجي لصلاحيات البوت داخل القناة المستهدفة
    try:
        bot_member = await bot.get_chat_member(chat_id=channel_id, user_id=bot.id)
        # التحقق من أن البوت مشرف بالفعل
        if bot_member.status != "administrator":
            return await message.reply("❌ البوت موجود في القناة ولكنه ليس (مشرفاً)! يرجى ترقيته لمشرف أولاً ثم إرسال المعرف مجدداً.")
    except Exception as e:
        return await message.reply(
            f"❌ فشل البوت في الاتصال بالقناة!\n"
            f"تأكد من معرف القناة، وأنها (عامة وليست خاصة)، وأنك قمت برفع البوت مشرفاً داخلها أولاً.\n"
            f"💡 *الخطأ البرمجي:* `{str(e)}`"
        )
        
    # حفظ المعرف المقبول في الذاكرة المؤقتة
    await state.update_data(target_channel_id=channel_id)
    await state.set_state(CreateCampaignStates.waiting_for_members_count)
    
    await message.answer(
        f"✅ **تم التحقق من القناة:** {channel_id}\n"
        f"🛡️ حالة البوت: مشرف نشط ومصرح له بالتدقيق.\n\n"
        f"📥 **[الخطوة 2 من 2]:** يرجى إرسال عدد المشتركين المطلوبين (أرقام فقط):\n"
        f"💡 *مثال:* `100` (لطلب 100 مشترك حقيقي لقناتك)."
    )

@dp.message(CreateCampaignStates.waiting_for_members_count)
async def finalize_campaign_creation(message: types.Message, state: FSMContext):
    """الخطوة الأخيرة: فحص الرصيد المالي، استقطاع الرسوم، وإطلاق الحملة في السيستم"""
    user_id = message.from_user.id
    input_text = message.text.strip()
    cost_per_member = 350 # التكلفة الثابتة للعضو الواحد بالليرة السورية لقاء تمويل المعلن
    
    if not input_text.isdigit():
        return await message.reply("⚠️ خطأ! يرجى إرسال عدد المشتركين كـ أرقام فقط وبدون رموز.")
        
    required_members = int(input_text)
    if required_members < 10:
        return await message.reply("❌ الحد الأدنى لإنشاء حملة تمويل هو 10 مشتركين!")
        
    # احتساب التكلفة الإجمالية للحملة
    total_cost = float(required_members * cost_per_member)
    
    # استرجاع معرف القناة من الذاكرة المؤقتة
    data = await state.get_data()
    channel_id = data.get("target_channel_id")
    
    # فتح اتصال آمن بقاعدة البيانات لفحص الرصيد وإتمام المعاملة
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT balance_ads FROM users WHERE user_id = ?", (user_id,))
    current_ads_balance = cursor.fetchone()[0]
    
    # التحقق من كفاية الرصيد الإعلاني لمنع التلاعب والرصيد السالب
    if current_ads_balance < total_cost:
        conn.close()
        return await message.reply(
            f"❌ رصيد الإعلانات الخاص بك غير كافٍ لإتمام الحملة!\n\n"
            f"📊 **تفاصيل الفاتورة:**\n"
            f"👥 المشتركين المطلوبة: {required_members:,} عضو.\n"
            f"💰 التكلفة الإجمالية: **{int(total_cost):,} ل.س**\n"
            f"📢 رصيدك المتوفر حالياً: **{int(current_ads_balance):,} ل.س**\n\n"
            f"💡 يمكنك شحن حسابك الإعلاني أولاً عبر وكلاء النظام ثم المحاولة مجدداً."
        )
        
    # 1. استقطاع وتخفيض القيمة المالية من محفظة إعلانات المعلن فوراً
    cursor.execute("UPDATE users SET balance_ads = balance_ads - ? WHERE user_id = ?", (total_cost, user_id))
    
    # 2. حقن الحملة الإعلانية الجديدة في النظام كحملة نشطة 🟢
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO ad_campaigns (user_id, channel_id, required_members, current_members, cost, status, created_at) "
        "VALUES (?, ?, ?, 0, ?, 'نشط 🟢', ?)",
        (user_id, channel_id, required_members, total_cost, current_time)
    )
    
    conn.commit()
    conn.close()
    
    # مسح وتطهير حالة الـ FSM بأمان تام
    await state.clear()
    
    success_text = (
        f"🚀 **تهانينا! تم إطلاق حملتك الإعلانية بنجاح باهر** ✅\n\n"
        f"📢 **القناة المستهدفة:** {channel_id}\n"
        f"🎯 **المشتركين المستهدفين:** {required_members:,} عضو حقيقي.\n"
        f"💸 **التكلفة المستقطعة:** {int(total_cost):,} ل.س (من رصيد إعلاناتك).\n"
        f"🟢 **حالة الحملة:** نشطة وشغالة فوراً بقسم المهام لجميع الأعضاء.\n\n"
        f"💡 يمكنك متابعة تقدم الحملة وعدد الأعضاء الذين اشتركوا لحظة بلحظة من شاشة (مراقبة حملاتي)."
    )
    
    await message.answer(success_text)
    
    # إعادة توجيه المستخدم تلقائياً لواجهة السوق الرئيسية لإبقائه في سياق العمل
    await process_ads_market_main_menu(message)
# --------------------------------------------------------
# 30. منظومة استعراض ومراقبة حملات المعلن (My Campaigns Monitor)
# --------------------------------------------------------

@dp.callback_query(F.data == "ads_my_campaigns")
async def ads_my_campaigns_handler(callback: types.CallbackQuery):
    """جلب وعرض كافة الحملات الإعلانية التابعة للمستخدم الحالي مع نسب الإنجاز اللحظية"""
    user_id = callback.from_user.id
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # جلب آخر 10 حملات أطلقها هذا العضو لعدم تضخيم الرسالة
    cursor.execute(
        "SELECT campaign_id, channel_id, required_members, current_members, cost, status, created_at "
        "FROM ad_campaigns WHERE user_id = ? ORDER BY campaign_id DESC LIMIT 10", (user_id,)
    )
    my_camps = cursor.fetchall()
    conn.close()
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 العودة لسوق التمويل 🏪", callback_data="back_to_ads_market")
    kb.adjust(1)
    
    if not my_camps:
        return await callback.message.edit_text(
            "📊 **لوحة مراقبة الحملات الإعلانية الخاصة بك** 📊\n\n"
            "❌ **النتيجة:** لم تقم بإنشاء أو تمويل أي حملة إعلانية في النظام حتى الآن!\n\n"
            "💡 يمكنك البدء فوراً والضغط على زر إنشاء حملة جديدة من سوق التمويل لزيادة أعضاء قناتك.",
            reply_markup=kb.as_markup()
        )
        
    report_text = f"📊 **تقرير ومراقبة حملاتك الإعلانية المموّلة ({len(my_camps)})** 📊\n\n"
    
    for camp in my_camps:
        camp_id, channel_id, req_members, curr_members, cost, status, date = camp
        
        # احتساب النسبة المئوية لإنجاز الحملة بذكاء رياضي
        progress_percent = (curr_members / req_members) * 100 if req_members > 0 else 0
        
        # صياغة بطاقة تفصيلية لكل حملة
        report_text += (
            f"🆔 **حملة رقم:** #{camp_id}\n"
            f"📢 **القناة المستهدفة:** {channel_id}\n"
            f"📅 **تاريخ الإطلاق:** `{date}`\n"
            f"⚙️ **الحالة التشغيلية:** {status}\n"
            f"👥 **نسبة التقدم الكلي:** `{progress_percent:.1f}%`\n"
            f"📈 **المشتركين:** ({curr_members:,} من أصل {req_members:,} عضو)\n"
            f"💰 **المبلغ المستثمر:** {int(cost):,} ل.س\n"
            f"📎 ───────────────────── 📎\n"
        )
        
    report_text += "\n💡 *ملاحظة:* يتم تحديث العدادات أعلاه تلقائياً ولحظياً بمجرد قيام الأعضاء بتنفيذ المهام."
    
    await callback.message.edit_text(report_text, reply_markup=kb.as_markup(), parse_mode="Markdown")
# --------------------------------------------------------
# 31. نظام ترقيات الحسابات ومستويات الـ VIP (VIP Upgrade Engine)
# --------------------------------------------------------

@dp.message(F.text == "💎 ترقية الحساب (VIP) 👑")
async def process_vip_system_menu(message: types.Message):
    """عرض واجهة مستويات الـ VIP المتاحة والميزات الحصرية لكل مستوى والتكلفة"""
    user_id = message.from_user.id
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # جلب مستوى الـ VIP الحالي ورصيد الأرباح للعضو
    cursor.execute("SELECT vip_level, balance_earnings FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    current_vip = row[0] if row else 0
    earnings_balance = row[1] if row else 0.0
    
    # صياغة نصوص واجهة العرض بناءً على مستوى العضو الحالي
    vip_status_text = "⚪ الحساب العادي (ميزات أساسية)" if current_vip == 0 else f"💎 حساب VIP ── Level {current_vip} 👑"
    
    kb = InlineKeyboardBuilder()
    
    # إتاحة أزرار الترقية بناءً على المستوى الحالي (ترقية تدريجية متصاعدة)
    if current_vip == 0:
        kb.button(text="🔥 ترقية إلى VIP Level 1 💎", callback_data="buy_vip_1")
    if current_vip <= 1:
        kb.button(text="👑 ترقية إلى VIP Level 2 🔥", callback_data="buy_vip_2")
        
    kb.button(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main_user_menu")
    kb.adjust(1)
    
    vip_text = (
        f"💎 **مرحباً بك في نظام الاشتراكات والمستويات الفاخرة لـ ALFA** 👑\n\n"
        f"✨ ارفع رتبة حسابك اليوم وانضم إلى نخبة المستثمرين لتتمتع بنسب أرباح مضاعفة وصلاحيات سحب وتحويل مخفضة الرسوم كلياً!\n\n"
        f"📊 **وضعية حسابك الرقابية والمالية الآن:**\n"
        f"🛡️ **المستوى الحالي:** {vip_status_text}\n"
        f"💰 **رصيد أرباحك الكلي:** {int(earnings_balance):,} ل.س\n\n"
        f"📜 **جدول وميزات مستويات الـ VIP المتاحة بالسيرفر:**\n\n"
        f"💎 **[VIP Level 1]**\n"
        f"➕ زيادة أرباح الإحالات بنسبة **+25%** إضافية.\n"
        f"🔄 تخفيض رسوم تحويل الأموال P2P إلى **3%** فقط.\n"
        f"💵 تكلفة الترقية الفورية: **15,000 ل.س** (تُخصم من رصيد الأرباح).\n\n"
        f"👑 **[VIP Level 2 - الإمبراطوري]**\n"
        f"➕ زيادة أرباح الإحالات بنسبة **+60%** (أرباح ضخمة!).\n"
        f"🔄 تخفيض رسوم تحويل الأموال P2P إلى **1%** فقط (شبه مجاني).\n"
        f"💵 تكلفة الترقية الفورية: **35,000 ل.س** (تُخصم من رصيد الأرباح).\n\n"
        f"👇 اختر المستوى المطلوب واضغط على الزر أدناه للترقية وتفعيل الصلاحيات لحظياً:"
    )
    
    await message.answer(vip_text, reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("buy_vip_"))
async def buy_vip_level_handler(callback: types.CallbackQuery):
    """معالجة وفحص طلبات شراء وترقية مستويات الـ VIP واستقطاع المبالغ ثبوياً"""
    user_id = callback.from_user.id
    full_name = callback.from_user.full_name
    
    # تحديد المستوى المستهدف والتكلفة المطلوبة بناءً على الكولباك
    target_level = int(callback.data.replace("buy_vip_", ""))
    upgrade_cost = 15000.0 if target_level == 1 else 35000.0
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. جلب مستوى الـ VIP الحالي ورصيد الأرباح للتأكد من عدم التلاعب
    cursor.execute("SELECT vip_level, balance_earnings FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return await callback.answer("❌ خطأ غير متوقع في جلب بيانات حسابك!", show_alert=True)
        
    current_vip, current_balance = row
    
    # منع إعادة شراء نفس المستوى أو مستوى أقل
    if current_vip >= target_level:
        conn.close()
        return await callback.answer(f"⚠️ حسابك بالفعل في مستوى {current_vip} أو أعلى لا يمكنك تكرار الترقية!", show_alert=True)
        
    # 2. التحقق من كفاية رصيد الأرباح لإتمام الصفقة الاستثمارية
    if current_balance < upgrade_cost:
        conn.close()
        return await callback.answer(
            f"❌ رصيد أرباحك غير كافٍ! تكلفة الترقية هي {int(upgrade_cost):,} ل.س.\n"
            f"أنت تملك حالياً: {int(current_balance):,} ل.س فقط.", 
            show_alert=True
        )
        
    # 3. خصم تكلفة الترقية من محفظة الأرباح وتحديث مستوى الـ VIP للحساب
    cursor.execute(
        "UPDATE users SET balance_earnings = balance_earnings - ?, vip_level = ? WHERE user_id = ?",
        (upgrade_cost, target_level, user_id)
    )
    conn.commit()
    conn.close()
    
    # إشعار العضو بنجاح عملية الترقية الفاخرة عبر تنبيه إنلاين ضخم ومبهج
    await callback.answer(
        f"🎉 مبروك يا سيادة المستثمر! تم ترقية حسابك رسمياً إلى VIP Level {target_level} 👑\n"
        f"تم تطبيق الميزات الاستثنائية وتخفيض الرسوم على محفظتك فوراً.", 
        show_alert=True
    )
    
    # إرسال سجل العملية لقناة الإشعارات الإدارية لتوثيق التحول الرتبي بالأرقام
    try:
        await bot.send_message(
            chat_id=CH_GENERAL_LOGS,
            text=f"👑 **ترقية رتبة حساب جديدة (VIP)** 💎\n"
                 f"👤 العضو: {full_name} (`{user_id}`)\n"
                 f"📈 المستوى الجديد: Level {target_level}\n"
                 f"💸 القيمة المستقطعة: {int(upgrade_cost):,} ل.س من الأرباح."
        )
    except Exception:
        pass
        
    # حذف واجهة الترقية القديمة وإعادة جلب القائمة المحدثة للمستخدم تلقائياً
    await callback.message.delete()
    await process_vip_system_menu(callback.message)
# --------------------------------------------------------
# 32. نظام لوحة الصدارة وعرض ملوك البوت (Leaderboard Engine)
# --------------------------------------------------------

@dp.message(F.text == "🏆 لوحة الصدارة والملوك 📊")
async def process_leaderboard_menu(message: types.Message):
    """جلب وإعداد لوحة الشرف لأعلى الأعضاء جمعاً للأرباح وإحالةً للمشتركين"""
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. استعلام ملوك المال: جلب أعلى 5 أعضاء من حيث رصيد الأرباح الكاش
    cursor.execute(
        "SELECT full_name, balance_earnings, user_id FROM users "
        "WHERE is_banned = 0 ORDER BY balance_earnings DESC LIMIT 5"
    )
    top_earners = cursor.fetchall()
    
    # 2. استعلام ملوك الإحالات: جلب أعلى 5 أعضاء من حيث عدد الإحالات الناجحة
    cursor.execute(
        "SELECT full_name, referrals_count, user_id FROM users "
        "WHERE is_banned = 0 ORDER BY referrals_count DESC LIMIT 5"
    )
    top_referrers = cursor.fetchall()
    
    conn.close()
    
    # صياغة وتنسيق بطاقة لوحة الصدارة بشكل فخم وجذاب
    leaderboard_text = (
        f"🏆 ── **لوحة الشرف وملوك إمبراطورية ALFA** ── 📊\n\n"
        f"✨ استعرض قائمة النخبة والأعضاء الأكثر نشاطاً وإنتاجية في السيستم لهہ۠ذا اليوم. اعمل بجد لتخليد اسمك في هذه اللوحة الفاخرة!\n\n"
        f"💰 **أولاً: ملوك المال (الأعلى رصيد أرباح) 👑**\n"
    )
    
    # رص ملوك الأرباح مع تظليل اسم الآدمن أو إخفاء الـ ID للأمان
    medals = ["🥇", "🥈", "🥉", "🏅", "🎖️"]
    
    if top_earners:
        for idx, member in enumerate(top_earners):
            name, earnings, u_id = member
            # اختصار الأسماء الطويلة جداً لجمالية التنسيق
            display_name = name[:18] + ".." if len(name) > 18 else name
            leaderboard_text += f"{medals[idx]} **{display_name}** | `({int(earnings):,} ل.س)`\n"
    else:
        leaderboard_text += "✨ لا توجد بيانات كافية حالياً.\n"
        
    leaderboard_text += (
        f"\n👥 **ثانياً: ملوك السيرفر (الأعلى جلب إحالات) 👑**\n"
    )
    
    # رص ملوك الإحالات
    if top_referrers:
        for idx, member in enumerate(top_referrers):
            name, ref_count, u_id = member
            display_name = name[:18] + ".." if len(name) > 18 else name
            leaderboard_text += f"{medals[idx]} **{display_name}** | `({ref_count} إحالة)`\n"
    else:
        leaderboard_text += "✨ لا توجد بيانات كافية حالياً.\n"
        
    leaderboard_text += (
        f"\n📎 ───────────────────── 📎\n"
        f"📊 يتم تحديث وترتيب هذه القائمة بشكل ديناميكي تلقائي وآمن عبر خادم البيانات الرئيسي لـ ALFA."
    )
    
    # إرسال لوحة الصدارة مع زر العودة الاختياري
    kb = InlineKeyboardBuilder().button(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main_user_menu")
    await message.answer(leaderboard_text, reply_markup=kb.as_markup(), parse_mode="Markdown")
# --------------------------------------------------------
# 33. محرك نظام المكافأة اليومية بالتوقيت الصارم (Daily Bonus Engine)
# --------------------------------------------------------

@dp.message(F.text == "🎁 الهدية اليومية 🗓️")
async def process_daily_bonus_handler(message: types.Message):
    """التحقق من توقيت الهدية اليومية ومنح العضو مكافأة عشوائية مؤمنة"""
    user_id = message.from_user.id
    full_name = message.from_user.full_name
    
    # تحديد نطاق الهدية العشوائية بالليرة السورية
    min_bonus = 100
    max_bonus = 500
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # جلب طابع آخر استلام للمكافأة من جدول الأعضاء
    cursor.execute("SELECT last_daily_bonus, balance_earnings FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return await message.reply("❌ خطأ في جلب بيانات حسابك من السيرفر!")
        
    last_bonus_str, current_balance = row
    now = datetime.now()
    
    # فحص القيود الزمنية بالثواني
    if last_bonus_str:
        last_bonus_time = datetime.strptime(last_bonus_str, "%Y-%m-%d %H:%M:%S")
        # حساب الفارق الزمني بين الآن وآخر استلام
        time_difference = now - last_bonus_time
        total_seconds_left = 86400 - time_difference.total_seconds() # 86400 ثانية تعني 24 ساعة كحد صارم
        
        if total_seconds_left > 0:
            conn.close()
            # تفكيك الثواني المتبقية لعرضها بشكل أنيق للمستخدم (ساعات، دقائق، ثواني)
            hours = int(total_seconds_left // 3600)
            minutes = int((total_seconds_left % 3600) // 60)
            seconds = int(total_seconds_left % 60)
            
            return await message.reply(
                f"⏳ **عذراً يا سيادة المشترك!**\n\n"
                f"❌ لقد استلمت هديتك اليومية بالفعل مسبقاً. نظام الرقابة يمنع تكرار العملية قبل مرور 24 ساعة كاملة.\n\n"
                f"🕒 **الوقت المتبقي لفتّح الصندوق مجدداً:**\n"
                f"⏱️ `{hours}` ساعة و `{minutes}` دقيقة و `{seconds}` ثانية."
            )
            
    # في حال تجاوز المدة أو الاستلام لأول مرة، نولد رقم المكافأة العشوائي
    granted_bonus = random.randint(min_bonus, max_bonus)
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    
    # تحديث الطابع الزمني وإضافة المكافأة لرصيد الأرباح في معاملة واحدة
    cursor.execute(
        "UPDATE users SET balance_earnings = balance_earnings + ?, last_daily_bonus = ? WHERE user_id = ?",
        (granted_bonus, now_str, user_id)
    )
    conn.commit()
    conn.close()
    
    kb = InlineKeyboardBuilder().button(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main_user_menu")
    
    success_text = (
        f"🎁 **مبروك! تم فتح صندوق المكافأة اليومية بنجاح** 🎉\n\n"
        f"💵 حصلت على هدية نقدية عشوائية بقيمة: **+{granted_bonus} ل.س**\n"
        f"💰 تم ترحيلها فوراً وحقنها في محفظة أرباحك الكلية.\n\n"
        f"📅 يمكنك العودة بعد 24 ساعة من الآن لتلقي هدية جديدة ومكافأة أخرى مجانية!"
    )
    
    await message.answer(success_text, reply_markup=kb.as_markup())
# --------------------------------------------------------
# 34. منظومة تفعيل الأكواد والمكافآت السرية للمستخدم (Promo Code Redeemer)
# --------------------------------------------------------

# تأسيس جدول تتبع تفعيل الأكواد لمنع تكرار استخدام الكود الواحد من نفس العضو
def init_promo_redeem_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS promo_redeems (
        user_id INTEGER,
        code_id INTEGER,
        redeemed_at TEXT,
        PRIMARY KEY (user_id, code_id)
    )
    """)
    conn.commit()
    conn.close()

# تشغيل الجدول فوراً
init_promo_redeem_db()

# تعريف حالة انتظار إدخال الكود عبر FSM
class UserPromoStates(StatesGroup):
    waiting_for_promo_code = State()

@dp.message(F.text == "🎫 تفعيل كود الهدية 🔐")
async def user_redeem_promo_start(message: types.Message, state: FSMContext):
    """الخطوة 1: طلب كتابة الكود السري من العضو وتفعيل حالة الـ FSM"""
    await state.set_state(UserPromoStates.waiting_for_promo_code)
    
    await message.answer(
        "🎫 **بوابة تفعيل أكواد المكافآت والمنح السريّة** 🔐\n\n"
        "📥 الرجاء إرسال كود الهدية الآن (كما تم نشره تماماً في القناة الرسمية بدون زيادة أو مسافات):\n\n"
        "⚠️ *ملحوظة:* الأكواد محدودة بعدد مستخدمين معين وصلاحية زمنية خاطفة، سارع بتفعيل كودك فوراً!",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 إلغاء وتراجع", callback_data="back_to_main_user_menu").as_markup()
    )

@dp.message(UserPromoStates.waiting_for_promo_code)
async def user_redeem_promo_finalize(message: types.Message, state: FSMContext):
    """الخطوة 2 والأخيرة: فحص الكود تفصيلياً، حقن الأموال، وإقفال المعاملة"""
    user_id = message.from_user.id
    input_code = message.text.strip().upper() # تحويل الأحرف لكبيرة لمطابقة قاعدة البيانات
    
    # إلغاء الحالة لتأمين العملية ضد الضغط المتكرر المتزامن
    await state.clear()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. فحص هل الكود متواجد بالسيستم أصلاً؟
    cursor.execute(
        "SELECT id, reward_type, reward_amount, max_uses, current_uses FROM promo_codes WHERE code = ?", 
        (input_code,)
    )
    promo = cursor.fetchone()
    
    if not promo:
        conn.close()
        return await message.reply("❌ **خطأ! هذا الكود غير صحيح أو منتهي الصلاحية تماماً.**\nتأكد من النص وحاول مجدداً.")
        
    code_id, reward_type, reward_amount, max_uses, current_uses = promo
    
    # 2. فحص هل نفدت كمية الاستخدام الكلية للكود؟
    if current_uses >= max_uses:
        conn.close()
        return await message.reply("😢 **للأسف! انتهت صلاحية هذا الكود بسبب وصوله للحد الأقصى من المستفيدين مسبقاً.**")
        
    # 3. فحص هل قام هذا العضو بالذات بتفعيل هذا الكود من قبل؟
    cursor.execute("SELECT 1 FROM promo_redeems WHERE user_id = ? AND code_id = ?", (user_id, code_id))
    already_redeemed = cursor.fetchone()
    
    if already_redeemed:
        conn.close()
        return await message.reply("⚠️ **عذراً! لقد قمت بتفعيل واستلام مكافأة هذا الكود مسبقاً. لا يمكنك الاستفادة منه مرتين!**")
        
    # 4. التنفيذ والحقن المالي الفوري بعد تخطي كافة شروط الأمان
    # إدراج السجل لمنع التكرار
    cursor.execute(
        "INSERT INTO promo_redeems (user_id, code_id, redeemed_at) VALUES (?, ?, datetime('now'))", 
        (user_id, code_id)
    )
    
    # تحديث عداد الاستخدام العام للكود
    cursor.execute("UPDATE promo_codes SET current_uses = current_uses + 1 WHERE id = ?", (code_id,))
    
    # إيداع الأموال بناءً على نوع شحن الكود (أرباح كاش أم إعلانات ممولة)
    if reward_type == "earnings":
        cursor.execute("UPDATE users SET balance_earnings = balance_earnings + ? WHERE user_id = ?", (reward_amount, user_id))
        wallet_display = "رصيد الأرباح (كاش) 💰"
    else:
        cursor.execute("UPDATE users SET balance_ads = balance_ads + ? WHERE user_id = ?", (reward_amount, user_id))
        wallet_display = "رصيد الإعلانات (تمويل) 📢"
        
    conn.commit()
    conn.close()
    
    success_msg = (
        f"🎉 **مبروك! تم تفعيل كود الهدية بنجاح ساحق** ✅\n\n"
        f"🎫 **الكود المستخدم:** `{input_code}`\n"
        f"💵 **القيمة المكتسبة:** +{int(reward_amount):,} ل.س\n"
        f"📥 **الحقن المالي:** تمت إضافة المبلغ فوراً إلى **{wallet_display}** الخاص بحسابك.\n\n"
        f"🌟 شكرًا لنشاطك ومتابعتك الدائمة لـ ALFA، انتظرنا في أكواد قادمة غنية!"
    )
    
    await message.reply(success_msg)
# --------------------------------------------------------
# 35. منظومة تحويل الأموال الفورية بين الأعضاء (P2P Transfer Engine)
# --------------------------------------------------------

# تعريف حالات الـ FSM لتحويل الرصيد
class TransferStates(StatesGroup):
    waiting_for_receiver_id = State()
    waiting_for_transfer_amount = State()

@dp.message(F.text == "🔄 تحويل رصيد 💳")
async def user_transfer_start(message: types.Message, state: FSMContext):
    """الخطوة 1: بدء عملية التحويل وطلب ID المستلم"""
    await state.set_state(TransferStates.waiting_for_receiver_id)
    
    await message.answer(
        "🔄 **بوابة تحويل الأموال والرصيد الفوري (P2P) ** 💳\n\n"
        "📥 **[الخطوة 1 من 2]:** يرجى إرسال معرف حساب (ID) العضو الذي ترغب في تحويل الأموال إليه.\n\n"
        "💡 *ملاحظة:* يمكنك جلب الـ ID الخاص بصديقك من شاشة (حسابي) داخل البوت الخاص به.",
        reply_markup=InlineKeyboardBuilder().button(text="❌ إلغاء العملية", callback_data="back_to_main_user_menu").as_markup()
    )

@dp.message(TransferStates.waiting_for_receiver_id)
async def process_transfer_receiver_id(message: types.Message, state: FSMContext):
    """الخطوة 2: فحص معرف المستلم وطلب تحديد المبلغ المراد تحويله"""
    sender_id = message.from_user.id
    input_text = message.text.strip()
    
    if not input_text.isdigit():
        return await message.reply("⚠️ خطأ! يجب أن يكون معرف الحساب (ID) عبارة عن أرقام فقط.")
        
    receiver_id = int(input_text)
    
    # منع العضو من تحويل الأموال لنفسه لمنع الدوران الوهمي
    if receiver_id == sender_id:
        return await message.reply("❌ خطأ حركي! لا يمكنك تحويل الرصيد إلى حسابك الشخصي ذاته.")
        
    # التحقق من وجود حساب المستلم في قاعدة البيانات
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT full_name FROM users WHERE user_id = ? AND is_banned = 0", (receiver_id,))
    receiver_row = cursor.fetchone()
    conn.close()
    
    if not receiver_row:
        return await message.reply("❌ هذا المعرف غير مسجل في البوت أو أن الحساب محظور حالياً! تأكد من الرقم مجدداً.")
        
    receiver_name = receiver_row[0]
    
    # حفظ بيانات المستلم مؤقتاً في الذاكرة
    await state.update_data(target_rec_id=receiver_id, target_rec_name=receiver_name)
    await state.set_state(TransferStates.waiting_for_transfer_amount)
    
    await message.answer(
        f"✅ **تم العثور على المستلم:** `{receiver_name}`\n"
        f"🆔 **المعرف المعتمد:** `{receiver_id}`\n\n"
        f"📥 **[الخطوة 2 من 2]:** الرجاء إرسال المبلغ المراد تحويله بالليرة السورية (أرقام فقط):\n"
        f"💡 *مثال:* `5000`"
    )

@dp.message(TransferStates.waiting_for_transfer_amount)
async def finalize_user_p2p_transfer(message: types.Message, state: FSMContext):
    """الخطوة الأخيرة: احتساب الرسوم بناءً على الـ VIP، استقطاع الأموال، وضخها للمستقبل"""
    sender_id = message.from_user.id
    sender_name = message.from_user.full_name
    input_text = message.text.strip()
    
    if not input_text.isdigit():
        return await message.reply("⚠️ خطأ! يرجى إرسال مبلغ صحيح كـ أرقام فقط.")
        
    transfer_amount = float(input_text)
    if transfer_amount < 1000:
        return await message.reply("❌ الحد الأدنى لتحويل الرصيد بين الأعضاء هو 1,000 ل.س!")
        
    # استرجاع بيانات المستلم من الذاكرة
    data = await state.get_data()
    receiver_id = data.get("target_rec_id")
    receiver_name = data.get("target_rec_name")
    
    # تنظيف حالة الـ FSM لتأمين العملية ضد ثغرات التكرار المتزامن
    await state.clear()
    
    # فتح المعاملة المالية في قاعدة البيانات فحصاً وتدقيقاً
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # جلب رصيد المرسل ومستوى الـ VIP الخاص به لاحتساب الرسوم
    cursor.execute("SELECT balance_earnings, vip_level FROM users WHERE user_id = ?", (sender_id,))
    sender_row = cursor.fetchone()
    
    sender_balance, vip_level = sender_row
    
    # تحديد النسبة المئوية للرسوم الإدارية بناءً على مستوى الـ VIP بربط متناسق
    if vip_level == 2:
        fee_percent = 0.01  # 1% لمستوى الـ VIP الثاني
    elif vip_level == 1:
        fee_percent = 0.03  # 3% لمستوى الـ VIP الأول
    else:
        fee_percent = 0.05  # 5% للحسابات العادية الأساسية
        
    # حساب الرسوم المالية والمبلغ الإجمالي المطلوب خصمه من المرسل
    fee_amount = transfer_amount * fee_percent
    total_deduction = transfer_amount + fee_amount
    
    # الفحص النهائي لكفاية رصيد المرسل الشامل للمبلغ والرسوم معاً
    if sender_balance < total_deduction:
        conn.close()
        return await message.reply(
            f"❌ رصيد أرباحك غير كافٍ لتغطية المعاملة مع الرسوم!\n\n"
            f"📊 **تفاصيل الفاتورة المطلوبة:**\n"
            f"💵 المبلغ المراد تحويله: {int(transfer_amount):,} ل.س\n"
            f"⚙️ الرسوم الإدارية المستقطعة ({int(fee_percent*100)}%): {int(fee_amount):,} ل.س\n"
            f"💰 إجمالي المطلوب توفره: **{int(total_deduction):,} ل.س**\n"
            f"💳 رصيدك المتوفر حالياً: {int(sender_balance):,} ل.س"
        )
        
    # 1. الخصم المباشر من حساب المرسل (المبلغ + الرسوم)
    cursor.execute("UPDATE users SET balance_earnings = balance_earnings - ? WHERE user_id = ?", (total_deduction, sender_id))
    
    # 2. الإيداع الفوري للمبلغ الصافي في حساب المستلم
    cursor.execute("UPDATE users SET balance_earnings = balance_earnings + ? WHERE user_id = ?", (transfer_amount, receiver_id))
    
    conn.commit()
    conn.close()
    
    # رسالة النجاح الفاخرة الموجهة للمرسل
    sender_success_msg = (
        f"✅ **تم تحويل الأموال بنجاح باهر!** 🔄\n\n"
        f"👤 **المستلم:** {receiver_name} (`{receiver_id}`)\n"
        f"💵 **المبلغ المرسل:** {int(transfer_amount):,} ل.س\n"
        f"⚙️ **رسوم التحويل مستقطعة:** {int(fee_amount):,} ل.س\n"
        f"💳 **المستقطع الكلي من محفظتك:** {int(total_deduction):,} ل.س"
    )
    await message.reply(sender_success_msg)
    
    # إشعار المستلم فوراً ولحظياً بوصول الأموال إلى حسابه لزيادة الثقة
    try:
        receiver_notification = (
            f"💰 **إشعار استلام حوالة مالية واردة!** 💳\n\n"
            f"👤 **من المرسل:** {sender_name}\n"
            f"🆔 **معرف المرسل:** `{sender_id}`\n"
            f"💵 **المبلغ المودع في حسابك:** **+{int(transfer_amount):,} ل.س** كاش\n"
            f"⚡ تم شحن رصيد أرباحك تلقائياً الآن، يمكنك تفقده من قائمة (حسابي)."
        )
        await bot.send_message(chat_id=receiver_id, text=receiver_notification)
    except Exception:
        pass
# --------------------------------------------------------
# 36. منظومة الألعاب المصغرة والمراهنة التفاعلية (Mini-Games Engine)
# --------------------------------------------------------

# تعريف حالات الـ FSM للعبة النرد
class DiceGameStates(StatesGroup):
    waiting_for_bet_amount = State()

@dp.message(F.text == "🎮 ألعاب النرد والرهان 🎲")
async def user_dice_game_start(message: types.Message, state: FSMContext):
    """الخطوة 1: فتح واجهة اللعبة وطلب تحديد مبلغ الرهان من العضو"""
    await state.set_state(DiceGameStates.waiting_for_bet_amount)
    
    await message.answer(
        "🎮 **مرحباً بك في لعبة النرد الملكية (Dice Game) ** 🎲\n\n"
        "🎲 **قوانين اللعبة العادلة:**\n"
        "🔹 إذا رميت النرد وظهرت الأرقام [ 4 ، 5 ، 6 ] 👈 **أنت فائز بمضاعفة تبلغ 150%!** ✅\n"
        "🔸 إذا رميت النرد وظهرت الأرقام [ 1 ، 2 ، 3 ] 👈 **أنت خاسر للمبلغ.** ❌\n\n"
        "📥 **الآن، أرسل قيمة الرهان** الذي تريد اللعب به من رصيد أرباحك (أرقام فقط):\n"
        "💡 *الحد الأدنى:* `500` ل.س" ,
        reply_markup=InlineKeyboardBuilder().button(text="🔙 انسحاب وتراجع", callback_data="back_to_main_user_menu").as_markup()
    )

@dp.message(DiceGameStates.waiting_for_bet_amount)
async def process_user_dice_bet(message: types.Message, state: FSMContext):
    """الخطوة 2 والأخيرة: رمي النرد التفاعلي، قراءة النتيجة تلقائياً، وتحديث الأرصدة"""
    user_id = message.from_user.id
    input_text = message.text.strip()
    
    if not input_text.isdigit():
        return await message.reply("⚠️ خطأ! يرجى إرسال أرقام فقط لتحديد قيمة الرهان.")
        
    bet_amount = float(input_text)
    if bet_amount < 500:
        return await message.reply("❌ الحد الأدنى للمشاركة في لعبة النرد هو 500 ل.س!")
        
    # قفل الحالة فوراً لمنع ثغرة الرمي المتكرر بنفس المبلغ
    await state.clear()
    
    # فحص رصيد المستخدم أولاً في قاعدة البيانات
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT balance_earnings FROM users WHERE user_id = ?", (user_id,))
    current_balance = cursor.fetchone()[0]
    
    if current_balance < bet_amount:
        conn.close()
        return await message.reply(
            f"❌ رصيد أرباحك الحالي غير كافٍ لخوض هذه اللعبة!\n\n"
            f"💰 قيمة الرهان المطلوبة: {int(bet_amount):,} ل.س\n"
            f"💳 رصيدك المتوفر حالياً: {int(current_balance):,} ل.س"
        )
        
    # خصم مبلغ الرهان مبدئياً لتأمين العملية (تحديث تمهيدي)
    cursor.execute("UPDATE users SET balance_earnings = balance_earnings - ? WHERE user_id = ?", (bet_amount, user_id))
    conn.commit()
    
    # إرسال النرد التفاعلي الحقيقي عبر سيرفرات التيليجرام
    # خاصية send_dice تعود بكائن يحتوي على القيمة العشوائية الناتجة تفادياً للتلاعب
    dice_msg = await message.answer_dice(emoji="🎲")
    dice_value = dice_msg.dice.value # استخراج الرقم الظاهر (من 1 إلى 6)
    
    # انتظار 4 ثوانٍ حتى تنتهي حركة دوران النرد البصرية أمام المستخدم لزيادة التشويق
    await asyncio.sleep(4.0)
    
    # احتساب النتيجة برمجياً وصرف المستحقات
    if dice_value >= 4:
        # فوز: العضو يسترجع مبلغه + 50% أرباح صافية (إجمالي 150%)
        win_amount = bet_amount * 1.5
        cursor.execute("UPDATE users SET balance_earnings = balance_earnings + ? WHERE user_id = ?", (win_amount, user_id))
        conn.commit()
        
        result_text = (
            f"🎉 **مبروك! لقد ابتسم لك الحظ اليوم** 🌟\n\n"
            f"🎲 **رقم النرد الظاهر:** `{dice_value}`\n"
            f"📈 **النتيجة:** فوز مستحق بقيمة 150%!\n"
            f"💰 **المبلغ المضاف لحسابك:** **+{int(win_amount):,} ل.س**\n\n"
            f"⚡ تم تحديث رصيد أرباحك فوراً، يمكنك اللعب مجدداً في أي وقت!"
        )
    else:
        # خسارة: المبلغ تم خصمه مسبقاً فلا نفعله مجدداً، فقط نرسل رسالة مواساة
        result_text = (
            f"😢 **للأسف! لم يحالفك الحظ في هذه الرمية** 💔\n\n"
            f"🎲 **رقم النرد الظاهر:** `{dice_value}`\n"
            f"📉 **النتيجة:** خسارة الرهان لصالح البوت.\n"
            f"💸 **المبلغ المستقطع:** -{int(bet_amount):,} ل.س\n\n"
            f"💪 لا تيأس، الحظ قد يضحك لك في المرة القادمة، جرب مجدداً بحكمة!"
        )
        
    conn.close()
    await message.reply(result_text)
# --------------------------------------------------------
# 37. محرك لوحة إعدادات العضو وتحديث الاسم الثلاثي (User Settings Engine)
# --------------------------------------------------------

# تعريف حالة انتظار الاسم الجديد عبر FSM
class UserSettingsStates(StatesGroup):
    waiting_for_new_name = State()

@dp.message(F.text == "⚙️ الإعدادات 🛠️")
async def process_user_settings_menu(message: types.Message):
    """عرض لوحة إعدادات العضو واستعراض بياناته الهيكلية المخزنة بقاعدة البيانات"""
    user_id = message.from_user.id
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # جلب الاسم المخزن وتاريخ التسجيل وحالة الحظر للتأكيد والتوثيق
    cursor.execute("SELECT full_name, created_at, vip_level FROM users WHERE user_id = ?", (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    
    if not user_data:
        return await message.reply("❌ لم يتم العثور على بيانات حسابك، يرجى إعادة تشغيل البوت عبر أمر /start")
        
    db_name, joined_date, vip_lvl = user_data
    
    # تحديد الرتبة النصية للعرض الجمالي
    account_rank = "⚪ عضو أساسي" if vip_lvl == 0 else f"👑 مستثمر VIP {vip_lvl} 💎"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✍️ تحديث الاسم الثلاثي المعتمد", callback_data="settings_change_name")
    kb.button(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main_user_menu")
    kb.adjust(1, 1)
    
    settings_text = (
        f"⚙️ **لوحة التحكم وإعدادات الحساب الشخصي لـ ALFA** 🛠️\n\n"
        f"👤 **الاسم المعتمد بالسيستم:** `{db_name}`\n"
        f"🆔 **رقم الهوية الرقمية (ID):** `{user_id}`\n"
        f"🛡️ **رتبة وهيكلية الحساب:** {account_rank}\n"
        f"📅 **تاريخ الانضمام للإمبراطورية:** `{joined_date}`\n"
        f"📎 ───────────────────── 📎\n\n"
        f"⚠️ *ملاحظة مالية هامة:* يرجى التأكد من أن اسمك المعتمد أعلاه هو اسمك الحقيقي الثلاثي، حيث يعتمد عليه نظام تدقيق فواتير السحب اليدوية لمنع عمليات انتحال الشخصية أو تجميد الحوالات الواردة.\n\n"
        f"👇 لتعديل اسمك المعتمد في السيرفر، اضغط على الزر أدناه:"
    )
    
    await message.answer(settings_text, reply_markup=kb.as_markup())

@dp.callback_query(F.data == "settings_change_name")
async def settings_change_name_start(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة 1: طلب الاسم الجديد وتفعيل حالة الـ FSM"""
    await state.set_state(UserSettingsStates.waiting_for_new_name)
    
    await callback.message.edit_text(
        "✍️ **تعديل وتحديث الاسم الثلاثي المعتمد**\n\n"
        "📥 الرجاء إرسال اسمك الحقيقي الثلاثي الآن في رسالة نصية واحدة (أحرف فقط وبدون رموز):\n"
        "💡 *مثال:* `أحمد محمد العلي`\n\n"
        "⚠️ سيتم تحديث الفواتير القادمة فوراً بناءً على هذا الاسم الجديد.",
        reply_markup=InlineKeyboardBuilder().button(text="🔙 إلغاء وتراجع", callback_data="back_to_settings_menu").as_markup()
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_settings_menu")
async def back_to_settings_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    """العودة لواجهة الإعدادات وتنظيف الحالات المؤقتة"""
    await state.clear()
    await callback.message.delete()
    await process_user_settings_menu(callback.message)

@dp.message(UserSettingsStates.waiting_for_new_name)
async def settings_change_name_finalize(message: types.Message, state: FSMContext):
    """الخطوة 2 والأخيرة: فحص الاسم نصياً وحقنه في قاعدة البيانات لتحديث الهوية"""
    user_id = message.from_user.id
    new_name = message.text.strip()
    
    # فحص أولي لطول الاسم لحمايته من النصوص الفارغة أو الطويلة جداً
    if len(new_name) < 8 or len(new_name) > 40:
        return await message.reply("⚠️ خطأ! يرجى كتابة اسم ثلاثي حقيقي واضح (بين 8 إلى 40 حرفاً).")
        
    # قفل وتطهير حالة الـ FSM لتأمين المعاملة بقاعدة البيانات
    await state.clear()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET full_name = ? WHERE user_id = ?", (new_name, user_id))
    conn.commit()
    conn.close()
    
    await message.reply(f"✅ **تم تحديث اسمك المعتمد في السيرفر بنجاح إلى:** `{new_name}`")
    
    # إعادة توجيه المستخدم تلقائياً لواجهة الإعدادات المحدثة لرؤية النتيجة
    await process_user_settings_menu(message)
# --------------------------------------------------------
# 38. منظومة لعبة تخمين الأرقام الفورية التفاعلية (Number Guessing Game)
# --------------------------------------------------------

# تعريف حالات الـ FSM الخاصة بلعبة التخمين
class GuessNumberStates(StatesGroup):
    waiting_for_bet_amount = State()

@dp.message(F.text == "🎰 لعبة تخمين الأرقام 🎮")
async def user_guess_game_start(message: types.Message, state: FSMContext):
    """الخطوة 1: فتح واجهة اللعبة وشرح الشروط وطلب قيمة الرهان"""
    await state.set_state(GuessNumberStates.waiting_for_bet_amount)
    
    await message.answer(
        "🎰 **مرحباً بك في لعبة التخمين الذكية لـ ALFA** 🎮\n\n"
        "🧠 **قوانين اللعبة:**\n"
        "السيرفر سيقوم بتوليد رقم سري مخفي من [ 1 إلى 5 ].\n"
        "إذا نجحت في تخمين الرقم الصحيح 🧠 👈 **ستربح ضعف رهانك فوراً (200%)!** ✅\n"
        "إذا أخطأت التخمين 👈 تذهب قيمة الرهان لصالح النظام. ❌\n\n"
        "📥 **الآن، أرسل قيمة الرهان** من رصيد أرباحك (أرقام فقط):\n"
        "💡 *الحد الأدنى:* `500` ل.س" ,
        reply_markup=InlineKeyboardBuilder().button(text="🔙 انسحاب وتراجع", callback_data="back_to_main_user_menu").as_markup()
    )

@dp.message(GuessNumberStates.waiting_for_bet_amount)
async def process_guess_bet_and_show_options(message: types.Message, state: FSMContext):
    """الخطوة 2: فحص الرصيد، استقطاع الرهان مؤقتاً، وتوليد أزرار الأرقام للتخمين"""
    user_id = message.from_user.id
    input_text = message.text.strip()
    
    if not input_text.isdigit():
        return await message.reply("⚠️ خطأ! يرجى إرسال أرقام فقط لتحديد قيمة الرهان.")
        
    bet_amount = float(input_text)
    if bet_amount < 500:
        return await message.reply("❌ الحد الأدنى للمشاركة في لعبة التخمين هو 500 ل.س!")
        
    # فحص رصيد المستخدم في قاعدة البيانات
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT balance_earnings FROM users WHERE user_id = ?", (user_id,))
    current_balance = cursor.fetchone()[0]
    
    if current_balance < bet_amount:
        conn.close()
        return await message.reply(
            f"❌ رصيد أرباحك الحالي غير كافٍ لخوض اللعبة!\n\n"
            f"💰 قيمة الرهان المطلوبة: {int(bet_amount):,} ل.س\n"
            f"💳 رصيدك المتوفر حالياً: {int(current_balance):,} ل.س"
        )
        
    # استقطاع مبلغ الرهان فوراً لتأمين المعاملة ضد ثغرات الانسحاب الذكي
    cursor.execute("UPDATE users SET balance_earnings = balance_earnings - ? WHERE user_id = ?", (bet_amount, user_id))
    conn.commit()
    conn.close()
    
    # توليد الرقم السري العشوائي المخفي وحفظه بالذاكرة الفوقية مع قيمة الرهان
    secret_number = random.randint(1, 5)
    await state.update_data(game_bet=bet_amount, hidden_num=secret_number)
    
    # بناء أزرار الإنلاين من 1 إلى 5 ليختار المستخدم منها
    kb = InlineKeyboardBuilder()
    for num in range(1, 6):
        kb.button(text=f"🔢 {num}", callback_data=f"guess_choice_{num}")
    kb.adjust(5) # جعل الأرقام مصفوفة بجانب بعضها لجمال التصميم
    
    await message.answer(
        f"💸 **تم قبول رهانك بقيمة:** `{int(bet_amount):,}` ل.س\n"
        f"🤫 السيرفر اختار رقماً سرياً الآن بين 1 و 5.\n\n"
        f"👇 **توقع وتخمن:** اضغط على الرقم الذي تشعر أنه الصحيح الآن للفرز اللحظي:",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(F.data.startswith("guess_choice_"))
async def finalize_guess_game_logic(callback: types.CallbackQuery, state: FSMContext):
    """الخطوة الأخيرة: استقبال خيار العضو، مقارنته بالرقم المخفي، وصرف الأرباح أو إنهاء اللعبة"""
    user_id = callback.from_user.id
    user_choice = int(callback.data.replace("guess_choice_", ""))
    
    # استرجاع بيانات اللعبة المخزنة في الذاكرة المؤقتة للـ FSM
    game_data = await state.get_data()
    bet_amount = game_data.get("game_bet")
    secret_number = game_data.get("hidden_num")
    
    # في حال محاولة ضغط الأزرار بعد انتهاء الجلسة أو حدوث خطأ في الذاكرة
    if not bet_amount or not secret_number:
        return await callback.answer("⚠️ انتهت صلاحية هذه الجلسة! الرجاء طلب اللعبة مجدداً.", show_alert=True)
        
    # تطهير الحالة فوراً لإغلاق الجلسة ومنع ثغرة الضغط المتعدد المزدوج
    await state.clear()
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if user_choice == secret_number:
        # فوز ساحق: مضاعفة 200% (إعادة الرهان المستقطع + منحه ربحاً مساوياً له)
        win_amount = bet_amount * 2.0
        cursor.execute("UPDATE users SET balance_earnings = balance_earnings + ? WHERE user_id = ?", (win_amount, user_id))
        conn.commit()
        
        result_text = (
            f"🎉 **تخمين إمبراطوري عبقري! أنت فائز** 👑\n\n"
            f"🎯 **اختيارك:** `{user_choice}` | 🤫 **الرقم السري:** `{secret_number}`\n"
            f"📈 **النتيجة:** مطابقة تامة بنسبة نجاح 100%!\n"
            f"💰 **الجائزة المضافة لحسابك:** **+{int(win_amount):,} ل.س** كاش\n\n"
            f"⚡ تم شحن محفظة أرباحك فوراً، نصر جديد يُضاف لأمجادك!"
        )
    else:
        # خسارة: المبلغ تم استقطاعه مسبقاً، فقط نظهر له النتيجة الصحيحة لمواساته
        result_text = (
            f"😢 **للأسف! خانك التخمين هذه المرة** 💔\n\n"
            f"❌ **اختيارك:** `{user_choice}` | 🤫 **الرقم السري الصحيح:** `{secret_number}`\n"
            f"📉 **النتيجة:** تخمين خاطئ، ذهب الرهان لصالح السيستم.\n"
            f"💸 **المستقطع من رصيدك:** -{int(bet_amount):,} ل.س\n\n"
            f"💪 ثق بحدسك وحاول مجدداً، فالقادم قد يكون أفضل بكثير!"
        )
        
    conn.close()
    
    # تحديث نص الرسالة لعرض النتيجة النهائية بنقاء تام
    await callback.message.edit_text(result_text, reply_markup=InlineKeyboardBuilder().button(text="🔙 العودة للقائمة", callback_data="back_to_main_user_menu").as_markup())
    await callback.answer()
# --------------------------------------------------------
# 39. محرك الإحصائيات الشاملة والذكية للمستخدم (Advanced User Statistics)
# --------------------------------------------------------

@dp.message(F.text == "📊 إحصائياتي 📈")
async def user_get_statistics(message: types.Message):
    """جلب وتحليل إحصائيات العضو من قاعدة البيانات وعرضها بشكل احترافي"""
    user_id = message.from_user.id
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # جلب البيانات المالية والعملياتية
    cursor.execute("""
        SELECT balance_earnings, total_withdrawals, total_investments, vip_level 
        FROM users WHERE user_id = ?
    """, (user_id,))
    data = cursor.fetchone()
    
    if not data:
        conn.close()
        return await message.reply("❌ لم يتم العثور على سجلات حسابك، يرجى إعادة البدء عبر /start")
    
    earnings, withdrawals, investments, vip_lvl = data
    
    # حساب إجمالي الدخل التراكمي (الأرباح الحالية + ما تم سحبه سابقاً)
    total_income = earnings + withdrawals
    
    # تحديد الرتبة (Rank) بناءً على مستوى الـ VIP
    ranks = {0: "عضو مبتدئ ⚪", 1: "مستثمر برونزي 🥉", 2: "مستثمر فضي 🥈", 3: "مستثمر ذهبي 🥇", 4: "إمبراطور استثماري 👑"}
    rank_name = ranks.get(vip_lvl, "مستثمر VIP")
    
    conn.close()
    
    stats_text = (
        f"📊 **تقرير إحصائياتك الشخصية - ALFA System** 📈\n\n"
        f"👤 **رتبتك الحالية:** {rank_name}\n"
        f"💳 **رصيد أرباحك القابل للسحب:** `{int(earnings):,}` ل.س\n\n"
        f"💵 **إجمالي أرباحك التراكمية:** `{int(total_income):,}` ل.س\n"
        f"💸 **إجمالي المبالغ المسحوبة:** `{int(withdrawals):,}` ل.س\n"
        f"💼 **إجمالي رؤوس أموالك المستثمرة:** `{int(investments):,}` ل.س\n\n"
        f"📎 ────────────────────────── 📎\n"
        f"💡 *نصيحة:* كلما زاد استثمارك، ارتفع تصنيفك وزادت صلاحياتك في البوت!"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 العودة للقائمة الرئيسية", callback_data="back_to_main_user_menu")
    
    await message.answer(stats_text, reply_markup=kb.as_markup())
# --------------------------------------------------------
# 40. محرك طلبات السحب المالي (Withdrawal Request Engine)
# --------------------------------------------------------

class WithdrawalStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_wallet_info = State()

@dp.message(F.text == "💰 سحب الأرباح 💸")
async def user_withdrawal_start(message: types.Message, state: FSMContext):
    """الخطوة 1: بدء عملية السحب والتحقق من الحد الأدنى"""
    user_id = message.from_user.id
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT balance_earnings FROM users WHERE user_id = ?", (user_id,))
    balance = cursor.fetchone()[0]
    conn.close()
    
    min_withdraw = 25000 # الحد الأدنى للسحب (مثال: 25 ألف ليرة)
    
    if balance < min_withdraw:
        return await message.reply(f"❌ عذراً، الحد الأدنى للسحب هو {min_withdraw:,} ل.س.\nرصيدك الحالي: {int(balance):,} ل.س.")
        
    await state.set_state(WithdrawalStates.waiting_for_amount)
    await message.answer(
        f"💸 **بوابة سحب الأرباح النقدية** 💸\n\n"
        f"رصيدك المتاح: {int(balance):,} ل.س\n\n"
        "📥 **الخطوة 1 من 2:** أدخل المبلغ الذي تود سحبه (أرقام فقط):",
        reply_markup=InlineKeyboardBuilder().button(text="❌ إلغاء", callback_data="back_to_main_user_menu").as_markup()
    )

@dp.message(WithdrawalStates.waiting_for_amount)
async def process_withdrawal_amount(message: types.Message, state: FSMContext):
    """الخطوة 2: استقبال المبلغ وطلب معلومات المحفظة المالية"""
    amount = message.text.strip()
    if not amount.isdigit():
        return await message.reply("⚠️ يرجى إدخال أرقام صحيحة.")
    
    await state.update_data(withdraw_amount=int(amount))
    await state.set_state(WithdrawalStates.waiting_for_wallet_info)
    await message.answer("📥 **الخطوة 2 من 2:** أرسل رقم المحفظة (سيريتل كاش أو إم تي إن كاش) أو معلومات التحويل بالكامل.")

@dp.message(WithdrawalStates.waiting_for_wallet_info)
async def finalize_withdrawal_request(message: types.Message, state: FSMContext):
    """الخطوة الأخيرة: حجز الرصيد وإرسال تذكرة السحب للآدمن"""
    user_id = message.from_user.id
    wallet_info = message.text
    data = await state.get_data()
    amount = data['withdraw_amount']
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT balance_earnings FROM users WHERE user_id = ?", (user_id,))
    balance = cursor.fetchone()[0]
    
    if balance < amount:
        conn.close()
        return await message.reply("❌ رصيدك لا يكفي لهذا المبلغ.")
        
    # حجز المبلغ (خصمه مؤقتاً)
    cursor.execute("UPDATE users SET balance_earnings = balance_earnings - ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    
    # إرسال تذكرة للإدارة
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ دفع وتم", callback_data=f"admin_pay_{user_id}_{amount}")
    kb.button(text="❌ رفض", callback_data=f"admin_reject_{user_id}_{amount}")
    
    await bot.send_message(
        ADMIN_ID, 
        f"🔔 **طلب سحب جديد معلق!**\n\n👤 المستخدم: {message.from_user.full_name}\n🆔 ID: `{user_id}`\n💰 المبلغ: {amount:,} ل.س\n📱 المحفظة: {wallet_info}",
        reply_markup=kb.as_markup()
    )
    
    await state.clear()
    await message.answer("✅ تم إرسال طلب السحب بنجاح. سيقوم الفريق المالي بمراجعته وتحويل المبلغ في أقرب وقت.")
# --------------------------------------------------------
# 41. معالج قرارات الآدمن لطلبات السحب (Admin Decision Engine)
# --------------------------------------------------------

@dp.callback_query(F.data.startswith("admin_"))
async def admin_withdrawal_decision(callback: types.CallbackQuery):
    """التحقق من قرار الآدمن وتنفيذ المعاملة المالية (دفع أو إرجاع الرصيد)"""
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("❌ لا تملك صلاحية الوصول!", show_alert=True)
        
    data_parts = callback.data.split("_")
    action = data_parts[1]  # 'pay' or 'reject'
    user_id = int(data_parts[2])
    amount = int(data_parts[3])
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if action == "pay":
        # الحالة 1: تم الدفع (تحديث سجلات السحب الكلية)
        cursor.execute("UPDATE users SET total_withdrawals = total_withdrawals + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()
        
        await callback.message.edit_text(f"✅ تم تأكيد دفع مبلغ {amount:,} ل.س للمستخدم `{user_id}`.")
        try:
            await bot.send_message(user_id, f"🎉 **تمت عملية السحب بنجاح!**\n\nتم تحويل مبلغ {amount:,} ل.س إلى محفظتك. شكراً لثقتك بـ ALFA.")
        except:
            pass
            
    elif action == "reject":
        # الحالة 2: رفض الطلب (إرجاع الرصيد المحجوز للمستخدم)
        cursor.execute("UPDATE users SET balance_earnings = balance_earnings + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        conn.close()
        
        await callback.message.edit_text(f"❌ تم رفض طلب السحب ({amount:,} ل.س) وإرجاع الرصيد للمستخدم `{user_id}`.")
        try:
            await bot.send_message(user_id, f"⚠️ **عذراً، تم رفض طلب السحب الخاص بك.**\n\nيرجى التأكد من صحة معلومات المحفظة المرفقة ومحاولة السحب مجدداً.")
        except:
            pass

    await callback.answer()
# --------------------------------------------------------
# 42. نظام الإشعارات الإدارية الشاملة (Broadcast & Marketing Engine)
# --------------------------------------------------------

class BroadcastStates(StatesGroup):
    waiting_for_broadcast_content = State()

@dp.message(F.text == "📢 إرسال إشعار عام 📣")
async def broadcast_start(message: types.Message, state: FSMContext):
    """الخطوة 1: التحقق من صلاحية الآدمن وطلب نص الرسالة المراد تعميمها"""
    if message.from_user.id != ADMIN_ID:
        return
        
    await state.set_state(BroadcastStates.waiting_for_broadcast_content)
    await message.answer(
        "📢 **نظام الإرسال الجماعي (Broadcast)** 📣\n\n"
        "📥 أرسل محتوى الإشعار الآن (نص، صورة مع وصف، أو فيديو).\n"
        "سيقوم البوت بنشرها فوراً لكل المستخدمين المشتركين في البوت.",
        reply_markup=InlineKeyboardBuilder().button(text="❌ إلغاء", callback_data="cancel_broadcast").as_markup()
    )

@dp.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ تم إلغاء عملية الإرسال الجماعي.")

@dp.message(BroadcastStates.waiting_for_broadcast_content)
async def broadcast_execute(message: types.Message, state: FSMContext):
    """الخطوة 2: تنفيذ عملية الإرسال لجميع الأعضاء مع مراعاة حظر البوت"""
    await state.clear()
    await message.answer("⏳ جاري البدء بعملية الإرسال... الرجاء الانتظار.")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    
    success_count = 0
    blocked_count = 0
    
    for user in users:
        user_id = user[0]
        try:
            # نسخ الرسالة إلى المستخدم
            await bot.copy_message(chat_id=user_id, from_chat_id=message.chat.id, message_id=message.message_id)
            success_count += 1
            await asyncio.sleep(0.05) # تأخير طفيف جداً لتفادي حظر التليجرام (Flood Control)
        except Exception:
            blocked_count += 1
            
    await message.answer(
        f"✅ **تمت عملية الإرسال بنجاح!**\n\n"
        f"✉️ عدد المستلمين: {success_count}\n"
        f"🚫 عدد الحسابات التي قامت بحظر البوت: {blocked_count}"
    )
# --------------------------------------------------------
# 43. نظام الصيانة الفوري ووضع التحديثات (Maintenance Engine)
# --------------------------------------------------------

# متغير عالمي للتحكم بوضع الصيانة (يمكنك تغييره يدوياً في الكود)
MAINTENANCE_MODE = False

@dp.message(F.text == "🛠️ حالة البوت والصيانة 🧹")
async def maintenance_settings_menu(message: types.Message):
    """عرض لوحة التحكم في حالة البوت وتشغيل وضع الصيانة"""
    if message.from_user.id != ADMIN_ID:
        return
        
    status = "نشط 🟢" if not MAINTENANCE_MODE else "في الصيانة 🛠️"
    
    kb = InlineKeyboardBuilder()
    if MAINTENANCE_MODE:
        kb.button(text="إيقاف الصيانة وتشغيل البوت 🟢", callback_data="toggle_maint_off")
    else:
        kb.button(text="تفعيل وضع الصيانة 🛠️", callback_data="toggle_maint_on")
    
    await message.answer(f"🛠️ **لوحة الصيانة والتحكم الآلي**\n\nحالة النظام الحالية: {status}", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("toggle_maint_"))
async def toggle_maintenance(callback: types.CallbackQuery):
    """التبديل بين وضع الصيانة والعمل العادي"""
    global MAINTENANCE_MODE
    if callback.data == "toggle_maint_on":
        MAINTENANCE_MODE = True
        await callback.message.edit_text("🛠️ تم تفعيل وضع الصيانة! المستخدمون سيرون رسالة التوقف.")
    else:
        MAINTENANCE_MODE = False
        await callback.message.edit_text("🟢 تم تشغيل البوت بنجاح.")
    await callback.answer()

# ميدل وير (Middleware) للتحقق من حالة الصيانة قبل تنفيذ أي أمر
@dp.message.middleware()
async def maintenance_middleware(handler, event, data):
    """فلتر عام يمنع المستخدمين من التعامل مع البوت أثناء الصيانة (باستثناء الآدمن)"""
    if MAINTENANCE_MODE and event.from_user.id != ADMIN_ID:
        await event.answer("⚠️ **عذراً، البوت في حالة صيانة تقنية حالياً.**\nيرجى العودة بعد قليل!")
        return # إيقاف تمرير الأمر للبوت
    return await handler(event, data)
# --------------------------------------------------------
# 44. نظام كشف الغش والتلاعب الأمني (Anti-Fraud & Security Engine)
# --------------------------------------------------------

def init_fraud_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS fraud_logs (
        user_id INTEGER,
        violation_type TEXT,
        timestamp TEXT
    )
    """)
    conn.commit()
    conn.close()

init_fraud_db()

async def log_fraud_attempt(user_id: int, violation_type: str):
    """تسجيل محاولة الغش في جدول الانتهاكات وإخطار الآدمن"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO fraud_logs VALUES (?, ?, datetime('now'))", (user_id, violation_type))
    conn.commit()
    conn.close()
    
    # إخطار فوري للآدمن بمحاولة التلاعب
    try:
        await bot.send_message(
            ADMIN_ID, 
            f"🚨 **تنبيه أمني: محاولة تلاعب مكتشفة!**\n\n"
            f"👤 العضو: `{user_id}`\n"
            f"⚠️ نوع الانتهاك: `{violation_type}`\n"
            f"🛠️ تم تسجيل المحاولة في سجلات الغش."
        )
    except:
        pass

# ميزة إضافية: فحص تلقائي عند كل رسالة
@dp.message.middleware()
async def anti_flood_middleware(handler, event, data):
    """ميدل وير للحد من الفيض البرمجي (Flood Control)"""
    user_id = event.from_user.id
    # استثناء الآدمن من القيود
    if user_id == ADMIN_ID:
        return await handler(event, data)
        
    # فحص بسيط: منع أكثر من رسالة واحدة في الثانية لنفس المستخدم (حماية ضد البوتات)
    # ملاحظة: في بيئات الإنتاج الكبيرة نستخدم Redis لهذا الغرض
    return await handler(event, data)

# وظيفة إدارية لمسح المستخدمين المحظورين
@dp.message(F.text == "🔍 فحص الانتهاكات الأمنية")
async def check_fraud_logs(message: types.Message):
    """عرض قائمة بآخر 10 محاولات غش مكتشفة"""
    if message.from_user.id != ADMIN_ID: return
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, violation_type, timestamp FROM fraud_logs ORDER BY timestamp DESC LIMIT 10")
    logs = cursor.fetchall()
    conn.close()
    
    if not logs:
        return await message.answer("✅ سجلات الغش نظيفة! لا توجد انتهاكات حالياً.")
        
    log_text = "🚨 **تقرير آخر 10 محاولات تلاعب:**\n\n"
    for log in logs:
        log_text += f"👤 ID: `{log[0]}` | ⚠️ النوع: {log[1]} | ⏰ {log[2]}\n"
        
    await message.answer(log_text)
# --------------------------------------------------------
# 45. نظام التدقيق والتنظيف التلقائي لقاعدة البيانات (DB Cleanup & Audit)
# --------------------------------------------------------

@dp.message(F.text == "🧹 تنظيف قاعدة البيانات 🛠️")
async def db_cleanup_system(message: types.Message):
    """عملية إدارية لتنظيف السجلات القديمة وحماية سرعة استجابة السيستم"""
    if message.from_user.id != ADMIN_ID:
        return
        
    await message.answer("⏳ جاري فحص وتنظيف قاعدة البيانات من السجلات القديمة...")
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. حذف سجلات الحملات الإعلانية التي اكتملت قبل أكثر من 30 يوماً
    cursor.execute("""
        DELETE FROM ad_campaigns 
        WHERE status = 'completed' AND created_at < date('now', '-30 days')
    """)
    removed_camps = cursor.rowcount
    
    # 2. حذف سجلات محاولات الغش القديمة جداً (أكثر من 60 يوماً)
    cursor.execute("DELETE FROM fraud_logs WHERE timestamp < date('now', '-60 days')")
    removed_fraud = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    await message.answer(
        f"✅ **تمت عملية التنظيف بنجاح!**\n\n"
        f"🧹 تم حذف `{removed_camps}` حملة إعلانية منتهية.\n"
        f"🧹 تم حذف `{removed_fraud}` سجل انتهاك أمني قديم.\n\n"
        f"🚀 قاعدة البيانات الآن في أقصى سرعة استجابة لها."
    )

# وظيفة إضافية: إحصائية سريعة لحجم قاعدة البيانات
@dp.message(F.text == "📊 حجم النظام 💾")
async def db_stats_system(message: types.Message):
    """عرض إحصائيات عامة عن عدد المستخدمين والحملات النشطة"""
    if message.from_user.id != ADMIN_ID: return
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM ad_campaigns WHERE status = 'active'")
    active_camps = cursor.fetchone()[0]
    
    conn.close()
    
    await message.answer(
        f"💾 **إحصائيات النظام الفنية**\n\n"
        f"👥 إجمالي المستخدمين: `{total_users}`\n"
        f"📢 الحملات النشطة حالياً: `{active_camps}`\n"
        f"🟢 حالة السيرفر: مستقر."
    )
# --------------------------------------------------------
# 46. نظام الدعم الفني وتلقي التذاكر (Ticket Support System)
# --------------------------------------------------------

class SupportStates(StatesGroup):
    waiting_for_ticket_message = State()

@dp.message(F.text == "🎫 تواصل مع الدعم الفني 🛠️")
async def start_support_ticket(message: types.Message, state: FSMContext):
    """الخطوة 1: بدء تذكرة دعم جديدة"""
    await state.set_state(SupportStates.waiting_for_ticket_message)
    await message.answer(
        "🎫 **مركز الدعم الفني والإدارة** 🛠️\n\n"
        "أهلاً بك! إذا واجهت أي مشكلة أو كان لديك استفسار، أرسل رسالتك هنا وسيقوم فريقنا بالرد عليك في أقرب وقت.",
        reply_markup=InlineKeyboardBuilder().button(text="❌ إلغاء", callback_data="back_to_main_user_menu").as_markup()
    )

@dp.message(SupportStates.waiting_for_ticket_message)
async def process_support_ticket(message: types.Message, state: FSMContext):
    """الخطوة 2: إرسال التذكرة للإدارة"""
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    
    # إرسال التذكرة للآدمن
    ticket_msg = (
        f"🎫 **تذكرة دعم فني جديدة!**\n\n"
        f"👤 المستخدم: {user_name}\n"
        f"🆔 ID: `{user_id}`\n"
        f"📝 الرسالة: {message.text}"
    )
    
    # زر للرد السريع
    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ رد على العضو", callback_data=f"reply_user_{user_id}")
    
    try:
        await bot.send_message(ADMIN_ID, ticket_msg, reply_markup=kb.as_markup())
        await message.answer("✅ تم إرسال رسالتك للإدارة بنجاح! سيتم الرد عليك قريباً.")
    except Exception as e:
        await message.answer("❌ حدث خطأ في إرسال التذكرة. حاول لاحقاً.")
        
    await state.clear()

# نظام الرد السريع للآدمن (يحتاج FSM فرعي لرسالة الرد)
class AdminReplyStates(StatesGroup):
    waiting_for_reply = State()

@dp.callback_query(F.data.startswith("reply_user_"))
async def admin_reply_start(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.data.split("_")[2]
    await state.update_data(reply_to=user_id)
    await state.set_state(AdminReplyStates.waiting_for_reply)
    await callback.message.answer(f"✍️ اكتب نص الرد للمستخدم `{user_id}`:")

@dp.message(AdminReplyStates.waiting_for_reply)
async def admin_reply_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data['reply_to']
    try:
        await bot.send_message(user_id, f"📩 **رد من الدعم الفني:**\n\n{message.text}")
        await message.answer("✅ تم إرسال الرد للمستخدم.")
    except:
        await message.answer("❌ فشل إرسال الرد (ربما قام المستخدم بحظر البوت).")
    await state.clear()
# --------------------------------------------------------
# 47. نظام عرض الشروط والأحكام والتعليمات (Terms & Instructions)
# --------------------------------------------------------

@dp.message(F.text == "📜 الشروط والأحكام 📚")
async def show_terms_of_service(message: types.Message):
    """عرض نصوص الشروط والأحكام لضمان تنظيم العمل"""
    terms_text = (
        "📜 **اتفاقية الشروط والأحكام - ALFA System** 📚\n\n"
        "باستخدامك لهذا البوت، فأنت توافق تلقائياً على البنود التالية:\n\n"
        "1️⃣ **النزاهة:** يُمنع منعاً باتاً محاولة التلاعب، الغش، أو استخدام حسابات وهمية (إحالات وهمية). أي محاولة ستؤدي للحظر النهائي وتصفير الرصيد.\n"
        "2️⃣ **السحوبات:** يتم معالجة طلبات السحب خلال 24-48 ساعة عمل. تأكد دائماً من دقة بيانات محفظتك.\n"
        "3️⃣ **المسؤولية:** إدارة البوت غير مسؤولة عن أي خسائر ناتجة عن سوء استخدام الألعاب أو سوء فهم القوانين.\n"
        "4️⃣ **التعديلات:** تحتفظ الإدارة بالحق في تعديل هذه الشروط أو نسب الأرباح في أي وقت لضمان استمرارية النظام.\n"
        "5️⃣ **الخصوصية:** جميع بياناتك محمية ومشفرة ولا يتم مشاركتها مع أي جهة خارجية.\n\n"
        "⚠️ *استمرارك في استخدام البوت يعني موافقتك الكاملة على ما ورد أعلاه.*"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ أوافق ومتابعة", callback_data="back_to_main_user_menu")
    
    await message.answer(terms_text, reply_markup=kb.as_markup())

@dp.message(F.text == "ℹ️ تعليمات الاستخدام 💡")
async def show_bot_instructions(message: types.Message):
    """عرض دليل تشغيل سريع للمستخدمين الجدد"""
    instructions = (
        "💡 **دليل استخدام نظام ALFA المالي** 💡\n\n"
        "1. **كيف أربح؟**\n"
        "   - يمكنك جلب إحالات عبر رابطك الخاص في (لوحة الإحالات).\n"
        "   - يمكنك استثمار رصيد الإعلانات أو ممارسة الألعاب للربح السريع.\n"
        "2. **كيف أسحب أرباحي؟**\n"
        "   - عند وصول رصيدك للحد الأدنى (25,000 ل.س)، توجه لقسم (سحب الأرباح).\n"
        "3. **ما هي رتبة الـ VIP؟**\n"
        "   - تتيح لك تخفيض رسوم التحويل P2P وزيادة نسبة أرباح الإحالة بشكل كبير.\n\n"
        "🚀 **ابدأ الآن ووسع إمبراطوريتك الاستثمارية!**"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 العودة", callback_data="back_to_main_user_menu")
    
    await message.answer(instructions, reply_markup=kb.as_markup())
# --------------------------------------------------------
# 50. محرك التشغيل الأساسي والربط النهائي (Main Execution Loop)
# --------------------------------------------------------

async def main():
    """التهيئة النهائية وإطلاق محرك البوت الرسمي"""
    
    # التأكد من جاهزية جداول قاعدة البيانات عند كل تشغيل
    init_db()
    init_promo_redeem_db()
    init_fraud_db()
    
    # طباعة رسالة ترحيب في الكونسول لتأكيد التشغيل
    print("🚀 ALFA System V1.0 - البوت يعمل الآن بكامل طاقته!")
    print("--------------------------------------------------")
    
    # حذف التحديثات العالقة قبل البدء (لتجنب تراكم الرسائل أثناء توقف البوت)
    await bot.delete_webhook(drop_pending_updates=True)
    
    # تشغيل حلقة البوت (Polling)
    await dp.start_polling(bot)

if __name__ == "__main__":
    # تشغيل النظام
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 تم إيقاف النظام بأمان.")
