# 评审报告附录A 10条回归用例
from triage import triage

test_cases = [
    ("3号楼412水龙头一直漏水，地面有积水", "给排水类", "P1", "success"),
    ("图书馆3楼灯坏了", "水电类", "P1", "success"),
    ("1教A区501投影仪无法开机，上课急用", "多媒体设备类", "P1", "success"),
    ("2026年11月24日 3号楼漏水", "给排水类", "P1", "need_more_info"),
    ("5号楼302 插座冒烟 有焦味", "水电类", "P0", "success"),
    ("图书馆电梯困人了", "公共设施类", "P0", "success"),
    ("宿舍门锁打不开，钥匙断在里面", "门窗家具类", "P1", "need_more_info"),
    ("墙面有点脏，想申请粉刷", None, "P2", "need_more_info"),
    ("", "无文字仅图片", "P2", "need_more_info"),
    ("9号楼302 门锁坏了", "门窗家具类", "P1", "success"),
]

passed = 0
for idx, (text, exp_cat, exp_urg, exp_status) in enumerate(test_cases, 1):
    if idx == 9:
        # 模拟仅上传图片
        res = triage("", uploaded_image=True)
    else:
        res = triage(text)
    ok = True
    if res["status"] != exp_status:
        ok = False
    if exp_cat and res.get("fault_category_name") != exp_cat and exp_cat != "无文字仅图片":
        ok = False
    if res.get("urgency") != exp_urg and exp_status == "success":
        ok = False
    if ok:
        passed +=1
        print(f"[通过] 用例{idx}")
    else:
        print(f"[失败] 用例{idx}，实际状态{res['status']} 分类{res.get('fault_category_name')} 紧急度{res.get('urgency')}")
        print("追问：", res["followup_questions"])

print(f"\n回归测试完成：{passed}/{len(test_cases)} 条通过")
