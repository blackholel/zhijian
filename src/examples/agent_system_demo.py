"""
Yuxi-Know 增强智能体系统演示
展示完整的多Agent协作研究流程
"""
import asyncio
import logging
from typing import Dict, List, Any
from datetime import datetime

# 导入核心模块
from ..agents.manager import AgentManager
from ..agents.orchestrator import ResearchOrchestrator
from ..research.workflow import WorkflowEngine
from ..research.models import ResearchRequest, WorkflowType
from ..agents.base.agent import AgentConfig, AgentType
from ..core.error_handling import (
    global_error_handler, 
    global_retry_manager,
    retry,
    handle_errors,
    YuxiKnowError
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentSystemDemo:
    """智能体系统演示"""
    
    def __init__(self):
        self.agent_manager = AgentManager()
        self.orchestrator = ResearchOrchestrator()
        self.workflow_engine = WorkflowEngine()
        
    async def initialize(self):
        """初始化系统"""
        logger.info("正在初始化智能体系统...")
        
        try:
            # 初始化各个组件
            await self.orchestrator.initialize()
            await self.workflow_engine.initialize()
            
            logger.info("系统初始化完成")
            
        except Exception as e:
            logger.error(f"系统初始化失败: {e}")
            raise
    
    @retry()
    @handle_errors(global_error_handler)
    async def demo_single_agent_creation(self) -> str:
        """演示单个Agent创建"""
        logger.info("=== 演示单个Agent创建 ===")
        
        # 创建研究员Agent配置
        config = AgentConfig(
            agent_id="demo_researcher_001",
            agent_type=AgentType.RESEARCHER,
            name="演示研究员",
            description="用于演示的研究员智能体",
            capabilities=[],
            selected_knowledge_bases=["demo_kb_1", "demo_kb_2"],
            selected_mcp_tools=["web_search", "text_analyzer"],
            llm_config={
                "provider": "openai",
                "model": "gpt-4",
                "temperature": 0.7
            },
            prompt_templates={},
            user_id="demo_user",
            organization_id="demo_org"
        )
        
        # 创建Agent
        agent = await self.agent_manager.create_agent(config)
        
        logger.info(f"成功创建Agent: {agent.config.agent_id}")
        
        # 测试Agent执行
        test_task = {
            "task_type": "query",
            "query": "什么是人工智能？",
            "knowledge_bases": ["demo_kb_1"],
            "mode": "hybrid",
            "limit": 5
        }
        
        result = await agent.execute(test_task)
        logger.info(f"Agent执行结果: {result.get('success', False)}")
        
        return agent.config.agent_id
    
    async def demo_multi_agent_collaboration(self) -> str:
        """演示多Agent协作"""
        logger.info("=== 演示多Agent协作 ===")
        
        # 启动研究任务
        session_id = await self.orchestrator.start_research(
            user_id="demo_user",
            topic="大语言模型的发展趋势",
            objective="深入了解大语言模型的技术发展、应用场景和未来趋势",
            knowledge_bases=["ai_research_kb", "tech_trends_kb"],
            mcp_tools=["academic_search", "trend_analyzer"],
            strategy="adaptive"
        )
        
        logger.info(f"启动研究会话: {session_id}")
        
        # 监控研究进度
        await self._monitor_research_progress(session_id)
        
        return session_id
    
    async def demo_workflow_execution(self) -> str:
        """演示工作流执行"""
        logger.info("=== 演示工作流执行 ===")
        
        # 创建研究请求
        research_request = ResearchRequest(
            topic="量子计算的商业应用",
            objective="分析量子计算在不同商业领域的应用潜力和挑战",
            knowledge_bases=["quantum_computing_kb", "business_analysis_kb"],
            mcp_tools=["market_analyzer", "tech_evaluator"],
            workflow_type=WorkflowType.DEEP,
            config={
                "analysis_depth": "comprehensive",
                "output_formats": ["markdown", "html"],
                "quality_thresholds": {
                    "min_findings": 10,
                    "min_confidence": 0.8
                }
            }
        )
        
        # 启动工作流
        execution_id = await self.workflow_engine.start_workflow(
            workflow_id=research_request.workflow_type.value,
            session_id=f"demo_workflow_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            user_id="demo_user",
            initial_data={
                "topic": research_request.topic,
                "objective": research_request.objective,
                "knowledge_bases": research_request.knowledge_bases,
                "mcp_tools": research_request.mcp_tools,
                "config": research_request.config
            }
        )
        
        logger.info(f"启动工作流执行: {execution_id}")
        
        # 监控工作流执行
        await self._monitor_workflow_execution(execution_id)
        
        return execution_id
    
    async def demo_error_handling(self):
        """演示错误处理"""
        logger.info("=== 演示错误处理 ===")
        
        try:
            # 故意触发错误
            raise YuxiKnowError(
                "这是一个演示错误",
                error_type=ErrorType.AGENT_ERROR,
                severity=ErrorSeverity.MEDIUM,
                details={"demo": True},
                context={"operation": "error_demo"}
            )
            
        except YuxiKnowError as e:
            error_info = await global_error_handler.handle_error(e)
            logger.info(f"错误已处理: {error_info.error_id}")
        
        # 演示重试机制
        retry_count = 0
        
        @retry()
        async def failing_function():
            nonlocal retry_count
            retry_count += 1
            if retry_count < 3:
                raise Exception(f"模拟失败 {retry_count}")
            return f"成功执行 (尝试了 {retry_count} 次)"
        
        try:
            result = await failing_function()
            logger.info(f"重试成功: {result}")
        except Exception as e:
            logger.error(f"重试最终失败: {e}")
    
    async def demo_knowledge_base_integration(self):
        """演示知识库集成"""
        logger.info("=== 演示知识库集成 ===")
        
        # 模拟知识库查询
        from ..agents.knowledge.kb_manager import KnowledgeBaseManager
        
        kb_manager = KnowledgeBaseManager()
        
        # 加载知识库
        kb = await kb_manager.load_knowledge_base("demo_kb", "demo_user")
        
        if kb:
            # 执行查询
            results = await kb_manager.query_knowledge_bases(
                query="人工智能的历史发展",
                kb_ids=["demo_kb"],
                user_id="demo_user",
                limit=5
            )
            
            logger.info(f"知识库查询结果: {len(results)} 条")
            
            # 显示结果摘要
            for i, result in enumerate(results[:3]):
                logger.info(f"结果 {i+1}: {result.get('content', '')[:100]}...")
        else:
            logger.warning("知识库加载失败")
    
    async def demo_mcp_tools_integration(self):
        """演示MCP工具集成"""
        logger.info("=== 演示MCP工具集成 ===")
        
        from ..mcp_integration.registry import MCPRegistry
        
        mcp_registry = MCPRegistry()
        
        # 注册演示MCP服务器
        await mcp_registry.register_server(
            server_name="demo_server",
            server_config={
                "type": "stdio",
                "command": "demo_mcp_server",
                "args": [],
                "env": {}
            }
        )
        
        # 列出可用工具
        tools = await mcp_registry.list_tools()
        logger.info(f"可用MCP工具: {len(tools)} 个")
        
        # 调用演示工具
        if tools:
            tool_name = tools[0].name
            result = await mcp_registry.call_tool(
                tool_name=tool_name,
                arguments={"query": "test"},
                user_id="demo_user"
            )
            
            logger.info(f"MCP工具调用结果: {result.get('success', False)}")
    
    async def _monitor_research_progress(self, session_id: str):
        """监控研究进度"""
        logger.info(f"开始监控研究进度: {session_id}")
        
        max_wait_time = 300  # 5分钟超时
        check_interval = 10   # 每10秒检查一次
        elapsed_time = 0
        
        while elapsed_time < max_wait_time:
            try:
                status = await self.orchestrator.get_session_status(session_id)
                
                logger.info(f"研究进度: {status['progress']:.2%} - 状态: {status['status']}")
                
                if status['status'] in ['completed', 'failed', 'cancelled']:
                    break
                
                await asyncio.sleep(check_interval)
                elapsed_time += check_interval
                
            except Exception as e:
                logger.error(f"获取研究状态失败: {e}")
                break
        
        # 获取最终结果
        try:
            results = await self.orchestrator.get_session_results(session_id)
            logger.info(f"研究完成，生成了 {len(results.get('execution_results', []))} 个执行结果")
            
            if results.get('final_report'):
                logger.info("已生成最终研究报告")
            
        except Exception as e:
            logger.error(f"获取研究结果失败: {e}")
    
    async def _monitor_workflow_execution(self, execution_id: str):
        """监控工作流执行"""
        logger.info(f"开始监控工作流执行: {execution_id}")
        
        max_wait_time = 300  # 5分钟超时
        check_interval = 10   # 每10秒检查一次
        elapsed_time = 0
        
        while elapsed_time < max_wait_time:
            try:
                status = await self.workflow_engine.get_execution_status(execution_id)
                
                logger.info(f"工作流进度: {status['progress']:.2%} - 当前节点: {status['current_node']}")
                
                if status['status'] in ['completed', 'failed', 'cancelled']:
                    break
                
                await asyncio.sleep(check_interval)
                elapsed_time += check_interval
                
            except Exception as e:
                logger.error(f"获取工作流状态失败: {e}")
                break
        
        # 获取最终结果
        try:
            result = await self.workflow_engine.get_execution_result(execution_id)
            logger.info(f"工作流完成，执行了 {len(result.get('workflow_events', []))} 个事件")
            
            if result.get('orchestrator_results', {}).get('final_report'):
                logger.info("已生成最终工作流报告")
            
        except Exception as e:
            logger.error(f"获取工作流结果失败: {e}")
    
    async def run_complete_demo(self):
        """运行完整演示"""
        logger.info("开始运行Yuxi-Know增强智能体系统完整演示")
        
        try:
            # 初始化系统
            await self.initialize()
            
            # 1. 单个Agent创建演示
            agent_id = await self.demo_single_agent_creation()
            
            # 2. 知识库集成演示
            await self.demo_knowledge_base_integration()
            
            # 3. MCP工具集成演示
            await self.demo_mcp_tools_integration()
            
            # 4. 错误处理演示
            await self.demo_error_handling()
            
            # 5. 多Agent协作演示
            session_id = await self.demo_multi_agent_collaboration()
            
            # 6. 工作流执行演示
            execution_id = await self.demo_workflow_execution()
            
            logger.info("完整演示运行成功！")
            
            # 输出演示总结
            await self._generate_demo_summary(agent_id, session_id, execution_id)
            
        except Exception as e:
            logger.error(f"演示运行失败: {e}")
            raise
        
        finally:
            # 清理资源
            await self._cleanup()
    
    async def _generate_demo_summary(self, agent_id: str, session_id: str, execution_id: str):
        """生成演示总结"""
        logger.info("=== 演示总结 ===")
        
        summary = {
            "演示时间": datetime.now().isoformat(),
            "创建的Agent": agent_id,
            "研究会话": session_id,
            "工作流执行": execution_id,
            "系统特性": [
                "✅ 动态Agent创建和管理",
                "✅ 知识库动态加载和查询",
                "✅ MCP工具集成和调用",
                "✅ 多Agent协作和编排",
                "✅ 工作流状态管理",
                "✅ 错误处理和重试机制",
                "✅ 实时监控和状态跟踪"
            ],
            "核心优势": [
                "🔧 模块化架构设计",
                "🔄 智能重试和容错",
                "📊 全面的状态监控",
                "🛡️ 完善的权限控制",
                "⚡ 异步高性能处理",
                "🔌 可插拔工具生态",
                "📈 可扩展性设计"
            ]
        }
        
        logger.info("演示总结:")
        for key, value in summary.items():
            if isinstance(value, list):
                logger.info(f"{key}:")
                for item in value:
                    logger.info(f"  {item}")
            else:
                logger.info(f"{key}: {value}")
    
    async def _cleanup(self):
        """清理资源"""
        logger.info("正在清理演示资源...")
        
        try:
            # 关闭工作流引擎
            await self.workflow_engine.shutdown()
            
            # 关闭编排器
            await self.orchestrator.shutdown()
            
            logger.info("资源清理完成")
            
        except Exception as e:
            logger.error(f"资源清理失败: {e}")


# 运行演示
async def main():
    """主函数"""
    demo = AgentSystemDemo()
    await demo.run_complete_demo()


if __name__ == "__main__":
    # 设置错误处理回调
    async def log_error_callback(error_info):
        logger.warning(f"错误回调触发: {error_info.error_type.value} - {error_info.message}")
    
    global_error_handler.register_callback(log_error_callback)
    
    # 运行演示
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("演示被用户中断")
    except Exception as e:
        logger.error(f"演示运行异常: {e}")
        raise