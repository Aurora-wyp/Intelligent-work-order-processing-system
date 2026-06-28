# 🎫 智能工单处理系统（Smart Ticket Processing System）

基于大语言模型（LLM）ReAct Agent 的企业客服工单自动分类、路由与回复生成系统。

## 功能特性

- **智能分类** — 自动将用户工单分类为退款、技术问题、业务咨询、账户问题、其他五大类别
- **优先级判定** — 根据「条件 + 判断标准」双层规则自动判定 P1/P2/P3 优先级
- **队列路由** — 按类别自动路由到对应处理队列（退款队列、技术队列、销售队列、支持队列、通用队列）
- **知识库检索（RAG）** — 基于 ChromaDB 向量数据库检索相关历史案例，Agent 自主判断是否调用
- **回复草稿生成** — 结合检索结果与回复模板，自动生成专业客服回复草稿
- **历史记忆** — 基于 Redis 持久化工单历史，上下文注入提升 Agent 判断连续性
- **在线评估** — 内置 30 条标注测试用例的自动化评估脚本，覆盖分类准确率、延迟分布、工具成功率等维度

## 技术栈

| 组件 | 技术 |
|------|------|
| Web UI | Streamlit |
| LLM 框架 | LangChain（Agent + Tools + Middleware） |
| 大模型 | 通义千问 Qwen3.7-Plus（阿里云 DashScope，OpenAI 兼容模式） |
| 嵌入模型 | text-embedding-v4（DashScope） |
| 向量数据库 | ChromaDB |
| 会话存储 | Redis |
| 配置管理 | YAML |

## 项目结构

```
├── app.py                       # Streamlit Web 入口
├── react_agent.py               # ReAct Agent 核心
├── eval.py                      # 在线评估脚本
├── agent/
│   ├── tools/
│   │   ├── agent_tools.py       # Agent 工具定义（路由、模板、RAG）
│   │   └── middleware.py        # 工具调用监控中间件
│   └── memory/
│       ├── base.py              # 记忆存储抽象接口
│       └── redis_store.py       # Redis 持久化记忆实现
├── config/
│   ├── agent.example.yml        # Agent 配置示例（模型名 + Redis + 记忆参数）
│   ├── chroma.yml               # ChromaDB 配置（分块策略 + 检索参数）
│   ├── prompts.yml              # 提示词路径配置
│   └── routes.json              # 工单类型→队列路由表
├── model/
│   └── factory.py               # LLM / Embedding 模型工厂（OpenAI 兼容模式）
├── rag/
│   ├── rag_service.py           # RAG 摘要服务（LangChain LCEL）
│   └── vector_store.py          # ChromaDB 向量存储（增量加载 + MD5 去重）
├── utils/
│   ├── config_handler.py        # YAML 配置加载器
│   ├── file_handler.py          # 文件 I/O 工具
│   ├── logger_handler.py        # 日志管理
│   ├── path_tool.py             # 项目路径解析
│   └── prompt_loader.py         # Prompt 文件加载器
├── prompts/
│   ├── main_prompt.txt          # Agent 主系统提示词
│   └── rag_summarize.txt        # RAG 摘要提示词
├── data/                        # 知识库文档（按类别+优先级组织）
├── templates/                   # 回复模板（按工单类别）
├── chroma_db/                   # ChromaDB 持久化存储
└── log/                         # 应用日志
```

## 快速开始

### 环境要求

- Python 3.10+
- Redis（本地运行，默认 127.0.0.1:6379）
- 阿里云 DashScope API Key

### 安装步骤

```bash
# 1. 克隆项目
git clone <your-repo-url>
cd 智能工单处理系统

# 2. 安装依赖
pip install streamlit langchain langchain-openai langchain-community langchain-chroma chromadb redis pyyaml pypdf dashscope langgraph

# 3. 配置
cp config/agent.example.yml config/agent.yml
# 编辑 config/agent.yml，填入模型名称和 API Key（已自动读取 DASHSCOPE_API_KEY 环境变量）

# 4. 启动 Redis（如未运行）
redis-server

# 5. 构建知识库向量索引（首次运行）
python -m rag.vector_store

# 6. 启动应用
streamlit run app.py

# 7. (可选) 运行评估
python eval.py
```

### 配置说明

编辑 `config/agent.yml`：

```yaml
# LLM 模型配置（通过 DashScope OpenAI 兼容接口调用）
chat_model_name: qwen3.7-plus
embedding_model_name: text-embedding-v4

# 工单路由配置
routes_config_path: config/routes.json
templates_dir: templates

# Redis 配置
redis_host: 127.0.0.1
redis_port: 6379
redis_db: 0
redis_password: ""

# 记忆配置
memory_max_size: 20        # 最大记忆条数
memory_context_size: 5     # 注入上下文的最近条数
```

> API Key 通过环境变量 `DASHSCOPE_API_KEY` 传入，无需写在配置文件中。

## 工作流程

```
用户提交工单
    │
    ▼
┌─── Redis 历史注入 ──────────────────────────┐
│  "【历史工单参考】...\n【当前用户工单】..."       │
└────────────────────────────────────────────┘
    │
    ▼
┌─ ReAct Agent 推理循环 ──────────────────────┐
│                                             │
│  1. 分析工单内容 → 判断类别                   │
│  2. 按「条件+判断标准」判定 P1/P2/P3 优先级     │
│  3. （可选）调用 rag_summarize 检索知识库       │
│  4. 调用 route_ticket → 查 routes.json 路由   │
│  5. 调用 get_reply_template → 加载回复模板    │
│  6. 结合模板+检索结果 → 生成个性化回复草稿       │
│                                             │
│  Middleware 全链路记录工具调用日志              │
└────────────────────────────────────────────┘
    │
    ▼
  输出：分类结果 + 路由队列 + 回复草稿
    │
    ▼
  写入 Redis ticket:history（供下一条工单参考）
```

### 三个 Agent 工具

| 工具 | 作用 | 数据来源 |
|------|------|---------|
| `route_ticket` | 工单类别 → 路由队列 | `config/routes.json` |
| `get_reply_template` | 加载回复模板 + 占位符替换 | `templates/{type}.txt` |
| `rag_summarize` | 知识库语义检索 + LLM 摘要 | ChromaDB + `data/` |

## 在线评估

执行 `python eval.py` 运行 30 条标注测试用例（5 类覆盖 P1/P2/P3），自动输出评估报告并保存至 `eval_result.json`。

### 评估维度

| 维度 | 计算方式 |
|------|---------|
| 分类准确率 | 正则提取 Agent 输出中的 ticket_type → 与标注比对 |
| 优先级准确率 | 正则提取 priority → 与标注比对 |
| 工具成功率 | 解析 `log/agent_*.log` 中 Middleware 记录的调用成功/失败日志 |
| 端到端延迟 | `time.perf_counter()` 计时 → 统计 Avg/P50/P95/Min/Max |
| 分类一致性 | 连续同类工单 → 检查 Agent 分类是否保持稳定 |

### 测试用例设计

测试用例按 5 类 × 多优先级分布，标注依据 system prompt 中的分类与优先级定义规则，并包含边界模糊样本（如「注销账户」涉及 account 和 other 的边界）。

## 知识库

`data/` 目录下包含 23 条中文客服场景案例，覆盖 5 大类别 × 3 个优先级的真实业务场景：

| 类别 | P1 | P2 | P3 |
|------|-----|-----|-----|
| refund | 消费欺诈、大额支付异常 | 七天无理由、商品瑕疵 | 重复支付、优惠券未生效 |
| technical_issue | 系统宕机、数据丢失 | 单模块异常、固件兼容性 | 界面显示、统计延迟 |
| business_inquiry | 紧急商务合作 | 批量采购询价 | 功能咨询、操作指导 |
| account_issue | 账户被黑、管理员误封 | 无法登录、换绑手机号 | 实名认证审核慢 |
| other | 法律合规要求 | 功能建议反馈 | 注销账户、隐私政策咨询 |

每案例包含：场景描述 + 分步骤处理流程 + 时效承诺 + 升级路径。

## 工单分类与路由

| 工单类型 | 路由队列 | 模板 |
|----------|----------|------|
| refund（退款） | refund_queue | 3-5 工作日退款 |
| technical_issue（技术问题） | tech_queue | 按优先级 SLA |
| business_inquiry（业务咨询） | sales_queue | 1 工作日内回电 |
| account_issue（账户问题） | support_queue | 身份验证流程 |
| other（其他） | general_queue | 通用确认 |

## License

MIT
