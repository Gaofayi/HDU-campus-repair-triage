import streamlit as st
import json
import csv
import os
from datetime import datetime, timedelta
from triage import triage, merge_manual_selection
from mock_data import query_available_workers, check_inventory, generate_work_order_id
from config import (DATA_DIR, WEEKDAY_SLOTS, WEEKEND_SLOTS, ANYTIME_SLOT,
                    MANUAL_URGENCY_REASONS, FAULT_CATEGORIES,
                    STUDENT_RESPONSE_TEXT, SELF_HELP_SOLUTIONS)

st.set_page_config(
    page_title="杭电校园报修智能分诊派单系统",
    page_icon="🔧",
    layout="centered"
)

# 初始化session状态
if "triage_result" not in st.session_state:
    st.session_state.triage_result = None
if "worker_candidates" not in st.session_state:
    st.session_state.worker_candidates = None
if "inventory_result" not in st.session_state:
    st.session_state.inventory_result = None
if "confirmed_order" not in st.session_state:
    st.session_state.confirmed_order = None
if "manual_chat_note" not in st.session_state:
    st.session_state.manual_chat_note = ""
if "student_order_id" not in st.session_state:
    st.session_state.student_order_id = ""

st.title("杭电校园报修智能分诊派单系统")
st.caption("杭州电子科技大学 · AIGC智能体原型 · 人工确认后派单")

tab1, tab2, tab3 = st.tabs(["学生报修与进度查询", "调度员确认派单", "工单台账"])

# ===================== 学生报修+查询页 =====================
with tab1:
    # 顶部工单查询入口
    st.subheader("工单进度查询")
    query_order_id = st.text_input("输入工单号查询最新状态", placeholder="例如HDU20261123001")
    if st.button("查询工单"):
        ledger_path = os.path.join(DATA_DIR, "工单台账.json")
        found = None
        if os.path.exists(ledger_path):
            with open(ledger_path, "r", encoding="utf-8") as f:
                ledger = json.load(f)
            for order in ledger:
                if order["work_order_id"] == query_order_id.strip():
                    found = order
                    break
        if found:
            st.success(f"工单状态：{found['status']}")
            st.write(f"预约上门时间：{found['appointment_date']} {found['appointment_slot']}")
            st.write(f"故障类型：{found['fault_type']}，最终紧急度：{found['final_urgency']}")
            st.write(f"维修人员：{found['worker_name']}，联系电话：{found['worker_phone']}")
            if found.get("chat_record"):
                st.write(f"沟通备注：{found['chat_record']}")
        else:
            st.warning("未查询到工单，请确认工单号是否正确，或工单仍在待确认队列")

    st.divider()
    st.subheader("提交新报修")
    report_text = st.text_area("文字描述故障（口语化即可）", height=100,
                               placeholder="例如：3号楼412水龙头一直漏水，地面有积水")
    uploaded_img = st.file_uploader("上传故障照片（可选）", type=["jpg", "jpeg", "png"])
    if uploaded_img is not None:
        st.image(uploaded_img, caption="已上传故障照片", width=300)

    st.divider()
    st.write("选择预约上门时间")
    today = datetime.now().date()
    max_date = today + timedelta(days=7)
    appointment_date = st.date_input("预约日期", min_value=today, max_value=max_date, value=today)
    is_weekend = appointment_date.weekday() >= 5
    base_slots = WEEKEND_SLOTS if is_weekend else WEEKDAY_SLOTS
    available_slots = []
    now_hour = datetime.now().hour + datetime.now().minute / 60
    for slot in base_slots:
        if appointment_date == today:
            if slot["start_hour"] > now_hour:
                available_slots.append(slot)
        else:
            available_slots.append(slot)
    all_slot_options = [s["label"] for s in available_slots] + [ANYTIME_SLOT["label"]]
    appointment_slot_label = st.selectbox("预约时段", options=all_slot_options) if all_slot_options else ""
    appointment_note = st.text_input("特殊时间备注（可选）")

    with st.expander("手动点选故障信息（可选，可修正AI判断）"):
        manual_category_options = ["自动判断（以文字识别为准）"] + [cat["name"] for cat in FAULT_CATEGORIES]
        manual_category = st.selectbox("故障大类", options=manual_category_options)
        manual_urgency_options = ["AI自动判断", "P0", "P1", "P2"]
        manual_urgency = st.selectbox("紧急程度", options=manual_urgency_options)

    if st.button("提交报修", type="primary"):
        if not report_text and uploaded_img is None:
            st.warning("请输入文字或上传照片")
        elif not appointment_slot_label:
            st.warning("请选择有效预约时段")
        else:
            with st.spinner("智能体正在处理..."):
                result = triage(report_text, uploaded_img)
                result = merge_manual_selection(result, manual_category, manual_urgency, False)
                result["appointment_date"] = appointment_date.strftime("%Y-%m-%d")
                result["appointment_slot"] = appointment_slot_label
                result["appointment_note"] = appointment_note
                result["post_upgrade_applied"] = False
                result["upgrade_reason"] = ""
                # 立刻给学生生成预工单号
                pre_order_id = generate_work_order_id()
                result["pre_order_id"] = pre_order_id
                st.session_state.triage_result = result
                st.session_state.student_order_id = pre_order_id
                st.session_state.confirmed_order = None

                if result["status"] == "need_more_info":
                    st.warning("信息待补充，请完善后重新提交")
                    for q in result["followup_questions"]:
                        st.write(f"- {q}")
                else:
                    # 内部调度数据
                    sufficient, missing = check_inventory(result["required_parts"])
                    st.session_state.inventory_result = (sufficient, missing)
                    required_skill = result["required_skills"][0] if result["required_skills"] else None
                    workers, worker_error = query_available_workers(required_skill,
                                                                   is_p0=(result["urgency"]=="P0"))
                    st.session_state.worker_candidates = (workers, worker_error)

    # 学生侧完整回执（提交成功后立刻展示，不是只有等待）
    if st.session_state.triage_result and st.session_state.triage_result["status"] != "need_more_info":
        res = st.session_state.triage_result
        st.divider()
        st.success("✅ 报修提交成功，以下是你的报修回执与临时处理建议")
        # 学生可见核心信息，不展示内部置信度
        st.write(f"**预工单号**：{res['pre_order_id']}")
        loc_text = f"{res['building']}号楼" if isinstance(res['building'], int) else res['building']
        st.write(f"**报修位置**：{loc_text} {res['room']}室")
        st.write(f"**故障类型**：{res['fault_category_name']}")
        st.write(f"**预约时间**：{res['appointment_date']} {res['appointment_slot']}")
        st.write(f"**响应说明**：{STUDENT_RESPONSE_TEXT[res['urgency']]}")
        st.write("**当前状态**：已提交，等待调度员人工确认派单，确认后可在本页顶部用工单号查询维修人员信息")

        if res.get("security_tip"):
            st.warning(f"⚠️ 安全提示：{res['security_tip']}")

        # 自助解决办法（学生要的即时处理方案）
        st.divider()
        st.write("### 临时自助排查与处理建议")
        solutions = SELF_HELP_SOLUTIONS[res["fault_category_name"]]
        for sol in solutions:
            st.write(f"- {sol}")

        # 后置升级入口
        st.divider()
        with st.expander("对结果有异议？申请人工加急/复核"):
            upgrade_reason = st.selectbox("升级原因", options=MANUAL_URGENCY_REASONS)
            upgrade_note = st.text_area("补充说明", height=60)
            if st.button("提交升级申请"):
                res["post_upgrade_applied"] = True
                res["manual_urgent_request"] = True
                res["upgrade_reason"] = upgrade_reason + " " + upgrade_note
                st.session_state.triage_result = res
                st.rerun()

# ===================== 调度员页 =====================
with tab2:
    st.subheader("调度员人工确认（强制环节）")
    if st.session_state.triage_result and st.session_state.triage_result["status"] != "need_more_info":
        res = st.session_state.triage_result
        st.write(f"预约时间：{res['appointment_date']} {res['appointment_slot']}")
        if res.get("appointment_note"):
            st.write(f"学生备注：{res['appointment_note']}")
        if res.get("post_upgrade_applied"):
            st.error("人工申请升级：" + res.get("upgrade_reason", ""))

        st.divider()
        default_idx = ["P0","P1","P2"].index(res.get("urgency", "P1"))
        adjust_urgency = st.radio("最终紧急度", options=["P0", "P1", "P2"],
                                  index=default_idx, horizontal=True)
        manual_chat_note = st.text_area("人工沟通记录", value=st.session_state.manual_chat_note)
        st.session_state.manual_chat_note = manual_chat_note

        workers, worker_error = st.session_state.worker_candidates
        if worker_error == "no_available_worker":
            st.error("无空闲人员，需手动调度")
            selected_worker_name = st.text_input("指定维修人员")
        else:
            selected_worker_name = st.selectbox("选择派单人员",
                                                options=[w["name"] for w in workers],
                                                index=0)
        confirm_note = st.text_area("派单备注", value="按预约时间上门")

        if st.button("确认派单并归档", type="primary"):
            worker_info = next(w for w in workers if w["name"] == selected_worker_name) if not worker_error else {"name": selected_worker_name, "phone": "人工录入"}
            order_data = {
                "work_order_id": res["pre_order_id"],
                "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "building": res.get("building"),
                "room": res.get("room"),
                "fault_type": res.get("fault_category_name"),
                "ai_urgency": res.get("urgency"),
                "final_urgency": adjust_urgency,
                "post_upgrade": res.get("post_upgrade_applied", False),
                "appointment_date": res.get("appointment_date"),
                "appointment_slot": res.get("appointment_slot"),
                "appointment_note": res.get("appointment_note", ""),
                "worker_name": worker_info["name"],
                "worker_phone": worker_info.get("phone", ""),
                "chat_record": manual_chat_note,
                "confirm_note": confirm_note,
                "upgrade_reason": res.get("upgrade_reason", ""),
                "raw_report": report_text,
                "status": "已派单，等待上门"
            }
            st.session_state.confirmed_order = order_data
            ledger_path = os.path.join(DATA_DIR, "工单台账.json")
            ledger = []
            if os.path.exists(ledger_path):
                with open(ledger_path, "r", encoding="utf-8") as f:
                    ledger = json.load(f)
            ledger.append(order_data)
            with open(ledger_path, "w", encoding="utf-8") as f:
                json.dump(ledger, f, ensure_ascii=False, indent=2)
            csv_path = os.path.join(DATA_DIR, "工单台账.csv")
            with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
                if ledger:
                    writer = csv.DictWriter(f, fieldnames=ledger[0].keys())
                    writer.writeheader()
                    writer.writerows(ledger)
            st.success("派单成功，学生可通过工单号查询到维修人员信息")
    else:
        st.info("暂无可确认工单")

# ===================== 台账页 =====================
with tab3:
    st.subheader("历史工单台账")
    ledger_path = os.path.join(DATA_DIR, "工单台账.json")
    if os.path.exists(ledger_path):
        with open(ledger_path, "r", encoding="utf-8") as f:
            ledger = json.load(f)
        st.dataframe(ledger, use_container_width=True)
        with open(ledger_path, "rb") as f:
            st.download_button("下载JSON台账", f, "工单台账.json")
        csv_path = os.path.join(DATA_DIR, "工单台账.csv")
        if os.path.exists(csv_path):
            with open(csv_path, "rb") as f:
                st.download_button("下载CSV台账", f, "工单台账.csv")
    else:
        st.info("暂无历史工单")
