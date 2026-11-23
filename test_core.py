# 核心分诊逻辑测试脚本
from triage import triage

test_cases = [
    {
        "name": "P0给排水正常场景",
        "text": "3号楼412水龙头一直漏水，地面有积水，快泡到插座了",
        "expect_urgency": "P0",
        "expect_category": "给排水类"
    },
    {
        "name": "信息缺失场景",
        "text": "灯不亮了",
        "expect_status": "need_more_info"
    },
    {
        "name": "P0高风险焦味场景",
        "text": "5教203实验室有焦味，插座冒烟",
        "expect_urgency": "P0",
        "expect_category": "水电类"
    },
    {
        "name": "P1普通照明故障",
        "text": "7号楼209宿舍灯管不亮了，开关没问题",
        "expect_urgency": "P1",
        "expect_category": "水电类"
    },
    {
        "name": "P2轻微故障",
        "text": "12号楼306柜门有点轻微异响，合页有点松",
        "expect_urgency": "P2",
        "expect_category": "门窗家具类"
    }
]

if __name__ == "__main__":
    passed = 0
    for case in test_cases:
        res = triage(case["text"])
        ok = True
        if "expect_status" in case:
            ok = ok and res["status"] == case["expect_status"]
        if "expect_urgency" in case:
            ok = ok and res["urgency"] == case["expect_urgency"]
        if "expect_category" in case:
            ok = ok and res["fault_category_name"] == case["expect_category"]
        status = "通过" if ok else "失败"
        print(f"[{status}] {case['name']}")
        if not ok:
            print(f"  实际结果：status={res['status']}, urgency={res.get('urgency')}, category={res.get('fault_category_name')}")
        else:
            passed += 1
    print(f"\n核心测试完成：{passed}/{len(test_cases)} 条通过")
