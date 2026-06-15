from langchain_core.documents import Document

from model.factory import chat_model
from rag.vector_store import VectorStoreService
from utils.prompt_loader import load_rag_prompts
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import  PromptTemplate


class RagSummarizeService():
    def __init__(self):
        self.vector_store=VectorStoreService()
        self.retriever=self.vector_store.get_retriever()
        self.prompt_text=load_rag_prompts()
        self.prompt_template=PromptTemplate.from_template(self.prompt_text)
        self.model=chat_model
        self.chain=self._init_chain()

    def _init_chain(self):
        chain=self.prompt_template | self.model | StrOutputParser()
        return chain

    def retriever_docs(self,query:str)->list[Document]:
        return self.retriever.invoke(query)

    def rag_summarize(self,query:str):
        context_docs=self.retriever_docs(query)
        context=""
        counter=0
        for doc in context_docs:
            counter+=1
            context+=f"【参考资料{counter}】:参考资料：{doc.page_content} | 参考元数据：{doc.metadata}"

        return self.chain.invoke({"input":query,"context":context})


if __name__=="__main__":
    rag_conf=RagSummarizeService()
    res=rag_conf.rag_summarize("怎么维修")
    print(res)