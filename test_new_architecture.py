"""
新数据库架构测试脚本

验证统一数据库管理器的功能
"""

import asyncio
import sys
import os

# 添加项目路径
sys.path.append('/home/Projects/Yuxi-Know-main')

from src.database.manager import UnifiedDatabaseManager
from src.database.repositories.user_repository import UserInfo
from src.utils.logging_config import logger


async def test_database_architecture():
    """测试新数据库架构"""
    print("🔄 开始测试新数据库架构...")
    
    # 创建数据库管理器
    async with UnifiedDatabaseManager() as db_manager:
        print("✅ 数据库管理器创建成功")
        
        # 测试健康检查
        print("\n🔍 执行健康检查...")
        health = await db_manager.health_check()
        print(f"健康状态: {health.get('status', 'unknown')}")
        
        # 测试数据库连接
        print("\n🔗 测试数据库连接...")
        connection_summary = db_manager.connection_manager.get_connection_summary()
        print(f"连接总数: {connection_summary.get('total_adapters', 0)}")
        print(f"已连接: {connection_summary.get('connected_count', 0)}")
        print(f"连接错误: {connection_summary.get('error_count', 0)}")
        
        # 测试适配器
        print("\n🔌 测试数据库适配器...")
        adapters = ['server_db', 'neo4j', 'redis', 'milvus', 'minio']
        for adapter_name in adapters:
            try:
                adapter = await db_manager.connection_manager.get_adapter(adapter_name)
                if adapter:
                    print(f"  ✅ {adapter_name}: 可用")
                else:
                    print(f"  ❌ {adapter_name}: 不可用")
            except Exception as e:
                print(f"  ⚠️  {adapter_name}: 错误 - {e}")
        
        # 测试仓储层
        print("\n📦 测试仓储层...")
        try:
            user_repo = db_manager.get_user_repository()
            repo_health = await user_repo.health_check()
            print(f"  ✅ 用户仓储: {repo_health.get('status', 'unknown')}")
        except Exception as e:
            print(f"  ❌ 用户仓储错误: {e}")
        
        # 测试配置管理
        print("\n⚙️  测试配置管理...")
        try:
            config_info = {
                'environment': db_manager.config_manager.environment,
                'databases': db_manager.config_manager.get_all_database_names()
            }
            print(f"  环境: {config_info['environment']}")
            print(f"  配置的数据库: {len(config_info['databases'])}")
        except Exception as e:
            print(f"  ⚠️  配置管理错误: {e}")
        
        print("\n🎉 数据库架构测试完成!")


def test_imports():
    """测试导入是否正常"""
    print("📦 测试模块导入...")
    
    try:
        from src.database import DatabaseAdapter, DatabaseType, ConnectionStatus
        print("  ✅ 基础类导入成功")
    except Exception as e:
        print(f"  ❌ 基础类导入失败: {e}")
    
    try:
        from src.database.adapters import PostgreSQLAdapter, Neo4jAdapter, RedisAdapter
        print("  ✅ 适配器导入成功")
    except Exception as e:
        print(f"  ❌ 适配器导入失败: {e}")
    
    try:
        from src.database.repositories import UserRepository, KnowledgeRepository
        print("  ✅ 仓储导入成功")
    except Exception as e:
        print(f"  ❌ 仓储导入失败: {e}")
    
    try:
        from src.database.manager import get_database_manager
        print("  ✅ 管理器导入成功")
    except Exception as e:
        print(f"  ❌ 管理器导入失败: {e}")


def test_config():
    """测试配置文件"""
    print("\n⚙️  测试配置文件...")
    
    try:
        from src.database.config_manager import DatabaseConfigManager
        config_manager = DatabaseConfigManager()
        
        print(f"  环境: {config_manager.environment}")
        databases = config_manager.get_all_database_names()
        print(f"  数据库数量: {len(databases)}")
        
        # 验证配置
        for db_name in databases[:3]:  # 只测试前3个
            is_valid = config_manager.validate_database_config(db_name)
            print(f"  {db_name}: {'✅ 有效' if is_valid else '❌ 无效'}")
            
    except Exception as e:
        print(f"  ❌ 配置测试失败: {e}")


if __name__ == "__main__":
    print("🚀 新数据库架构验证测试")
    print("=" * 50)
    
    # 测试导入
    test_imports()
    
    # 测试配置
    test_config()
    
    # 测试数据库架构
    try:
        asyncio.run(test_database_architecture())
    except KeyboardInterrupt:
        print("\n⏹️  测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✨ 测试完成")