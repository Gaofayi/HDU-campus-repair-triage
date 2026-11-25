# 核心分诊逻辑，修复所有已知算法缺陷
import re
from config import (FAULT_CATEGORIES, P0_KEYWORDS, CONFIDENCE_THRESHOLD,
                    P0_SECURITY_TIPS, BUILDINGS)

# 统一所有合法楼栋白名单，不再硬编码
ALL_VALID_BUILDINGS = (
    [str(x) for x in BUILDINGS["dormitory"]]
    + BUILDINGS["teaching"]
    + BUILDINGS["public"]
)

def extract_building_room(text):
    """
    修复楼栋覆盖、房号正则bug
    公共建筑优先，不被后续数字覆盖，房号不匹配年份/日期
    """
    building = None
    room = None
    # 1. 优先匹配公共建筑，匹配到后锁定，不被后续数字覆盖
    for pub in (BUILDINGS["teaching"] + BUILDINGS["public"]):
        if pub in text:
            building = pub
            break
    # 2. 未匹配到公共建筑时，匹配X教/数字号楼
    if building is None:
        teaching_match = re.search(r"(\d{1,2})\s*教", text)
        if teaching_match:
            building = f"{teaching_match.group(1)}教"
        building_match = re.search(r"(\d{1,2})\s*号?楼", text)
        if building_match:
            building = int(building_match.group(1))
    # 3. 修复房号正则：仅匹配楼栋后、带房间/室/号房标识，排除年份
    text_clean = re.sub(r"\d{4}年\d{1,2}月\d{1,2}日", "", text)
    room_match = re.search(r"(?:房间|室|号房|寝室)\s*(\d{3,4})", text_clean)
    if not room_match:
        room_match = re.search(r"(?:号楼|楼|教)\s*(\d{3,4})", text_clean)
    if room_match:
        room = room_match.group(1)
    return building, room

def detect_fault_category(text):
    """修复置信度计算，长词优先，多命中加分，单字专属词可达标"""
    category_scores = []
    for cat in FAULT_CATEGORIES:
        hit_count = 0
        hit_keywords = []
        total_weight = 0
        sorted_keywords = sorted(cat["keywords"], key=lambda x: len(x), reverse=True)
        for kw in sorted_keywords:
            if kw in text:
                hit_count += 1
                hit_keywords.append(kw)
                total_weight += 0.15 + len(kw) * 0.05
        if hit_count > 0:
            score = min(0.6 + total_weight, 0.98)
            category_scores.append({
                "category": cat,
                "score": score,
                "hit_keywords": hit_keywords
            })
    if not category_scores:
        # 兜底强特征匹配，新增多媒体类
        fallback_rules = [
            (["灯", "电", "插座", "开关", "跳闸"], "水电类"),
            (["水", "漏", "堵", "马桶", "滴水"], "给排水类"),
            (["门", "窗", "锁", "家具", "柜子"], "门窗家具类"),
            (["网", "wifi", "WiFi", "路由器"], "网络类"),
            (["空调", "风扇", "吊扇"], "空调类"),
            (["实验", "仪器", "试剂"], "实验设备类"),
            (["烟感", "消防", "报警器", "门禁", "监控"], "消防安防类"),
            (["电梯", "洗衣机", "饮水机", "开水器"], "公共设施类"),
            (["投影", "幕布", "音响", "麦克风", "多媒体"], "多媒体设备类")
        ]
        for features, cat_name in fallback_rules:
            if any(feat in text for feat in features):
                fallback_cat = next(c for c in FAULT_CATEGORIES if c["name"] == cat_name)
                return fallback_cat, 0.75, ["口语特征兜底匹配"]
        return None, 0, []

    cat_names = [x["category"]["name"] for x in category_scores]
    # 公共区域设备优先公共设施类
    if any(word in text for word in ["楼道", "公共", "楼层", "电梯间"]) and "公共设施类" in cat_names:
        public_match = [x for x in category_scores if x["category"]["name"] == "公共设施类"]
        if public_match:
            return public_match[0]["category"], max(public_match[0]["score"], 0.8), public_match[0]["hit_keywords"]
    # 实验专属词优先
    if any(kw in text for kw in ["通风橱", "实验仪器", "化学品", "实验台"]):
        exp_match = [x for x in category_scores if x["category"]["name"] == "实验设备类"]
        if exp_match:
            return exp_match[0]["category"], max(exp_match[0]["score"], 0.9), exp_match[0]["hit_keywords"]
    # 水电/给排水冲突
    if "水电类" in cat_names and "给排水类" in cat_names:
        core_electric = any(kw in text for kw in ["漏电", "触电", "插座故障", "电路故障"])
        if core_electric:
            category_scores = sorted(category_scores, key=lambda x:
                0 if x["category"]["name"] == "水电类" else 1)
            return category_scores[0]["category"], category_scores[0]["score"], category_scores[0]["hit_keywords"]
    # 取最高分
    category_scores = sorted(category_scores, key=lambda x: x["score"], reverse=True)
    best = category_scores[0]
    return best["category"], best["score"], best["hit_keywords"]

def detect_p0(text, category_name):
    """收窄P0判定，仅真实即时风险触发"""
    hit_p0_keywords = []
    for kw in P0_KEYWORDS:
        if kw in text:
            hit_p0_keywords.append(kw)
    if not hit_p0_keywords:
        return False, [], None
    # 匹配安全提示
    if category_name and "给排水" in category_name:
        tip = P0_SECURITY_TIPS["给排水"]
    elif category_name and "水电" in category_name:
        tip = P0_SECURITY_TIPS["水电"]
    elif category_name and "门窗" in category_name:
        tip = P0_SECURITY_TIPS["门窗"]
    elif category_name and "消防安防" in category_name:
        tip = P0_SECURITY_TIPS["消防安防"]
    elif category_name and "公共设施" in category_name:
        tip = P0_SECURITY_TIPS["公共设施"]
    else:
        tip = P0_SECURITY_TIPS["通用"]
    return True, hit_p0_keywords, tip

def detect_urgency(text, is_p0):
    """修复P2不可达问题：P0→P2轻微→P1功能失效"""
    if is_p0:
        return "P0"
    # 先判断P2轻微场景
    p2_signals = ["轻微", "有点", "效果差", "异响", "有点松", "晃动", "不顺畅",
                  "偶尔", "外观", "小问题", "异味不明显", "偶尔不凉", "信号稍差"]
    is_p2 = any(sig in text for sig in p2_signals)
    p1_core_signals = ["坏了", "不亮", "没电", "无法使用", "不能用", "堵塞", "损坏",
                       "打不开", "关不上", "不制冷", "不转", "失效", "没反应", "断网",
                       "漏水", "无法开机", "反水", "连不上", "不出水", "不显示", "没声音"]
    has_core_failure = any(sig in text for sig in p1_core_signals)
    if is_p2 and not has_core_failure:
        return "P2"
    if has_core_failure:
        return "P1"
    return "P2"

def simulate_image_recognition(uploaded_file):
    """明确标注演示模拟，不自动抬高置信度，不作为分诊依据"""
    if uploaded_file is None:
        return None, 0
    result = {
        "scene": "故障现场（演示版模拟识别，结果仅作参考）",
        "visible_fault": "模拟识别到可见故障点（正式版接入多模态模型）",
        "risk": "模拟识别暂未发现即时高风险",
        "is_demo": True
    }
    return result, 0.3

def triage(text, uploaded_image=None):
    """完整分诊主函数，白名单校验"""
    result = {
        "status": "success",
        "need_more_info": False,
        "followup_questions": [],
        "building": None,
        "room": None,
        "fault_category": None,
        "fault_category_name": None,
        "urgency": None,
        "confidence": 0,
        "hit_keywords": [],
        "required_skills": [],
        "required_tools": [],
        "required_parts": [],
        "security_tip": None,
        "image_result": None,
        "invalid_building": False
    }

    # 无文字仅图片：要求补文字
    if not text.strip() and uploaded_image is not None:
        result["status"] = "need_more_info"
        result["followup_questions"].append("请补充文字描述故障现象，仅上传照片无法完成分诊")
        return result

    # 1. 图片识别（模拟，不主导结果）
    if uploaded_image is not None:
        img_result, img_conf = simulate_image_recognition(uploaded_image)
        result["image_result"] = img_result
        result["confidence"] = max(result["confidence"], img_conf)

    # 2. 故障分类
    category, cat_score, hit_kws = detect_fault_category(text)
    if category:
        result["fault_category"] = category
        result["fault_category_name"] = category["name"]
        result["hit_keywords"] = hit_kws
        result["required_skills"] = category["skills"][:2]
        result["required_tools"] = category["tools"][:4]
        result["required_parts"] = category["spare_parts"][:4]
        result["confidence"] = max(result["confidence"], cat_score)

    # 3. P0硬规则优先
    is_p0, p0_kws, security_tip = detect_p0(text, result["fault_category_name"])
    if is_p0:
        result["security_tip"] = security_tip
        result["hit_keywords"].extend(p0_kws)
        result["confidence"] = max(result["confidence"], 0.9)

    # 4. 位置提取与白名单校验
    building, room = extract_building_room(text)
    if building is not None:
        building_str = str(building)
        if building_str not in ALL_VALID_BUILDINGS:
            result["invalid_building"] = True
            result["followup_questions"].append(f"楼栋{building_str}不在校区范围内，请确认正确楼栋编号")
    result["building"] = building
    result["room"] = room

    # 5. 紧急度
    result["urgency"] = detect_urgency(text, is_p0)

    # 6. 追问逻辑
    followups = list(result["followup_questions"])
    is_public_scene = (
        result["fault_category_name"] in ["公共设施类", "消防安防类", "多媒体设备类"]
        or isinstance(building, str)
        or any(word in text for word in ["公共", "楼道", "电梯", "楼层"])
    )
    if building is None and not result["invalid_building"]:
        followups.append("请补充具体楼栋编号（例如3号楼/5教/图书馆）")
    if room is None and not is_public_scene:
        followups.append("请补充具体房间号（例如412室）")
    if category is None:
        followups.append("请补充具体故障现象，比如漏水、灯不亮、门锁损坏等")

    location_complete = building is not None and (room is not None or is_public_scene)
    info_complete = location_complete and (category is not None) and not result["invalid_building"]
    result["followup_questions"] = followups

    if info_complete and result["confidence"] >= CONFIDENCE_THRESHOLD:
        result["need_more_info"] = False
        result["status"] = "success"
    else:
        result["need_more_info"] = True
        result["status"] = "need_more_info"
    return result

def merge_manual_selection(triage_result, manual_category, manual_urgency, manual_apply_urgent=False):
    """合并手动选择，加急不直接置P0，需调度员审核"""
    if manual_category and manual_category != "自动判断（以文字识别为准）":
        for cat in FAULT_CATEGORIES:
            if cat["name"] == manual_category:
                triage_result["fault_category"] = cat
                triage_result["fault_category_name"] = cat["name"]
                triage_result["required_skills"] = cat["skills"][:2]
                triage_result["required_tools"] = cat["tools"][:4]
                triage_result["required_parts"] = cat["spare_parts"][:4]
                triage_result["confidence"] = max(triage_result["confidence"], 0.9)
                break
    if manual_urgency and manual_urgency != "AI自动判断":
        triage_result["urgency"] = manual_urgency
    if manual_apply_urgent:
        triage_result["manual_urgent_request"] = True
    else:
        triage_result["manual_urgent_request"] = False
    return triage_result
