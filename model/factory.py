from abc import ABC, abstractmethod
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_community.embeddings import DashScopeEmbeddings
from utils.config_handler import agent_conf
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
import os

class BaseModelFactory(ABC):
    @abstractmethod
    def generator(self)->Optional[Embeddings | BaseChatModel]:
        pass

class ChatModelFactory(BaseModelFactory):
    def generator(self)->Optional[Embeddings | BaseChatModel]:
        return ChatOpenAI(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=os.environ.get("DASHSCOPE_API_KEY"),
            model=agent_conf['chat_model_name'],
        )

class EmbeddingsFactory(BaseModelFactory):
    def generator(self)->Optional[Embeddings | BaseChatModel]:
        return DashScopeEmbeddings(model=agent_conf['embedding_model_name'])


chat_model=ChatModelFactory().generator()
embedding_model=EmbeddingsFactory().generator()
