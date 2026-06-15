from utils.config_handler import prompts_conf
from utils.path_tool import get_abs_path
from utils.logger_handler import logger


def _read_prompt(path_key: str, error_tag: str) -> str:
    """通用提示词文件读取。"""
    try:
        file_path = get_abs_path(prompts_conf[path_key])
    except KeyError as e:
        logger.error(f"[{error_tag}] yaml 配置中缺少 {path_key} 配置项")
        raise e

    try:
        return open(file_path, 'r', encoding='utf-8').read()
    except Exception as e:
        logger.error(f"[{error_tag}] 解析提示词出错: {str(e)}")
        raise e


def load_system_prompts():
    """加载主系统提示词（兼容旧接口，实际指向工单 Agent 提示词）。"""
    return _read_prompt('main_prompt_path', 'load_system_prompts')


def load_ticket_system_prompt():
    """加载工单处理 Agent 系统提示词。"""
    return _read_prompt('main_prompt_path', 'load_ticket_system_prompt')


def load_rag_prompts():
    """加载 RAG 总结提示词。"""
    return _read_prompt('rag_summarize_prompt_path', 'load_rag_prompts')


