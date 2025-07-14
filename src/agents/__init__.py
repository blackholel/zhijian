import asyncio
from typing import TYPE_CHECKING, Dict, Any, List, Optional, Union, AsyncIterator
from src.agents.chatbot import ChatbotAgent
from src.agents.react import ReActAgent
from src.utils import logger

if TYPE_CHECKING:
    from src.agents.context import UserContext
    from src.agents.registry import BaseAgent
    from langchain_core.runnables import RunnableConfig

class AgentManager:
    """
    重构后的智能体管理器
    
    集成权限控制、依赖注入和用户上下文管理的企业级智能体管理器。
    支持细粒度权限控制、实例缓存和智能体生命周期管理。
    """
    
    _instance: Optional['AgentManager'] = None
    
    def __new__(cls) -> 'AgentManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            # 智能体注册表
            self._classes = {}
            self._instances = {}  # 存储已创建的 agent 实例
            
            # 依赖注入
            from src.agents.dependencies import get_agent_dependencies
            self._dependencies = get_agent_dependencies()
            self._tools_factory = None
            
            # 初始化状态
            self._initialized = False
            
            logger.debug("AgentManager 实例创建完成")
    
    async def initialize(self):
        """异步初始化智能体管理器"""
        if self._initialized:
            return
        
        try:
            # 1. 初始化依赖
            await self._dependencies.initialize_all()
            
            # 2. 创建权限感知工具工厂
            from src.agents.tools_factory import PermissionAwareToolsFactory
            
            permission_engine = await self._dependencies.permission_engine
            kb_manager = await self._dependencies.kb_manager
            
            self._tools_factory = PermissionAwareToolsFactory(
                permission_engine, kb_manager
            )
            
            # 3. 初始化所有智能体实例
            await self.init_all_agents()
            
            self._initialized = True
            logger.info("AgentManager 初始化完成")
            
        except Exception as e:
            logger.error(f"AgentManager 初始化失败: {e}")
            raise

    def register_agent(self, agent_class):
        """注册智能体类"""
        self._classes[agent_class.name] = agent_class
        logger.debug(f"注册智能体: {agent_class.name}")

    async def init_all_agents(self):
        """初始化所有智能体实例（基础实例，不包含用户特定的实例）"""
        for agent_class in self._classes.values():
            if agent_class.name not in self._instances:
                try:
                    # 创建基础实例，无用户上下文
                    instance = await self._create_agent_instance(agent_class)
                    self._instances[agent_class.name] = instance
                    logger.debug(f"初始化智能体实例: {agent_class.name}")
                except Exception as e:
                    logger.error(f"初始化智能体实例失败 {agent_class.name}: {e}")

    async def _create_agent_instance(self, agent_class):
        """创建智能体实例，注入依赖"""
        try:
            # 获取依赖
            db_manager = await self._dependencies.db_manager
            permission_engine = await self._dependencies.permission_engine
            kb_manager = await self._dependencies.kb_manager
            
            # 创建实例并注入依赖
            instance = agent_class(
                db_manager=db_manager,
                permission_engine=permission_engine,
                kb_manager=kb_manager
            )
            
            return instance
        except Exception as e:
            logger.error(f"创建智能体实例失败 {agent_class}: {e}")
            # 降级处理：创建无依赖注入的实例
            return agent_class()

    async def get_agent(self, 
                       agent_name: str, 
                       user_context: Optional['UserContext'] = None,
                       **kwargs) -> 'BaseAgent':
        """
        获取智能体实例
        
        Args:
            agent_name: 智能体名称
            user_context: 用户上下文（可选）
            **kwargs: 其他参数
            
        Returns:
            BaseAgent: 智能体实例
            
        Raises:
            PermissionError: 无权限访问智能体
            ValueError: 智能体不存在
        """
        # 确保管理器已初始化
        if not self._initialized:
            await self.initialize()
        
        # 检查智能体是否存在
        if agent_name not in self._classes:
            raise ValueError(f"智能体不存在: {agent_name}")
        
        # 权限检查
        if user_context:
            if not await self._check_agent_permission(user_context, agent_name, "access"):
                raise PermissionError(f"用户无权访问智能体: {agent_name}")
        
        # 获取或创建实例
        if user_context:
            # 为特定用户创建专用实例
            instance_key = f"{agent_name}_{user_context.user_id}"
            if instance_key not in self._instances:
                agent_class = self._classes[agent_name]
                self._instances[instance_key] = await self._create_agent_instance(agent_class)
                logger.debug(f"为用户 {user_context.user_id} 创建智能体实例: {agent_name}")
            
            return self._instances[instance_key]
        else:
            # 返回基础实例
            if agent_name not in self._instances:
                agent_class = self._classes[agent_name]
                self._instances[agent_name] = await self._create_agent_instance(agent_class)
            
            return self._instances[agent_name]

    async def execute_agent(self, 
                           agent_name: str, 
                           messages: List, 
                           user_context: 'UserContext',
                           config: Optional['RunnableConfig'] = None,
                           stream_mode: str = "messages",
                           stream: bool = True) -> Union[AsyncIterator[Any], Any]:
        """
        执行智能体 - 需要用户上下文和权限检查
        
        Args:
            agent_name: 智能体名称
            messages: 消息列表
            user_context: 用户上下文
            config: 运行时配置
            stream_mode: 流模式（"messages" 或 "values"）
            
        Returns:
            智能体执行结果
            
        Raises:
            PermissionError: 无权限执行智能体
        """
        # 权限检查
        if not await self._check_agent_permission(user_context, agent_name, "execute"):
            raise PermissionError(f"用户无权执行智能体: {agent_name}")
        
        # 获取智能体实例
        agent = await self.get_agent(agent_name, user_context)
        
        # 构建运行时配置
        if config is None:
            from langchain_core.runnables import RunnableConfig
            config = RunnableConfig(configurable={})
        
        # 确保配置对象有configurable字段
        if "configurable" not in config:
            config["configurable"] = {}
            
        # 确保配置中包含用户上下文
        config["configurable"]["user_context"] = user_context
        
        # 执行智能体
        try:
            if stream:
                # 流式执行
                if stream_mode == "values":
                    return agent.stream_values(messages, config, user_context)
                else:
                    return agent.stream_messages(messages, config, user_context)
            else:
                # 非流式执行 - 收集完整结果
                result_messages = []
                if stream_mode == "values":
                    async for chunk in agent.stream_values(messages, config, user_context):
                        result_messages.append(chunk)
                else:
                    async for chunk in agent.stream_messages(messages, config, user_context):
                        result_messages.append(chunk)
                
                # 返回最后一个消息或所有消息
                if result_messages:
                    return result_messages[-1] if len(result_messages) == 1 else result_messages
                else:
                    return {"error": "No response generated"}
                    
        except Exception as e:
            logger.error(f"智能体执行失败 {agent_name}: {e}")
            raise

    async def _check_agent_permission(self, user_context: 'UserContext', agent_name: str, permission: str) -> bool:
        """
        检查智能体权限
        
        Args:
            user_context: 用户上下文
            agent_name: 智能体名称
            permission: 权限类型（access, execute）
            
        Returns:
            bool: 是否有权限
        """
        try:
            # 超级管理员权限
            if user_context.has_permission("*:*"):
                return True
            
            # 检查具体智能体权限
            agent_permission = f"agent:{agent_name}:{permission}"
            if user_context.has_permission(agent_permission):
                return True
            
            # 检查通用智能体权限
            if user_context.has_permission(f"agent:{permission}"):
                return True
            
            # 通过权限引擎进行详细检查
            permission_engine = await self._dependencies.permission_engine
            
            from server.auth.permission_framework.resources import AgentResource
            from server.auth.permission_framework.core import Permission
            
            # 验证权限是否为有效枚举值
            try:
                perm_enum = Permission(permission)
            except ValueError:
                logger.warning(f"无效权限类型: {permission}, 使用默认检查")
                # 对于非标准权限，依赖前面的字符串匹配检查
                return False
            
            return await permission_engine.check_permission_simple(
                user_id=user_context.user_id,
                resource=AgentResource(agent_name),
                permission=perm_enum
            )
            
        except Exception as e:
            logger.warning(f"智能体权限检查失败 {agent_name}: {e}")
            return False

    def get_agents(self) -> List['BaseAgent']:
        """获取所有智能体实例"""
        return list(self._instances.values())

    async def get_agents_info(self, user_context: Optional['UserContext'] = None) -> List[Dict[str, Any]]:
        """
        获取智能体信息
        
        Args:
            user_context: 用户上下文，用于权限过滤
            
        Returns:
            List[Dict[str, Any]]: 智能体信息列表
        """
        if not self._initialized:
            await self.initialize()
        
        agents_info = []
        
        for agent_name, agent_class in self._classes.items():
            try:
                # 权限检查
                if user_context and not await self._check_agent_permission(user_context, agent_name, "access"):
                    continue
                
                # 获取智能体实例
                agent = await self.get_agent(agent_name, user_context)
                agent_info = await agent.get_info()
                
                # 添加权限信息
                if user_context:
                    agent_info["permissions"] = {
                        "access": await self._check_agent_permission(user_context, agent_name, "access"),
                        "execute": await self._check_agent_permission(user_context, agent_name, "execute")
                    }
                
                agents_info.append(agent_info)
                
            except Exception as e:
                logger.error(f"获取智能体信息失败 {agent_name}: {e}")
        
        return agents_info

    async def get_available_tools(self, user_context: 'UserContext') -> Dict[str, Any]:
        """
        获取用户可用工具
        
        Args:
            user_context: 用户上下文
            
        Returns:
            Dict[str, Any]: 可用工具字典
        """
        if not self._tools_factory:
            await self.initialize()
        
        return await self._tools_factory.get_user_tools(user_context)

    def clear_user_cache(self, user_id: str):
        """
        清除用户相关的缓存
        
        Args:
            user_id: 用户ID
        """
        # 清除用户智能体实例
        keys_to_remove = [key for key in self._instances.keys() if key.endswith(f"_{user_id}")]
        for key in keys_to_remove:
            del self._instances[key]
        
        # 清除工具缓存
        if self._tools_factory:
            self._tools_factory.clear_cache(user_id)
        
        logger.debug(f"已清除用户 {user_id} 的缓存")

    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            Dict[str, Any]: 健康状态信息
        """
        health_status = {
            "initialized": self._initialized,
            "registered_agents": list(self._classes.keys()),
            "active_instances": len(self._instances),
            "dependencies": {},
            "tools_factory": bool(self._tools_factory)
        }
        
        if self._initialized:
            try:
                health_status["dependencies"] = await self._dependencies.health_check()
            except Exception as e:
                logger.error(f"依赖健康检查失败: {e}")
                health_status["dependencies"] = {"error": str(e)}
        
        return health_status


# === 全局实例和向后兼容 ===

agent_manager = AgentManager()
agent_manager.register_agent(ChatbotAgent)
agent_manager.register_agent(ReActAgent)

# 向后兼容的初始化函数
async def init_agent_manager():
    """
    初始化智能体管理器 - 向后兼容
    
    建议在应用启动时调用此函数
    """
    await agent_manager.initialize()

# 向后兼容的同步初始化（旧版本API）
def init_all_agents_sync():
    """
    同步初始化所有智能体 - 向后兼容
    
    注意：此函数为向后兼容而保留，建议使用异步版本
    """
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果事件循环正在运行，创建任务
            asyncio.create_task(agent_manager.initialize())
        else:
            # 如果事件循环未运行，直接运行
            loop.run_until_complete(agent_manager.initialize())
    except Exception as e:
        logger.warning(f"同步初始化失败，将在首次使用时异步初始化: {e}")

# 保持向后兼容的全局函数
def get_agent_legacy(agent_name: str, **kwargs):
    """
    获取智能体 - 向后兼容的旧版本接口
    
    注意：此函数不包含权限检查，建议使用新的异步接口
    """
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 在运行的事件循环中使用
            return asyncio.create_task(agent_manager.get_agent(agent_name, **kwargs))
        else:
            # 直接运行
            return loop.run_until_complete(agent_manager.get_agent(agent_name, **kwargs))
    except Exception as e:
        logger.error(f"获取智能体失败: {e}")
        raise

async def get_agents_info_legacy():
    """
    获取智能体信息 - 向后兼容
    """
    return await agent_manager.get_agents_info()

# 向后兼容：尝试同步初始化（如果可能）
try:
    init_all_agents_sync()
except Exception as e:
    logger.info(f"智能体管理器将在首次使用时初始化: {e}")

__all__ = [
    "agent_manager", 
    "init_agent_manager",
    "get_agent_legacy", 
    "get_agents_info_legacy"
]


if __name__ == "__main__":
    # 测试代码
    async def test_agent_manager():
        """测试智能体管理器"""
        print("=== 智能体管理器测试 ===")
        
        # 初始化
        await agent_manager.initialize()
        print("✅ 智能体管理器初始化完成")
        
        # 健康检查
        health = await agent_manager.health_check()
        print(f"📊 健康状态: {health}")
        
        # 获取智能体信息
        agents_info = await agent_manager.get_agents_info()
        print(f"🤖 可用智能体: {[info['name'] for info in agents_info]}")
    
    # 运行测试
    import asyncio
    asyncio.run(test_agent_manager())
