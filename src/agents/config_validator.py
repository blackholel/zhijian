"""
配置验证器和降级机制
"""

import logging
from typing import Any, Dict, Tuple, Optional, Type
from dataclasses import fields, dataclass
from src.utils import logger


class ConfigurationValidator:
    """配置验证器"""
    
    @staticmethod
    def validate_field(field_name: str, value: Any, field_type: Type) -> Tuple[bool, Any]:
        """
        验证和转换配置字段
        
        Args:
            field_name: 字段名称
            value: 字段值
            field_type: 字段类型
            
        Returns:
            Tuple[bool, Any]: (是否验证成功, 转换后的值)
        """
        try:
            if field_type == float:
                converted_value = float(value)
                # 温度参数范围验证
                if field_name == "temperature":
                    if not (0.0 <= converted_value <= 2.0):
                        logger.warning(f"温度参数超出范围 [0.0, 2.0]: {converted_value}")
                        return False, None
                return True, converted_value
            elif field_type == int:
                converted_value = int(value)
                # 令牌数量范围验证
                if field_name == "max_tokens":
                    if not (1 <= converted_value <= 32768):
                        logger.warning(f"最大令牌数超出范围 [1, 32768]: {converted_value}")
                        return False, None
                return True, converted_value
            elif field_type == bool:
                if isinstance(value, bool):
                    return True, value
                elif isinstance(value, str):
                    return True, value.lower() in ('true', '1', 'yes', 'on')
                else:
                    return True, bool(value)
            elif field_type == str:
                return True, str(value)
            elif hasattr(field_type, '__origin__') and field_type.__origin__ is list:
                # 处理列表类型
                if isinstance(value, list):
                    return True, value
                elif isinstance(value, str):
                    # 尝试按逗号分割
                    return True, [item.strip() for item in value.split(',')]
                else:
                    return True, [value]
            else:
                return True, value
        except (ValueError, TypeError) as e:
            logger.warning(f"配置字段类型转换失败: {field_name}={value}, 类型: {field_type}, 错误: {e}")
            return False, None


class ConfigurationFallback:
    """配置降级处理"""
    
    @staticmethod
    def get_fallback_config(agent_name: str) -> Dict[str, Any]:
        """
        获取降级配置
        
        Args:
            agent_name: 智能体名称
            
        Returns:
            Dict[str, Any]: 降级配置字典
        """
        fallback_configs = {
            "chatbot": {
                "temperature": 0.7,
                "max_tokens": 2048,
                "model": "zhipu/glm-4-plus",
                "system_prompt": "You are a helpful assistant.",
                "tools": []
            },
            "default": {
                "temperature": 0.7,
                "max_tokens": 2048,
                "model": "zhipu/glm-4-plus",
                "system_prompt": "You are a helpful assistant.",
                "tools": []
            }
        }
        
        config = fallback_configs.get(agent_name, fallback_configs["default"])
        logger.info(f"使用降级配置: {agent_name} -> {config}")
        return config
    
    @staticmethod
    def validate_and_fallback(
        config_dict: Dict[str, Any], 
        config_class: Type, 
        agent_name: str
    ) -> Dict[str, Any]:
        """
        验证配置并在需要时应用降级
        
        Args:
            config_dict: 配置字典
            config_class: 配置类
            agent_name: 智能体名称
            
        Returns:
            Dict[str, Any]: 验证后的配置字典
        """
        validated_config = {}
        fallback_config = ConfigurationFallback.get_fallback_config(agent_name)
        
        # 获取配置类的所有字段
        config_fields = {f.name: f for f in fields(config_class)}
        
        for field_name, field_info in config_fields.items():
            if field_name in config_dict:
                # 验证现有配置
                is_valid, converted_value = ConfigurationValidator.validate_field(
                    field_name, config_dict[field_name], field_info.type
                )
                if is_valid:
                    validated_config[field_name] = converted_value
                else:
                    # 使用降级配置
                    if field_name in fallback_config:
                        validated_config[field_name] = fallback_config[field_name]
                        logger.warning(f"配置验证失败，使用降级配置: {field_name} = {fallback_config[field_name]}")
            else:
                # 使用降级配置
                if field_name in fallback_config:
                    validated_config[field_name] = fallback_config[field_name]
        
        return validated_config


class ConfigurationMonitor:
    """配置加载监控"""
    
    def __init__(self):
        self.metrics = {
            "config_load_success": 0,
            "config_load_failed": 0,
            "config_validation_failed": 0,
            "fallback_used": 0,
            "db_config_failed": 0,
            "file_config_failed": 0
        }
    
    def record_config_load(self, success: bool, fallback_used: bool = False):
        """记录配置加载指标"""
        if success:
            self.metrics["config_load_success"] += 1
        else:
            self.metrics["config_load_failed"] += 1
        
        if fallback_used:
            self.metrics["fallback_used"] += 1
    
    def record_validation_failure(self):
        """记录配置验证失败"""
        self.metrics["config_validation_failed"] += 1
    
    def record_db_config_failure(self):
        """记录数据库配置加载失败"""
        self.metrics["db_config_failed"] += 1
    
    def record_file_config_failure(self):
        """记录文件配置加载失败"""
        self.metrics["file_config_failed"] += 1
    
    def get_metrics(self) -> Dict[str, int]:
        """获取监控指标"""
        return self.metrics.copy()
    
    def reset_metrics(self):
        """重置监控指标"""
        for key in self.metrics:
            self.metrics[key] = 0


# 全局配置监控实例
config_monitor = ConfigurationMonitor()


def get_config_monitor() -> ConfigurationMonitor:
    """获取配置监控实例"""
    return config_monitor