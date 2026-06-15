import os
from langchain_chroma import Chroma
from langchain_core.documents import Document
from utils.file_handler import text_loader,pdf_loader,listdir_with_allowed_type,get_file_md5_hex
from utils.config_handler import chroma_conf
from model.factory import embedding_model
from langchain_text_splitters import RecursiveCharacterTextSplitter
from utils.config_handler import get_abs_path
from utils.logger_handler import logger

class VectorStoreService:
    def __init__(self):
        self.vector_store = Chroma(
            collection_name=chroma_conf['collection_name'],
            embedding_function=embedding_model,
            persist_directory=chroma_conf['persist_directory'],
        )

        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=chroma_conf['chunk_size'],
            chunk_overlap=chroma_conf['chunk_overlap'],
            separators=chroma_conf['separators'],
            length_function=len
        )

    def get_retriever(self):
        return self.vector_store.as_retriever(search_kwargs={"k":chroma_conf['k']})

    def load_document(self):
        def check_md5_hex(md5_for_hex:str):
            if not os.path.exists(get_abs_path(chroma_conf['md5_hex_store'])):
                open(get_abs_path(chroma_conf['md5_hex_store']), 'w',encoding="utf-8").close()
                return False

            with open(get_abs_path(chroma_conf['md5_hex_store']),'r',encoding="utf-8") as f:
                for line in f.readlines():
                    line = line.strip()
                    if line==md5_for_hex:
                        return True

                return False

        def save_md5_hex(md5_for_hex:str):
            with open(get_abs_path(chroma_conf['md5_hex_store']),'a',encoding="utf-8") as f:
                f.write(md5_for_hex+"\n")

        def get_file_document(read_path:str):
            if read_path.endswith('txt'):
                return text_loader(read_path)

            if read_path.endswith('pdf'):
                return pdf_loader(read_path)

            return []

        allowed_files_path=listdir_with_allowed_type(
            get_abs_path(chroma_conf['data_path']),
            tuple(chroma_conf['allowed_knowledge_file_type']),
        )

        for path in allowed_files_path:
            md5_hex=get_file_md5_hex(path)

            if check_md5_hex(md5_hex):
                logger.info(f"[加载知识库]{path}内容已经存在知识库内，跳过")
                continue

            try:
                documents:list[Document]=get_file_document(path)
                if not documents:
                    logger.warning(f"[加载知识库]{path}内没有有效文本内容，跳过")
                    continue

                split_document:list[Document]=self.spliter.split_documents(documents)

                if not split_document:
                    logger.warning(f"[加载知识库]{path}分片后没有有效文本内容，跳过")
                    continue

                self.vector_store.add_documents(split_document)
                save_md5_hex(md5_hex)
                logger.info(f"[加载知识库]{path}内容加载成功")

            except Exception as e:
                logger.error(f"[加载知识库]{path}加载失败:{str(e)}",exc_info=True)


if __name__=='__main__':
    vs=VectorStoreService()
    vs.load_document()
    retriever=vs.get_retriever()
    res=retriever.invoke("迷路")
    for doc in res:
        print(doc.page_content)





