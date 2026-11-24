# 模拟排班与备件库存数据
from datetime import datetime
import random
import os
from config import WORK_ORDER_PREFIX, DATA_DIR

# 维修人员排班表（模拟6名维修人员，覆盖不同技能）
WORKERS = [
    {
        "worker_id": "W001",
        "name": "张师傅",
        "skills": ["水管维修", "厨卫维修", "管道疏通", "防水抢修"],
        "phone": "138****1001",
        "available": True,
        "current_orders": 1,
        "max_orders": 3,
        "location": "12号楼",
        "work_area": "宿舍区"
    },
    {
        "worker_id": "W002",
        "name": "李师傅",
        "skills": ["水管维修", "防水抢修"],
        "phone": "138****1002",
        "available": True,
        "current_orders": 2,
        "max_orders": 3,
        "location": "8号楼",
        "work_area": "宿舍区"
    },
    {
        "worker_id": "W003",
        "name": "王师傅",
        "skills": ["电工维修", "电路检修", "配电检修"],
        "phone": "138****1003",
        "available": True,
        "current_orders": 0,
        "max_orders": 3,
        "location": "5号楼",
        "work_area": "宿舍区"
    },
    {
        "worker_id": "W004",
        "name": "赵师傅",
        "skills": ["电工维修", "电路抢修", "实验设备维修"],
        "phone": "138****1004",
        "available": False,  # 模拟当日已排满，用于无空闲异常分支
        "current_orders": 3,
        "max_orders": 3,
        "location": "教学区",
        "work_area": "教学区"
    },
    {
        "worker_id": "W005",
        "name": "陈师傅",
        "skills": ["门窗维修", "家具维修", "开锁维修"],
        "phone": "138****1005",
        "available": True,
        "current_orders": 1,
        "max_orders": 3,
        "location": "后勤大厅",
        "work_area": "全区"
    },
    {
        "worker_id": "W006",
        "name": "周师傅",
        "skills": ["空调维修", "电器维修", "网络运维"],
        "phone": "138****1006",
        "available": True,
        "current_orders": 1,
        "max_orders": 3,
        "location": "29号楼",
        "work_area": "宿舍区"
    },
    {
        "worker_id": "W007",
        "name": "郑师傅",
        "skills": ["消防维保", "安防运维", "电工维修"],
        "phone": "138****1007",
        "available": True,
        "current_orders": 0,
        "max_orders": 2,
        "location": "后勤大厅",
        "work_area": "全校区"
    },
    {
        "worker_id": "W008",
        "name": "王师傅",
        "skills": ["电梯维保", "公共设施维修", "家电维修"],
        "phone": "138****1008",
        "available": True,
        "current_orders": 1,
        "max_orders": 2,
        "location": "13号楼",
        "work_area": "宿舍区"
    }
]

# 模拟备件库存
INVENTORY = {
    "水龙头": 8,
    "阀芯": 12,
    "生料带": 20,
    "活动扳手": 5,
    "水管": 6,
    "密封圈": 15,
    "灯管": 10,
    "灯泡": 25,
    "插座面板": 7,
    "空气开关": 4,
    "测电笔": 6,
    "锁芯": 9,
    "门锁": 5,
    "合页": 11,
    "玻璃": 3,
    "水晶头": 30,
    "网线": 10,
    "制冷剂": 2,
    "电容": 6,
    "遥控器": 3,
    "保险丝": 8,
    "烟雾报警器": 4,
    "应急灯": 6,
    "门禁配件": 3,
    "电梯配件": 2,
    "饮水机滤芯": 5,
    # 模拟备件不足场景
    "备用阀芯": 0,
    "PPR水管": 1,
    "漏电保护器": 0,
    "消防专用电池": 0
}

def query_available_workers(required_skill, is_p0=False):
    """
    查询匹配技能的可用维修人员
    返回：(候选列表, 异常状态)
    """
    matched = []
    for worker in WORKERS:
        if required_skill in worker["skills"]:
            if is_p0:
                # P0工单只要没完全排满都可以接单
                if worker["current_orders"] < worker["max_orders"]:
                    matched.append(worker)
            else:
                if worker["available"] and worker["current_orders"] < worker["max_orders"]:
                    matched.append(worker)
    # 按当前工单数量升序，模拟距离/负载最优
    matched = sorted(matched, key=lambda x: x["current_orders"])
    if len(matched) == 0:
        return [], "no_available_worker"
    return matched[:3], None

def check_inventory(required_parts):
    """
    校验备件库存
    返回：(充足备件列表, 缺失备件列表)
    """
    sufficient = []
    missing = []
    for part in required_parts:
        stock = INVENTORY.get(part, 0)
        if stock > 0:
            sufficient.append({"part": part, "stock": stock})
        else:
            missing.append({"part": part, "stock": 0})
    return sufficient, missing

def generate_work_order_id():
    """生成工单号：HDU+年月日+3位流水号，自动读取台账递增，兼容首次运行"""
    date_str = datetime.now().strftime("%Y%m%d")
    max_serial = 0
    ledger_path = os.path.join(DATA_DIR, "工单台账.json")
    try:
        if os.path.exists(ledger_path):
            import json
            with open(ledger_path, "r", encoding="utf-8") as f:
                ledger = json.load(f)
            # 筛选当天工单，提取最大流水号
            for order in ledger:
                order_id = order.get("work_order_id", "")
                prefix = f"{WORK_ORDER_PREFIX}{date_str}"
                if order_id.startswith(prefix):
                    try:
                        serial_num = int(order_id[len(prefix):])
                        if serial_num > max_serial:
                            max_serial = serial_num
                    except ValueError:
                        continue
    except Exception:
        # 云端文件异常时兜底从1开始，不阻断提交
        max_serial = 0
    serial = max_serial + 1
    return f"{WORK_ORDER_PREFIX}{date_str}{serial:03d}"
