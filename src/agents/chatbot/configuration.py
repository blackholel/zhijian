import uuid

from dataclasses import dataclass, field

from src.agents.registry import Configuration
from src.agents.tools_factory import get_all_tools

@dataclass(kw_only=True)
class ChatbotConfiguration(Configuration):
    """Chatbot 的配置

    配置说明：

    metadata 中 configurable 为 True 的配置项可以被用户配置，
    configurable 为 False 的配置项不能被用户配置，只能由开发者预设。
    """

    system_prompt: str = field(
        default="You are a helpful assistant.",
        metadata={
            "name": "系统提示词",
            "configurable": True,
            "description": "用来描述智能体的角色和行为"
        },
    )

    model: str = field(
        default="zhipu/glm-4-plus",
        metadata={
            "name": "智能体模型",
            "configurable": True,
            "options": [],
            "description": "智能体的驱动模型"
        },
    )

    tools: list[str] = field(
        default_factory=list,
        metadata={
            "name": "工具",
            "configurable": True,
            "options": list(get_all_tools().keys()),  # 这里的选择是所有的工具
            "description": "工具列表"
        },
    )

    temperature: float = field(
        default=0.7,
        metadata={
            "name": "温度参数",
            "configurable": True,
            "description": "控制生成文本的随机性，范围0-1"
        },
    )

    max_tokens: int = field(
        default=2048,
        metadata={
            "name": "最大令牌数",
            "configurable": True,
            "description": "生成文本的最大长度"
        },
    )

    top_p: float = field(
        default=0.9,
        metadata={
            "name": "Top-p采样",
            "configurable": True,
            "description": "控制生成文本的多样性"
        },
    )

    frequency_penalty: float = field(
        default=0.0,
        metadata={
            "name": "频率惩罚",
            "configurable": True,
            "description": "减少重复内容的惩罚系数"
        },
    )

    presence_penalty: float = field(
        default=0.0,
        metadata={
            "name": "存在惩罚",
            "configurable": True,
            "description": "鼓励谈论新话题的惩罚系数"
        },
    )
