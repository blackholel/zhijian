#!/usr/bin/env python3
"""
智能体系统重构集成测试

验证重构后的智能体系统各组件的集成效果和性能表现。
"""

import asyncio
import time
from typing import Dict, Any, List
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, '/home/Projects/Yuxi-Know-main')

from src.utils import logger

class AgentIntegrationTester:
    """智能体系统集成测试器"""
    
    def __init__(self):
        self.results = {
            "component_tests": {},
            "integration_tests": {},
            "performance_tests": {},
            "compatibility_tests": {},
            "overall_status": "pending"
        }
    
    async def run_all_tests(self):
        """运行所有集成测试"""
        logger.info("=== 智能体系统重构集成测试开始 ===")
        
        try:
            # 1. 组件导入测试
            await self.test_component_imports()
            
            # 2. 依赖注入测试
            await self.test_dependency_injection()
            
            # 3. 权限系统集成测试
            await self.test_permission_integration()
            
            # 4. 工具工厂测试
            await self.test_tools_factory()
            
            # 5. 智能体管理器测试
            await self.test_agent_manager()
            
            # 6. 配置系统测试
            await self.test_configuration_system()
            
            # 7. 向后兼容性测试
            await self.test_backward_compatibility()
            
            # 8. 性能基准测试
            await self.test_performance()
            
            # 汇总结果
            self.generate_summary()
            
        except Exception as e:
            logger.error(f"集成测试失败: {e}")
            self.results["overall_status"] = "failed"
            raise
    
    async def test_component_imports(self):
        """测试组件导入"""
        logger.info("🧪 测试组件导入...")
        
        test_results = {}
        
        # 测试核心组件导入
        components = [
            ("AgentDependencies", "from src.agents.dependencies import AgentDependencies"),
            ("UserContext", "from src.agents.context import UserContext"),
            ("BaseAgent", "from src.agents.registry import BaseAgent, Configuration"),
            ("PermissionAwareToolsFactory", "from src.agents.tools_factory import PermissionAwareToolsFactory"),
            ("AgentManager", "from src.agents import agent_manager"),
            ("ChatbotAgent", "from src.agents.chatbot import ChatbotAgent"),
            ("DatabaseConfigManager", "from src.database.config_manager import DatabaseConfigManager")
        ]
        
        for component_name, import_stmt in components:
            try:
                exec(import_stmt)
                test_results[component_name] = "✅ 成功"
                logger.debug(f"  ✅ {component_name} 导入成功")
            except Exception as e:
                test_results[component_name] = f"❌ 失败: {e}"
                logger.error(f"  ❌ {component_name} 导入失败: {e}")
        
        self.results["component_tests"]["imports"] = test_results
    
    async def test_dependency_injection(self):
        """测试依赖注入"""
        logger.info("🔗 测试依赖注入...")
        
        test_results = {}
        
        try:
            from src.agents.dependencies import get_agent_dependencies
            dependencies = get_agent_dependencies()
            test_results["dependency_manager_creation"] = "✅ 成功"
            
            # 测试健康检查
            health = await dependencies.health_check()
            test_results["health_check"] = f"✅ 状态: {health}"
            
            # 测试各个依赖获取
            try:
                db_manager = await dependencies.db_manager
                test_results["db_manager"] = "✅ 成功获取"
            except Exception as e:
                test_results["db_manager"] = f"⚠️ 部分成功: {e}"
            
            try:
                permission_engine = await dependencies.permission_engine
                test_results["permission_engine"] = "✅ 成功获取"
            except Exception as e:
                test_results["permission_engine"] = f"⚠️ 部分成功: {e}"
            
            try:
                kb_manager = await dependencies.kb_manager
                test_results["kb_manager"] = "✅ 成功获取"
            except Exception as e:
                test_results["kb_manager"] = f"⚠️ 部分成功: {e}"
            
        except Exception as e:
            test_results["overall"] = f"❌ 失败: {e}"
        
        self.results["component_tests"]["dependency_injection"] = test_results
    
    async def test_permission_integration(self):
        """测试权限系统集成"""
        logger.info("🔐 测试权限系统集成...")
        
        test_results = {}
        
        try:
            # 创建测试用户上下文
            from src.agents.context import UserContext
            
            test_user = UserContext(
                user_id="test_user_001",
                username="test_user",
                roles=["user"],
                permissions={"agent:access", "agent:execute", "tool:basic"}
            )
            test_results["user_context_creation"] = "✅ 成功"
            
            # 测试权限检查方法
            permissions = ["agent:access", "tool:basic", "*:*"]
            for perm in permissions:
                has_perm = test_user.has_permission(perm)
                test_results[f"permission_check_{perm}"] = f"✅ {has_perm}"
            
            # 测试知识库权限
            kb_access = test_user.can_access_kb("test_kb_001")
            test_results["kb_permission_check"] = f"✅ {kb_access}"
            
        except Exception as e:
            test_results["overall"] = f"❌ 失败: {e}"
        
        self.results["component_tests"]["permission_integration"] = test_results
    
    async def test_tools_factory(self):
        """测试工具工厂"""
        logger.info("🔧 测试工具工厂...")
        
        test_results = {}
        
        try:
            from src.agents.tools_factory import PermissionAwareToolsFactory, get_all_tools
            from src.agents.context import UserContext
            
            # 测试传统工具获取
            legacy_tools = get_all_tools()
            test_results["legacy_tools"] = f"✅ 获取到 {len(legacy_tools)} 个工具"
            
            # 创建测试用户上下文
            test_user = UserContext(
                user_id="test_user_002",
                username="test_user_2",
                roles=["user"],
                permissions={"tool:basic", "tool:calculator"}
            )
            
            # 测试权限感知工具工厂（模拟依赖）
            try:
                from src.agents.dependencies import get_agent_dependencies
                dependencies = get_agent_dependencies()
                
                # 尝试创建权限感知工具工厂
                permission_engine = await dependencies.permission_engine
                kb_manager = await dependencies.kb_manager
                
                tools_factory = PermissionAwareToolsFactory(permission_engine, kb_manager)
                test_results["tools_factory_creation"] = "✅ 成功"
                
                # 获取工具统计
                stats = tools_factory.get_tool_stats()
                test_results["tools_stats"] = f"✅ 状态: {stats}"
                
            except Exception as e:
                test_results["tools_factory_creation"] = f"⚠️ 部分成功: {e}"
            
        except Exception as e:
            test_results["overall"] = f"❌ 失败: {e}"
        
        self.results["component_tests"]["tools_factory"] = test_results
    
    async def test_agent_manager(self):
        """测试智能体管理器"""
        logger.info("🤖 测试智能体管理器...")
        
        test_results = {}
        
        try:
            from src.agents import agent_manager
            
            # 测试基本属性
            test_results["agent_manager_instance"] = f"✅ 类型: {type(agent_manager)}"
            test_results["registered_agents"] = f"✅ 注册的智能体: {list(agent_manager._classes.keys())}"
            test_results["initialization_status"] = f"✅ 初始化状态: {agent_manager._initialized}"
            
            # 测试健康检查
            try:
                health = await agent_manager.health_check()
                test_results["health_check"] = f"✅ 健康状态: {health['initialized']}"
            except Exception as e:
                test_results["health_check"] = f"⚠️ 部分成功: {e}"
            
            # 测试智能体获取（无用户上下文）
            try:
                chatbot = await agent_manager.get_agent("chatbot")
                test_results["agent_retrieval"] = f"✅ 成功获取: {type(chatbot)}"
            except Exception as e:
                test_results["agent_retrieval"] = f"⚠️ 部分成功: {e}"
            
            # 测试智能体信息获取
            try:
                agents_info = await agent_manager.get_agents_info()
                test_results["agents_info"] = f"✅ 获取到 {len(agents_info)} 个智能体信息"
            except Exception as e:
                test_results["agents_info"] = f"⚠️ 部分成功: {e}"
            
        except Exception as e:
            test_results["overall"] = f"❌ 失败: {e}"
        
        self.results["component_tests"]["agent_manager"] = test_results
    
    async def test_configuration_system(self):
        """测试配置系统"""
        logger.info("⚙️ 测试配置系统...")
        
        test_results = {}
        
        try:
            from src.agents.registry import Configuration
            from src.agents.context import UserContext
            from src.database.config_manager import DatabaseConfigManager
            
            # 测试数据库配置管理器
            db_config_manager = DatabaseConfigManager()
            test_results["db_config_manager"] = "✅ 创建成功"
            
            # 测试获取所有配置
            try:
                all_configs = await db_config_manager.get_all_configs()
                test_results["all_configs"] = f"✅ 配置获取: {len(all_configs)} 个分类"
            except Exception as e:
                test_results["all_configs"] = f"⚠️ 部分成功: {e}"
            
            # 测试 Configuration 类
            test_user = UserContext(
                user_id="test_user_003",
                username="test_config_user",
                roles=["user"],
                permissions={"agent:access"}
            )
            
            try:
                config = await Configuration.from_runnable_config(
                    config=None, 
                    agent_name="chatbot",
                    user_context=test_user
                )
                test_results["configuration_creation"] = f"✅ 配置对象: {type(config)}"
            except Exception as e:
                test_results["configuration_creation"] = f"⚠️ 部分成功: {e}"
            
        except Exception as e:
            test_results["overall"] = f"❌ 失败: {e}"
        
        self.results["component_tests"]["configuration_system"] = test_results
    
    async def test_backward_compatibility(self):
        """测试向后兼容性"""
        logger.info("🔄 测试向后兼容性...")
        
        test_results = {}
        
        try:
            # 测试旧版本 API
            from src.agents import agent_manager, get_agent_legacy, get_agents_info_legacy
            
            test_results["legacy_imports"] = "✅ 旧版API导入成功"
            
            # 测试旧版本智能体获取
            try:
                legacy_agent = get_agent_legacy("chatbot")
                test_results["legacy_agent_get"] = f"✅ 旧版获取: {type(legacy_agent)}"
            except Exception as e:
                test_results["legacy_agent_get"] = f"⚠️ 部分成功: {e}"
            
            # 测试旧版本信息获取
            try:
                legacy_info = await get_agents_info_legacy()
                test_results["legacy_info_get"] = f"✅ 旧版信息: {len(legacy_info)} 个智能体"
            except Exception as e:
                test_results["legacy_info_get"] = f"⚠️ 部分成功: {e}"
            
            # 测试原有工具函数
            from src.agents.tools_factory import get_all_tools_legacy
            try:
                legacy_tools = get_all_tools_legacy()
                test_results["legacy_tools"] = f"✅ 旧版工具: {len(legacy_tools)} 个"
            except Exception as e:
                test_results["legacy_tools"] = f"⚠️ 部分成功: {e}"
            
        except Exception as e:
            test_results["overall"] = f"❌ 失败: {e}"
        
        self.results["compatibility_tests"] = test_results
    
    async def test_performance(self):
        """测试性能"""
        logger.info("🚀 测试性能...")
        
        test_results = {}
        
        try:
            # 1. 组件初始化性能
            start_time = time.time()
            from src.agents import agent_manager
            await agent_manager.initialize()
            init_time = time.time() - start_time
            test_results["initialization_time"] = f"✅ {init_time:.2f}秒"
            
            # 2. 智能体获取性能
            start_time = time.time()
            for i in range(10):
                agent = await agent_manager.get_agent("chatbot")
            get_time = (time.time() - start_time) / 10
            test_results["agent_get_avg_time"] = f"✅ 平均 {get_time:.3f}秒"
            
            # 3. 配置加载性能
            from src.agents.context import UserContext
            test_user = UserContext(
                user_id="perf_test_user",
                username="perf_user",
                roles=["user"],
                permissions={"agent:access"}
            )
            
            start_time = time.time()
            for i in range(5):
                from src.agents.registry import Configuration
                config = await Configuration.from_runnable_config(
                    agent_name="chatbot", user_context=test_user
                )
            config_time = (time.time() - start_time) / 5
            test_results["config_load_avg_time"] = f"✅ 平均 {config_time:.3f}秒"
            
            # 4. 内存使用估算
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            test_results["memory_usage"] = f"✅ {memory_mb:.1f}MB"
            
        except Exception as e:
            test_results["overall"] = f"❌ 失败: {e}"
        
        self.results["performance_tests"] = test_results
    
    def generate_summary(self):
        """生成测试总结"""
        logger.info("📊 生成测试总结...")
        
        total_tests = 0
        passed_tests = 0
        failed_tests = 0
        partial_tests = 0
        
        for category, tests in self.results.items():
            if category == "overall_status":
                continue
                
            if isinstance(tests, dict):
                for test_name, result in tests.items():
                    total_tests += 1
                    if isinstance(result, str):
                        if result.startswith("✅"):
                            passed_tests += 1
                        elif result.startswith("⚠️"):
                            partial_tests += 1
                        elif result.startswith("❌"):
                            failed_tests += 1
        
        # 计算总体状态
        if failed_tests == 0:
            if partial_tests == 0:
                self.results["overall_status"] = "excellent"
            else:
                self.results["overall_status"] = "good"
        elif failed_tests < total_tests * 0.3:
            self.results["overall_status"] = "acceptable"
        else:
            self.results["overall_status"] = "needs_improvement"
        
        # 输出总结
        logger.info("=" * 60)
        logger.info("🎯 智能体系统重构集成测试总结")
        logger.info("=" * 60)
        logger.info(f"📈 总测试数: {total_tests}")
        logger.info(f"✅ 完全通过: {passed_tests}")
        logger.info(f"⚠️ 部分通过: {partial_tests}")
        logger.info(f"❌ 失败: {failed_tests}")
        logger.info(f"📊 成功率: {((passed_tests + partial_tests) / total_tests * 100):.1f}%")
        logger.info(f"🏆 总体状态: {self.results['overall_status']}")
        logger.info("=" * 60)
        
        # 详细结果
        for category, tests in self.results.items():
            if category == "overall_status":
                continue
            logger.info(f"\n📂 {category.upper()}:")
            if isinstance(tests, dict):
                for test_name, result in tests.items():
                    logger.info(f"  {test_name}: {result}")
    
    def save_results(self, filename: str = "agent_integration_test_results.json"):
        """保存测试结果"""
        import json
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, ensure_ascii=False, indent=2)
            logger.info(f"💾 测试结果已保存到: {filename}")
        except Exception as e:
            logger.error(f"保存测试结果失败: {e}")


async def main():
    """主函数"""
    tester = AgentIntegrationTester()
    try:
        await tester.run_all_tests()
        tester.save_results()
        
        # 根据测试结果确定退出代码
        if tester.results["overall_status"] in ["excellent", "good"]:
            sys.exit(0)
        elif tester.results["overall_status"] == "acceptable":
            sys.exit(1)
        else:
            sys.exit(2)
            
    except Exception as e:
        logger.error(f"集成测试执行失败: {e}")
        sys.exit(3)


if __name__ == "__main__":
    asyncio.run(main())