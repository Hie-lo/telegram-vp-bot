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
import subprocess
import sys
import asyncio
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
ASK_TEST_REMINDER_TEXT = 20
ASK_PRE_EXPIRE_MINUTES = 21

ASK_REFERRAL_SETTING_TYPE = 22
ASK_REFERRAL_BONUS_REFERRER = 23
ASK_REFERRAL_BONUS_REFERRED = 24
ASK_REFERRAL_PURCHASE_PERCENT = 25
ASK_REFERRAL_EVENT_START = 26
ASK_REFERRAL_EVENT_END = 27

ASK_BROADCAST_TYPE = 30
ASK_BROADCAST_CONTENT = 31
ASK_BROADCAST_CAPTION = 32
ASK_BROADCAST_FILTER = 33
ASK_BROADCAST_CONFIRM = 34
# Helper functions for permissions
def is_admin(user_id: int) -> bool:
    return db.is_admin(user_id)

def is_owner(user_id: int) -> bool:
    return db.is_owner(user_id)

# ==================== KEYBOARDS ====================

def get_main_keyboard(user_id: int = None):
    admin = is_admin(user_id) if user_id else False
    if admin:
        keyboard = [
            [InlineKeyboardButton("💰 کیف پول من", callback_data="wallet"), InlineKeyboardButton("📦 خرید پلن", callback_data="buy_plan")],
            [InlineKeyboardButton("🎁 درخواست تست", callback_data="test_request"), InlineKeyboardButton("📞 پشتیبانی", callback_data="support")],
            [InlineKeyboardButton("🔗 دعوت از دوستان", callback_data="referral_menu")],
            [InlineKeyboardButton("⚙️ پنل مدیریت", callback_data="admin_panel")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("💰 کیف پول من", callback_data="wallet"), InlineKeyboardButton("📦 خرید پلن", callback_data="buy_plan")],
            [InlineKeyboardButton("🎁 درخواست تست", callback_data="test_request"), InlineKeyboardButton("📞 پشتیبانی", callback_data="support")],
            [InlineKeyboardButton("🔗 دعوت از دوستان", callback_data="referral_menu")]
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
        keyboard.insert(2, [InlineKeyboardButton("👑 مدیریت ادمین‌ها", callback_data="admin_manage_admins")])  
        keyboard.insert(5, [InlineKeyboardButton("🔄 ری‌استارت ربات", callback_data="restart_bot")])
        keyboard.insert(6, [InlineKeyboardButton("⚙️ تنظیمات پیام تست", callback_data="test_reminder_settings")]) 
        keyboard.insert(7, [InlineKeyboardButton("🎁 تنظیمات رفرال", callback_data="referral_admin_panel")])
        keyboard.insert(8, [InlineKeyboardButton("📦 بک‌آپ دستی", callback_data="manual_backup")])
        keyboard.insert(8, [InlineKeyboardButton("📊 گزارش رفرال", callback_data="export_referral_report")])
        keyboard.insert(9, [InlineKeyboardButton("📊 حسابداری", callback_data="accounting_report")])
    keyboard.append([InlineKeyboardButton("📢 پیام همگانی", callback_data="broadcast_menu")])
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
    existing_user = db.get_user(user.id)
    is_new_user = existing_user is None
    
    # ثبت کاربر (اگر وجود داشته باشد، تغییری نمی‌کند)
    db.add_user(user_id=user.id, username=user.username, first_name=user.first_name)
    
    # پردازش رفرال فقط برای کاربران جدید (اولین بار است که ربات را استارت می‌زنند)
    args = context.args
    if is_new_user and args and db.get_referral_settings().get('is_active', 0):
        referral_code = args[0]
        referrer = db.get_user_by_referral_code(referral_code)
        if referrer and referrer['user_id'] != user.id:
            # ثبت referrer_id برای کاربر جدید
            conn = db.get_db()
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET referrer_id = ? WHERE user_id = ?', (referrer['user_id'], user.id))
            conn.commit()
            conn.close()
            
            # اعطای پاداش ثبت‌نام
            settings = db.get_referral_settings()
            if settings.get('signup_bonus_referrer', 0) > 0:
                db.update_balance(referrer['user_id'], settings['signup_bonus_referrer'])
                db.add_transaction(referrer['user_id'], settings['signup_bonus_referrer'])
                db.add_referral_log(referrer['user_id'], user.id, 'signup', settings['signup_bonus_referrer'])
            if settings.get('signup_bonus_referred', 0) > 0:
                db.update_balance(user.id, settings['signup_bonus_referred'])
                db.add_transaction(user.id, settings['signup_bonus_referred'])
                # (اختیاری) برای آمار رفرال خود کاربر جدید، لاگ نمی‌زنیم
            # ارسال پیام به معرف‌کننده
            try:
                await context.bot.send_message(
                    referrer['user_id'],
                    f"🎉 کاربر جدید با لینک شما ثبت‌نام کرد!\n💰 {settings.get('signup_bonus_referrer', 0):,} تومان به کیف پولتان اضافه شد."
                )
            except:
                pass
    
    # ادامه کد اصلی start (نمایش پیام خوش‌آمدگویی)
    admin = is_admin(user.id)
    if admin:
        welcome_text = f"👑 **خوش آمدی ادمین عزیز!** {user.first_name}\n\n🌟 به ربات فروش کانفیگ خوش آمدی.\n⚙️ **پنل مدیریت در انتهای منو قرار دارد.**\n\n💫 از منوی زیر گزینه مورد نظرت رو انتخاب کن:"
    else:
        welcome_text = f"✨ به ربات فروش کانفیگ خوش آمدی {user.first_name}!\n\n🌟 با استفاده از این ربات می‌تونی کانفیگ VPN با کیفیت بالا دریافت کنی.\n\n💫 از منوی زیر گزینه مورد نظرت رو انتخاب کن:"
    await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=get_main_keyboard(user.id))
 
    
async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass  # نادیده گرفتن خطای منقضی شدن
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
    panel_username = f"user_{user_id}_{order_id}"
    result = pg_api.create_user(traffic_gb=plan['traffic_gb'], expire_days=plan['duration_days'], username=panel_username)
    if result and result.get('success'):
        # ذخیره لینک و نام کاربری پنل در سفارش
        db.update_order_config(order_id, result['config_link'])

        conn = db.get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE orders SET panel_username = ? WHERE id = ?', (panel_username, order_id))
        conn.commit()
        conn.close()
            # پورسانت رفرال (اگر رفرال فعال باشد و کاربر توسط کسی معرفی شده باشد)
        settings = db.get_referral_settings()
        if settings.get('is_active', 0):
            user_data = db.get_user(user_id)
            referrer_id = user_data.get('referrer_id')
            if referrer_id:
                commission = int(plan['price_rial'] * settings.get('purchase_percent', 5) / 100)
                if commission > 0:
                    db.update_balance(referrer_id, commission)
                    db.add_transaction(referrer_id, commission)
                    db.add_referral_log(referrer_id, user_id, 'purchase', commission)
                    try:
                        await context.bot.send_message(referrer_id, f"🎉 کاربری که دعوت کردید خریدی انجام داد!\n💰 {commission:,} تومان به کیف پولتان اضافه شد.")
                    except:
                        pass
            # ثبت لاگ حسابداری
        panel_cost_per_gb = 7000  # هزینه هر گیگ به صاحب پنل
        referral_cost = commission if 'commission' in locals() else 0
        db.add_sales_log(
            order_id=order_id,
            user_id=user_id,
            plan_id=plan['id'],
            traffic_gb=plan['traffic_gb'],
            user_price=plan['price_rial'],
            panel_cost_per_gb=panel_cost_per_gb,
            referral_cost=referral_cost
        )
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
    """لغو عملیات جاری (شارژ دستی، کاهش موجودی، مدیریت ادمین، و ...)"""
    # کلیدهای مربوط به مکالمه‌های مختلف
    keys_to_remove = [
    'charge_user_id', 'charge_username',
    'debit_user_id', 'debit_username', 'debit_current_balance',
    'reject_payment_id', 'reject_user_id', 'reject_amount', 'reject_message_id',
    'test_user_id', 'test_username',
    'new_plan_name', 'new_plan_traffic', 'new_plan_duration',
    'payment_amount', 'waiting_for_receipt' 
    ]
    for key in keys_to_remove:
        context.user_data.pop(key, None)
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
    """نمایش لیست کاربران با صفحه‌بندی (ادمین‌ها)"""
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز", reply_markup=get_back_button())
        return
    
    # دریافت صفحه جاری
    page = context.user_data.get('users_page', 1)
    per_page = 10
    total_users = db.count_users()
    total_pages = (total_users + per_page - 1) // per_page if total_users > 0 else 1
    
    if page < 1:
        page = 1
    if page > total_pages and total_pages > 0:
        page = total_pages
    
    users = db.get_users_paginated(page, per_page, 'newest')
    
    # ساخت متن
    text = f"👥 **لیست کاربران** (صفحه {page} از {total_pages})\n\n"
    for u in users:
        # ban_status = "🚫 بن شده" if u.get('is_banned', 0) else "✅ فعال"
        text += f"🆔 `{u['user_id']}`\n"
        text += f"👤 @{u['username'] or 'بدون یوزرنیم'} | {u['first_name'] or 'نامشخص'}\n"
        # text += f"💰 موجودی: {u['balance']:,} تومان | {ban_status}\n"
        text += f"💰 موجودی: {u['balance']:,} تومان\n"
        text += f"📅 تاریخ عضویت: {u['created_at'][:16]}\n"
        text += f"─────────────────\n"
    
    # کیبورد صفحه‌بندی
    keyboard = []
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"users_page_{page-1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"users_page_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # دکمه خروجی اکسل (فقط مالک)
    if is_owner(query.from_user.id):
        keyboard.append([InlineKeyboardButton("📥 خروجی اکسل کاربران", callback_data="export_users_excel")])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")])
    
    try:
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Error in admin_list_users: {e}")
        # اگر خطا در ویرایش بود، پیام جدید بفرست
        await context.bot.send_message(chat_id=query.from_user.id, text=text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def users_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغییر صفحه در لیست کاربران"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    page = int(query.data.split('_')[2])
    context.user_data['users_page'] = page
    await admin_list_users(update, context)

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


# ==================== TEST REMINDER SETTINGS (OWNER ONLY) ====================

async def test_reminder_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش منوی تنظیمات پیام تست (فقط مالک)"""
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ فقط مالک ربات به این بخش دسترسی دارد.", reply_markup=get_back_button())
        return
    
    settings = db.get_test_reminder_settings()
    status_text = "✅ فعال" if settings.get('is_active', 1) else "❌ غیرفعال"
    keyboard = [
        [InlineKeyboardButton(f"🔘 وضعیت: {status_text}", callback_data="toggle_test_reminder")],
        [InlineKeyboardButton("✏️ تغییر متن پیام", callback_data="edit_test_reminder_text")],
        [InlineKeyboardButton("⏱ تغییر زمان یادآوری (قبل از اتمام)", callback_data="edit_pre_expire_minutes")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
    ]
    text = f"⚙️ **تنظیمات پیام تست**\n\n"
    text += f"📌 وضعیت: {status_text}\n"
    text += f"⏰ یادآوری قبل از اتمام: {settings.get('pre_expire_minutes', 5)} دقیقه\n"
    text += f"📝 متن پیام:\n{settings.get('message_text', '')}\n"
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def toggle_test_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغییر وضعیت فعال/غیرفعال پیام تست"""
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    
    settings = db.get_test_reminder_settings()
    new_status = not settings.get('is_active', 1)
    db.update_test_reminder_settings(is_active=new_status)
    await test_reminder_settings_menu(update, context)

async def edit_test_reminder_text_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ویرایش متن پیام تست"""
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    
    await query.edit_message_text(
        "✏️ **ویرایش متن پیام تست**\n\n"
        "متن جدید را ارسال کنید. می‌توانید از ایموجی و Markdown استفاده کنید.\n"
        "برای لغو، /cancel را بزنید.",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data="test_reminder_settings")]])
    )
    return ASK_TEST_REMINDER_TEXT

async def edit_test_reminder_text_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت متن جدید و ذخیره"""
    new_text = update.message.text.strip()
    if not new_text:
        await update.message.reply_text("❌ متن نمی‌تواند خالی باشد. دوباره ارسال کنید یا /cancel")
        return ASK_TEST_REMINDER_TEXT
    
    db.update_test_reminder_settings(message_text=new_text)
    await update.message.reply_text("✅ متن پیام تست با موفقیت به‌روز شد.")
    # نمایش مجدد منوی تنظیمات
    # برای سادگی، از یک پیام جدید استفاده می‌کنیم
    keyboard = [[InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data="test_reminder_settings")]]
    await update.message.reply_text("⚙️ برای بازگشت به منوی تنظیمات، روی دکمه کلیک کنید.", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def edit_pre_expire_minutes_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع تغییر زمان یادآوری قبل از اتمام"""
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    
    await query.edit_message_text(
        "⏱ **تغییر زمان یادآوری قبل از اتمام تست**\n\n"
        "لطفاً تعداد دقیقه (عدد بین 1 تا 30) را وارد کنید:\n"
        "مثال: `5`",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data="test_reminder_settings")]])
    )
    return ASK_PRE_EXPIRE_MINUTES

async def edit_pre_expire_minutes_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت زمان جدید و ذخیره"""
    try:
        minutes = int(update.message.text.strip())
        if minutes < 1 or minutes > 30:
            raise ValueError
    except:
        await update.message.reply_text("❌ لطفاً یک عدد بین 1 تا 30 وارد کنید:")
        return ASK_PRE_EXPIRE_MINUTES
    
    db.update_test_reminder_settings(pre_expire_minutes=minutes)
    await update.message.reply_text(f"✅ زمان یادآوری به {minutes} دقیقه قبل از اتمام تغییر کرد.")
    keyboard = [[InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data="test_reminder_settings")]]
    await update.message.reply_text("⚙️ برای بازگشت به منوی تنظیمات، روی دکمه کلیک کنید.", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END


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


async def restart_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ فقط مالک ربات به این بخش دسترسی دارد.", reply_markup=get_back_button())
        return
    await query.edit_message_text("🔄 در حال ری‌استارت ربات... لطفاً چند لحظه صبر کنید.")
    
    # ری‌استارت سرویس systemd
    subprocess.Popen(["sudo", "systemctl", "restart", "telegram-bot.service"])
    
    # خروج از برنامه (ربات متوقف می‌شود و systemd آن را دوباره راه‌اندازی می‌کند)
    sys.exit(0)


async def check_test_reminders(context: ContextTypes.DEFAULT_TYPE):
    """بررسی تست‌ها و ارسال پیام‌های یادآوری (هر دقیقه اجرا می‌شود)"""
    settings = db.get_test_reminder_settings()
    if not settings.get('is_active', 1):
        return
    
    pre_minutes = settings.get('pre_expire_minutes', 5)
    message_text = settings.get('message_text', '')
    
    # پیام قبل از انقضا
    tests_pre = db.get_tests_needing_pre_reminder(pre_minutes)
    for test in tests_pre:
        user_id = test['user_id']
        # ارسال پیام یادآوری 5 دقیقه قبل
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"⏰ **تست رایگان شما در {pre_minutes} دقیقه دیگر به پایان می‌رسد!**\n\nبرای ادامه استفاده، یکی از پلن‌های ما را خریداری کنید.",
                parse_mode='Markdown'
            )
            db.mark_pre_reminder_sent(user_id)
        except Exception as e:
            logger.error(f"Pre-reminder failed for user {user_id}: {e}")
    
    # پیام پس از انقضا
    tests_expired = db.get_expired_tests_needing_reminder()
    for test in tests_expired:
        user_id = test['user_id']
        # ارسال پیام پس از اتمام تست با دکمه‌های خرید و شارژ
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 خرید پلن", callback_data="buy_plan")],
            [InlineKeyboardButton("💳 شارژ کیف پول", callback_data="charge_wallet")]
        ])
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=message_text,
                parse_mode='Markdown',
                reply_markup=keyboard if settings.get('include_buttons', 1) else None
            )
            db.mark_reminder_sent(user_id)
        except Exception as e:
            logger.error(f"Post-reminder failed for user {user_id}: {e}")


# ---------------BackUp-----------------

async def manual_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تهیه بک‌آپ دستی از دیتابیس و ارسال فایل به مالک"""
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ فقط مالک ربات به این بخش دسترسی دارد.", reply_markup=get_back_button())
        return
    
    await query.edit_message_text("⏳ در حال تهیه بک‌آپ از دیتابیس...")
    
    backup_file = db.create_backup()
    if backup_file:
        with open(backup_file, 'rb') as f:
            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=f,
                filename=f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                caption="📦 **بک‌آپ دیتابیس**\n\nتاریخ: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        import os
        os.remove(backup_file)
        await query.edit_message_text("✅ بک‌آپ با موفقیت ارسال شد.")
    else:
        await query.edit_message_text("❌ خطا در تهیه بک‌آپ!")



# ==================== REFERRAL SYSTEM ====================

async def referral_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش منوی رفرال و اطلاعات دعوت"""
    try:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        
        user = db.get_user(user_id)
        if not user.get('referral_code'):
            db.generate_unique_referral_code(user_id)
            user = db.get_user(user_id)
        
        referral_code = user.get('referral_code')
        stats = db.get_referral_stats(user_id)
        settings = db.get_referral_settings()
        
        text = f"🔗 **سیستم دعوت از دوستان**\n\n"
        text += f"لینک دعوت شما:\n`https://t.me/{context.bot.username}?start={referral_code}`\n\n"
        text += f"🎁 **پاداش‌ها:**\n"
        text += f"• به ازای هر دوست دعوت شده: {settings.get('signup_bonus_referrer', 0):,} تومان\n"
        text += f"• دوست شما نیز {settings.get('signup_bonus_referred', 0):,} تومان هدیه می‌گیرد\n"
        text += f"• از هر خرید دوستتان، {settings.get('purchase_percent', 5)}% به حساب شما واریز می‌شود\n\n"
        text += f"📊 **آمار شما:**\n"
        text += f"👥 تعداد دعوت‌ها: {stats['signups']}\n"
        text += f"💰 درآمد از رفرال: {stats['earnings']:,} تومان\n"
        
        keyboard = [
            [InlineKeyboardButton("📋 لینک دعوت من", callback_data="my_referral_link")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
        ]
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        logger.error(f"Error in referral_menu: {e}")
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ خطا در نمایش منوی دعوت. لطفاً دوباره تلاش کنید.")

async def my_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لینک دعوت به صورت کپی‌شونده"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user = db.get_user(user_id)
    referral_code = user.get('referral_code')
    if not referral_code:
        referral_code = db.generate_unique_referral_code(user_id)
    
    text = f"🔗 **لینک دعوت شما**\n\n"
    text += f"`https://t.me/{context.bot.username}?start={referral_code}`\n\n"
    text += f"این لینک را برای دوستان خود بفرستید.\n"
    text += f"به ازای هر ثبت‌نام، پاداش دریافت می‌کنید."
    keyboard = [[InlineKeyboardButton("🔙 بازگشت", callback_data="referral_menu")]]
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


# ==================== REFERRAL ADMIN PANEL (OWNER ONLY) ====================

async def referral_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش منوی مدیریت رفرال (فقط مالک)"""
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ فقط مالک ربات به این بخش دسترسی دارد.", reply_markup=get_back_button())
        return
    
    settings = db.get_referral_settings()
    status_text = "✅ فعال" if settings.get('is_active', 0) else "❌ غیرفعال"
    
    keyboard = [
        [InlineKeyboardButton(f"🔘 وضعیت: {status_text}", callback_data="referral_toggle_status")],
        [InlineKeyboardButton("💰 تغییر پاداش معرف", callback_data="ref_set_referrer_bonus")],
        [InlineKeyboardButton("🎁 تغییر پاداش معرفی‌شونده", callback_data="ref_set_referred_bonus")],
        [InlineKeyboardButton("📊 تغییر درصد پورسانت خرید", callback_data="ref_set_percent")],
        [InlineKeyboardButton("📅 تنظیم تاریخ شروع جشنواره", callback_data="ref_set_event_start")],
        [InlineKeyboardButton("📅 تنظیم تاریخ پایان جشنواره", callback_data="ref_set_event_end")],
        [InlineKeyboardButton("🔄 بازنشانی آمار رفرال", callback_data="referral_reset_stats")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
    ]
    
    text = f"🎁 **مدیریت سیستم رفرال**\n\n"
    text += f"📌 وضعیت: {status_text}\n"
    text += f"💰 پاداش معرف: {settings.get('signup_bonus_referrer', 0):,} تومان\n"
    text += f"🎁 پاداش معرفی‌شونده: {settings.get('signup_bonus_referred', 0):,} تومان\n"
    text += f"📊 درصد پورسانت خرید: {settings.get('purchase_percent', 5)}%\n"
    if settings.get('event_start_date'):
        text += f"📅 تاریخ شروع: {settings['event_start_date'][:16]}\n"
    if settings.get('event_end_date'):
        text += f"📅 تاریخ پایان: {settings['event_end_date'][:16]}\n"
    
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def referral_toggle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغییر وضعیت فعال/غیرفعال سیستم رفرال"""
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    
    settings = db.get_referral_settings()
    new_status = not settings.get('is_active', 0)
    db.update_referral_settings(is_active=new_status)
    await referral_admin_panel(update, context)

# ---------- تنظیم پاداش معرف (referrer) ----------
async def referral_set_bonus_referrer_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    await query.edit_message_text(
        "💰 **تغییر پاداش معرف**\n\nلطفاً مبلغ جدید را به تومان وارد کنید (عدد صحیح):\nمثال: `5000`",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data="referral_admin_panel")]])
    )
    return ASK_REFERRAL_BONUS_REFERRER

async def referral_set_bonus_referrer_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
        if amount < 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ لطفاً یک عدد صحیح نامنفی وارد کنید:")
        return ASK_REFERRAL_BONUS_REFERRER
    
    db.update_referral_settings(signup_bonus_referrer=amount)
    
    # ارسال یک پیام واحد با دکمه بازگشت
    keyboard = [[InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data="referral_admin_panel")]]
    await update.message.reply_text(
        f"✅ پاداش معرف به {amount:,} تومان تغییر کرد.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

# ---------- تنظیم پاداش معرفی‌شونده (referred) ----------
async def referral_set_bonus_referred_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    await query.edit_message_text(
        "🎁 **تغییر پاداش معرفی‌شونده**\n\nلطفاً مبلغ جدید را به تومان وارد کنید (عدد صحیح):\nمثال: `2000`",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data="referral_admin_panel")]])
    )
    return ASK_REFERRAL_BONUS_REFERRED

async def referral_set_bonus_referred_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
        if amount < 0:
            raise ValueError
    except:
        await update.message.reply_text("❌ لطفاً یک عدد صحیح نامنفی وارد کنید:")
        return ASK_REFERRAL_BONUS_REFERRED
    
    db.update_referral_settings(signup_bonus_referred=amount)
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data="referral_admin_panel")]]
    await update.message.reply_text(
        f"✅ پاداش معرفی‌شونده به {amount:,} تومان تغییر کرد.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

# ---------- تنظیم درصد پورسانت خرید ----------
async def referral_set_purchase_percent_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    await query.edit_message_text(
        "📊 **تغییر درصد پورسانت خرید**\n\nلطفاً درصد جدید (عدد بین 0 تا 100) را وارد کنید:\nمثال: `5`",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data="referral_admin_panel")]])
    )
    return ASK_REFERRAL_PURCHASE_PERCENT

async def referral_set_purchase_percent_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        percent = int(update.message.text.strip())
        if percent < 0 or percent > 100:
            raise ValueError
    except:
        await update.message.reply_text("❌ لطفاً یک عدد بین 0 تا 100 وارد کنید:")
        return ASK_REFERRAL_PURCHASE_PERCENT
    
    db.update_referral_settings(purchase_percent=percent)
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data="referral_admin_panel")]]
    await update.message.reply_text(
        f"✅ درصد پورسانت خرید به {percent}% تغییر کرد.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ConversationHandler.END

# ---------- تنظیم تاریخ شروع و پایان جشنواره ----------
async def referral_set_event_start_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    await query.edit_message_text(
        "📅 **تنظیم تاریخ شروع جشنواره**\n\nلطفاً تاریخ را به فرمت `YYYY-MM-DD HH:MM:SS` وارد کنید.\n"
        "مثال: `2025-01-01 00:00:00`\n\nبرای حذف محدودیت، عبارت `none` را وارد کنید.",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data="referral_admin_panel")]])
    )
    return ASK_REFERRAL_EVENT_START

async def referral_set_event_start_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == 'none':
        db.update_referral_settings(event_start_date=None)
        await update.message.reply_text("✅ محدودیت تاریخ شروع برداشته شد.")
    else:
        try:
            datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
            db.update_referral_settings(event_start_date=text)
            await update.message.reply_text(f"✅ تاریخ شروع به {text} تنظیم شد.")
        except ValueError:
            await update.message.reply_text("❌ فرمت تاریخ نامعتبر. لطفاً دوباره وارد کنید (مثال: 2025-01-01 00:00:00) یا none:")
            return ASK_REFERRAL_EVENT_START
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data="referral_admin_panel")]]
    await update.message.reply_text("برای بازگشت روی دکمه کلیک کنید.", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

async def referral_set_event_end_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    await query.edit_message_text(
        "📅 **تنظیم تاریخ پایان جشنواره**\n\nلطفاً تاریخ را به فرمت `YYYY-MM-DD HH:MM:SS` وارد کنید.\n"
        "مثال: `2025-01-01 00:00:00`\n\nبرای حذف محدودیت، عبارت `none` را وارد کنید.",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data="referral_admin_panel")]])
    )
    return ASK_REFERRAL_EVENT_END

async def referral_set_event_end_get(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() == 'none':
        db.update_referral_settings(event_end_date=None)
        await update.message.reply_text("✅ محدودیت تاریخ پایان برداشته شد.")
    else:
        try:
            datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
            db.update_referral_settings(event_end_date=text)
            await update.message.reply_text(f"✅ تاریخ پایان به {text} تنظیم شد.")
        except ValueError:
            await update.message.reply_text("❌ فرمت تاریخ نامعتبر. لطفاً دوباره وارد کنید (مثال: 2025-01-01 00:00:00) یا none:")
            return ASK_REFERRAL_EVENT_END
    
    keyboard = [[InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data="referral_admin_panel")]]
    await update.message.reply_text("برای بازگشت روی دکمه کلیک کنید.", reply_markup=InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END

# ---------- بازنشانی آمار رفرال ----------
async def referral_reset_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز")
        return
    db.reset_referral_stats()
    await query.edit_message_text("✅ آمار رفرال تمام کاربران با موفقیت بازنشانی شد.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="referral_admin_panel")]]))



# ==================== REFERRAL SETTINGS HELPERS ====================

async def ref_wait_for_input(update: Update, context: ContextTypes.DEFAULT_TYPE, setting_type: str, prompt: str):
    """تنظیم وضعیت انتظار برای دریافت ورودی از کاربر"""
    query = update.callback_query
    await query.answer()
    context.user_data['ref_setting_type'] = setting_type
    keyboard = [[InlineKeyboardButton("🔙 انصراف", callback_data="referral_admin_panel")]]
    await query.edit_message_text(prompt, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def ref_set_referrer_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ref_wait_for_input(update, context, 'referrer_bonus', 
        "💰 **تغییر پاداش معرف**\n\nلطفاً مبلغ جدید را به تومان وارد کنید (عدد صحیح):\nمثال: `5000`")

async def ref_set_referred_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ref_wait_for_input(update, context, 'referred_bonus',
        "🎁 **تغییر پاداش معرفی‌شونده**\n\nلطفاً مبلغ جدید را به تومان وارد کنید (عدد صحیح):\nمثال: `2000`")

async def ref_set_percent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ref_wait_for_input(update, context, 'purchase_percent',
        "📊 **تغییر درصد پورسانت خرید**\n\nلطفاً درصد جدید (عدد بین 0 تا 100) را وارد کنید:\nمثال: `5`")

async def ref_set_event_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ref_wait_for_input(update, context, 'event_start',
        "📅 **تنظیم تاریخ شروع جشنواره**\n\nلطفاً تاریخ را به فرمت `YYYY-MM-DD HH:MM:SS` وارد کنید.\n"
        "مثال: `2025-01-01 00:00:00`\n\nبرای حذف محدودیت، عبارت `none` را وارد کنید.")

async def ref_set_event_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await ref_wait_for_input(update, context, 'event_end',
        "📅 **تنظیم تاریخ پایان جشنواره**\n\nلطفاً تاریخ را به فرمت `YYYY-MM-DD HH:MM:SS` وارد کنید.\n"
        "مثال: `2025-01-01 00:00:00`\n\nبرای حذف محدودیت، عبارت `none` را وارد کنید.")


async def handle_ref_setting_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هندلر عمومی برای دریافت ورودی تنظیمات رفرال"""
    setting_type = context.user_data.get('ref_setting_type')
    if not setting_type:
        return  # در حالت انتظار نیستیم
    
    text = update.message.text.strip()
    success = False
    reply_text = ""
    
    try:
        if setting_type == 'referrer_bonus':
            amount = int(text)
            if amount < 0: raise ValueError
            db.update_referral_settings(signup_bonus_referrer=amount)
            reply_text = f"✅ پاداش معرف به {amount:,} تومان تغییر کرد."
            success = True
        
        elif setting_type == 'referred_bonus':
            amount = int(text)
            if amount < 0: raise ValueError
            db.update_referral_settings(signup_bonus_referred=amount)
            reply_text = f"✅ پاداش معرفی‌شونده به {amount:,} تومان تغییر کرد."
            success = True
        
        elif setting_type == 'purchase_percent':
            percent = int(text)
            if percent < 0 or percent > 100: raise ValueError
            db.update_referral_settings(purchase_percent=percent)
            reply_text = f"✅ درصد پورسانت خرید به {percent}% تغییر کرد."
            success = True
        
        elif setting_type == 'event_start':
            if text.lower() == 'none':
                db.update_referral_settings(event_start_date=None)
                reply_text = "✅ محدودیت تاریخ شروع برداشته شد."
                success = True
            else:
                datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
                db.update_referral_settings(event_start_date=text)
                reply_text = f"✅ تاریخ شروع به {text} تنظیم شد."
                success = True
        
        elif setting_type == 'event_end':
            if text.lower() == 'none':
                db.update_referral_settings(event_end_date=None)
                reply_text = "✅ محدودیت تاریخ پایان برداشته شد."
                success = True
            else:
                datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
                db.update_referral_settings(event_end_date=text)
                reply_text = f"✅ تاریخ پایان به {text} تنظیم شد."
                success = True
        
    except ValueError:
        await update.message.reply_text("❌ مقدار نامعتبر. لطفاً دوباره تلاش کنید یا /cancel")
        return
    
    if success:
        # پاک کردن وضعیت انتظار
        context.user_data.pop('ref_setting_type', None)
        keyboard = [[InlineKeyboardButton("🔙 بازگشت به تنظیمات", callback_data="referral_admin_panel")]]
        await update.message.reply_text(reply_text, reply_markup=InlineKeyboardMarkup(keyboard))

# ==================== EXPORT REFERRAL REPORT (OWNER ONLY) ====================

async def export_referral_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export all referral logs to Excel file (owner only)"""
    query = update.callback_query
    await query.answer()
    
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ فقط مالک ربات به این بخش دسترسی دارد.", reply_markup=get_back_button())
        return
    
    await query.edit_message_text("⏳ در حال تولید فایل اکسل گزارش رفرال... لطفاً صبر کنید.")
    
    try:
        file_path = db.export_referral_logs_to_excel()
        with open(file_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=f,
                filename=f"referral_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                caption="📊 **گزارش کامل رفرال‌ها**\n\nتاریخ: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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



# ==================== ACCOUNTING ====================
async def accounting_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش خلاصه حسابداری (فقط مالک) با احتساب پاداش‌ها"""
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ فقط مالک ربات به این بخش دسترسی دارد.", reply_markup=get_back_button())
        return
    
    summary = db.get_accounting_summary()
    
    text = f"📊 **گزارش حسابداری جامع**\n\n"
    text += f"💰 **کل فروش پلن‌ها:** {summary['total_sales']:,} تومان\n"
    text += f"🏭 **هزینه پنل (بدهی به صاحب پنل):** {summary['total_panel_cost']:,} تومان\n"
    text += f"🎁 **کل پاداش‌های رفرال پرداختی:** {summary['total_referral_payout']:,} تومان\n"
    text += f"📥 **کل واریزهای نقدی کاربران:** {summary['total_deposits']:,} تومان\n"
    text += f"💼 **موجودی فعلی کیف پول کاربران:** {summary['current_wallet_balance']:,} تومان\n\n"
    text += f"📈 **سود خالص واقعی شما:** {summary['real_net_profit']:,} تومان\n"
    text += f"🔹 *سود خالص = فروش - هزینه پنل - پاداش رفرال*\n\n"
    text += f"⚠️ **توصیه:** حداقل {summary['total_panel_cost']:,} تومان را برای پرداخت به صاحب پنل نگه دارید.\n"
    text += f"🧾 **موجودی قابل برداشت (با احتیاط):** {summary['current_wallet_balance'] - summary['total_panel_cost']:,} تومان"
    
    keyboard = [
        [InlineKeyboardButton("📥 خروجی اکسل فروش", callback_data="export_accounting_excel")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
    ]
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

async def export_accounting_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """خروجی اکسل از تمام فروش‌ها (فقط مالک)"""
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ فقط مالک ربات به این بخش دسترسی دارد.", reply_markup=get_back_button())
        return
    
    await query.edit_message_text("⏳ در حال تولید فایل اکسل حسابداری...")
    try:
        file_path = db.export_accounting_to_excel()
        with open(file_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=f,
                filename=f"accounting_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                caption="📊 **گزارش کامل حسابداری**"
            )
        import os
        os.remove(file_path)
    except Exception as e:
        logger.error(f"Excel export error: {e}")
        await query.edit_message_text("❌ خطا در تولید فایل اکسل.")
        return
    
    owner = is_owner(query.from_user.id)
    await context.bot.send_message(chat_id=query.from_user.id, text="⚙️ **پنل مدیریت**", parse_mode='Markdown', reply_markup=get_admin_panel_keyboard(owner))

async def export_users_excel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export all users to Excel (owner only)"""
    query = update.callback_query
    await query.answer()
    if not is_owner(query.from_user.id):
        await query.edit_message_text("❌ فقط مالک ربات به این بخش دسترسی دارد.", reply_markup=get_back_button())
        return
    
    await query.edit_message_text("⏳ در حال تولید فایل اکسل کاربران...")
    try:
        file_path = db.export_users_to_excel()
        with open(file_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=query.from_user.id,
                document=f,
                filename=f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                caption="📊 **لیست کامل کاربران**\n\nتاریخ: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        import os
        os.remove(file_path)
    except Exception as e:
        logger.error(f"Excel export error: {e}")
        await query.edit_message_text("❌ خطا در تولید فایل اکسل.", reply_markup=get_back_button())
        return
    
    # بازگشت به لیست کاربران (با حفظ صفحه جاری)
    await admin_list_users(update, context)

# ==================== BROADCAST SYSTEM (ADMINS + OWNER) ====================

async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش منوی ارسال پیام همگانی (فقط ادمین‌ها)"""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ دسترسی غیرمجاز", reply_markup=get_back_button())
        return
    
    settings = db.get_broadcast_settings()
    admin_id = query.from_user.id
    is_owner_flag = is_owner(admin_id)
    
    # بررسی محدودیت‌ها برای ادمین معمولی
    if not is_owner_flag:
        # تعداد امروز
        today_count = db.get_admin_broadcast_today_count(admin_id)
        if today_count >= settings['daily_limit']:
            await query.edit_message_text(
                f"❌ شما امروز {today_count} بار از سقف مجاز ({settings['daily_limit']}) استفاده کرده‌اید.\nلطفاً فردا تلاش کنید.",
                reply_markup=get_back_button()
            )
            return
        # cooldown
        last_time = db.get_last_broadcast_time(admin_id)
        if last_time:
            cooldown_seconds = settings['cooldown_minutes'] * 60
            elapsed = (datetime.now() - last_time).total_seconds()
            if elapsed < cooldown_seconds:
                remaining = int(cooldown_seconds - elapsed)
                await query.edit_message_text(
                    f"❌ لطفاً {remaining} ثانیه صبر کنید تا دوباره بتوانید پیام همگانی بفرستید.",
                    reply_markup=get_back_button()
                )
                return
    
    keyboard = [
        [InlineKeyboardButton("📝 ارسال متن", callback_data="broadcast_type_text")],
        [InlineKeyboardButton("🖼 ارسال عکس", callback_data="broadcast_type_photo")],
        [InlineKeyboardButton("🎥 ارسال ویدئو", callback_data="broadcast_type_video")],
        [InlineKeyboardButton("📎 ارسال فایل", callback_data="broadcast_type_document")],
        [InlineKeyboardButton("🎤 ارسال ویس", callback_data="broadcast_type_voice")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
    ]
    await query.edit_message_text(
        "📢 **ارسال پیام همگانی**\n\nنوع پیام مورد نظر را انتخاب کنید:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return

# ---------- انتخاب نوع پیام ----------
async def broadcast_type_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    msg_type = query.data.split('_')[2]  # text, photo, video, document, voice
    context.user_data['broadcast_type'] = msg_type
    context.user_data['broadcast_caption'] = None
    
    if msg_type == 'text':
        await query.edit_message_text(
            "✏️ **ارسال متن همگانی**\n\nمتن خود را ارسال کنید:",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data="broadcast_menu")]])
        )
        return ASK_BROADCAST_CONTENT
    else:
        # برای عکس، ویدئو، فایل، ویس
        prompt = {
            'photo': '🖼 **ارسال عکس همگانی**\n\nلطفاً عکس را ارسال کنید.\nبعد از عکس می‌توانید کپشن (اختیاری) نیز بفرستید.',
            'video': '🎥 **ارسال ویدئو همگانی**\n\nلطفاً ویدئو را ارسال کنید.\nبعد از ویدئو می‌توانید کپشن (اختیاری) نیز بفرستید.',
            'document': '📎 **ارسال فایل همگانی**\n\nلطفاً فایل را ارسال کنید.\nبعد از فایل می‌توانید کپشن (اختیاری) نیز بفرستید.',
            'voice': '🎤 **ارسال ویس همگانی**\n\nلطفاً ویس را ارسال کنید.\n(ویس کپشن ندارد)'
        }
        await query.edit_message_text(
            prompt.get(msg_type, 'لطفاً محتوا را ارسال کنید.'),
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 انصراف", callback_data="broadcast_menu")]])
        )
        return ASK_BROADCAST_CONTENT

# ---------- دریافت محتوا (متن یا فایل) ----------

async def broadcast_filter_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    filter_type = query.data.split('_')[2]  # all, tested, buyers, active_7d
    context.user_data['broadcast_filter'] = filter_type
    
    target_count = db.get_target_users_count(filter_type)
    if target_count == 0:
        await query.edit_message_text("❌ هیچ کاربری در این گروه وجود ندارد.\nلطفاً گروه دیگری را انتخاب کنید.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="broadcast_menu")]]))
        return
    
    context.user_data['broadcast_target_count'] = target_count
    keyboard = [
        [InlineKeyboardButton("✅ بله، ارسال شود", callback_data="broadcast_confirm_yes")],
        [InlineKeyboardButton("❌ خیر، لغو", callback_data="broadcast_menu")]
    ]
    await query.edit_message_text(
        f"📢 **تأیید نهایی**\n\n"
        f"نوع پیام: {context.user_data['broadcast_type']}\n"
        f"تعداد گیرندگان: {target_count} نفر\n\n"
        f"آیا برای ارسال اطمینان دارید؟",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ASK_BROADCAST_CONFIRM

async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = query.from_user.id
    admin_username = query.from_user.username
    msg_type = context.user_data['broadcast_type']
    content = context.user_data['broadcast_content']
    caption = context.user_data.get('broadcast_caption')
    target_filter = context.user_data['broadcast_filter']
    target_count = context.user_data['broadcast_target_count']
    
    # ثبت لاگ
    broadcast_id = db.log_broadcast(admin_id, admin_username, msg_type, content, caption, target_filter)
    
    # شروع ارسال در پس‌زمینه (برای جلوگیری از timeout)
    context.application.create_task(
        send_broadcast_messages(context.application, broadcast_id, admin_id, msg_type, content, caption, target_filter, target_count, query.message.chat_id)
    )
    
    await query.edit_message_text(
        f"⏳ ارسال پیام همگانی به {target_count} کاربر آغاز شد.\n"
        f"شما پس از اتمام، نتیجه را دریافت خواهید کرد.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_panel")]])
    )
    return ConversationHandler.END

async def send_broadcast_messages(app, broadcast_id, admin_id, msg_type, content, caption, target_filter, target_count, report_chat_id):
    """ارسال تدریجی پیام‌ها با تأخیر (برای جلوگیری از محدودیت)"""
    success = 0
    failed = 0
    users = db.get_target_users(target_filter)
    total = len(users)
    
    for idx, user_id in enumerate(users, 1):
        try:
            if msg_type == 'text':
                await app.bot.send_message(chat_id=user_id, text=content, parse_mode='Markdown')
            elif msg_type == 'photo':
                await app.bot.send_photo(chat_id=user_id, photo=content, caption=caption, parse_mode='Markdown')
            elif msg_type == 'video':
                await app.bot.send_video(chat_id=user_id, video=content, caption=caption, parse_mode='Markdown')
            elif msg_type == 'document':
                await app.bot.send_document(chat_id=user_id, document=content, caption=caption, parse_mode='Markdown')
            elif msg_type == 'voice':
                await app.bot.send_voice(chat_id=user_id, voice=content)
            success += 1
        except Exception as e:
            logger.error(f"Broadcast failed for user {user_id}: {e}")
            failed += 1
        
        # تأخیر 0.5 ثانیه بین هر پیام برای جلوگیری از محدودیت
        if idx % 20 == 0:
            await asyncio.sleep(1)
        else:
            await asyncio.sleep(0.3)
    
    db.update_broadcast_stats(broadcast_id, total, success, failed, 'completed')
    await app.bot.send_message(
        chat_id=report_chat_id,
        text=f"✅ **ارسال پیام همگانی پایان یافت.**\n\n"
             f"👥 تعداد کل: {total}\n"
             f"✅ موفق: {success}\n"
             f"❌ ناموفق: {failed}\n"
             f"🆔 شماره درخواست: {broadcast_id}",
        parse_mode='Markdown'
    )

async def broadcast_get_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت محتوا (متن یا فایل) برای ارسال همگانی"""
    msg_type = context.user_data.get('broadcast_type')
    if msg_type == 'text':
        text = update.message.text
        if not text:
            await update.message.reply_text("❌ متن نمی‌تواند خالی باشد. دوباره ارسال کنید.")
            return ASK_BROADCAST_CONTENT
        context.user_data['broadcast_content'] = text
        context.user_data['broadcast_caption'] = None
    else:
        # دریافت فایل
        file_id = None
        if msg_type == 'photo' and update.message.photo:
            file_id = update.message.photo[-1].file_id
        elif msg_type == 'video' and update.message.video:
            file_id = update.message.video.file_id
        elif msg_type == 'document' and update.message.document:
            file_id = update.message.document.file_id
        elif msg_type == 'voice' and update.message.voice:
            file_id = update.message.voice.file_id
        else:
            await update.message.reply_text("❌ نوع فایل ارسالی با نوع انتخابی همخوانی ندارد. دوباره تلاش کنید.")
            return ASK_BROADCAST_CONTENT
        
        context.user_data['broadcast_content'] = file_id
        if msg_type != 'voice' and update.message.caption:
            context.user_data['broadcast_caption'] = update.message.caption
        else:
            context.user_data['broadcast_caption'] = None
    
    # --- بعد از دریافت محتوا، کیبورد فیلتر را نمایش بده و به حالت بعدی برو ---
    keyboard = [
        [InlineKeyboardButton("👥 همه کاربران", callback_data="broadcast_filter_all")],
        [InlineKeyboardButton("🎁 کاربران تست‌دهنده", callback_data="broadcast_filter_tested")],
        [InlineKeyboardButton("🛒 کاربران خریدار", callback_data="broadcast_filter_buyers")],
        [InlineKeyboardButton("📆 کاربران فعال (۷ روز اخیر)", callback_data="broadcast_filter_active_7d")],
        [InlineKeyboardButton("🔙 انصراف", callback_data="broadcast_menu")]
    ]
    await update.message.reply_text(
        "📊 **انتخاب مخاطبان**\n\nلطفاً گروه هدف خود را انتخاب کنید:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ASK_BROADCAST_FILTER
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
        allow_reentry=True,
    )
    charge_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_charge_by_id_start, pattern="^charge_by_id$"), CallbackQueryHandler(admin_charge_by_username_start, pattern="^charge_by_username$")],
        states={ASK_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, manual_charge_get_user)], ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_charge_get_amount)]},
        fallbacks=[CommandHandler("cancel", manual_charge_cancel)],
        allow_reentry=True,
        
    )
    test_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_test_by_id_start, pattern="^admin_test_by_id$"), CallbackQueryHandler(admin_test_by_username_start, pattern="^admin_test_by_username$")],
        states={ASK_TEST_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_test_get_user)]},
        fallbacks=[CommandHandler("cancel", manual_charge_cancel)],
        allow_reentry=True,
        
    )
    payment_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(rial_payment_start, pattern="^rial_payment$")],
        states={ASK_PAYMENT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, rial_payment_get_amount)]},
        fallbacks=[CommandHandler("cancel", manual_charge_cancel)],
        allow_reentry=True,
        
    )
    reject_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(reject_payment, pattern="^reject_payment_\\d+$")],
        states={ASK_REJECT_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reject_reason), CallbackQueryHandler(cancel_reject_callback, pattern="^cancel_reject$")]},
        fallbacks=[CommandHandler("cancel", manual_charge_cancel)],
        allow_reentry=True,
        
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
        allow_reentry=True,
        
    )
    add_admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_admin_start, pattern="^add_admin$")],
        states={ASK_ADMIN_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_get_user)]},
        fallbacks=[CommandHandler("cancel", manual_charge_cancel)],
        allow_reentry=True,
        
    )
    remove_admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(remove_admin_start, pattern="^remove_admin$")],
        states={ASK_REMOVE_ADMIN_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_admin_get_user)]},
        fallbacks=[CommandHandler("cancel", manual_charge_cancel)],
        allow_reentry=True,
        
    )
        # conversation: edit test reminder text
    edit_reminder_text_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_test_reminder_text_start, pattern="^edit_test_reminder_text$")],
        states={ASK_TEST_REMINDER_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_test_reminder_text_get)]},
        fallbacks=[CommandHandler("cancel", manual_charge_cancel)],
        allow_reentry=True
    )
    # conversation: edit pre-expire minutes
    edit_pre_expire_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_pre_expire_minutes_start, pattern="^edit_pre_expire_minutes$")],
        states={ASK_PRE_EXPIRE_MINUTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_pre_expire_minutes_get)]},
        fallbacks=[CommandHandler("cancel", manual_charge_cancel)],
        allow_reentry=True
    )
        # conversation: broadcast
    broadcast_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_type_handler, pattern="^broadcast_type_")],
        states={
            ASK_BROADCAST_CONTENT: [MessageHandler(filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL | filters.Voice.ALL, broadcast_get_content)],
            ASK_BROADCAST_FILTER: [CallbackQueryHandler(broadcast_filter_handler, pattern="^broadcast_filter_")],
            ASK_BROADCAST_CONFIRM: [CallbackQueryHandler(broadcast_confirm, pattern="^broadcast_confirm_yes$")],
        },
        fallbacks=[CommandHandler("cancel", manual_charge_cancel)],
        allow_reentry=True,
        per_message=True
    )


    app.add_handler(broadcast_conv)
    app.add_handler(CallbackQueryHandler(broadcast_menu, pattern="^broadcast_menu$"))

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
    app.add_handler(edit_reminder_text_conv)
    app.add_handler(edit_pre_expire_conv)
    app.add_handler(CallbackQueryHandler(test_reminder_settings_menu, pattern="^test_reminder_settings$"))
    app.add_handler(CallbackQueryHandler(toggle_test_reminder, pattern="^toggle_test_reminder$"))
    app.add_handler(CommandHandler("addadmin", add_admin_start))
    app.add_handler(CommandHandler("addplan", add_plan_start))
    app.add_handler(CallbackQueryHandler(restart_bot, pattern="^restart_bot$"))
    app.add_handler(CallbackQueryHandler(manual_backup, pattern="^manual_backup$"))

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

    app.add_handler(CallbackQueryHandler(users_pagination, pattern="^users_page_\\d+$"))
    app.add_handler(CallbackQueryHandler(export_users_excel, pattern="^export_users_excel$"))
    

    #Refferal-handlers
    app.add_handler(CallbackQueryHandler(ref_set_referrer_bonus, pattern="^ref_set_referrer_bonus$"))
    app.add_handler(CallbackQueryHandler(ref_set_referred_bonus, pattern="^ref_set_referred_bonus$"))
    app.add_handler(CallbackQueryHandler(ref_set_percent, pattern="^ref_set_percent$"))
    app.add_handler(CallbackQueryHandler(ref_set_event_start, pattern="^ref_set_event_start$"))
    app.add_handler(CallbackQueryHandler(ref_set_event_end, pattern="^ref_set_event_end$"))

    app.add_handler(CallbackQueryHandler(referral_admin_panel, pattern="^referral_admin_panel$"))
    app.add_handler(CallbackQueryHandler(referral_toggle_status, pattern="^referral_toggle_status$"))
    app.add_handler(CallbackQueryHandler(referral_reset_stats, pattern="^referral_reset_stats$"))
    app.add_handler(CallbackQueryHandler(referral_menu, pattern="^referral_menu$"))
    app.add_handler(CallbackQueryHandler(my_referral_link, pattern="^my_referral_link$"))

    app.add_handler(CallbackQueryHandler(export_referral_report, pattern="^export_referral_report$"))

    # Accounting handlers
    app.add_handler(CallbackQueryHandler(accounting_report, pattern="^accounting_report$"))
    app.add_handler(CallbackQueryHandler(export_accounting_excel, pattern="^export_accounting_excel$"))

        # هندلر عمومی برای ورودی تنظیمات رفرال (عدد و تاریخ)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ref_setting_input), group=1)
    
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_receipt))
    
        # راه‌اندازی JobQueue برای یادآوری تست
    if app.job_queue:
        app.job_queue.run_repeating(check_test_reminders, interval=60, first=10)
    else:
        logger.warning("JobQueue not available! Test reminders will not work.")

    print("🤖 ربات با موفقیت روشن شد...")
    app.run_polling()

if __name__ == "__main__":
    main()