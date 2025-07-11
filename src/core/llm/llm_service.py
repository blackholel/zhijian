"""
LLM服务管理
统一的LLM服务封装，支持多种模型和配置
"""

import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Union, AsyncGenerator
from datetime import datetime
from enum import Enum
from dataclasses import dataclass

from src.models.chat_model import OpenAIBase, OpenModel, CustomModel
from src.utils.logging_config import logger


class LLMProvider(str, Enum):
    """LLM提供商"""
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    ZHIPU = "zhipu"
    CLAUDE = "claude"
    GEMINI = "gemini"
    LOCAL = "local"


@dataclass
class LLMConfig:
    """LLM配置"""
    provider: LLMProvider
    model_name: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 0.9
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    timeout: int = 60
    max_retries: int = 3
    stream: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "provider": self.provider.value,
            "model_name": self.model_name,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "stream": self.stream
        }


class LLMService:
    """LLM服务管理器"""
    
    def __init__(self):
        self._models: Dict[str, OpenAIBase] = {}
        self._configs: Dict[str, LLMConfig] = {}
        self._usage_stats: Dict[str, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()
    
    async def register_model(self, model_id: str, config: LLMConfig) -> bool:
        """注册LLM模型"""
        async with self._lock:
            try:
                # 根据提供商创建模型实例
                if config.provider == LLMProvider.OPENAI:
                    if config.api_key and config.base_url:
                        # 自定义OpenAI配置
                        model = OpenAIBase(
                            api_key=config.api_key,
                            base_url=config.base_url,
                            model_name=config.model_name
                        )
                    else:
                        # 使用默认OpenAI配置
                        model = OpenModel(model_name=config.model_name)
                else:
                    # 其他提供商使用自定义模型
                    model_info = {
                        "name": config.model_name,
                        "api_key": config.api_key,
                        "api_base": config.base_url
                    }
                    model = CustomModel(model_info)
                
                # 注册模型
                self._models[model_id] = model
                self._configs[model_id] = config
                self._usage_stats[model_id] = {
                    "total_requests": 0,
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "error_count": 0,
                    "last_used": None
                }
                
                logger.info(f"LLM模型 {model_id} 注册成功")
                return True
                
            except Exception as e:
                logger.error(f"注册LLM模型 {model_id} 失败: {e}")
                return False
    
    async def get_model(self, model_id: str) -> Optional[OpenAIBase]:
        """获取LLM模型"""
        return self._models.get(model_id)
    
    async def list_models(self) -> List[str]:
        """列出所有模型"""
        return list(self._models.keys())
    
    async def chat_completion(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> Dict[str, Any]:
        """聊天完成"""
        model = await self.get_model(model_id)
        if not model:
            raise ValueError(f"模型 {model_id} 不存在")
        
        try:
            # 记录使用
            await self._record_usage(model_id, len(messages))
            
            # 调用模型predict方法
            response = model.predict(messages, stream=False)
            
            # 转换为标准格式
            result = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": response.content if hasattr(response, 'content') else str(response)
                        }
                    }
                ],
                "usage": {
                    "total_tokens": len(str(response)) // 4  # 简单估算
                }
            }
            
            # 记录响应
            await self._record_response(model_id, result)
            
            return result
            
        except Exception as e:
            await self._record_error(model_id, str(e))
            raise
    
    async def stream_chat_completion(
        self,
        model_id: str,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式聊天完成"""
        model = await self.get_model(model_id)
        if not model:
            raise ValueError(f"模型 {model_id} 不存在")
        
        try:
            # 记录使用
            await self._record_usage(model_id, len(messages))
            
            # 流式调用
            for chunk in model.predict(messages, stream=True):
                # 转换为标准格式
                result = {
                    "choices": [
                        {
                            "delta": {
                                "content": chunk.content if hasattr(chunk, 'content') else str(chunk)
                            }
                        }
                    ]
                }
                yield result
                
        except Exception as e:
            await self._record_error(model_id, str(e))
            raise
    
    async def _record_usage(self, model_id: str, message_count: int):
        """记录使用情况"""
        stats = self._usage_stats.get(model_id, {})
        stats["total_requests"] = stats.get("total_requests", 0) + 1
        stats["last_used"] = datetime.now().isoformat()
        self._usage_stats[model_id] = stats
    
    async def _record_response(self, model_id: str, response: Dict[str, Any]):
        """记录响应"""
        stats = self._usage_stats.get(model_id, {})
        
        # 记录token使用
        if "usage" in response:
            usage = response["usage"]
            stats["total_tokens"] = stats.get("total_tokens", 0) + usage.get("total_tokens", 0)
        
        self._usage_stats[model_id] = stats
    
    async def _record_error(self, model_id: str, error: str):
        """记录错误"""
        stats = self._usage_stats.get(model_id, {})
        stats["error_count"] = stats.get("error_count", 0) + 1
        stats["last_error"] = error
        self._usage_stats[model_id] = stats
    
    async def get_usage_stats(self, model_id: Optional[str] = None) -> Dict[str, Any]:
        """获取使用统计"""
        if model_id:
            return self._usage_stats.get(model_id, {})
        return self._usage_stats.copy()
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        healthy_models = []
        unhealthy_models = []
        
        for model_id, model in self._models.items():
            try:
                # 简单的健康检查
                test_response = model.predict([
                    {"role": "user", "content": "Hello"}
                ], stream=False)
                if test_response:
                    healthy_models.append(model_id)
                else:
                    unhealthy_models.append(model_id)
            except Exception as e:
                unhealthy_models.append(model_id)
                logger.error(f"模型 {model_id} 健康检查失败: {e}")
        
        return {
            "total_models": len(self._models),
            "healthy_models": healthy_models,
            "unhealthy_models": unhealthy_models,
            "health_percentage": len(healthy_models) / len(self._models) * 100 if self._models else 0
        }


# 全局LLM服务实例
llm_service = LLMService()


async def get_llm_service() -> LLMService:
    """获取LLM服务实例"""
    return llm_service


async def setup_default_models():
    """设置默认模型"""
    import os
    
    # 设置默认的OpenAI模型
    if os.getenv("OPENAI_API_KEY"):
        openai_config = LLMConfig(
            provider=LLMProvider.OPENAI,
            model_name="gpt-3.5-turbo",
            api_key=os.getenv("OPENAI_API_KEY"),
            temperature=0.7,
            max_tokens=4096
        )
        await llm_service.register_model("openai-gpt35", openai_config)
    
    # 设置默认的DeepSeek模型
    if os.getenv("DEEPSEEK_API_KEY"):
        deepseek_config = LLMConfig(
            provider=LLMProvider.DEEPSEEK,
            model_name="deepseek-chat",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com/v1",
            temperature=0.7,
            max_tokens=4096
        )
        await llm_service.register_model("deepseek-chat", deepseek_config)
    
    logger.info("默认LLM模型设置完成")