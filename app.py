"""
Smart Ticket Router —— 智能工单自动分类与回复系统
"""
import re
import json
import streamlit as st
from react_agent import ReactAgent
from agent.tools.agent_tools import get_last_route

# ── 工具函数 ──────────────────────────────────────────────
def _split(text: str):
    m = re.search(r"最终回复草稿|回复草稿|最终回复", text)
    if m:
        return text[:m.start()].strip(), text[m.end():].strip()
    return text.strip(), ""


def _load_msgs(r):
    return [json.loads(i) for i in r.lrange("chat:messages", 0, -1)]


def _save_msg(r, role, content):
    r.rpush("chat:messages", json.dumps({"role": role, "content": content}, ensure_ascii=False))


# ── 页面配置 ──────────────────────────────────────────────
st.set_page_config(page_title="智能工单路由", page_icon="🎫", layout="wide")

if "agent" not in st.session_state:
    st.session_state["agent"] = ReactAgent()

agent = st.session_state["agent"]
r = agent.memory.redis

if "messages" not in st.session_state:
    st.session_state["messages"] = _load_msgs(r)

# ── 主页面 ────────────────────────────────────────────────
st.title("🎫 智能工单处理系统")
st.caption("自动分类 · 优先级判定 · 智能路由 · 一键生成回复")
st.divider()

for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("请输入工单内容..."):
    st.chat_message("user").markdown(prompt)
    st.session_state["messages"].append({"role": "user", "content": prompt})
    _save_msg(r, "user", prompt)

    with st.chat_message("assistant"):
        with st.spinner("Agent 分析中..."):
            full = ""
            placeholder = st.empty()
            for chunk in agent.execute_stream(prompt):
                full += chunk
                _, reply = _split(full)
                if reply:
                    placeholder.markdown(reply)
                else:
                    placeholder.caption("分析中...")

    _, reply = _split(full)
    saved = reply if reply else full
    st.session_state["messages"].append({"role": "assistant", "content": saved})
    _save_msg(r, "assistant", saved)

    # 写入工单历史（Redis 持久化，含用户问题和 Agent 回复）
    route_info = get_last_route()
    agent.record_ticket(
        ticket_type=route_info.get("ticket_type", "unknown"),
        priority=route_info.get("priority", "P3"),
        content=prompt[:200],
        route=route_info.get("route", "unknown"),
        reply=saved[:500],
    )
    st.rerun()
