import sqlite3

DB_NAME = 'pasarguard_data.db'

def add_past_sales():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # اطلاعات دو فروش
    sales_data = [
        {'user_id': 5362255830, 'username': 'radineshun', 'plan_id': 7, 'amount': 150000, 'traffic_gb': 10},
        {'user_id': 8276664099, 'username': 'sarelaccessories', 'plan_id': 7, 'amount': 150000, 'traffic_gb': 10}
    ]
    
    panel_cost_per_gb = 7000  # هزینه هر گیگ به صاحب پنل
    
    for sale in sales_data:
        user_id = sale['user_id']
        plan_id = sale['plan_id']
        amount = sale['amount']
        traffic_gb = sale['traffic_gb']
        
        # پیدا کردن order_id برای این کاربر و پلن (با فرض اینکه سفارش با status='completed' وجود دارد)
        cursor.execute('''
            SELECT id FROM orders 
            WHERE user_id = ? AND plan_id = ? AND amount = ? AND status = 'completed'
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id, plan_id, amount))
        order_row = cursor.fetchone()
        
        if not order_row:
            print(f"⚠️ سفارش تکمیل شده برای کاربر {user_id} (@{sale['username']}) یافت نشد. درج نمی‌شود.")
            continue
        
        order_id = order_row[0]
        
        # محاسبه هزینه پنل و سود خالص
        panel_cost = traffic_gb * panel_cost_per_gb
        referral_cost = 0  # در آن زمان رفرال نداشتیم
        net_profit = amount - panel_cost - referral_cost
        
        # بررسی اینکه آیا قبلاً این فروش در sales_logs ثبت شده است
        cursor.execute('SELECT 1 FROM sales_logs WHERE order_id = ?', (order_id,))
        if cursor.fetchone():
            print(f"ℹ️ فروش برای order_id {order_id} (کاربر {user_id}) قبلاً ثبت شده است.")
            continue
        
        # درج رکورد جدید
        cursor.execute('''
            INSERT INTO sales_logs 
            (order_id, user_id, plan_id, traffic_gb, user_price, panel_cost, referral_cost, net_profit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (order_id, user_id, plan_id, traffic_gb, amount, panel_cost, referral_cost, net_profit))
        
        print(f"✅ فروش برای کاربر {user_id} (@{sale['username']}) با order_id={order_id} اضافه شد.")
    
    conn.commit()
    conn.close()
    print("\n✅ عملیات به پایان رسید.")

if __name__ == '__main__':
    add_past_sales()