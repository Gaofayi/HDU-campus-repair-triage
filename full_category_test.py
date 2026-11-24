# 全量8大类场景覆盖测试
from triage import triage

test_cases = [
    ("3号楼412水龙头一直漏水", "给排水类", "P0"),
    ("5号楼203马桶堵了水下不去", "给排水类", "P1"),
    ("13号楼309厕所灯不亮了", "水电类", "P1"),
    ("7号楼615插座焦味冒烟", "水电类", "P0"),
    ("2号楼108门锁打不开钥匙断了", "门窗家具类", "P1"),
    ("4号楼502衣柜柜门掉了", "门窗家具类", "P1"),
    ("8号楼307WiFi连不上没网", "网络类", "P1"),
    ("10号楼209网线断了频繁掉线", "网络类", "P1"),
    ("12号楼401空调不制冷不转", "空调类", "P1"),
    ("27号楼112吊扇坏了异响", "空调类", "P1"),
    ("11教实验室通风橱失效", "实验设备类", "P0"),
    ("图书馆显微镜开机报错", "实验设备类", "P1"),
    ("13号楼309烟雾报警器失灵", "消防安防类", "P0"),
    ("22号楼门禁坏了刷不开", "消防安防类", "P1"),
    ("3号楼楼道监控摄像头模糊", "消防安防类", "P2"),
    ("5号楼电梯困人了", "公共设施类", "P0"),
    ("3号楼公共洗衣机不转漏水", "公共设施类", "P1"),
    ("18号楼直饮水机不出水", "公共设施类", "P1"),
    ("29号楼楼道灯不亮", "公共设施类", "P1"),
]

passed = 0
failed = 0
for text, expect_cat, expect_urgency in test_cases:
    res = triage(text)
    if res["status"] == "success" and res["fault_category_name"] == expect_cat and res["urgency"] == expect_urgency:
        passed += 1
        print(f"[通过] {text}")
    else:
        failed += 1
        print(f"[失败] {text}，实际分类{res['fault_category_name']} 紧急度{res['urgency']} 状态{res['status']}")

print(f"\n全量场景测试完成：{passed}/{len(test_cases)} 条通过，失败{failed}条")
