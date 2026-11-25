# SQLite持久化层，Python内置无需额外依赖，解决并发、数据共享、重启丢失问题
import sqlite3
import os
from datetime import datetime
from config import DATA_DIR, WORK_ORDER_PREFIX

DB_PATH = os.path.join(DATA_DIR, "repair_orders.db")
# 演示用调度员口令，可自行修改
DISPATCHER_PASSWORD = "hdu123456"

def get_conn():
    """获取数据库连接，开启行工厂"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """初始化数据库表结构，首次启动自动执行"""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS work_orders (
        work_order_id TEXT PRIMARY KEY,
        create_time TEXT NOT NULL,
        building TEXT,
        room TEXT,
        fault_type TEXT NOT NULL,
        ai_urgency TEXT,
        final_urgency TEXT NOT NULL,
        post_upgrade INTEGER DEFAULT 0,
        appointment_date TEXT NOT NULL,
        appointment_slot TEXT NOT NULL,
        appointment_note TEXT,
        worker_name TEXT,
        worker_phone TEXT,
        chat_record TEXT,
        confirm_note TEXT,
        upgrade_reason TEXT,
        upgrade_reply TEXT,
        raw_report TEXT NOT NULL,
        status TEXT NOT NULL,
        satisfaction INTEGER,
        evaluation TEXT,
        is_demo INTEGER DEFAULT 0
    )
    ''')
    conn.commit()
    # 首次启动自动加载演示数据
    count = cursor.execute("SELECT COUNT(*) FROM work_orders").fetchone()[0]
    if count == 0:
        seed_demo_data()
    conn.close()

def generate_work_order_id():
    """事务生成递增不重复工单号，解决并发重复问题"""
    today_str = datetime.now().strftime("%Y%m%d")
    prefix = f"{WORK_ORDER_PREFIX}{today_str}"
    conn = get_conn()
    cursor = conn.cursor()
    # 加事务锁，避免并发重复
    cursor.execute("BEGIN IMMEDIATE")
    rows = cursor.execute(
        "SELECT work_order_id FROM work_orders WHERE work_order_id LIKE ?",
        (f"{prefix}%",)
    ).fetchall()
    max_serial = 0
    for row in rows:
        try:
            serial = int(row["work_order_id"][len(prefix):])
            if serial > max_serial:
                max_serial = serial
        except ValueError:
            continue
    new_id = f"{prefix}{max_serial + 1:03d}"
    conn.commit()
    conn.close()
    return new_id

def insert_order(order_data):
    """插入新工单"""
    conn = get_conn()
    conn.execute('''
    INSERT INTO work_orders (
        work_order_id, create_time, building, room, fault_type, ai_urgency,
        final_urgency, post_upgrade, appointment_date, appointment_slot,
        appointment_note, worker_name, worker_phone, chat_record, confirm_note,
        upgrade_reason, upgrade_reply, raw_report, status, satisfaction, evaluation, is_demo
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0)
    ''', (
        order_data["work_order_id"],
        order_data["create_time"],
        str(order_data["building"]) if order_data["building"] else "",
        order_data["room"] or "",
        order_data["fault_type"],
        order_data["ai_urgency"],
        order_data["final_urgency"],
        1 if order_data["post_upgrade"] else 0,
        order_data["appointment_date"],
        order_data["appointment_slot"],
        order_data["appointment_note"] or "",
        order_data["worker_name"] or "",
        order_data["worker_phone"] or "",
        order_data["chat_record"] or "",
        order_data["confirm_note"] or "",
        order_data["upgrade_reason"] or "",
        order_data["upgrade_reply"] or "",
        order_data["raw_report"],
        order_data["status"],
        0
    ))
    conn.commit()
    conn.close()

def update_dispatch(order_id, final_urgency, worker_name, worker_phone,
                    chat_record, confirm_note, upgrade_reply):
    """调度员确认派单更新"""
    conn = get_conn()
    is_upgrade = conn.execute(
        "SELECT post_upgrade FROM work_orders WHERE work_order_id=?", (order_id,)
    ).fetchone()["post_upgrade"]
    new_status = "加急工单已优先派单，等待上门" if is_upgrade else "已派单，等待上门"
    conn.execute('''
    UPDATE work_orders
    SET final_urgency=?, worker_name=?, worker_phone=?, chat_record=?,
        confirm_note=?, upgrade_reply=?, status=?
    WHERE work_order_id=?
    ''', (final_urgency, worker_name, worker_phone, chat_record,
          confirm_note, upgrade_reply, new_status, order_id))
    conn.commit()
    conn.close()

def cancel_order(order_id):
    """学生取消工单"""
    conn = get_conn()
    conn.execute("UPDATE work_orders SET status=? WHERE work_order_id=?",
                 ("已取消", order_id))
    conn.commit()
    conn.close()

def submit_evaluation(order_id, score, text):
    """提交满意度评价"""
    conn = get_conn()
    conn.execute('''
    UPDATE work_orders SET satisfaction=?, evaluation=?, status=?
    WHERE work_order_id=?
    ''', (score, text, "已完成，已评价", order_id))
    conn.commit()
    conn.close()

def query_order_by_id(order_id):
    """根据工单号查询"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM work_orders WHERE work_order_id=?",
                       (order_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def list_orders_by_status(status=None):
    """按状态列出工单，空则返回全部"""
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM work_orders WHERE status=? ORDER BY create_time DESC",
            (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM work_orders ORDER BY create_time DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def list_pending_orders():
    """列出所有待确认工单（调度工作台）"""
    conn = get_conn()
    rows = conn.execute('''
    SELECT * FROM work_orders
    WHERE status IN ("待确认", "待确认（加急复核中）")
    ORDER BY post_upgrade DESC, create_time ASC
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]

def reset_demo_data():
    """一键清空并重置为演示数据"""
    conn = get_conn()
    conn.execute("DELETE FROM work_orders")
    conn.commit()
    conn.close()
    seed_demo_data()

def seed_demo_data():
    """内置8条演示工单，覆盖所有状态和场景"""
    demo_orders = [
        {
            "work_order_id": f"{WORK_ORDER_PREFIX}{datetime.now().strftime('%Y%m%d')}001",
            "create_time": datetime.now().strftime("%Y-%m-%d 09:12:33"),
            "building": "3", "room": "412",
            "fault_type": "给排水类", "ai_urgency": "P1", "final_urgency": "P1",
            "post_upgrade": False,
            "appointment_date": datetime.now().strftime("%Y-%m-%d"),
            "appointment_slot": "14:00-18:00 下午时段",
            "appointment_note": "下午课后有人",
            "worker_name": "张师傅", "worker_phone": "138****1001",
            "chat_record": "已电话确认宿舍有人",
            "confirm_note": "按预约时间上门更换水龙头",
            "upgrade_reason": "", "upgrade_reply": "",
            "raw_report": "3号楼412水龙头滴水，关不紧",
            "status": "已派单，等待上门", "is_demo": 1
        },
        {
            "work_order_id": f"{WORK_ORDER_PREFIX}{datetime.now().strftime('%Y%m%d')}002",
            "create_time": datetime.now().strftime("%Y-%m-%d 10:05:21"),
            "building": "7", "room": "615",
            "fault_type": "水电类", "ai_urgency": "P0", "final_urgency": "P0",
            "post_upgrade": False,
            "appointment_date": datetime.now().strftime("%Y-%m-%d"),
            "appointment_slot": "当日无时间限制，随时可上门",
            "appointment_note": "",
            "worker_name": "李师傅", "worker_phone": "138****1002",
            "chat_record": "紧急工单，已通知学生断电",
            "confirm_note": "立刻上门排查插座烧焦问题",
            "upgrade_reason": "", "upgrade_reply": "",
            "raw_report": "7号楼615插座冒烟有焦味",
            "status": "加急工单已优先派单，等待上门", "is_demo": 1
        },
        {
            "work_order_id": f"{WORK_ORDER_PREFIX}{datetime.now().strftime('%Y%m%d')}003",
            "create_time": datetime.now().strftime("%Y-%m-%d 10:40:18"),
            "building": "5", "room": "",
            "fault_type": "公共设施类", "ai_urgency": "P0", "final_urgency": "P0",
            "post_upgrade": False,
            "appointment_date": datetime.now().strftime("%Y-%m-%d"),
            "appointment_slot": "当日无时间限制，随时可上门",
            "appointment_note": "",
            "worker_name": "王师傅", "worker_phone": "138****1008",
            "chat_record": "已联动安保安抚被困学生",
            "confirm_note": "立刻到场电梯救援",
            "upgrade_reason": "", "upgrade_reply": "",
            "raw_report": "5号楼电梯困人了",
            "status": "加急工单已优先派单，等待上门", "is_demo": 1
        },
        {
            "work_order_id": f"{WORK_ORDER_PREFIX}{datetime.now().strftime('%Y%m%d')}004",
            "create_time": datetime.now().strftime("%Y-%m-%d 11:22:05"),
            "building": "13", "room": "309",
            "fault_type": "消防安防类", "ai_urgency": "P0", "final_urgency": "P0",
            "post_upgrade": True,
            "appointment_date": datetime.now().strftime("%Y-%m-%d"),
            "appointment_slot": "19:00-21:30 晚间在宿舍时段",
            "appointment_note": "晚自习后有人",
            "worker_name": "郑师傅", "worker_phone": "138****1007",
            "chat_record": "学生申请加急，已核实报警器误报",
            "confirm_note": "晚间上门更换烟感电池",
            "upgrade_reason": "认为故障有安全隐患，要求加急",
            "upgrade_reply": "已核实情况，调整为P0加急，按你预约的晚间时段上门",
            "raw_report": "13号楼309烟雾报警器一直响",
            "status": "加急工单已优先派单，等待上门", "is_demo": 1
        },
        {
            "work_order_id": f"{WORK_ORDER_PREFIX}{datetime.now().strftime('%Y%m%d')}005",
            "create_time": datetime.now().strftime("%Y-%m-%d 12:15:44"),
            "building": "2", "room": "108",
            "fault_type": "门窗家具类", "ai_urgency": "P1", "final_urgency": "P1",
            "post_upgrade": False,
            "appointment_date": (datetime.now()).strftime("%Y-%m-%d"),
            "appointment_slot": "14:00-18:00 下午时段",
            "appointment_note": "",
            "worker_name": "", "worker_phone": "",
            "chat_record": "", "confirm_note": "",
            "upgrade_reason": "", "upgrade_reply": "",
            "raw_report": "2号楼108门锁打不开，钥匙断了",
            "status": "待确认", "is_demo": 1
        },
        {
            "work_order_id": f"{WORK_ORDER_PREFIX}{datetime.now().strftime('%Y%m%d')}006",
            "create_time": datetime.now().strftime("%Y-%m-%d 13:01:17"),
            "building": "8", "room": "307",
            "fault_type": "网络类", "ai_urgency": "P1", "final_urgency": "P1",
            "post_upgrade": False,
            "appointment_date": datetime.now().strftime("%Y-%m-%d"),
            "appointment_slot": "19:00-21:30 晚间在宿舍时段",
            "appointment_note": "",
            "worker_name": "", "worker_phone": "",
            "chat_record": "", "confirm_note": "",
            "upgrade_reason": "", "upgrade_reply": "",
            "raw_report": "8号楼307WiFi连不上，网口灯不亮",
            "status": "待确认", "is_demo": 1
        },
        {
            "work_order_id": f"{WORK_ORDER_PREFIX}{datetime.now().strftime('%Y%m%d')}007",
            "create_time": datetime.now().strftime("%Y-%m-%d 14:32:50"),
            "building": "12", "room": "401",
            "fault_type": "空调类", "ai_urgency": "P2", "final_urgency": "P2",
            "post_upgrade": False,
            "appointment_date": (datetime.now() + __import__('datetime').timedelta(days=2)).strftime("%Y-%m-%d"),
            "appointment_slot": "09:00-12:00 上午时段",
            "appointment_note": "周末有人",
            "worker_name": "周师傅", "worker_phone": "138****1006",
            "chat_record": "已确认不影响使用，排期2天后",
            "confirm_note": "上门加氟处理",
            "upgrade_reason": "", "upgrade_reply": "",
            "raw_report": "空调制冷效果有点差，偶尔不凉",
            "status": "已完成，已评价", "satisfaction": 5,
            "evaluation": "师傅很准时，处理完制冷正常了", "is_demo": 1
        },
        {
            "work_order_id": f"{WORK_ORDER_PREFIX}{datetime.now().strftime('%Y%m%d')}008",
            "create_time": datetime.now().strftime("%Y-%m-%d 15:20:02"),
            "building": "图书馆", "room": "",
            "fault_type": "水电类", "ai_urgency": "P1", "final_urgency": "P1",
            "post_upgrade": False,
            "appointment_date": datetime.now().strftime("%Y-%m-%d"),
            "appointment_slot": "当日无时间限制，随时可上门",
            "appointment_note": "",
            "worker_name": "李师傅", "worker_phone": "138****1002",
            "chat_record": "已联系图书馆管理员",
            "confirm_note": "更换三楼楼道照明",
            "upgrade_reason": "", "upgrade_reply": "",
            "raw_report": "图书馆3楼灯坏了",
            "status": "已完成", "is_demo": 1
        }
    ]
    conn = get_conn()
    for order in demo_orders:
        conn.execute('''
        INSERT INTO work_orders (
            work_order_id, create_time, building, room, fault_type, ai_urgency,
            final_urgency, post_upgrade, appointment_date, appointment_slot,
            appointment_note, worker_name, worker_phone, chat_record, confirm_note,
            upgrade_reason, upgrade_reply, raw_report, status, satisfaction, evaluation, is_demo
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            order["work_order_id"], order["create_time"], order["building"], order["room"],
            order["fault_type"], order["ai_urgency"], order["final_urgency"],
            1 if order["post_upgrade"] else 0, order["appointment_date"],
            order["appointment_slot"], order["appointment_note"], order["worker_name"],
            order["worker_phone"], order["chat_record"], order["confirm_note"],
            order["upgrade_reason"], order["upgrade_reply"], order["raw_report"],
            order["status"], order.get("satisfaction"), order.get("evaluation"), 1
        ))
    conn.commit()
    conn.close()

# 启动时自动初始化
init_db()
