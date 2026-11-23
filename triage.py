# 核心分诊逻辑
import re
from config import FAULT_CATEGORIES, P0_KEYWORDS, CONFIDENCE_THRESHOLD, P0_SECURITY_TIPS

def extract_building_room(text):
    """从文本提取楼栋和房间号，支持数字号楼、X教教学楼格式"""
    building = None
    room = None
    # 先匹配 X教（教学楼格式，例如5教）
    teaching_match = re.search(r"(\d{1,2})\s*教", text)
    if teaching_match:
        building = f"{teaching_match.group(1)}教"
    # 匹配 X号楼 / X楼（宿舍楼格式）
    building_match = re.search(r"(\d{1,2})\s*号?楼", text)
    if building_match:
        building = int(building_match.group(1))
    # 匹配 XXXX房间 / XXXX室 / 数字房号
    room_match = re.search(r"(\d{3,4})\s*(?:房间|室|号房)?", text)
    if room_match:
        room = room_match.group(1)
    return building, room

def detect_fault_category(text):
    """关键词匹配故障大类，长关键词优先，专属词加权重，处理多分类冲突"""
    category_scores = []
    for cat in FAULT_CATEGORIES:
        hit_count = 0
        hit_keywords = []
        total_weight = 0
        # 按关键词长度降序，长词优先命中，避免短词误匹配
        sorted_keywords = sorted(cat["keywords"], key=lambda x: len(x), reverse=True)
        for kw in sorted_keywords:
            if kw in text:
                hit_count += 1
                hit_keywords.append(kw)
                # 词越长权重越高，3字以上专属词权重翻倍
                total_weight += len(kw) * 0.08
        if hit_count > 0:
            # 置信度计算：基础分+权重分
            score = min(0.5 + total_weight, 0.98)
            category_scores.append({
                "category": cat,
                "score": score,
                "hit_keywords": hit_keywords
            })
    if not category_scores:
        return None, 0, []
    # 特殊冲突处理：仅当核心故障是水电/触电本身才优先水电；漏水导致的插座泡水，主分类仍为给排水
    cat_names = [x["category"]["name"] for x in category_scores]
    if "水电类" in cat_names and "给排水类" in cat_names:
        core_electric = any(kw in text for kw in ["漏电", "触电", "插座本身故障", "电路故障"])
        if core_electric:
            category_scores = sorted(category_scores, key=lambda x:
                0 if x["category"]["name"] == "水电类" else 1)
            return category_scores[0]["category"], category_scores[0]["score"], category_scores[0]["hit_keywords"]
    # 特殊冲突：命中实验专属长词（通风橱、实验仪器），优先实验设备类
    if any(kw in text for kw in ["通风橱", "实验仪器", "化学品", "实验台"]):
        exp_match = [x for x in category_scores if x["category"]["name"] == "实验设备类"]
        if exp_match:
            return exp_match[0]["category"], max(exp_match[0]["score"], 0.9), exp_match[0]["hit_keywords"]
    # 取得分最高的分类
    category_scores = sorted(category_scores, key=lambda x: x["score"], reverse=True)
    best = category_scores[0]
    return best["category"], best["score"], best["hit_keywords"]

def detect_p0(text, category_name):
    """优先判断P0硬规则，全局扫描"""
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
    else:
        tip = P0_SECURITY_TIPS["通用"]
    return True, hit_p0_keywords, tip

def detect_urgency(text, is_p0):
    """P0判断完后，先判断P2轻微场景，再判断P1"""
    if is_p0:
        return "P0"
    # P1先判断核心功能是否失效：如果同时命中P1/P2，优先P1
    p1_signals = ["坏了", "不亮", "没电", "无法使用", "不能用", "堵塞", "损坏", "打不开",
                  "关不上", "不制冷", "不转", "断裂", "失效", "没反应", "无网", "断网",
                  "空调漏水", "漏水", "无法开机", "反水"]
    is_p1 = any(sig in text for sig in p1_signals)
    if is_p1:
        return "P1"
    # 再判断P2：仅轻微异响、松动，无核心功能失效
    p2_signals = ["轻微", "单个", "信号差", "异响", "有点松", "晃动", "不顺畅",
                  "经常断网", "外观", "小问题", "异味"]
    is_p2 = any(sig in text for sig in p2_signals)
    if is_p2:
        return "P2"
    return "P2"

def simulate_image_recognition(uploaded_file):
    """
    离线模拟照片识别结果（无API时可完整演示）
    实际接入多模态API时替换此函数即可
    """
    if uploaded_file is None:
        return None, 0
    result = {
        "scene": "故障现场",
        "visible_fault": "通过照片识别到可见故障点",
        "risk": "暂未识别到即时高风险",
        "confidence": 0.82
    }
    return result, 0.82

def triage(text, uploaded_image=None):
    """
    完整分诊主函数
    返回：分诊结果字典，位置缺失不阻断分类，仅标记待确认
    """
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
        "image_result": None
    }

    # 1. 照片识别
    if uploaded_image is not None:
        img_result, img_conf = simulate_image_recognition(uploaded_image)
        result["image_result"] = img_result
        result["confidence"] = max(result["confidence"], img_conf)

    # 2. 先做故障分类
    category, cat_score, hit_kws = detect_fault_category(text)
    if category:
        result["fault_category"] = category
        result["fault_category_name"] = category["name"]
        result["hit_keywords"] = hit_kws
        result["required_skills"] = category["skills"][:2]
        result["required_tools"] = category["tools"][:4]
        result["required_parts"] = category["spare_parts"][:4]
        result["confidence"] = max(result["confidence"], cat_score)

    # 3. 先判断P0硬规则（即使分类/位置没识别到也要判断）
    is_p0, p0_kws, security_tip = detect_p0(text, result["fault_category_name"])
    if is_p0:
        result["security_tip"] = security_tip
        result["hit_keywords"].extend(p0_kws)
        # P0置信度至少0.9
        result["confidence"] = max(result["confidence"], 0.9)

    # 4. 提取位置信息
    building, room = extract_building_room(text)
    result["building"] = building
    result["room"] = room

    # 5. 判断紧急度
    result["urgency"] = detect_urgency(text, is_p0)

    # 6. 收集待追问信息：仅核心字段真的缺失才提示，信息完整不做冗余提示
    followups = []
    if building is None:
        followups.append("请补充具体楼栋编号（例如3号楼/5教）")
    if room is None:
        followups.append("请补充具体房间号（例如412室）")
    if category is None:
        followups.append("请补充具体故障现象，比如漏水、灯不亮、门锁损坏等")

    # 核心字段完整且置信度达标：直接判定信息完整，清空所有待完善提示
    info_complete = (building is not None) and (room is not None) and (category is not None)
    if info_complete and result["confidence"] >= CONFIDENCE_THRESHOLD:
        result["followup_questions"] = []
        result["need_more_info"] = False
        result["status"] = "success"
    else:
        # 只有真的缺字段/置信度不足才进入追问
        if category is None or result["confidence"] < CONFIDENCE_THRESHOLD:
            result["status"] = "need_more_info"
            result["need_more_info"] = True
            result["followup_questions"] = followups if followups else [
                "故障描述不够清晰，请补充故障现象、是否有安全隐患"
            ]
        else:
            # 分类正常但位置缺失：保留待补充提示，不阻断分诊结果
            result["followup_questions"] = followups
            result["need_more_info"] = len(followups) > 0

    return result

def merge_manual_selection(triage_result, manual_category, manual_urgency, manual_apply_urgent=False):
    """
    合并用户手动点选的信息：手动选择优先级高于AI判断
    """
    # 手动指定故障分类
    if manual_category and manual_category != "自动判断（以文字识别为准）":
        for cat in FAULT_CATEGORIES:
            if cat["name"] == manual_category:
                triage_result["fault_category"] = cat
                triage_result["fault_category_name"] = cat["name"]
                triage_result["required_skills"] = cat["skills"][:2]
                triage_result["required_tools"] = cat["tools"][:4]
                triage_result["required_parts"] = cat["spare_parts"][:4]
                triage_result["confidence"] = max(triage_result["confidence"], 0.95)
                break
    # 手动指定紧急度
    if manual_urgency and manual_urgency != "AI自动判断":
        triage_result["urgency"] = manual_urgency
    # 人工申请加急：强制标记，不被AI结果覆盖
    if manual_apply_urgent:
        triage_result["manual_urgent_request"] = True
        triage_result["urgency"] = "P0"
        triage_result["confidence"] = max(triage_result["confidence"], 0.98)
    else:
        triage_result["manual_urgent_request"] = False
    return triage_result
