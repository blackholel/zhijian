"""
LightRAG模型适配器 - 集成项目统一配置系统
"""

import os
import logging
from typing import Dict, Any, Optional, Callable
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
from lightrag.utils import EmbeddingFunc

from src import config
from src.models import select_model
from src.utils import get_docker_safe_url

logger = logging.getLogger(__name__)


class LightRAGModelAdapter:
    """
    LightRAG模型适配器
    负责将项目统一配置系统的模型转换为LightRAG兼容的函数接口
    """
    
    def __init__(self):
        self.config = config
        
    def get_llm_func(self, llm_config: Dict[str, Any] = None, kb_id: str = None) -> Callable:
        """
        获取LightRAG兼容的LLM函数
        
        Args:
            llm_config: 知识库级别的LLM配置
            kb_id: 知识库ID，用于日志记录
            
        Returns:
            async callable: LightRAG兼容的LLM函数
        """
        # 获取模型配置（支持多级降级）
        model_info = self._get_model_config("llm", llm_config, kb_id)
        
        # 记录使用的模型配置
        logger.info(f"LightRAG LLM配置 [kb_id={kb_id}]: provider={model_info.get('provider')}, model={model_info.get('model_name')}")
        
        async def llm_model_func(prompt, system_prompt=None, history_messages=[], **kwargs):
            """LightRAG兼容的LLM调用函数"""
            try:
                return await openai_complete_if_cache(
                    model_info.get("model_name"),
                    prompt,
                    system_prompt=system_prompt,
                    history_messages=history_messages,
                    api_key=model_info.get("api_key"),
                    base_url=get_docker_safe_url(model_info.get("base_url")),
                    extra_body={"enable_thinking": False},
                    **kwargs,
                )
            except Exception as e:
                logger.error(f"LLM调用失败 [kb_id={kb_id}]: {e}")
                raise
                
        return llm_model_func
    
    def get_embedding_func(self, embed_config: Dict[str, Any] = None, kb_id: str = None) -> EmbeddingFunc:
        """
        获取LightRAG兼容的Embedding函数
        
        Args:
            embed_config: 知识库级别的嵌入模型配置
            kb_id: 知识库ID，用于日志记录
            
        Returns:
            EmbeddingFunc: LightRAG兼容的嵌入函数
        """
        # 获取嵌入模型配置（支持多级降级）
        model_info = self._get_embedding_config(embed_config, kb_id)
        
        # 记录使用的嵌入模型配置
        logger.info(f"LightRAG嵌入模型配置 [kb_id={kb_id}]: model={model_info.get('model_name')}, dimension={model_info.get('dimension')}")
        
        return EmbeddingFunc(
            embedding_dim=model_info.get("dimension", 1024),
            max_token_size=4096,
            func=lambda texts: openai_embed(
                texts=texts,
                model=model_info.get("model_name"),
                api_key=model_info.get("api_key"),
                base_url=get_docker_safe_url(model_info.get("base_url"))
            ),
        )
    
    def _get_model_config(self, model_type: str, kb_config: Dict[str, Any] = None, kb_id: str = None) -> Dict[str, Any]:
        """
        获取模型配置，支持多级降级：知识库配置 → 系统默认配置 → 硬编码降级
        
        Args:
            model_type: 模型类型 ("llm" 或 "embedding")
            kb_config: 知识库级别配置
            kb_id: 知识库ID
            
        Returns:
            Dict: 模型配置信息
        """
        try:
            # 1. 优先使用知识库级别配置
            if kb_config and self._validate_kb_config(kb_config):
                logger.debug(f"使用知识库级别配置 [kb_id={kb_id}]")
                return self._convert_kb_config_to_model_info(kb_config)
            
            # 2. 使用系统默认配置
            return self._get_system_default_config(model_type, kb_id)
            
        except Exception as e:
            logger.warning(f"获取模型配置失败 [kb_id={kb_id}]: {e}, 使用降级配置")
            return self._get_fallback_config(model_type)
    
    def _get_embedding_config(self, embed_config: Dict[str, Any] = None, kb_id: str = None) -> Dict[str, Any]:
        """
        获取嵌入模型配置，支持多级降级
        
        Args:
            embed_config: 知识库级别的嵌入模型配置
            kb_id: 知识库ID
            
        Returns:
            Dict: 嵌入模型配置信息
        """
        try:
            # 1. 优先使用知识库级别配置
            if embed_config and self._validate_embed_config(embed_config):
                logger.debug(f"使用知识库级别嵌入配置 [kb_id={kb_id}]")
                return embed_config
            
            # 2. 使用系统默认嵌入配置
            embed_model_id = self.config.embed_model
            if embed_model_id and embed_model_id in self.config.embed_model_names:
                embed_info = self.config.embed_model_names[embed_model_id]
                logger.debug(f"使用系统默认嵌入配置 [kb_id={kb_id}]: {embed_model_id}")
                
                return {
                    "model_name": embed_info.get("name"),
                    "dimension": embed_info.get("dimension", 1024),
                    "api_key": os.getenv(embed_info.get("api_key", "OPENAI_API_KEY"), "no_api_key"),
                    "base_url": embed_info.get("base_url", "http://localhost:8081/v1").replace("/embeddings", "")
                }
            
            # 3. 降级配置
            logger.warning(f"使用嵌入模型降级配置 [kb_id={kb_id}]")
            return self._get_fallback_embed_config()
            
        except Exception as e:
            logger.error(f"获取嵌入模型配置失败 [kb_id={kb_id}]: {e}, 使用降级配置")
            return self._get_fallback_embed_config()
    
    def _get_system_default_config(self, model_type: str, kb_id: str = None) -> Dict[str, Any]:
        """
        获取系统默认模型配置
        
        Args:
            model_type: 模型类型
            kb_id: 知识库ID
            
        Returns:
            Dict: 模型配置信息
        """
        provider = self.config.model_provider
        model_name = self.config.model_name
        
        if not provider or provider not in self.config.model_names:
            # 使用第一个可用的模型提供商
            if self.config.valuable_model_provider:
                provider = self.config.valuable_model_provider[0]
                model_name = self.config.model_names[provider].get("default")
                logger.info(f"使用第一个可用提供商 [kb_id={kb_id}]: {provider}/{model_name}")
            else:
                raise ValueError("没有可用的模型提供商")
        
        # 使用select_model获取模型对象
        try:
            model_obj = select_model(provider, model_name)
            logger.debug(f"使用系统默认配置 [kb_id={kb_id}]: {provider}/{model_name}")
            
            return {
                "provider": provider,
                "model_name": model_obj.model_name,
                "api_key": model_obj.api_key,
                "base_url": model_obj.base_url
            }
        except Exception as e:
            logger.error(f"使用select_model失败 [kb_id={kb_id}]: {e}")
            raise
    
    def _validate_kb_config(self, kb_config: Dict[str, Any]) -> bool:
        """验证知识库级别配置是否有效"""
        required_fields = ["provider", "model_name"]
        return all(field in kb_config and kb_config[field] for field in required_fields)
    
    def _validate_embed_config(self, embed_config: Dict[str, Any]) -> bool:
        """验证嵌入模型配置是否有效"""
        required_fields = ["model_name", "base_url"]
        return all(field in embed_config and embed_config[field] for field in required_fields)
    
    def _convert_kb_config_to_model_info(self, kb_config: Dict[str, Any]) -> Dict[str, Any]:
        """将知识库配置转换为模型信息"""
        provider = kb_config.get("provider")
        model_name = kb_config.get("model_name")
        
        # 使用select_model获取标准化的模型对象
        model_obj = select_model(provider, model_name)
        
        return {
            "provider": provider,
            "model_name": model_obj.model_name,
            "api_key": model_obj.api_key,
            "base_url": model_obj.base_url
        }
    
    def _get_fallback_config(self, model_type: str) -> Dict[str, Any]:
        """
        获取降级配置
        
        Args:
            model_type: 模型类型
            
        Returns:
            Dict: 降级模型配置
        """
        # 使用SiliconFlow作为降级选择，因为通常有免费额度
        fallback_configs = {
            "llm": {
                "provider": "siliconflow",
                "model_name": "Qwen/Qwen3-8B",
                "api_key": os.getenv("SILICONFLOW_API_KEY", "no_api_key"),
                "base_url": "https://api.siliconflow.cn/v1"
            }
        }
        
        config = fallback_configs.get(model_type, fallback_configs["llm"])
        logger.warning(f"使用降级配置: {config}")
        return config
    
    def _get_fallback_embed_config(self) -> Dict[str, Any]:
        """获取嵌入模型降级配置"""
        return {
            "model_name": "BAAI/bge-m3",
            "dimension": 1024,
            "api_key": os.getenv("SILICONFLOW_API_KEY", "no_api_key"),
            "base_url": "https://api.siliconflow.cn/v1"
        }
    
    def create_kb_model_config(self, provider: str, model_name: str, embed_provider: str = None, embed_model: str = None) -> Dict[str, Any]:
        """
        创建知识库级别的模型配置
        
        Args:
            provider: LLM提供商
            model_name: LLM模型名
            embed_provider: 嵌入模型提供商（可选）
            embed_model: 嵌入模型名（可选）
            
        Returns:
            Dict: 知识库模型配置
        """
        config = {
            "llm_info": {
                "provider": provider,
                "model_name": model_name
            }
        }
        
        if embed_provider and embed_model:
            # 获取嵌入模型信息
            embed_key = f"{embed_provider}/{embed_model}"
            if embed_key in self.config.embed_model_names:
                embed_info = self.config.embed_model_names[embed_key]
                config["embed_info"] = {
                    "provider": embed_provider,
                    "model_name": embed_info.get("name"),
                    "dimension": embed_info.get("dimension", 1024),
                    "api_key": os.getenv(embed_info.get("api_key", "OPENAI_API_KEY")),
                    "base_url": embed_info.get("base_url")
                }
        
        return config
    
    def get_available_models(self) -> Dict[str, Any]:
        """
        获取所有可用的模型配置
        
        Returns:
            Dict: 包含LLM和嵌入模型的可用配置
        """
        return {
            "llm_providers": list(self.config.model_names.keys()),
            "llm_models": {
                provider: info.get("models", [])
                for provider, info in self.config.model_names.items()
            },
            "embed_models": list(self.config.embed_model_names.keys()),
            "available_providers": self.config.valuable_model_provider,
            "default_config": {
                "llm_provider": self.config.model_provider,
                "llm_model": self.config.model_name,
                "embed_model": self.config.embed_model
            }
        }


# 全局单例实例
_model_adapter = None

def get_lightrag_model_adapter() -> LightRAGModelAdapter:
    """获取LightRAG模型适配器单例"""
    global _model_adapter
    if _model_adapter is None:
        _model_adapter = LightRAGModelAdapter()
    return _model_adapter