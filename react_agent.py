from langchain.agents import create_agent
from agent.tools.agent_tools import route_ticket, get_reply_template, rag_summarize, set_ticket_id
from agent.tools.middleware import monitor_tool, log_before_model
from agent.memory import RedisMemoryStore
from model.factory import chat_model
from utils.prompt_loader import load_ticket_system_prompt
from utils.config_handler import agent_conf


class ReactAgent:
    """智能工单路由 Agent。

    """

    def __init__(self):
        # Redis 持久化记忆存储
        history_size = agent_conf.get("memory_max_size")
        self.memory = RedisMemoryStore(
            host=agent_conf.get("redis_host"),
            port=agent_conf.get("redis_port"),
            db=agent_conf.get("redis_db"),
            password=agent_conf.get("redis_password") or None,
            max_size=history_size,
        )

        # 加载系统提示词（从外部文件）
        system_prompt = load_ticket_system_prompt()

        # 使用 LangChain create_agent 创建 Agent（架构不变）
        self.agent = create_agent(
            model=chat_model,
            system_prompt=system_prompt,
            tools=[route_ticket, get_reply_template, rag_summarize],
            middleware=[monitor_tool, log_before_model],
        )

    def execute_stream(self, query: str):
        """流式执行 Agent，注入历史上下文供 Agent 参考。"""
        ticket_id = self._generate_ticket_id()
        set_ticket_id(ticket_id)

        history_context = self.memory.get_formatted_history(
            agent_conf.get("memory_context_size")
        )

        enriched_query = (
            f"【历史工单参考】\n{history_context}\n\n"
            f"【当前用户工单】\n{query}"
        )

        input_dict = {
            "messages": [
                {"role": "user", "content": enriched_query}
            ]
        }

        for chunk in self.agent.stream(input_dict, stream_mode="values"):
            latest_message = chunk["messages"][-1]
            if latest_message.content:
                yield latest_message.content.strip() + "\n"

    def _generate_ticket_id(self) -> str:
        """通过 Redis 自增生成工单编号。格式: TK-20260615-0001"""
        from datetime import date
        today = date.today().strftime("%Y%m%d")
        seq = self.memory.redis.incr(f"ticket:seq:{today}")
        return f"TK-{today}-{seq:04d}"

    def record_ticket(self, ticket_type: str, priority: str,
                      content: str, route: str, reply: str = ""):
        """记录一条已处理的工单到历史（含输入和输出）。"""
        self.memory.add({
            "ticket_type": ticket_type,
            "priority": priority,
            "content": content[:200],
            "route": route,
            "reply": reply[:500],
        })


if __name__ == '__main__':
    agent = ReactAgent()
    test_query = "我买的扫地机器人用了三天就坏了，我要退款！"
    print(f"测试工单: {test_query}\n")
    for chunk in agent.execute_stream(test_query):
        print(chunk, end="", flush=True)
    print("\n\n--- 历史记录 ---")
    print(agent.memory.get_formatted_history(5))
