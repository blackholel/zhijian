"""
文件状态管理服务

单一职责：专门管理文件处理状态
清晰边界：与业务逻辑层解耦
可扩展接口：支持多种状态查询模式

架构设计：
- 数据层：使用DTO标准化数据格式
- 缓存层：多级缓存策略提升性能
- 事件层：发布状态变化事件支持实时更新
- 监控层：性能监控和错误追踪
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Any, AsyncGenerator
from datetime import datetime, timedelta

from ..database.connection_manager import DatabaseConnectionManager
from ..database.repositories.knowledge_file_repository import KnowledgeFileRepository
from .monitoring import PerformanceMonitor
from .dto.file_status_dto import (
    FileStatusDto, 
    FileStatusSummaryDto, 
    FileStatusBatchResponseDto,
    FileStatusEventDto,
    FileStatus
)

logger = logging.getLogger(__name__)

# 兼容性：保持原有数据类以支持现有代码
from .dto.file_status_dto import FileStatusSummaryDto as FileStatusSummary
from .dto.file_status_dto import FileStatusDto as FileStatusInfo


class FileStatusCache:
    """文件状态缓存管理器 - 复用现有Redis适配器"""
    
    def __init__(self, connection_manager: DatabaseConnectionManager):
        self.connection_manager = connection_manager
        self.cache_ttl = 300  # 5分钟缓存
        self.memory_cache = {}  # L1内存缓存
        self.memory_cache_ttl = {}
        self.cache_prefix = "file_status"
        
    async def _get_redis_adapter(self):
        """获取Redis适配器"""
        try:
            return await self.connection_manager.get_adapter('redis')
        except Exception as e:
            logger.warning(f"获取Redis适配器失败: {e}")
            return None
    
    def _get_cache_key(self, key: str) -> str:
        """生成缓存键"""
        return f"{self.cache_prefix}:{key}"
    
    def _is_memory_cache_valid(self, key: str) -> bool:
        """检查内存缓存是否有效"""
        if key not in self.memory_cache:
            return False
        
        ttl = self.memory_cache_ttl.get(key, 0)
        return time.time() < ttl
    
    async def get_status_summary(self, kb_id: str) -> Optional[FileStatusSummaryDto]:
        """获取状态摘要 - 多层缓存"""
        cache_key = f"summary:{kb_id}"
        
        # L1: 内存缓存
        if self._is_memory_cache_valid(cache_key):
            return self.memory_cache[cache_key]
        
        # L2: Redis缓存
        try:
            redis_adapter = await self._get_redis_adapter()
            if redis_adapter and redis_adapter.is_available:
                cached_data = await redis_adapter.get(cache_key)  # 使用Redis适配器的内置键前缀
                if cached_data:
                    try:
                        # 如果cached_data已经是字典，直接使用
                        if isinstance(cached_data, dict):
                            data = cached_data
                        else:
                            data = json.loads(cached_data) if isinstance(cached_data, str) else cached_data
                        
                        # 确保 last_updated 是字符串类型
                        if 'last_updated' in data:
                            if not isinstance(data['last_updated'], str):
                                data['last_updated'] = str(data['last_updated'])
                        summary = FileStatusSummaryDto(**data)
                        # 更新内存缓存
                        self.memory_cache[cache_key] = summary
                        self.memory_cache_ttl[cache_key] = time.time() + 60  # 1分钟内存缓存
                        return summary
                    except Exception as e:
                        logger.warning(f"缓存反序列化失败: {e}")
                        return None
        except Exception as e:
            logger.warning(f"Redis缓存获取失败: {e}")
        
        return None
    
    async def set_status_summary(self, kb_id: str, summary: FileStatusSummaryDto):
        """设置状态摘要缓存"""
        cache_key = f"summary:{kb_id}"
        
        # L1: 内存缓存
        self.memory_cache[cache_key] = summary
        self.memory_cache_ttl[cache_key] = time.time() + 60
        
        # L2: Redis缓存
        try:
            redis_adapter = await self._get_redis_adapter()
            if redis_adapter and redis_adapter.is_available:
                await redis_adapter.set(
                    cache_key,  # Redis适配器会自动添加前缀
                    summary.to_dict(),  # 直接传递字典，Redis适配器会处理序列化
                    self.cache_ttl
                )
        except Exception as e:
            logger.warning(f"Redis缓存设置失败: {e}")
    
    async def get_files_status_page(self, kb_id: str, status_filter: str, 
                                   page: int, page_size: int) -> Optional[Dict[str, Any]]:
        """获取分页状态缓存"""
        cache_key = f"page:{kb_id}:{status_filter}:{page}:{page_size}"
        
        try:
            redis_adapter = await self._get_redis_adapter()
            if redis_adapter and redis_adapter.is_available:
                cached_data = await redis_adapter.get(cache_key)  # Redis适配器处理前缀
                if cached_data:
                    # Redis适配器已经处理了反序列化
                    return cached_data
        except Exception as e:
            logger.warning(f"分页缓存获取失败: {e}")
        
        return None
    
    async def set_files_status_page(self, kb_id: str, status_filter: str, 
                                   page: int, page_size: int, data: Dict[str, Any]):
        """设置分页状态缓存"""
        cache_key = f"page:{kb_id}:{status_filter}:{page}:{page_size}"
        
        try:
            redis_adapter = await self._get_redis_adapter()
            if redis_adapter and redis_adapter.is_available:
                # Redis适配器会处理序列化
                await redis_adapter.set(
                    cache_key,  # Redis适配器处理前缀
                    data,  # 直接传递字典
                    self.cache_ttl
                )
        except Exception as e:
            logger.warning(f"分页缓存设置失败: {e}")
    
    async def invalidate_kb_cache(self, kb_id: str):
        """清除知识库相关缓存"""
        # 清除内存缓存
        keys_to_remove = [key for key in self.memory_cache.keys() if kb_id in key]
        for key in keys_to_remove:
            self.memory_cache.pop(key, None)
            self.memory_cache_ttl.pop(key, None)
        
        # 清除Redis缓存
        try:
            redis_adapter = await self._get_redis_adapter()
            if redis_adapter and redis_adapter.is_available:
                pattern = f"*:{kb_id}:*"
                # 使用Redis适配器的模式删除
                deleted_count = await redis_adapter.delete_pattern(pattern)
                logger.info(f"清除Redis缓存: {deleted_count} 个键")
        except Exception as e:
            logger.warning(f"批量缓存清除失败: {e}")
    
    async def publish_status_change(self, kb_id: str, file_id: str, 
                                   old_status: str, new_status: str):
        """发布状态变化事件"""
        try:
            redis_adapter = await self._get_redis_adapter()
            if redis_adapter and redis_adapter.is_available:
                event = FileStatusEventDto.create_status_change_event(
                    file_id, kb_id, old_status, new_status
                )
                
                channel = f"kb_status:{kb_id}"
                # 使用Redis适配器的pub/sub功能
                await redis_adapter.publish(channel, json.dumps(event.to_dict()))
        except Exception as e:
            logger.warning(f"事件发布失败: {e}")


class FileStatusManager:
    """文件状态管理器 - 服务层"""
    
    def __init__(self, connection_manager: DatabaseConnectionManager):
        self.connection_manager = connection_manager
        self.file_repository = KnowledgeFileRepository(connection_manager)
        self.status_cache = FileStatusCache(connection_manager)
        self.performance_monitor = PerformanceMonitor(connection_manager)
        
    async def get_files_status_batch(self, kb_id: str, user_id: str, 
                                   status_filter: str = None,
                                   page: int = 1, page_size: int = 20) -> FileStatusBatchResponseDto:
        """批量获取文件状态 - 优化版使用DTO"""
        start_time = time.time()
        success = True
        error_message = None
        
        try:
            # 参数验证
            if page < 1:
                page = 1
            if page_size < 1 or page_size > 100:
                page_size = 20
            
            # 缓存检查
            cached_result = await self.status_cache.get_files_status_page(
                kb_id, status_filter or 'all', page, page_size
            )
            if cached_result:
                logger.debug(f"文件状态分页缓存命中: {kb_id}")
                # 转换为DTO格式
                files_dto = [FileStatusDto(**file_data) for file_data in cached_result.get('files', [])]
                return FileStatusBatchResponseDto(
                    files=files_dto,
                    pagination=cached_result.get('pagination', {}),
                    filter=cached_result.get('filter', 'all'),
                    timestamp=cached_result.get('timestamp', datetime.now().isoformat())
                )
            
            # 数据库查询
            offset = (page - 1) * page_size
            files = await self._get_files_by_status(kb_id, user_id, status_filter, offset, page_size)
            
            # 获取总数
            total_count = await self._get_files_count_by_status(kb_id, user_id, status_filter)
            
            # 构造文件状态DTO列表
            file_status_dtos = []
            for file_obj in files:
                try:
                    # 使用DTO转换器
                    file_dto = FileStatusDto.from_knowledge_file(file_obj)
                    # 动态获取处理进度
                    file_dto.processing_progress = await self._get_processing_progress(file_obj.file_id)
                    file_status_dtos.append(file_dto)
                except Exception as e:
                    logger.warning(f"文件状态DTO转换失败 {getattr(file_obj, 'file_id', 'unknown')}: {e}")
                    # 跳过有问题的文件，继续处理其他文件
            
            # 构造分页信息
            pagination = FileStatusBatchResponseDto.create_pagination_info(page, page_size, total_count)
            
            # 构造响应DTO
            response_dto = FileStatusBatchResponseDto(
                files=file_status_dtos,
                pagination=pagination,
                filter=status_filter or 'all'
            )
            
            # 缓存结果 (转换为字典格式)
            await self.status_cache.set_files_status_page(
                kb_id, status_filter or 'all', page, page_size, response_dto.to_dict()
            )
            
            logger.info(f"获取文件状态成功: {kb_id}, 页面{page}, 共{total_count}个文件")
            return response_dto
            
        except Exception as e:
            success = False
            error_message = str(e)
            logger.error(f"批量获取文件状态失败: {e}")
            # 返回空的响应DTO
            return FileStatusBatchResponseDto(
                files=[],
                pagination=FileStatusBatchResponseDto.create_pagination_info(page, page_size, 0),
                filter=status_filter or 'all'
            )
        finally:
            # 记录性能指标
            duration = time.time() - start_time
            self.performance_monitor.record_operation(
                operation="get_files_status_batch",
                duration=duration,
                success=success,
                error_message=error_message,
                kb_id=kb_id
            )
    
    async def get_status_summary(self, kb_id: str, user_id: str) -> FileStatusSummaryDto:
        """获取状态摘要统计"""
        try:
            # 缓存检查
            cached_summary = await self.status_cache.get_status_summary(kb_id)
            if cached_summary:
                logger.debug(f"状态摘要缓存命中: {kb_id}")
                return cached_summary
            
            # 数据库统计查询
            stats = await self.file_repository.get_file_statistics(database_id=kb_id, user_id=user_id)
            
            # 使用DTO工厂方法构造摘要
            summary = FileStatusSummaryDto.from_statistics(kb_id, stats)
            
            # 缓存摘要
            await self.status_cache.set_status_summary(kb_id, summary)
            
            logger.info(f"生成状态摘要成功: {kb_id}")
            return summary
            
        except Exception as e:
            logger.error(f"获取状态摘要失败: {e}")
            # 返回空的摘要DTO
            return FileStatusSummaryDto(
                kb_id=kb_id,
                total_files=0,
                uploaded_files=0,
                processing_files=0,
                completed_files=0,
                failed_files=0,
                success_rate=0.0,
                last_updated=datetime.now().isoformat()
            )
    
    async def watch_status_changes(self, kb_id: str, user_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """监听状态变化流 - 基于Redis pub/sub"""
        try:
            redis_adapter = await self.connection_manager.get_adapter('redis')
            if not redis_adapter or not redis_adapter.is_available:
                logger.warning("Redis不可用，无法监听状态变化")
                yield {
                    "type": "error",
                    "data": {"error": "Redis不可用"},
                    "timestamp": datetime.now().isoformat()
                }
                return
            
            channel = f"kb_status:{kb_id}"
            
            # 发送初始状态
            summary = await self.get_status_summary(kb_id, user_id)
            yield {
                "type": "initial_status",
                "data": summary.to_dict(),
                "timestamp": datetime.now().isoformat()
            }
            
            # 开始监听状态变化
            logger.info(f"开始监听状态变化: {kb_id}")
            
            # 使用增强的Redis pub/sub功能
            async for message in redis_adapter.subscribe(channel):
                try:
                    event_data = json.loads(message)
                    yield {
                        "type": "status_change",
                        "data": event_data,
                        "timestamp": datetime.now().isoformat()
                    }
                except json.JSONDecodeError as e:
                    logger.warning(f"解析事件消息失败: {e}")
                except Exception as e:
                    logger.error(f"处理状态变化事件失败: {e}")
                    
        except Exception as e:
            logger.error(f"监听状态变化失败: {e}")
            yield {
                "type": "error",
                "data": {"error": str(e)},
                "timestamp": datetime.now().isoformat()
            }
    
    async def update_file_status_with_event(self, file_id: str, new_status: str, 
                                          error_message: str = None) -> bool:
        """更新文件状态并发布事件"""
        try:
            # 获取旧状态
            file_obj = await self.file_repository.get_by_id(file_id, None, check_permission=False)
            if not file_obj:
                logger.warning(f"文件不存在: {file_id}")
                return False
            
            old_status = file_obj.status
            kb_id = file_obj.database_id
            
            # 更新状态
            success = await self.file_repository.update_file_status(file_id, new_status, error_message)
            
            if success:
                # 发布状态变化事件
                await self.status_cache.publish_status_change(kb_id, file_id, old_status, new_status)
                
                # 清除相关缓存
                await self.status_cache.invalidate_kb_cache(kb_id)
                
                logger.info(f"文件状态更新成功: {file_id} {old_status} -> {new_status}")
            
            return success
            
        except Exception as e:
            logger.error(f"更新文件状态失败: {e}")
            return False
    
    async def _get_files_by_status(self, kb_id: str, user_id: str, status_filter: str, 
                                  offset: int, limit: int) -> List[Any]:
        """根据状态获取文件列表"""
        try:
            # 使用现有的文件仓储方法
            files = await self.file_repository.get_files_by_database(kb_id, user_id)
            
            # 状态过滤
            if status_filter and status_filter != 'all':
                files = [f for f in files if f.status == status_filter]
            
            # 分页
            return files[offset:offset + limit]
            
        except Exception as e:
            logger.error(f"获取文件列表失败: {e}")
            return []
    
    async def _get_files_count_by_status(self, kb_id: str, user_id: str, status_filter: str) -> int:
        """根据状态获取文件总数"""
        try:
            files = await self.file_repository.get_files_by_database(kb_id, user_id)
            
            if status_filter and status_filter != 'all':
                files = [f for f in files if f.status == status_filter]
            
            return len(files)
            
        except Exception as e:
            logger.error(f"获取文件总数失败: {e}")
            return 0
    
    async def _get_processing_progress(self, file_id: str) -> Optional[Dict[str, Any]]:
        """获取处理进度（预留接口）"""
        try:
            # 这里可以扩展为实际的处理进度查询
            return None
        except Exception as e:
            logger.warning(f"获取处理进度失败 {file_id}: {e}")
            return None
    
    def _extract_error_message(self, file_obj: Any) -> Optional[str]:
        """提取错误信息"""
        try:
            if file_obj.status == 'failed':
                # 从元数据中提取错误信息
                metadata = getattr(file_obj, 'file_metadata', {}) or {}
                return metadata.get('error_message')
            return None
        except Exception as e:
            logger.warning(f"提取错误信息失败: {e}")
            return None
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 检查Redis连接
            redis_adapter = await self.connection_manager.get_adapter('redis')
            redis_status = redis_adapter.is_available if redis_adapter else False
            
            # 检查文件仓储
            file_repo_status = await self.file_repository.health_check()
            
            return {
                "status": "healthy" if redis_status and file_repo_status.get("status") == "healthy" else "degraded",
                "components": {
                    "redis_cache": {"status": "healthy" if redis_status else "error"},
                    "file_repository": file_repo_status,
                    "memory_cache": {"status": "healthy", "size": len(self.status_cache.memory_cache)}
                },
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }