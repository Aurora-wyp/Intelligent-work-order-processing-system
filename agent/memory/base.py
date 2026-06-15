from abc import ABC, abstractmethod
from typing import Optional


class BaseMemoryStore(ABC):
    """记忆存储抽象层。

    定义工单历史记录的存储接口，支持后续替换为 Redis 等外部存储。
    """

    @abstractmethod
    def add(self, ticket: dict) -> None:
        """添加一条工单记录。"""
        ...

    @abstractmethod
    def get_recent(self, n: int) -> list[dict]:
        """获取最近 N 条工单记录。"""
        ...

    @abstractmethod
    def clear(self) -> None:
        """清空所有记录。"""
        ...

    @abstractmethod
    def get_formatted_history(self, n: int) -> str:
        """获取格式化的历史记录文本，可直接注入 Prompt。"""
        ...
