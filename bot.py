#!/usr/bin/env python3
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, 
    ConversationHandler, filters, ContextTypes
)
import config
import database as db
from pasarguard_api import PasarGuardAPI

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

pg_api = PasarGuardAPI()

# Conversation states
ASK_PLAN_NAME, ASK_PLAN_TRAFFIC, ASK_PLAN_DURATION, ASK_PLAN_PRICE = range(13, 17)
ASK_USER_ID, ASK_AMOUNT, ASK_PAYMENT_AMOUNT = range(3)
ASK_TEST_USER = 10
ASK_REJECT_REASON = 11
ASK_DEBIT_AMOUNT = 12
ASK_ADMIN_USER_ID = 18
ASK_REMOVE_ADMIN_USER_ID = 19

# Helper functions for permissions
def is_admin(user_id: int) -> bool:
    return db.is_admin(user_id)

def is_owner(user_id: int) -> bool:
    return db.is_owner(user_id)

# ==================== KEYBOARDS ====================

def get_main_keyboard(user_id: int = None):
    # Check if user is admin (including owner)
    admin = is_admin(user_id) if user_id else False
    if admin:
        keyboard = [
            [InlineKeyboardButton("💰 کیف پول من", callback_data="wallet"), InlineKeyboardButton("📦 خرید پلن", callback_data="buy_plan")],
            [InlineKeyboardButton("🎁 درخواست تست", callback_data="test_request"), InlineKeyboardButton("📞 پشتیبانی", callback_data="support")],
            [InlineKeyboardButton("⚙️ پنل مدیریت", callback_data="admin_panel")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("💰 کیف پول من", callback_data="wallet"), InlineKeyboardButton("📦 خرید پلن", callback_data="buy_plan")],
            [InlineKeyboardButton("🎁 درخواست تست", callback_data="test_request"), InlineKeyboardButton("📞 پشتیبانی", callback_data="support")]
        ]
    return InlineKeyboardMarkup(keyboard)

def get_back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]])

def get_admin_panel_keyboard(owner: bool = False):
    keyboard = [
        [InlineKeyboardButton("📊 آمار ربات", callback_data="admin_stats")],
        [InlineKeyboardButton("➕ افزودن پلن جدید", callback_data="admin_add_plan"), InlineKeyboardButton("📋 لیست پلن‌ها", callback_data="admin_list_plans")],
        [InlineKeyboardButton("👥 لیست کاربران", callback_data="admin_list_users"), InlineKeyboardButton("💰 موجودی کل", callback_data="admin_total_balance")],
        [InlineKeyboardButton("🎁 ساخت تست برای کاربر", callback_data="admin_make_test"), InlineKeyboardButton("📋 درخواست‌های فعال پرداخت", callback_data="pending_payments_list")],
    ]
    if owner:
        # این دو دکمه فقط برای مالک نمایش داده می‌شوند
        keyboard.insert(0, [InlineKeyboardButton("💳 شارژ دستی کاربر", callback_data="admin_manual_charge"), InlineKeyboardButton("➖ کاهش موجودی کاربر", callback_data="admin_debit_balance")])
        keyboard.insert(3, [InlineKeyboardButton("📊 گزارش تراکنش‌ها", callback_data="export_transactions")])
        keyboard.insert(4, [InlineKeyboardButton("📈 آمار پیشرفته", callback_data="advanced_stats")])
        keyboard.insert(2, [InlineKeyboardButton("👑 مدیریت ادمین‌ها", callback_data="admin_manage_admins")])  # قبلاً بود
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard)

def get_charge_method_keyboard():
    keyboard = [
        [InlineKeyboardButton("🆔 شارژ با آیدی عددی", callback_data="charge_by_id"), InlineKeyboardButton("👤 شارژ با یوزرنیم", callback_data="charge_by_username")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
    ]
    return InlineKeyboardMarkup(keyboard)

def pending_list_keyboard(payments: list, page: int, total_pages: int):
    keyboard = []
    for p in payments:
        user = db.get_user(p['user_id'])
        username = f"@{user['username']}" if user and user['username'] else f"ID:{p['user_id']}"
        button_text = f"🆔 {p['id']} | {username} | {p['amount']:,} تومان"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_payment_{p['id']}")])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"pending_page_{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"pending_page_{page+1}"))
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)


# ==================== USER HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_user(user_id=user.id, username=user.username, first_name=user.first_name)
    admin = is_admin(user.id)
    if admin:
        welcome_text = f"👑 **خوش آمدی ادمین عزیز!** {user.first_name}\n\n🌟 به ربات فروش کانفیگ خوش آمدی.\n⚙️ **پنل مدیریت در انتهای منو قرار دارد.**\n\n💫 از منوی زیر گزینه مورد نظرت رو انتخاب کن:"
    else:
        welcome_text = f"✨ به ربات فروش کانفیگ خوش آمدی {user.first_name}!\n\n🌟 با استفاده از این ربات می‌تونی کانفیگ VPN با کیفیت بالا دریافت کنی.\n\n💫 از منوی زیر گزینه مورد نظرت رو انتخاب کن:"
    await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=get_main_keyboard(user.id))

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✨ منوی اصلی:", reply_markup=get_main_keyboard(query.from_user.id))

async def show_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    balance = db.get_user_balance(user_id)
    wallet_text = f"💼 **کیف پول شما**\n\n💰 موجودی ریالی: {balance:,} تومان\n\n🪙 پشتیبانی از رمزارز: به زودی...\n\n📌 برای خرید پلن، از بخش «خرید پلن» اقدام کن."
    keyboard = [[InlineKeyboardButton("💳 افزایش موجودی", callback_data="charge_wallet")], [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]]
    await query.edit_message_text(wallet_text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def charge_wallet_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("💰 پرداخت ریالی (کارت به کارت)", callback_data="rial_payment")],
        [InlineKeyboardButton("🪙 پرداخت رمز ارزی (به زودی)", callback_data="crypto_payment")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="wallet")]
    ]
    await query.edit_message_text("💳 **شارژ کیف پول**\n\nلطفاً روش پرداخت خود را انتخاب کنید:", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def rial_payment_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="charge_wallet")]]
    await query.edit_message_text("💰 **پرداخت ریالی**\n\nلطفاً مبلغ مورد نظر خود را به تومان وارد کنید:\nمثال: `50000`\n\nحداقل مبلغ: 10,000 تومان", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_PAYMENT_AMOUNT

async def rial_payment_get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
        if amount < 10000:
            await update.message.reply_text("❌ حداقل مبلغ شارژ 10,000 تومان است.\nلطفاً دوباره وارد کنید:")
            return ASK_PAYMENT_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید:")
        return ASK_PAYMENT_AMOUNT
    context.user_data['payment_amount'] = amount
    card_number = "6277-6014-3028-5161"  # شماره کارت خود را وارد کنید
    payment_text = f"💰 **شارژ کیف پول**\n\nمبلغ درخواستی: **{amount:,} تومان**\n\n🏦 لطفاً مبلغ فوق را به کارت زیر واریز کنید:\n\n`{card_number}`\n\nبه نام: **محمدرضا فردوسی**\n\n📎 **بعد از واریز، رسید (تصویر) را برای من ارسال کن.**\n\n⏳ پس از تأیید رسید توسط ادمین، موجودی شما افزایش می‌یابد."
    keyboard = [[InlineKeyboardButton("🔙 انصراف", callback_data="charge_wallet")]]
    await update.message.reply_text(payment_text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data['waiting_for_receipt'] = True
    return ConversationHandler.END

async def handle_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    amount = context.user_data.get('payment_amount')
    if not amount:
        await update.message.reply_text("❌ لطفاً ابتدا از طریق دکمه «افزایش موجودی» اقدام کنید.")
        return
    if not update.message.photo:
        await update.message.reply_text("❌ لطفاً یک تصویر از رسید ارسال کنید.")
        return
    photo_file_id = update.message.photo[-1].file_id
    payment_id = db.add_payment_request(user_id, amount, photo_file_id)
    
    user = db.get_user(user_id)
    username = f"@{user['username']}" if user['username'] else f"ID: {user_id}"
    admin_text = (
        f"🆕 **درخواست شارژ جدید**\n\n"
        f"👤 کاربر: {username}\n"
        f"👤 نام: {user.get('first_name', 'نامشخص')}\n"
        f"💰 مبلغ: {amount:,} تومان\n"
        f"🆔 شماره درخواست: {payment_id}\n\n"
        f"رسید کاربر:"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تأیید", callback_data=f"approve_payment_{payment_id}"),
         InlineKeyboardButton("❌ رد", callback_data=f"reject_payment_{payment_id}")]
    ])
    
    # ارسال به همه ادمین‌ها
    admins = db.get_all_admins()
    for admin in admins:
        try:
            await context.bot.send_photo(
                chat_id=admin['user_id'],
                photo=photo_file_id,
                caption=admin_text,
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Could not send to admin {admin['user_id']}: {e}")
    
    context.user_data.pop('payment_amount', None)
    await update.message.reply_text(
        f"✅ رسید شما دریافت شد.\n💰 مبلغ: {amount:,} تومان\n\n⏳ پس از تأیید ادمین، موجودی شما افزایش می‌یابد.\n🆔 شماره پیگیری: {payment_id}",
        reply_markup=get_main_keyboard(user_id)
    )

async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plans = db.get_active_plans()
    if not plans:
        await query.edit_message_text("❌ هیچ پلنی موجود نیست.", reply_markup=get_back_button())
        return
    text = "📦 **پلن‌های موجود:**\n\n"
    keyboard = []
    for plan in plans:
        text += f"▫️ **{plan['name']}** — {plan['traffic_gb']} گیگ / {plan['duration_days']} روز — {plan['price_rial']:,} تومان\n\n"
        keyboard.append([InlineKeyboardButton(f"✅ خرید {plan['name']}", callback_data=f"buy_{plan['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")])
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    plan_id = int(query.data.split('_')[1])
    plan = db.get_plan(plan_id)
    if not plan:
        await query.edit_message_text("❌ پلن مورد نظر یافت نشد.", reply_markup=get_back_button())
        return
    user_id = query.from_user.id
    balance = db.get_user_balance(user_id)
    if balance < plan['price_rial']:
        await query.edit_message_text(f"❌ موجودی کافی نیست!\n💰 موجودی: {balance:,} تومان\n💸 قیمت: {plan['price_rial']:,} تومان", reply_markup=get_back_button())
        return
    db.update_balance(user_id, -plan['price_rial'])
    order_id = db.create_order(user_id, plan['id'], plan['price_rial'])
    await query.edit_message_text("⏳ در حال ساخت کانفیگ...", reply_markup=get_back_button())
    result = pg_api.create_user(traffic_gb=plan['traffic_gb'], expire_days=plan['duration_days'], username=f"user_{user_id}_{order_id}")
    if result and result.get('success'):
        db.update_order_config(order_id, result['config_link'])
        await query.edit_message_text(f"✅ **خرید موفق!**\n\n🔗 لینک اشتراک:\n`{result['config_link']}`", parse_mode='Markdown', reply_markup=get_back_button())
    else:
        db.update_balance(user_id, plan['price_rial'])
        await query.edit_message_text("❌ خطا در پنل، مبلغ برگشت خورد.", reply_markup=get_back_button())

async def test_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if db.has_test_request(user_id):
        await query.edit_message_text("❌ شما قبلاً از سرویس تست استفاده کرده‌اید.", reply_markup=get_back_button())
        return
    await query.edit_message_text("⏳ در حال ساخت سرور تست 1 گیگ / 30 دقیقه...", reply_markup=get_back_button())
    result = pg_api.create_test_user()
    if result and result.get('success'):
        expire_time = datetime.now() + timedelta(minutes=30)
        db.add_test_request(user_id, expire_time)
        await query.edit_message_text(f"🎁 **سرور تست آماده شد!**\n\n🔗 لینک:\n`{result['config_link']}`\n\n⏱ 30 دقیقه معتبر است.", parse_mode='Markdown', reply_markup=get_back_button())
    else:
        await query.edit_message_text("❌ خطا در ساخت سرور تست.", reply_markup=get_back_button())

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📞 پشتیبانی: \n @Shadowlini \n @Mohammadfd8", reply_markup=get_back_button())


# ==================== ADMIN PANEL ====================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ دسترسی غیرمجاز", reply_markup=get_back_button())
        return
    owner = is_owner(user_id)
    await query.edit_message_text("⚙️ **پنل مدیریت**", parse_mode='Markdown', reply_markup=get_admin_panel_keyboard(owner))

async def admin_manual_charge_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    await query.edit_message_text("💳 روش شارژ را انتخاب کنید:", reply_markup=get_charge_method_keyboard())

async def admin_charge_by_id_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    await query.edit_message_text("🆔 آیدی عددی کاربر را ارسال کنید:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="admin_panel")]]))
    return ASK_USER_ID

async def admin_charge_by_username_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    await query.edit_message_text("👤 یوزرنیم کاربر را ارسال کنید (مثل @username):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="admin_panel")]]))
    return ASK_USER_ID

async def manual_charge_get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inp = update.message.text.strip()
    if inp.isdigit():
        uid = int(inp)
        user = db.get_user(uid)
    else:
        user = db.get_user_by_username(inp.lstrip('@'))
        uid = user['user_id'] if user else None
    if not user:
        await update.message.reply_text("❌ کاربر یافت نشد. دوباره تلاش کن یا /cancel")
        return ASK_USER_ID
    context.user_data['charge_user_id'] = uid
    context.user_data['charge_username'] = user.get('username', 'بدون یوزرنیم')
    await update.message.reply_text(f"✅ کاربر: {user.get('first_name')}\n💰 موجودی فعلی: {user['balance']:,} تومان\n\nحالا مبلغ به تومان را وارد کن:")
    return ASK_AMOUNT

async def admin_charge_get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ دسترسی غیرمجاز!")
        return ConversationHandler.END
    try:
        amount = int(update.message.text.strip())
        if amount <= 0:
            await update.message.reply_text("❌ مبلغ باید بیشتر از صفر باشد. دوباره وارد کن:")
            return ASK_AMOUNT
    except:
        await update.message.reply_text("❌ عدد معتبر وارد کن:")
        return ASK_AMOUNT
    uid = context.user_data['charge_user_id']
    if db.update_balance(uid, amount):
        db.add_transaction(uid, amount, update.effective_user.id)
        new_bal = db.get_user_balance(uid)
        await update.message.reply_text(f"✅ **شارژ انجام شد!**\n💰 موجودی جدید: {new_bal:,} تومان", parse_mode='Markdown', reply_markup=get_main_keyboard(update.effective_user.id))
        try:
            await context.bot.send_message(uid, f"🎉 کیف پول شما {amount:,} تومان شارژ شد.\n💰 موجودی جدید: {new_bal:,} تومان")
        except:
            pass
    else:
        await update.message.reply_text("❌ خطا در شارژ کیف پول!")
    return ConversationHandler.END

async def add_plan_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel add plan conversation and clear all related data"""
    # پاک کردن اطلاعات موقت
    for key in ['new_plan_name', 'new_plan_traffic', 'new_plan_duration']:
        context.user_data.pop(key, None)
    # ارسال پیام لغو
    await update.message.reply_text("❌ عملیات افزودن پلن لغو شد.", reply_markup=get_main_keyboard(update.effective_user.id))
    # پایان مکالمه
    return ConversationHandler.END

async def manual_charge_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو عملیات جاری (شارژ دستی، کاهش موجودی، تست، و ...)"""
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=get_main_keyboard(update.effective_user.id))
    return ConversationHandler.END

async def admin_stats_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT SUM(balance) FROM users")
    total_bal = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(*) FROM orders WHERE status='completed'")
    orders = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM test_requests")
    tests = c.fetchone()[0]
    conn.close()
    await query.edit_message_text(f"📊 **آمار ربات**\n\n👥 کاربران: {users}\n💰 کل موجودی: {total_bal:,} تومان\n🛒 سفارشات: {orders}\n🎁 تست‌ها: {tests}", parse_mode='Markdown', reply_markup=get_back_button())

async def admin_list_plans_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    plans = db.get_active_plans()
    if not plans:
        txt = "📦 هیچ پلنی وجود ندارد."
    else:
        txt = "📋 **لیست پلن‌ها:**\n\n"
        for p in plans:
            txt += f"🆔 {p['id']} - **{p['name']}** | {p['traffic_gb']}GB | {p['duration_days']} روز | {p['price_rial']:,} تومان\n"
    await query.edit_message_text(txt, parse_mode='Markdown', reply_markup=get_back_button())

async def admin_list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT user_id, username, first_name, balance FROM users ORDER BY created_at DESC LIMIT 20")
    users = c.fetchall()
    conn.close()
    if not users:
        txt = "👥 هنوز کاربری ثبت نشده."
    else:
        txt = "👥 **۲۰ کاربر آخر:**\n\n"
        for u in users:
            txt += f"🆔 `{u[0]}` | @{u[1] or '—'} | {u[2] or '—'} | {u[3]:,} تومان\n"
    await query.edit_message_text(txt, reply_markup=get_back_button())

async def admin_total_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    conn = db.get_db()
    c = conn.cursor()
    c.execute("SELECT SUM(balance) FROM users")
    total = c.fetchone()[0] or 0
    conn.close()
    await query.edit_message_text(f"💰 **مجموع موجودی کاربران:** {total:,} تومان", parse_mode='Markdown', reply_markup=get_back_button())

# ---------- Payment Approve/Reject ----------
async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز!")
        return
    payment_id = int(query.data.split('_')[2])
    payment = db.get_payment_request(payment_id)
    if not payment:
        await query.edit_message_text("❌ درخواست یافت نشد!")
        return
    if db.approve_payment(payment_id, query.from_user.id):
        user = db.get_user(payment['user_id'])
        # لاگ 
        db.add_payment_log(
            payment_id=payment_id,
            admin_id=query.from_user.id,
            admin_username=query.from_user.username,
            user_id=payment['user_id'],
            user_username=user.get('username'),
            amount=payment['amount'],
            status='approved'
        )
        await query.edit_message_caption(caption=f"✅ **تأیید شد!**\n👤 کاربر: @{user.get('username', '')}\n💰 مبلغ: {payment['amount']:,} تومان\nوضعیت: تأیید شده", reply_markup=None)
        try:
            await context.bot.send_message(chat_id=payment['user_id'], text=f"✅ **شارژ کیف پول شما تأیید شد!**\n\n💰 مبلغ: {payment['amount']:,} تومان\n💵 موجودی جدید: {db.get_user_balance(payment['user_id']):,} تومان\n\n📦 حالا می‌توانید پلن مورد نظر خود را خریداری کنید.", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Could not notify user: {e}")
    else:
        await query.edit_message_text("❌ خطا در تأیید درخواست!")

async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز!")
        return
    payment_id = int(query.data.split('_')[2])
    payment = db.get_payment_request(payment_id)
    if not payment:
        await query.edit_message_text("❌ درخواست یافت نشد!")
        return
    context.user_data['reject_payment_id'] = payment_id
    context.user_data['reject_user_id'] = payment['user_id']
    context.user_data['reject_amount'] = payment['amount']
    context.user_data['reject_message_id'] = query.message.message_id
    keyboard = [[InlineKeyboardButton("🔙 انصراف", callback_data="cancel_reject")]]
    await query.edit_message_caption(caption=f"❌ **رد درخواست شارژ**\n\n💰 مبلغ: {payment['amount']:,} تومان\n\nلطفاً دلیل رد را وارد کنید:\n(این دلیل برای کاربر ارسال خواهد شد)", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_REJECT_REASON

async def get_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text.strip()
    payment_id = context.user_data.get('reject_payment_id')
    user_id = context.user_data.get('reject_user_id')
    amount = context.user_data.get('reject_amount')
    msg_id = context.user_data.get('reject_message_id')
    if not payment_id:
        await update.message.reply_text("❌ خطا: درخواستی یافت نشد!")
        return ConversationHandler.END
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE payment_requests SET status = "rejected", reject_reason = ? WHERE id = ?', (reason, payment_id))
    conn.commit()
    conn.close()
    admin_id = update.effective_user.id
    admin_username = update.effective_user.username
    user = db.get_user(user_id)  # دریافت اطلاعات کاربر برای یوزرنیم
    user_username = user.get('username') if user else None
    db.add_payment_log(
        payment_id=payment_id,
        admin_id=admin_id,
        admin_username=admin_username,
        user_id=user_id,
        user_username=user_username,
        amount=amount,
        status='rejected',
        reject_reason=reason
    )
    try:
        await context.bot.delete_message(chat_id=update.effective_user.id, message_id=msg_id)
    except:
        pass
    await update.message.reply_text(f"✅ درخواست شماره {payment_id} با موفقیت رد شد.\nدلیل: {reason}\n\nبه کاربر اطلاع داده شد.", reply_markup=get_admin_panel_keyboard(is_owner(update.effective_user.id)))
    try:
        await context.bot.send_message(chat_id=user_id, text=f"❌ **درخواست شارژ شما رد شد!**\n\n💰 مبلغ: {amount:,} تومان\n📝 **دلیل رد:** {reason}\n\nلطفاً برای رفع مشکل با پشتیبانی تماس بگیرید یا مجدداً تلاش کنید.\n📞 پشتیبانی:\n @Shadowlini \n @Mohammadfd8", parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Could not notify user: {e}")
        await update.message.reply_text(f"⚠️ پیام برای کاربر ارسال نشد (ربات را بلاک کرده)")
    context.user_data.pop('reject_payment_id', None)
    context.user_data.pop('reject_user_id', None)
    context.user_data.pop('reject_amount', None)
    context.user_data.pop('reject_message_id', None)
    return ConversationHandler.END

# ---------- Pending Payments List and Details ----------
async def pending_payments_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز!", reply_markup=get_back_button())
        return
    
    if query.message.photo:
        await query.delete_message()
        send_new = True
    else:
        send_new = False
    
    page = context.user_data.get('pending_page', 1)
    per_page = 5
    total = db.count_pending_payments()
    if total == 0:
        text = "📭 هیچ درخواست پرداخت فعالی وجود ندارد."
        if send_new:
            await context.bot.send_message(chat_id=query.from_user.id, text=text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]]))
        else:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]]))
        return
    
    total_pages = (total + per_page - 1) // per_page
    if page < 1: page = 1
    if page > total_pages: page = total_pages
    
    payments = db.get_pending_payments_paginated(page, per_page, 'newest')
    text = f"📋 **درخواست‌های فعال پرداخت** (صفحه {page} از {total_pages})\n\n"
    for p in payments:
        user = db.get_user(p['user_id'])
        username = f"@{user['username']}" if user and user['username'] else f"ID:{p['user_id']}"
        text += f"🆔 درخواست `{p['id']}` | 👤 {username} | 💰 {p['amount']:,} تومان\n"
    
    context.user_data['pending_page'] = page
    if send_new:
        await context.bot.send_message(chat_id=query.from_user.id, text=text, reply_markup=pending_list_keyboard(payments, page, total_pages))
    else:
        await query.edit_message_text(text, reply_markup=pending_list_keyboard(payments, page, total_pages))

async def pending_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز!")
        return
    page = int(query.data.split('_')[2])
    context.user_data['pending_page'] = page
    if query.message.photo:
        await query.delete_message()
        await pending_payments_list(update, context)
    else:
        await pending_payments_list(update, context)

async def view_payment_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز!")
        return
    payment_id = int(query.data.split('_')[2])
    payment = db.get_payment_request(payment_id)
    if not payment or payment['status'] != 'pending':
        await query.edit_message_text("❌ درخواست نامعتبر یا قبلاً بررسی شده است.")
        return
    user = db.get_user(payment['user_id'])
    username = f"@{user['username']}" if user['username'] else f"ID: {user['user_id']}"
    caption = f"🆔 **درخواست شماره {payment['id']}**\n👤 کاربر: {username}\n💰 مبلغ: {payment['amount']:,} تومان\n📅 تاریخ: {payment['created_at'][:16]}\n📎 رسید ارسالی:"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تأیید", callback_data=f"approve_payment_{payment_id}"), InlineKeyboardButton("❌ رد", callback_data=f"reject_payment_{payment_id}")],
        [InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="pending_payments_list")]
    ])
    await query.edit_message_text("📸 در حال بارگذاری جزئیات درخواست...")
    await context.bot.send_photo(chat_id=query.from_user.id, photo=payment['receipt_file_id'], caption=caption, reply_markup=keyboard)
    await query.delete_message()


# ==================== ADMIN MAKE TEST ====================

async def admin_make_test_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    keyboard = [
        [InlineKeyboardButton("🆔 ساخت تست با آیدی عددی", callback_data="admin_test_by_id")],
        [InlineKeyboardButton("👤 ساخت تست با یوزرنیم", callback_data="admin_test_by_username")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
    ]
    await query.edit_message_text("🎁 **ساخت سرور تست برای کاربر**\n\nروش مورد نظر را انتخاب کنید:", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_test_by_id_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    await query.edit_message_text("🆔 آیدی عددی کاربر را ارسال کنید:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="admin_panel")]]))
    return ASK_TEST_USER

async def admin_test_by_username_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    await query.edit_message_text("👤 یوزرنیم کاربر را ارسال کنید (مثل @username):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="admin_panel")]]))
    return ASK_TEST_USER

async def admin_test_get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inp = update.message.text.strip()
    if inp.isdigit():
        uid = int(inp)
        user = db.get_user(uid)
    else:
        user = db.get_user_by_username(inp.lstrip('@'))
        uid = user['user_id'] if user else None
    if not user:
        await update.message.reply_text("❌ کاربر یافت نشد. /cancel برای لغو")
        return ASK_TEST_USER
    context.user_data['test_user_id'] = uid
    context.user_data['test_username'] = user.get('username', 'بدون یوزرنیم')
    await update.message.reply_text(f"✅ کاربر پیدا شد: {user.get('first_name')}\n\n⏳ در حال ساخت سرور تست (1 گیگ / 30 دقیقه)...")
    result = pg_api.create_test_user()
    if result and result.get('success'):
        link = result['config_link']
        await update.message.reply_text(f"✅ **سرور تست ساخته شد!**\n\n👤 کاربر: @{context.user_data['test_username']}\n🔗 لینک:\n`{link}`", parse_mode='Markdown', reply_markup=get_admin_panel_keyboard(is_owner(update.effective_user.id)))
        try:
            await context.bot.send_message(uid, f"🎁 **یک سرویس تست ویژه برای شما ساخته شد!**\n\n⚡ حجم: ۱ گیگابایت\n⏱ مدت: ۳۰ دقیقه\n\n🔗 لینک اشتراک:\n`{link}`\n\n📌 این سرویس توسط ادمین فعال شده است.", parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"⚠️ پیام برای کاربر ارسال نشد (ربات را بلاک کرده)")
    else:
        await update.message.reply_text("❌ خطا در ساخت سرور تست!", reply_markup=get_admin_panel_keyboard(is_owner(update.effective_user.id)))
    return ConversationHandler.END

async def delete_plan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ دسترسی غیرمجاز")
        return
    try:
        plan_id = int(context.args[0])
        if db.delete_plan(plan_id):
            await update.message.reply_text(f"✅ پلن با شناسه {plan_id} با موفقیت حذف شد.")
        else:
            await update.message.reply_text(f"❌ پلن با شناسه {plan_id} یافت نشد.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ استفاده: /delete_plan [شناسه پلن]")

async def cancel_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.delete_message()
    await context.bot.send_message(chat_id=query.from_user.id, text="⚙️ **پنل مدیریت**", parse_mode='Markdown', reply_markup=get_admin_panel_keyboard(is_owner(query.from_user.id)))
    return ConversationHandler.END


# ==================== ADMIN DEBIT BALANCE ====================

async def admin_debit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز!", reply_markup=get_back_button())
        return
    keyboard = [
        [InlineKeyboardButton("🆔 کاهش با آیدی عددی", callback_data="debit_by_id")],
        [InlineKeyboardButton("👤 کاهش با یوزرنیم", callback_data="debit_by_username")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
    ]
    await query.edit_message_text(
        "➖ **کاهش موجودی کاربر**\n\nلطفاً روش مورد نظر را انتخاب کنید:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def admin_debit_by_id_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("DEBUG: admin_debit_by_id_start called")
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز!")
        return
    await query.edit_message_text(
        "🆔 آیدی عددی کاربر را ارسال کنید:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="admin_panel")]])
    )
    return ASK_USER_ID

async def admin_debit_by_username_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز!")
        return
    await query.edit_message_text(
        "👤 یوزرنیم کاربر را ارسال کنید (مثل @username):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو", callback_data="admin_panel")]])
    )
    return ASK_USER_ID

async def debit_get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inp = update.message.text.strip()
    if inp.isdigit():
        uid = int(inp)
        user = db.get_user(uid)
    else:
        user = db.get_user_by_username(inp.lstrip('@'))
        uid = user['user_id'] if user else None
    if not user:
        await update.message.reply_text("❌ کاربر یافت نشد. دوباره تلاش کن یا /cancel")
        return ASK_USER_ID
    context.user_data['debit_user_id'] = uid
    context.user_data['debit_username'] = user.get('username', 'بدون یوزرنیم')
    context.user_data['debit_current_balance'] = user['balance']
    await update.message.reply_text(
        f"✅ کاربر پیدا شد: {user.get('first_name')}\n"
        f"💰 موجودی فعلی: {user['balance']:,} تومان\n\n"
        f"➖ حالا مبلغی که می‌خواهید **کم کنید** را وارد نمایید:",
        parse_mode='Markdown'
    )
    return ASK_DEBIT_AMOUNT

async def debit_get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ دسترسی غیرمجاز!")
        return ConversationHandler.END
    try:
        amount = int(update.message.text.strip())
        if amount <= 0:
            await update.message.reply_text("❌ مبلغ باید بیشتر از صفر باشد. دوباره وارد کن:")
            return ASK_DEBIT_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ لطفاً یک عدد معتبر وارد کنید:")
        return ASK_DEBIT_AMOUNT
    uid = context.user_data['debit_user_id']
    current_balance = context.user_data['debit_current_balance']
    if current_balance < amount:
        await update.message.reply_text(
            f"❌ موجودی کاربر کافی نیست!\n"
            f"💰 موجودی فعلی: {current_balance:,} تومان\n"
            f"➖ مبلغ درخواستی برای کم کردن: {amount:,} تومان\n\n"
            f"لطفاً مبلغ کمتری وارد کنید:",
            parse_mode='Markdown'
        )
        return ASK_DEBIT_AMOUNT
    if db.update_balance(uid, -amount):
        db.add_transaction(uid, -amount, update.effective_user.id)
        new_balance = db.get_user_balance(uid)
        await update.message.reply_text(
            f"✅ **کاهش موجودی انجام شد!**\n\n"
            f"👤 کاربر: @{context.user_data['debit_username']}\n"
            f"➖ مبلغ کاهش: {amount:,} تومان\n"
            f"💰 موجودی قبلی: {current_balance:,} تومان\n"
            f"💰 موجودی جدید: {new_balance:,} تومان",
            parse_mode='Markdown',
            reply_markup=get_admin_panel_keyboard(is_owner(update.effective_user.id))
        )
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=(
                    f"⚠️ **کاهش موجودی کیف پول**\n\n"
                    f"➖ مبلغ کاهش: {amount:,} تومان\n"
                    f"💰 موجودی جدید: {new_balance:,} تومان\n\n"
                    f"در صورت نیاز به توضیح، با پشتیبانی تماس بگیرید."
                ),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Could not notify user: {e}")
    else:
        await update.message.reply_text("❌ خطا در کاهش موجودی!")
    context.user_data.pop('debit_user_id', None)
    context.user_data.pop('debit_username', None)
    context.user_data.pop('debit_current_balance', None)
    return ConversationHandler.END


# ==================== ADD PLAN WITH CONVERSATION ====================

async def add_plan_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        send_func = query.message.reply_text
    else:
        send_func = update.message.reply_text

    if not is_admin(update.effective_user.id):
        await send_func("❌ دسترسی غیرمجاز")
        return ConversationHandler.END

    await send_func(
        "➕ **افزودن پلن جدید**\n\n"
        "لطفاً **نام پلن** را وارد کنید (ممکن است شامل فاصله باشد):\n"
        "مثال: `پایه ماهانه` یا `حرفه ای 3 ماهه`",
        parse_mode='Markdown'
    )
    return ASK_PLAN_NAME

async def add_plan_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("❌ نام نمی‌تواند خالی باشد. دوباره وارد کنید:")
        return ASK_PLAN_NAME
    context.user_data['new_plan_name'] = name
    await update.message.reply_text(
        f"✅ نام پلن: **{name}**\n\n"
        "حالا **حجم (به گیگابایت)** را وارد کنید:\n"
        "مثال: `10`"
    )
    return ASK_PLAN_TRAFFIC

async def add_plan_get_traffic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        traffic = int(update.message.text.strip())
        if traffic <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ لطفاً یک عدد صحیح مثبت برای حجم وارد کنید:")
        return ASK_PLAN_TRAFFIC
    context.user_data['new_plan_traffic'] = traffic
    await update.message.reply_text(
        f"✅ حجم: {traffic} گیگ\n\n"
        "حالا **مدت (به روز)** را وارد کنید:\n"
        "مثال: `30`"
    )
    return ASK_PLAN_DURATION

async def add_plan_get_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        days = int(update.message.text.strip())
        if days <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ لطفاً یک عدد صحیح مثبت برای مدت وارد کنید:")
        return ASK_PLAN_DURATION
    context.user_data['new_plan_duration'] = days
    await update.message.reply_text(
        f"✅ مدت: {days} روز\n\n"
        "حالا **قیمت (به تومان)** را وارد کنید:\n"
        "مثال: `50000`"
    )
    return ASK_PLAN_PRICE

async def add_plan_get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text.strip())
        if price <= 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ لطفاً یک عدد صحیح مثبت برای قیمت وارد کنید:")
        return ASK_PLAN_PRICE
    name = context.user_data['new_plan_name']
    traffic = context.user_data['new_plan_traffic']
    days = context.user_data['new_plan_duration']
    db.add_plan(name, traffic, days, price)
    await update.message.reply_text(
        f"✅ **پلن با موفقیت اضافه شد!**\n\n"
        f"📦 نام: {name}\n"
        f"📊 حجم: {traffic} گیگ\n"
        f"⏱ مدت: {days} روز\n"
        f"💰 قیمت: {price:,} تومان",
        parse_mode='Markdown'
    )
    for key in ['new_plan_name', 'new_plan_traffic', 'new_plan_duration']:
        context.user_data.pop(key, None)
    return ConversationHandler.END

async def add_plan_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ عملیات افزودن پلن لغو شد.")
    return ConversationHandler.END


# ==================== ADMIN MANAGEMENT (OWNER ONLY) ====================

async def admin_manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ فقط مالک ربات به این بخش دسترسی دارد.", reply_markup=get_back_button())
        return
    keyboard = [
        [InlineKeyboardButton("➕ افزودن ادمین جدید", callback_data="add_admin")],
        [InlineKeyboardButton("❌ حذف ادمین", callback_data="remove_admin")],
        [InlineKeyboardButton("📋 لیست ادمین‌ها", callback_data="list_admins")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
    ]
    await query.edit_message_text("👑 **مدیریت ادمین‌ها**\n\nلطفاً گزینه مورد نظر را انتخاب کنید:", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("DEBUG: add_admin_start called")
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز", reply_markup=get_back_button())
        return
    await query.edit_message_text(
        "➕ **افزودن ادمین جدید**\n\n"
        "لطفاً آیدی عددی یا یوزرنیم کاربر مورد نظر را ارسال کنید.\n"
        "مثال: `123456789` یا `@username`",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data="admin_manage_admins")]])
    )
    return ASK_ADMIN_USER_ID

async def add_admin_get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inp = update.message.text.strip()
    if inp.isdigit():
        uid = int(inp)
        user = db.get_user(uid)
    else:
        user = db.get_user_by_username(inp.lstrip('@'))
        uid = user['user_id'] if user else None
    if not user:
        await update.message.reply_text("❌ کاربر یافت نشد. لطفاً دوباره تلاش کنید یا /cancel")
        return ASK_ADMIN_USER_ID
    if is_admin(uid):
        await update.message.reply_text("❌ این کاربر قبلاً ادمین است.")
        return ConversationHandler.END
    added_by = update.effective_user.id
    if db.add_admin(uid, user.get('username'), added_by):
        await update.message.reply_text(f"✅ کاربر @{user.get('username') or uid} با موفقیت به ادمین‌ها اضافه شد.", reply_markup=get_main_keyboard(update.effective_user.id))
    else:
        await update.message.reply_text("❌ خطا در افزودن ادمین!")
    return ConversationHandler.END

async def remove_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز", reply_markup=get_back_button())
        return
    await query.edit_message_text(
        "❌ **حذف ادمین**\n\n"
        "لطفاً آیدی عددی یا یوزرنیم ادمین مورد نظر را ارسال کنید.\n"
        "توجه: مالک ربات قابل حذف نیست.",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data="admin_manage_admins")]])
    )
    return ASK_REMOVE_ADMIN_USER_ID

async def remove_admin_get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inp = update.message.text.strip()
    if inp.isdigit():
        uid = int(inp)
        user = db.get_user(uid)
    else:
        user = db.get_user_by_username(inp.lstrip('@'))
        uid = user['user_id'] if user else None
    if not user:
        await update.message.reply_text("❌ کاربر یافت نشد. لطفاً دوباره تلاش کنید یا /cancel")
        return ASK_REMOVE_ADMIN_USER_ID
    if is_owner(uid):
        await update.message.reply_text("❌ مالک ربات قابل حذف نیست.")
        return ConversationHandler.END
    if not is_admin(uid):
        await update.message.reply_text("❌ این کاربر ادمین نیست.")
        return ConversationHandler.END
    if db.remove_admin(uid):
        await update.message.reply_text(f"✅ ادمین @{user.get('username') or uid} با موفقیت حذف شد.", reply_markup=get_main_keyboard(update.effective_user.id))
    else:
        await update.message.reply_text("❌ خطا در حذف ادمین!")
    return ConversationHandler.END

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز", reply_markup=get_back_button())
        return
    admins = db.get_all_admins()
    if not admins:
        text = "📋 هیچ ادمینی یافت نشد."
    else:
        text = "👑 **لیست ادمین‌ها:**\n\n"
        for adm in admins:
            role = "👑 مالک" if adm['is_owner'] else "👤 ادمین"
            username = f"@{adm['username']}" if adm['username'] else f"ID: {adm['user_id']}"
            text += f"{role} | {username}\n"
            text += f"   افزوده شده در: {adm['added_at'][:16]}\n\n"
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_manage_admins")]]))


# ==================== EXPORT TRANSACTIONS (OWNER ONLY) ====================

async def export_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export all payment logs to Excel file (owner only)"""
    query = update.callback_query
    await query.answer()
    
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ فقط مالک ربات به این بخش دسترسی دارد.", reply_markup=get_back_button())
        return
    
    await query.edit_message_text("⏳ در حال تولید فایل اکسل... لطفاً صبر کنید.")
    
    try:
        file_path = db.export_payment_logs_to_excel()
        with open(file_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=f,
                filename="payment_logs.xlsx",
                caption="📊 **گزارش کامل تراکنش‌های مالی**\n\nتاریخ: " + datetime.now().strftime("%Y-%m-%d %H:%M")
            )
        import os
        os.remove(file_path)
    except Exception as e:
        logger.error(f"Excel export error: {e}")
        await query.edit_message_text("❌ خطا در تولید فایل اکسل. لطفاً دوباره تلاش کنید.", reply_markup=get_back_button())
        return
    
    # بعد از ارسال فایل، دوباره پنل مدیریت را نمایش بده
    owner = is_owner(query.from_user.id)
    await context.bot.send_message(chat_id=query.from_user.id, text="⚙️ **پنل مدیریت**", parse_mode='Markdown', reply_markup=get_admin_panel_keyboard(owner))


# ==================== ADVANCED STATS (OWNER ONLY) ====================

async def advanced_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش آمار پیشرفته فروش و درآمد (فقط مالک)"""
    query = update.callback_query
    await query.answer()
    
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ فقط مالک ربات به این بخش دسترسی دارد.", reply_markup=get_back_button())
        return
    
    await query.edit_message_text("⏳ در حال جمع‌آوری آمار... لطفاً صبر کنید.")
    
    # دریافت آمارها
    total_deposits = db.get_total_approved_deposits()
    best_plan = db.get_best_selling_plan()
    monthly_stats = db.get_current_month_stats()
    total_orders = db.get_total_orders_count()
    
    # ساخت متن
    text = "📊 **آمار پیشرفته ربات**\n\n"
    
    text += "💰 **وضعیت مالی**\n"
    text += f"• کل واریز‌های تأیید شده: {total_deposits:,} تومان\n"
    text += f"• درآمد خالص (فروش پلن‌ها): {monthly_stats['revenue']:,} تومان (ماه جاری)\n"
    text += f"• نسبت واریز به فروش: { (monthly_stats['revenue'] / total_deposits * 100) if total_deposits else 0:.1f}%\n\n"
    
    text += "📦 **فروش پلن‌ها**\n"
    text += f"• کل سفارشات تکمیل شده: {total_orders}\n"
    if best_plan:
        text += (f"• پرفروش‌ترین پلن: **{best_plan['name']}**\n"
                 f"   - حجم: {best_plan['traffic_gb']} گیگ / {best_plan['duration_days']} روز\n"
                 f"   - قیمت: {best_plan['price_rial']:,} تومان\n"
                 f"   - تعداد فروش: {best_plan['sales_count']}\n\n")
    else:
        text += "• هنوز فروشی ثبت نشده است.\n\n"
    
    text += "📅 **آمار ماه جاری**\n"
    text += f"• کاربران جدید: {monthly_stats['new_users']}\n"
    text += f"• سفارشات جدید: {monthly_stats['new_orders']}\n"
    text += f"• درآمد ماه: {monthly_stats['revenue']:,} تومان\n"
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت به پنل مدیریت", callback_data="admin_panel")]]
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


# ==================== MAIN ====================

def main():
    db.init_db()
    app = Application.builder().token(config.BOT_TOKEN).build()

    add_plan_conv = ConversationHandler(
        entry_points=[
            CommandHandler("add_plan", add_plan_start),
            CallbackQueryHandler(add_plan_start, pattern="^admin_add_plan$")
        ],
        states={
            ASK_PLAN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plan_get_name)],
            ASK_PLAN_TRAFFIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plan_get_traffic)],
            ASK_PLAN_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plan_get_duration)],
            ASK_PLAN_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_plan_get_price)],
        },
        fallbacks=[CommandHandler("cancel", add_plan_cancel)],
        allow_reentry=True
    )
    charge_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_charge_by_id_start, pattern="^charge_by_id$"), CallbackQueryHandler(admin_charge_by_username_start, pattern="^charge_by_username$")],
        states={ASK_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_charge_get_user)], ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_charge_get_amount)]},
        fallbacks=[CommandHandler("cancel", manual_charge_cancel)],
    )
    test_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_test_by_id_start, pattern="^admin_test_by_id$"), CallbackQueryHandler(admin_test_by_username_start, pattern="^admin_test_by_username$")],
        states={ASK_TEST_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_test_get_user)]},
        fallbacks=[CommandHandler("cancel", manual_charge_cancel)],
    )
    payment_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(rial_payment_start, pattern="^rial_payment$")],
        states={ASK_PAYMENT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, rial_payment_get_amount)]},
        fallbacks=[CommandHandler("cancel", manual_charge_cancel)],
    )
    reject_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(reject_payment, pattern="^reject_payment_\\d+$")],
        states={ASK_REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reject_reason), CallbackQueryHandler(cancel_reject_callback, pattern="^cancel_reject$")]},
        fallbacks=[CommandHandler("cancel", manual_charge_cancel)],
    )
    debit_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_debit_by_id_start, pattern="^debit_by_id$"),
            CallbackQueryHandler(admin_debit_by_username_start, pattern="^debit_by_username$")
        ],
        states={
            ASK_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, debit_get_user)],
            ASK_DEBIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, debit_get_amount)]
        },
        fallbacks=[CommandHandler("cancel", manual_charge_cancel)],
    )
    add_admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_admin_start, pattern="^add_admin$")],
        states={ASK_ADMIN_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_get_user)]},
        fallbacks=[CommandHandler("cancel", manual_charge_cancel)],
    )
    remove_admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(remove_admin_start, pattern="^remove_admin$")],
        states={ASK_REMOVE_ADMIN_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_admin_get_user)]},
        fallbacks=[CommandHandler("cancel", manual_charge_cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("delete_plan", delete_plan_command))
    app.add_handler(CommandHandler("cancel", manual_charge_cancel))
    app.add_handler(charge_conv)
    app.add_handler(test_conv)
    app.add_handler(payment_conv)
    app.add_handler(reject_conv)
    app.add_handler(debit_conv)
    app.add_handler(add_plan_conv)
    app.add_handler(add_admin_conv)
    app.add_handler(remove_admin_conv)
    app.add_handler(CommandHandler("addadmin", add_admin_start))
    app.add_handler(CommandHandler("addplan", add_plan_start))

    app.add_handler(CallbackQueryHandler(back_to_main, pattern="^back_to_main$"))
    app.add_handler(CallbackQueryHandler(show_wallet, pattern="^wallet$"))
    app.add_handler(CallbackQueryHandler(charge_wallet_menu, pattern="^charge_wallet$"))
    app.add_handler(CallbackQueryHandler(show_plans, pattern="^buy_plan$"))
    app.add_handler(CallbackQueryHandler(test_request, pattern="^test_request$"))
    app.add_handler(CallbackQueryHandler(support, pattern="^support$"))
    app.add_handler(CallbackQueryHandler(handle_buy, pattern="^buy_\\d+$"))
    app.add_handler(CallbackQueryHandler(advanced_stats, pattern="^advanced_stats$"))
    
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_manual_charge_menu, pattern="^admin_manual_charge$"))
    app.add_handler(CallbackQueryHandler(admin_stats_menu, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_list_plans_menu, pattern="^admin_list_plans$"))
    app.add_handler(CallbackQueryHandler(admin_list_users, pattern="^admin_list_users$"))
    app.add_handler(CallbackQueryHandler(admin_total_balance, pattern="^admin_total_balance$"))
    app.add_handler(CallbackQueryHandler(admin_make_test_menu, pattern="^admin_make_test$"))
    app.add_handler(CallbackQueryHandler(admin_debit_menu, pattern="^admin_debit_balance$"))
    app.add_handler(CallbackQueryHandler(admin_manage_admins, pattern="^admin_manage_admins$"))
    app.add_handler(CallbackQueryHandler(list_admins, pattern="^list_admins$"))
    
    app.add_handler(CallbackQueryHandler(export_transactions, pattern="^export_transactions$"))

    app.add_handler(CallbackQueryHandler(pending_payments_list, pattern="^pending_payments_list$"))
    app.add_handler(CallbackQueryHandler(pending_pagination, pattern="^pending_page_\\d+$"))
    app.add_handler(CallbackQueryHandler(view_payment_details, pattern="^view_payment_\\d+$"))
    
    app.add_handler(CallbackQueryHandler(approve_payment, pattern="^approve_payment_\\d+$"))
    
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_receipt))
    
    print("🤖 ربات با موفقیت روشن شد...")
    app.run_polling()

if __name__ == "__main__":
    main()