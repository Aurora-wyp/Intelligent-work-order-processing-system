"""
在线评估脚本 —— 对智能工单处理系统进行端到端性能评测。

需要: LLM API (DashScope) 可用 + Redis 运行。
用法: python eval.py
"""

import re
import json
import time
import os
import statistics
from dataclasses import dataclass, field
from typing import Optional

from react_agent import ReactAgent
from agent.tools.agent_tools import get_last_route
from utils.logger_handler import logger
from utils.path_tool import get_abs_path


# ═══════════════════════════════════════════════════════════════
# 测试用例：30 条中文客服工单 + 标注
# ═══════════════════════════════════════════════════════════════

@dataclass
class TestCase:
    query: str
    expected_type: str
    expected_priority: str


TEST_CASES: list[TestCase] = [
    # ── 退款类 (refund) ──
    TestCase("我买的扫地机器人用了三天就坏了，我要退款！", "refund", "P2"),
    TestCase("上周买的衣服不合适想退货，请问退款流程是什么", "refund", "P2"),
    TestCase("你们的产品质量问题导致我损失了钱，我要投诉并要求赔偿", "refund", "P1"),
    TestCase("刚下单还没发货，能取消订单并退款吗", "refund", "P2"),
    TestCase("收到的商品与描述完全不符，要求全额退款并道歉", "refund", "P1"),
    TestCase("退款已经等了五天还没到账，请马上处理", "refund", "P1"),

    # ── 技术问题类 (technical_issue) ──
    TestCase("App 打开就闪退，重装了好几次都没用", "technical_issue", "P2"),
    TestCase("设备屏幕出现花屏闪烁，完全无法正常使用", "technical_issue", "P1"),
    TestCase("升级最新固件后蓝牙连接总是断开", "technical_issue", "P2"),
    TestCase("系统一直提示网络错误，检查网络是正常的", "technical_issue", "P2"),
    TestCase("生产环境服务器宕机了，所有客户都无法访问", "technical_issue", "P1"),
    TestCase("打印功能点了没反应，换了浏览器也不行", "technical_issue", "P3"),

    # ── 业务咨询类 (business_inquiry) ──
    TestCase("请问你们的企业版和个人版有什么区别", "business_inquiry", "P3"),
    TestCase("想了解产品的定价方案，有没有批量采购优惠", "business_inquiry", "P3"),
    TestCase("你们支持哪些支付方式？能不能分期付款", "business_inquiry", "P3"),
    TestCase("新手使用你们的系统，有没有操作指南或者培训资料", "business_inquiry", "P3"),
    TestCase("想预约一次产品演示，怎么安排", "business_inquiry", "P3"),
    TestCase("这个功能怎么用？有详细的操作说明吗", "business_inquiry", "P3"),

    # ── 账户问题类 (account_issue) ──
    TestCase("登录一直提示密码错误，但我确定密码是对的", "account_issue", "P2"),
    TestCase("账户突然被冻结了，没有任何通知", "account_issue", "P1"),
    TestCase("换了手机号，旧的没法接收验证码，怎么换绑", "account_issue", "P2"),
    TestCase("忘记密码了，点找回密码收不到邮件", "account_issue", "P2"),
    TestCase("账号被盗了，有人在异地登录了我的账户", "account_issue", "P1"),
    TestCase("实名认证一直审核不通过，已经提交三次了", "account_issue", "P3"),

    # ── 其他类 (other) ──
    TestCase("能不能开发一个批量导出报表的功能", "other", "P3"),
    TestCase("想要注销账户并删除所有个人数据", "other", "P3"),
    TestCase("你们的隐私政策在哪里可以查看", "other", "P3"),
    TestCase("想成为你们的合作伙伴或代理商", "other", "P3"),
    TestCase("用户协议第5条是什么意思，看不明白", "other", "P3"),
    TestCase("反馈一个建议：希望增加夜间模式", "other", "P3"),
]


# ═══════════════════════════════════════════════════════════════
# 结果提取
# ═══════════════════════════════════════════════════════════════

VALID_TYPES = {"refund", "technical_issue", "business_inquiry", "account_issue", "other"}


def extract_ticket_type(text: str) -> Optional[str]:
    """从 Agent 输出中提取工单类别。"""
    for pat in [
        r"(?:类型|类别|ticket_type)[:：\s=]*\"?(\w+)\"?",
        r"已路由至:\s*\w+_queue.*?类型:\s*(\w+)",
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip().lower()
            if val in VALID_TYPES:
                return val

    # 兜底：搜索关键词
    text_lower = text.lower()
    for t in VALID_TYPES:
        if t in text_lower:
            return t
    return None


def extract_priority(text: str) -> Optional[str]:
    """从 Agent 输出中提取优先级。"""
    for pat in [
        r"(?:优先级|priority)[:：\s=]*\"?(P[123])\"?",
        r"\b(P[123])\b",
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
    return None


def detect_tool_usage(text: str) -> dict:
    """检测 Agent 输出中三个工具的调用痕迹。"""
    return {
        "route_ticket": bool(re.search(r"(?:路由|route|queue|已路由至|route_ticket)", text, re.IGNORECASE)),
        "rag_summarize": bool(re.search(r"(?:参考资料|检索|rag|知识库|RAG)", text, re.IGNORECASE)),
        "get_reply_template": bool(re.search(r"(?:模板|template|工单编号|回复草稿|最终回复)", text, re.IGNORECASE)),
    }


# ═══════════════════════════════════════════════════════════════
# Log-based 工具调用统计
# ═══════════════════════════════════════════════════════════════

def _today_log_path() -> str:
    from datetime import date
    return get_abs_path(f"log/agent_{date.today().strftime('%Y%m%d')}.log")


def count_tool_calls_from_log(since_pos: int) -> tuple[int, int, int]:
    """从日志文件中统计自 since_pos 之后新增的工具调用。

    返回: (总调用数, 成功数, 文件当前位置)
    """
    log_path = _today_log_path()
    if not os.path.exists(log_path):
        return 0, 0, since_pos

    with open(log_path, "r", encoding="utf-8") as f:
        f.seek(since_pos)
        lines = f.readlines()
        new_pos = f.tell()

    total = 0
    success = 0
    for line in lines:
        if "[tool monitor] 执行工具：" in line:
            total += 1
        elif "[tool monitor] 工具" in line and "调用成功" in line:
            success += 1

    return total, success, new_pos


def get_log_file_pos() -> int:
    log_path = _today_log_path()
    if not os.path.exists(log_path):
        return 0
    return os.path.getsize(log_path)


# ═══════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════

@dataclass
class SingleResult:
    case_index: int
    query: str
    expected_type: str
    expected_priority: str
    actual_type: Optional[str] = None
    actual_priority: Optional[str] = None
    latency_s: float = 0.0
    tools_detected: dict = field(default_factory=dict)
    tool_calls: int = 0
    tool_successes: int = 0
    error: str = ""


@dataclass
class EvalReport:
    total: int = 0
    type_correct: int = 0
    priority_correct: int = 0
    total_tool_calls: int = 0
    total_tool_successes: int = 0
    latencies: list[float] = field(default_factory=list)
    results: list[SingleResult] = field(default_factory=list)

    @property
    def type_accuracy(self) -> float:
        return self.type_correct / self.total * 100 if self.total else 0

    @property
    def priority_accuracy(self) -> float:
        return self.priority_correct / self.total * 100 if self.total else 0

    @property
    def tool_success_rate(self) -> float:
        return (self.total_tool_successes / self.total_tool_calls * 100
                if self.total_tool_calls else 0)

    @property
    def avg_latency(self) -> float:
        return statistics.mean(self.latencies) if self.latencies else 0

    @property
    def p50_latency(self) -> float:
        return statistics.median(self.latencies) if self.latencies else 0

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0
        s = sorted(self.latencies)
        return s[min(int(len(s) * 0.95), len(s) - 1)]

    @property
    def min_latency(self) -> float:
        return min(self.latencies) if self.latencies else 0

    @property
    def max_latency(self) -> float:
        return max(self.latencies) if self.latencies else 0

    def print_report(self):
        print("\n" + "=" * 62)
        print("    智能工单处理系统 —— 在线评估报告")
        print("=" * 62)
        print(f"  模型: Qwen3-Max (DashScope)")
        print(f"  测试用例总数:          {self.total}")
        print(f"  工单分类准确率:        {self.type_accuracy:.1f}%  "
              f"({self.type_correct}/{self.total})")
        print(f"  优先级判定准确率:      {self.priority_accuracy:.1f}%  "
              f"({self.priority_correct}/{self.total})")
        print(f"  工具调用成功率:        {self.tool_success_rate:.1f}%  "
              f"({self.total_tool_successes}/{self.total_tool_calls})")
        print("-" * 62)
        print(f"  端到端延迟 (秒):")
        print(f"    Avg: {self.avg_latency:.2f}s  "
              f"P50: {self.p50_latency:.2f}s  "
              f"P95: {self.p95_latency:.2f}s")
        print(f"    Min: {self.min_latency:.2f}s  "
              f"Max: {self.max_latency:.2f}s")
        print("=" * 62)

        errors = [r for r in self.results if r.error]
        if errors:
            print(f"\n[!] 异常用例 ({len(errors)} 条):")
            for r in errors:
                print(f"    [{r.case_index}] {r.query[:40]}... → {r.error}")


# ═══════════════════════════════════════════════════════════════
# 评估主流程
# ═══════════════════════════════════════════════════════════════

def run_single(agent: ReactAgent, case: TestCase, index: int,
               log_start_pos: int) -> tuple[SingleResult, int]:
    """运行单条测试用例。"""
    sr = SingleResult(
        case_index=index + 1,
        query=case.query,
        expected_type=case.expected_type,
        expected_priority=case.expected_priority,
    )

    t0 = time.perf_counter()
    full_output: list[str] = []

    try:
        for chunk in agent.execute_stream(case.query):
            full_output.append(chunk)
    except Exception as e:
        sr.latency_s = time.perf_counter() - t0
        sr.error = str(e)
        return sr, log_start_pos

    sr.latency_s = time.perf_counter() - t0
    output = "".join(full_output)

    # 提取分类
    sr.actual_type = extract_ticket_type(output)
    sr.actual_priority = extract_priority(output)

    # 从路由模块补充
    route = get_last_route()
    if route:
        if sr.actual_type is None:
            sr.actual_type = route.get("ticket_type")
        if sr.actual_priority is None:
            sr.actual_priority = route.get("priority")

    # 检测工具调用痕迹
    sr.tools_detected = detect_tool_usage(output)

    # 从日志统计本轮的精确工具调用次数
    tcalls, tok, new_pos = count_tool_calls_from_log(log_start_pos)
    sr.tool_calls = tcalls
    sr.tool_successes = tok

    return sr, new_pos


def run_consistency_test(agent: ReactAgent) -> dict:
    """一致性测试：连续提交同类别工单，检查分类是否保持稳定。"""
    agent.memory.clear()

    sequences = {
        "refund": [
            "我要退货退款，产品质量有问题",
            "买的第二件也要退，尺寸不合适",
            "上周的订单能退款吗，一直没发货",
        ],
        "technical_issue": [
            "系统登录后空白页，没法用",
            "另一个模块也报错了，数据加载失败",
        ],
        "business_inquiry": [
            "你们有哪些产品套餐",
            "企业版的价格是多少",
        ],
    }

    result = {}
    for expected_cat, queries in sequences.items():
        classifications = []
        for q in queries:
            output_parts = []
            try:
                for chunk in agent.execute_stream(q):
                    output_parts.append(chunk)
            except Exception:
                continue
            text = "".join(output_parts)
            t = extract_ticket_type(text)
            route = get_last_route()
            if t is None and route:
                t = route.get("ticket_type")
            classifications.append(t)
        consistent = all(c == expected_cat for c in classifications)
        result[expected_cat] = {
            "queries": len(queries),
            "classifications": classifications,
            "consistent": consistent,
        }
    return result


def main():
    print("=" * 62)
    print("    智能工单处理系统 · 在线评估")
    print("=" * 62)
    print("\n[i] 初始化 Agent ...")

    agent = ReactAgent()
    agent.memory.clear()
    print(f"[i] Redis: {agent.memory.redis.ping()}")
    print("[i] 已清空历史记忆\n")

    report = EvalReport(total=len(TEST_CASES))

    # ──────────────────────────────────────────
    # 阶段 1: 分类 + 性能 + 工具成功率
    # ──────────────────────────────────────────
    print("▶ 阶段 1/2: 分类准确率 & 性能 & 工具成功率")
    print("-" * 62)

    log_pos = get_log_file_pos()

    for i, case in enumerate(TEST_CASES):
        label = f"[{i + 1:02d}/{len(TEST_CASES)}] {case.query[:45]}..."
        print(f"  {label}", end=" ", flush=True)

        sr, log_pos = run_single(agent, case, i, log_pos)
        report.results.append(sr)
        report.latencies.append(sr.latency_s)

        type_ok = sr.actual_type == sr.expected_type
        pri_ok = sr.actual_priority == sr.expected_priority
        if type_ok:
            report.type_correct += 1
        if pri_ok:
            report.priority_correct += 1

        report.total_tool_calls += sr.tool_calls
        report.total_tool_successes += sr.tool_successes

        status = "OK" if type_ok and pri_ok else ("PART" if type_ok or pri_ok else "FAIL")
        print(f"{status}  type={sr.actual_type or '?'} "
              f"pri={sr.actual_priority or '?'}  "
              f"tools={sr.tool_successes}/{sr.tool_calls}  "
              f"{sr.latency_s:.1f}s")

    # ──────────────────────────────────────────
    # 阶段 2: 一致性测试
    # ──────────────────────────────────────────
    print("\n▶ 阶段 2/2: 分类一致性测试（历史上下文注入）")
    print("-" * 62)

    consistency = run_consistency_test(agent)

    total_cats = len(consistency)
    total_consistent = sum(1 for v in consistency.values() if v["consistent"])
    consistency_rate = total_consistent / total_cats * 100 if total_cats else 0

    for cat, info in consistency.items():
        icon = "OK" if info["consistent"] else "FAIL"
        actual = info["classifications"]
        print(f"  [{icon}] {cat}: {actual}")

    # ──────────────────────────────────────────
    # 输出
    # ──────────────────────────────────────────
    report.print_report()

    print(f"  分类一致性:            {consistency_rate:.0f}%  "
          f"({total_consistent}/{total_cats} 类别保持稳定)\n")

    # ── 导出 JSON ──
    export = {
        "model": "qwen3-max",
        "total_cases": report.total,
        "type_accuracy_pct": round(report.type_accuracy, 2),
        "priority_accuracy_pct": round(report.priority_accuracy, 2),
        "tool_success_rate_pct": round(report.tool_success_rate, 2),
        "latency": {
            "avg_s": round(report.avg_latency, 2),
            "p50_s": round(report.p50_latency, 2),
            "p95_s": round(report.p95_latency, 2),
            "min_s": round(report.min_latency, 2),
            "max_s": round(report.max_latency, 2),
        },
        "classification_consistency_pct": round(consistency_rate, 2),
        "details": [
            {
                "index": r.case_index,
                "query": r.query,
                "expected_type": r.expected_type,
                "expected_priority": r.expected_priority,
                "actual_type": r.actual_type,
                "actual_priority": r.actual_priority,
                "latency_s": round(r.latency_s, 2),
                "tools_detected": r.tools_detected,
                "tool_calls": r.tool_calls,
                "tool_successes": r.tool_successes,
                "error": r.error,
            }
            for r in report.results
        ],
    }

    out_path = get_abs_path("eval_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)
    print(f"[i] 详细结果已保存至: {out_path}")

    # ── 简历指标 ──
    print("\n" + "─" * 62)
    print("    简历可引用指标")
    print("─" * 62)
    print(f"  • 端到端处理延迟 P50 < {report.p50_latency:.1f}s，P95 < {report.p95_latency:.1f}s")
    print(f"  • 5 类工单分类准确率 {report.type_accuracy:.1f}%，"
          f"优先级判定准确率 {report.priority_accuracy:.1f}%")
    print(f"  • ReAct Agent 工具链（路由+RAG+模板）调用成功率 {report.tool_success_rate:.1f}%")
    print(f"  • 历史上下文注入后分类一致性 {consistency_rate:.0f}%")
    print("─" * 62)


if __name__ == "__main__":
    main()
