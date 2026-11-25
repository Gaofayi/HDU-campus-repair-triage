import streamlit as st
from datetime import datetime, timedelta
from triage import triage, merge_manual_selection
from mock_data import query_available_workers, check_inventory
from db import (generate_work_order_id, insert_order, update_dispatch,
                cancel_order, submit_evaluation, query_order_by_id,
                list_orders_by_status, list_pending_orders, reset_demo_data,
                DISPATCHER_PASSWORD)
from config import (WEEKDAY_SLOTS, WEEKEND_SLOTS, ANYTIME_SLOT,
                    MANUAL_URGENCY_REASONS, FAULT_CATEGORIES,
                    STUDENT_RESPONSE_TEXT, SELF_HELP_SOLUTIONS)

st.set_page_config(
    page_title="杭电校园报修智能分诊派单系统",
    page_icon="🔧",
    layout="centered"
)

# 初始化session
if "my_orders" not in st.session_state:
    st.session_state.my_orders = []
if "dispatch_logged_in" not in st.session_state:
    st.session_state.dispatch_logged_in = False
if "current_triage" not in st.session_state:
    st.session_state.current_triage = None
if "current_workers" not in st.session_state:
    st.session_state.current_workers = None

st.title("杭电校园报修智能分诊派单系统")
st.caption("杭州电子科技大学 · AIGC应用创新大赛作品 · 人工强制确认兜底")
st.info("首次加载休眠唤醒约需10-30秒，演示数据已内置，可直接操作", icon="ℹ️")

tab_student, tab_dispatch, tab_ledger = st.tabs(["学生报修", "调度员工作台", "工单台账"])

# ===================== 学生侧：报修为主，查询/我的工单次级 =====================
with tab_student:
    # 我的报修（不用记工单号，本地保存）
    with st.expander("我的报修记录与进度查询", expanded=False):
        # 工单号查询入口
        query_id = st.text_input("输入工单号查询", placeholder="HDU开头的完整工单号")
        if st.button("查询"):
            order = query_order_by_id(query_id.strip())
            if order:
                st.success(f"状态：{order['status']}")
                st.write(f"预约：{order['appointment_date']} {order['appointment_slot']}")
                st.write(f"维修人员：{order['worker_name'] or '待分配'}")
                if order["post_upgrade"]:
                    st.write(f"加急回复：{order['upgrade_reply']}")
            else:
                st.warning("未查询到工单")
        st.divider()
        if st.session_state.my_orders:
            for my_id in st.session_state.my_orders:
                order = query_order_by_id(my_id)
                if order:
                    st.write(f"**{my_id}** · {order['status']}")
                    col1, col2 = st.columns(2)
                    with col1:
                        if order["status"] not in ["已取消", "已完成，已评价"]:
                            if st.button("取消工单", key=f"cancel_{my_id}"):
                                cancel_order(my_id)
                                st.rerun()
                    with col2:
                        if order["status"] == "已派单，等待上门" or order["status"] == "加急工单已优先派单，等待上门":
                            with st.expander("提交满意度评价"):
                                score = st.slider("评分（1-5分）", 1, 5, 5, key=f"score_{my_id}")
                                eval_text = st.text_area("评价内容", key=f"eval_{my_id}")
                                if st.button("提交评价", key=f"submit_eval_{my_id}"):
                                    submit_evaluation(my_id, score, eval_text)
                                    st.rerun()
        else:
            st.write("暂无提交记录，提交报修后自动保存到这里")

    st.divider()
    st.subheader("提交新报修")
    # 两列布局，减少长表单
    col_left, col_right = st.columns(2)
    with col_left:
        report_text = st.text_area("故障描述（口语化即可）", height=120,
                                   placeholder="例如：3号楼412水龙头滴水，关不紧")
        uploaded_img = st.file_uploader("故障照片（可选）", type=["jpg", "jpeg", "png"])
        if uploaded_img:
            st.image(uploaded_img, width=200)
            st.caption("演示版图片识别为模拟结果，仅作参考")
    with col_right:
        today = datetime.now().date()
        app_date = st.date_input("预约日期", min_value=today,
                                 max_value=today + timedelta(days=7), value=today)
        is_weekend = app_date.weekday() >= 5
        base_slots = WEEKEND_SLOTS if is_weekend else WEEKDAY_SLOTS
        valid_slots = []
        now_h = datetime.now().hour + datetime.now().minute/60
        for s in base_slots:
            if app_date == today and s["start_hour"] <= now_h:
                continue
            valid_slots.append(s)
        slot_options = [s["label"] for s in valid_slots] + [ANYTIME_SLOT["label"]]
        app_slot = st.selectbox("预约时段", options=slot_options)
        st.caption("工作日/周末时段不同，当日已过期时段自动过滤")
        app_note = st.text_input("时间备注（可选）")
        with st.expander("手动选择故障信息（可选）"):
            manual_cat = st.selectbox("故障大类",
                ["自动判断"] + [c["name"] for c in FAULT_CATEGORIES])
            manual_urg = st.selectbox("紧急度", ["自动判断", "P0", "P1", "P2"])

    if st.button("提交报修", type="primary", use_container_width=True):
        # 就近校验提示
        if not report_text.strip() and not uploaded_img:
            st.error("请输入文字描述或上传故障照片", icon="⚠️")
        elif not report_text.strip():
            st.error("请补充文字描述，仅照片无法分诊")
        else:
            with st.spinner("智能体正在分诊..."):
                result = triage(report_text, uploaded_img)
                result = merge_manual_selection(result,
                    "" if manual_cat == "自动判断" else manual_cat,
                    "" if manual_urg == "自动判断" else manual_urg, False)
                if result["status"] == "need_more_info":
                    for q in result["followup_questions"]:
                        st.warning(q)
                else:
                    order_id = generate_work_order_id()
                    result["appointment_date"] = app_date.strftime("%Y-%m-%d")
                    result["appointment_slot"] = app_slot
                    result["appointment_note"] = app_note
                    # 匹配维修人员
                    skill = result["required_skills"][0] if result["required_skills"] else None
                    workers, w_err = query_available_workers(skill, result["urgency"] == "P0")
                    st.session_state.current_workers = (workers, w_err)
                    # 先以待确认入库
                    order_data = {
                        "work_order_id": order_id,
                        "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "building": result["building"],
                        "room": result["room"],
                        "fault_type": result["fault_category_name"],
                        "ai_urgency": result["urgency"],
                        "final_urgency": result["urgency"],
                        "post_upgrade": False,
                        "appointment_date": result["appointment_date"],
                        "appointment_slot": result["appointment_slot"],
                        "appointment_note": app_note,
                        "worker_name": "",
                        "worker_phone": "",
                        "chat_record": "",
                        "confirm_note": "",
                        "upgrade_reason": "",
                        "upgrade_reply": "",
                        "raw_report": report_text,
                        "status": "待确认"
                    }
                    insert_order(order_data)
                    st.session_state.my_orders.append(order_id)
                    st.session_state.current_triage = result
                    st.rerun()

    # 卡片式回执
    if st.session_state.current_triage and st.session_state.current_triage["status"] == "success":
        res = st.session_state.current_triage
        latest_id = st.session_state.my_orders[-1]
        st.divider()
        st.success("✅ 报修提交成功")
        st.write(f"**工单号：{latest_id}**")
        loc = f"{res['building']}号楼" if isinstance(res['building'], int) else res['building']
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("故障类型", res["fault_category_name"])
        with c2:
            st.metric("紧急度", res["urgency"])
        with c3:
            st.metric("预约时间", res["appointment_slot"])
        st.write(STUDENT_RESPONSE_TEXT[res["urgency"]])
        if res["security_tip"]:
            st.warning(res["security_tip"])
        with st.expander("临时自助排查方案"):
            for sol in SELF_HELP_SOLUTIONS[res["fault_category_name"]]:
                st.write(f"- {sol}")
        # 后置升级入口
        with st.expander("对结果有异议？申请人工复核"):
            upg_reason = st.selectbox("升级原因", MANUAL_URGENCY_REASONS)
            upg_note = st.text_area("补充说明")
            if st.button("提交复核申请"):
                order = query_order_by_id(latest_id)
                order["post_upgrade"] = 1
                order["upgrade_reason"] = upg_reason + " " + upg_note
                order["status"] = "待确认（加急复核中）"
                # 更新数据库
                import db
                conn = db.get_conn()
                conn.execute('''UPDATE work_orders SET post_upgrade=1, upgrade_reason=?, status=?
                                WHERE work_order_id=?''',
                             (order["upgrade_reason"], order["status"], latest_id))
                conn.commit()
                conn.close()
                st.success("复核申请已提交，调度员优先处理")
                st.rerun()

# ===================== 调度员工作台：口令登录，全量待办 =====================
with tab_dispatch:
    if not st.session_state.dispatch_logged_in:
        st.subheader("调度员登录")
        pwd = st.text_input("请输入调度口令", type="password")
        if st.button("登录"):
            if pwd == DISPATCHER_PASSWORD:
                st.session_state.dispatch_logged_in = True
                st.rerun()
            else:
                st.error("口令错误")
    else:
        st.subheader("待确认工单队列")
        pending = list_pending_orders()
        if not pending:
            st.info("暂无待确认工单")
        for order in pending:
            if order["post_upgrade"]:
                st.error("🚨 加急复核工单")
            else:
                st.info("普通待确认工单")
            st.write(f"工单号：{order['work_order_id']}")
            st.write(f"位置：{order['building']} {order['room']}")
            st.write(f"故障：{order['fault_type']}，AI建议等级：{order['ai_urgency']}")
            st.write(f"预约：{order['appointment_date']} {order['appointment_slot']}")
            if order["post_upgrade"]:
                st.write(f"升级原因：{order['upgrade_reason']}")
            with st.expander("处理派单"):
                # 匹配维修人员
                cat = next(c for c in FAULT_CATEGORIES if c["name"] == order["fault_type"])
                skill = cat["skills"][0]
                workers, w_err = query_available_workers(skill, order["final_urgency"] == "P0")
                if w_err:
                    w_name = st.text_input("手动指定人员", key=f"w_{order['work_order_id']}")
                    w_phone = "人工录入"
                else:
                    w_name = st.selectbox("派单人员", [w["name"] for w in workers],
                                          key=f"w_{order['work_order_id']}")
                    w_info = next(w for w in workers if w["name"] == w_name)
                    w_phone = w_info["phone"]
                final_urg = st.radio("最终紧急度", ["P0", "P1", "P2"],
                    index=["P0","P1","P2"].index(order["final_urgency"]),
                    horizontal=True, key=f"urg_{order['work_order_id']}")
                chat = st.text_area("沟通记录", key=f"chat_{order['work_order_id']}")
                upg_reply = ""
                if order["post_upgrade"]:
                    upg_reply = st.text_area("复核回复（学生可见）", key=f"upg_{order['work_order_id']}")
                note = st.text_area("派单备注", value="按预约时间上门", key=f"note_{order['work_order_id']}")
                if st.button("确认派单", key=f"btn_{order['work_order_id']}"):
                    if order["post_upgrade"] and not upg_reply.strip():
                        st.warning("请填写复核回复")
                    else:
                        update_dispatch(order["work_order_id"], final_urg,
                                        w_name, w_phone, chat, note, upg_reply)
                        st.success("派单成功")
                        st.rerun()
        st.divider()
        if st.button("退出登录"):
            st.session_state.dispatch_logged_in = False
            st.rerun()

# ===================== 台账页 =====================
with tab_ledger:
    st.subheader("全部工单台账")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("一键重置为演示数据"):
            reset_demo_data()
            st.success("演示数据已重置")
            st.rerun()
    all_orders = list_orders_by_status()
    st.dataframe(all_orders, use_container_width=True)
