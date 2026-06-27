import json
import os
from langchain_core.tools import tool
from rag.rag_service import RagSummarizeService
from utils.config_handler import agent_conf
from utils.path_tool import get_abs_path
from utils.logger_handler import logger

rag = RagSummarizeService()

# 当前工单编号 + 最后一次路由信息（由工具自动记录）
_current_ticket_id: str = ""
_last_route: dict = {}


def get_last_route() -> dict:
    return _last_route


def set_ticket_id(ticket_id: str):
    global _current_ticket_id
    _current_ticket_id = ticket_id


def _load_routes() -> dict:
    """从配置文件动态加载路由表。"""
    routes_path = get_abs_path(agent_conf.get("routes_config_path"))
    if not os.path.exists(routes_path):
        logger.error(f"[route_ticket] 路由配置文件不存在: {routes_path}")
        return {}
    with open(routes_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_template(ticket_type: str) -> str:
    """从 templates/ 目录动态加载回复模板。"""
    templates_dir = get_abs_path(agent_conf.get("templates_dir", "templates"))
    template_path = os.path.join(templates_dir, f"{ticket_type}.txt")
    if not os.path.exists(template_path):
        logger.warning(f"[get_reply_template] 模板文件不存在: {template_path}，回退到 other.txt")
        template_path = os.path.join(templates_dir, "other.txt")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


@tool(description="当工单问题需要参考历史案例或专业知识时，调用此工具从知识库检索相关解决方案")
def rag_summarize(query: str) -> str:
    """RAG 知识检索工具。当模型需要查找私有知识时调用此工具。"""
    return rag.rag_summarize(query)


@tool(description="根据工单类型和优先级进行自动路由，返回路由目标队列名称")
def route_ticket(ticket_type: str, priority: str, content: str) -> str:
    """工单路由工具。

    根据 ticket_type 从 config/routes.json 中查找对应的处理队列。

    参数:
        ticket_type: 工单类型 (refund / technical_issue / business_inquiry / account_issue / other)
        priority: 优先级 (P1 / P2 / P3)
        content: 工单原始内容摘要

    返回: 路由结果描述
    """
    routes = _load_routes()
    if not routes:
        return "路由配置加载失败，工单已转入 general_queue"

    queue = routes.get(ticket_type, routes.get("other", "general_queue"))
    # 记录路由信息，供 record_ticket 使用
    global _last_route
    _last_route = {"ticket_type": ticket_type, "priority": priority, "route": queue}
    logger.info(f"[route_ticket] 工单类型={ticket_type} 优先级={priority} → 路由到 {queue}")
    return f"工单已路由至: {queue}（类型: {ticket_type}, 优先级: {priority}）"


@tool(description="根据工单类型获取对应的回复模板，{ticket_id} 和 {priority} 已由系统自动替换")
def get_reply_template(ticket_type: str) -> str:
    """获取回复模板工具。{ticket_id} 和 {priority} 占位符由系统自动替换，无需传参。"""
    template = _load_template(ticket_type)
    # 自动替换占位符
    template = template.replace("{ticket_id}", _current_ticket_id)
    template = template.replace("{priority}", "根据实际情况判断")
    logger.info(f"[get_reply_template] 已加载 {ticket_type} 模板，工单编号={_current_ticket_id}")
    return template
