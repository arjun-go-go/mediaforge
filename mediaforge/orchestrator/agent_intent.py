from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

AgentIntent = Literal[
    "help",
    "reference_search",
    "generation",
    "quality_repair",
    "task_query",
    "conversation_fallback",
]


class AgentRoute(BaseModel):
    intent: AgentIntent
    execute_business_tool: bool


INTENT_TOOL_NAMES: dict[AgentIntent, frozenset[str]] = {
    "help": frozenset(),
    "reference_search": frozenset({"rag_search"}),
    "generation": frozenset({"rag_search", "submit_generation_job"}),
    "quality_repair": frozenset({"get_generation_job", "check_image_compliance"}),
    "task_query": frozenset({"get_generation_job"}),
    "conversation_fallback": frozenset(),
}

_HOW_WORDS = ("怎么", "如何", "怎样", "怎么用", "使用方法", "操作方法", "教程")
_SEARCH_WORDS = ("检索", "搜索", "查找", "找", "爆款", "相似商品", "参考图")
_GENERATION_WORDS = ("生成", "生图", "做主图", "做详情图", "商品图", "宣传图")
_REPAIR_WORDS = (
    "质量",
    "修复",
    "重试",
    "重新生成",
    "为什么失败",
    "失败原因",
    "不符合",
    "偏差",
    "一致性",
)


def tools_for_intent(intent: AgentIntent) -> frozenset[str]:
    return INTENT_TOOL_NAMES[intent]


def classify_agent_intent(message: str) -> AgentRoute:
    """Route core product intents before the model sees the request."""
    text = re.sub(r"\s+", "", message.strip().lower())

    if any(word in text for word in _HOW_WORDS):
        return AgentRoute(intent="help", execute_business_tool=False)
    if any(word in text for word in ("你会干啥", "你会什么", "你会干什么", "能做什么", "有什么功能")):
        return AgentRoute(intent="help", execute_business_tool=False)
    if any(
        word in text
        for word in (
            "哪个模型",
            "哪些模型",
            "图片模型",
            "模型配置",
            "系统提示词",
            "支持哪些平台",
        )
    ):
        return AgentRoute(intent="help", execute_business_tool=False)
    if any(word in text for word in ("图片", "主图", "详情图", "这张图")) and any(
        word in text for word in ("符合", "合规", "违规", "检查")
    ):
        return AgentRoute(intent="quality_repair", execute_business_tool=True)
    if any(word in text for word in ("提示词", "文案", "营销词")) and any(
        word in text for word in ("合规", "违规", "检查", "审核")
    ):
        return AgentRoute(intent="help", execute_business_tool=False)
    if any(word in text for word in _REPAIR_WORDS):
        return AgentRoute(intent="quality_repair", execute_business_tool=True)
    if (
        "任务" in text
        and any(word in text for word in ("进度", "状态", "完成", "结果", "怎么样"))
    ) or "jobid" in text:
        return AgentRoute(intent="task_query", execute_business_tool=True)
    if any(word in text for word in _GENERATION_WORDS):
        return AgentRoute(intent="generation", execute_business_tool=True)
    if any(word in text for word in _SEARCH_WORDS) and any(
        word in text
        for word in ("帮我", "给我", "开始", "查一个", "搜一个", "找一个", "检索", "搜索", "查找", "通过图片")
    ):
        return AgentRoute(intent="reference_search", execute_business_tool=True)
    return AgentRoute(intent="conversation_fallback", execute_business_tool=False)


def help_response(message: str) -> str:
    text = message.strip().lower()
    if any(word in text for word in _SEARCH_WORDS):
        return (
            "## 查找爆款参考\n\n"
            "1. 上传新品原图，或者直接在输入框粘贴图片。\n"
            "2. 可补充检索条件，例如类目、版型、颜色或材质："
            "“帮我找浅蓝色高腰微喇牛仔裤的爆款参考”。\n"
            "3. 我会通过图文检索和视觉重排返回可信候选，供选款和生图参考。"
        )
    if any(word in text for word in ("提示词合规", "文案合规", "营销词合规")):
        return "平台规则和提示词合规会在准备生图任务时自动检查，不需要单独操作。请先上传新品图并选择目标平台。"
    return (
        "我专注于四件事：查找爆款参考、准备商品图生成任务、检查并修复生成结果、查询当前任务。"
        "请先上传新品图，或直接告诉我想处理的任务。"
    )


def fallback_response() -> str:
    return (
        "我主要处理爆款图生产流程。你可以上传新品图后让我查找爆款参考或生成商品图，"
        "也可以提供任务编号，让我检查生成质量或查询进度。"
    )
