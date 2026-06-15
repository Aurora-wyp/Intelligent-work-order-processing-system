import json
from agent.memory.base import BaseMemoryStore


class RedisMemoryStore(BaseMemoryStore):
    """基于 Redis 的持久化记忆存储。

    工单历史存储在 Redis List 中，重启不丢失。
    """

    def __init__(self, host="127.0.0.1", port=6379, db=0, password=None,
                 max_size=20, key="ticket:history"):
        import redis
        self.redis = redis.Redis(host=host, port=port, db=db, password=password,
                                 decode_responses=True, protocol=2)
        self.max_size = max_size
        self.key = key

    def add(self, ticket: dict) -> None:
        self.redis.rpush(self.key, json.dumps(ticket, ensure_ascii=False))
        # 超出 max_size 时裁剪
        size = self.redis.llen(self.key)
        if size > self.max_size:
            self.redis.ltrim(self.key, size - self.max_size, -1)

    def get_recent(self, n: int) -> list[dict]:
        if n <= 0:
            return []
        items = self.redis.lrange(self.key, -n, -1)
        return [json.loads(item) for item in items]

    def clear(self) -> None:
        self.redis.delete(self.key)

    def get_formatted_history(self, n: int) -> str:
        recent = self.get_recent(n)
        if not recent:
            return "暂无历史工单记录。"

        lines = []
        for i, t in enumerate(recent, 1):
            lines.append(
                f"【历史工单{i}】类型: {t.get('ticket_type', '未知')} | "
                f"优先级: {t.get('priority', '未知')} | "
                f"用户问题: {t.get('content', '无')} | "
                f"路由: {t.get('route', '未知')} | "
                f"回复: {t.get('reply', '无')}"
            )
        return "\n".join(lines)
