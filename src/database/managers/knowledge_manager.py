"""
知识库管理器 - 业务逻辑层
"""

import logging
import uuid
import asyncio
import os
import tempfile
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from pathlib import Path

from ..repositories.knowledge_repository import KnowledgeRepository
from ..repositories.knowledge_file_repository import KnowledgeFileRepository
from ..repositories.knowledge_node_repository import KnowledgeNodeRepository
from ..repositories.permission_mixin import PermissionValidator, AuditLogger
from ..connection_manager import DatabaseConnectionManager
from src.knowledge_base.models.kb_models import KnowledgeDatabase, KnowledgeFile, KnowledgeNode
from ...services.file_status_manager import FileStatusManager

logger = logging.getLogger(__name__)


class LightRAGAdapter:
    """LightRAG适配器 - 提供统一接口，集成现有LightRAG系统"""
    
    def __init__(self, knowledge_base_manager: 'KnowledgeBaseManager'):
        self.manager = knowledge_base_manager
        
    def _safe_serialize_metadata(self, obj):
        """安全序列化元数据，防止SQLAlchemy对象"""
        if obj is None:
            return {}
        if isinstance(obj, dict):
            return obj
        # 如果是SQLAlchemy MetaData或其他不可序列化对象
        if hasattr(obj, '__class__') and 'sqlalchemy' in str(obj.__class__):
            logger.warning(f"跳过SQLAlchemy对象序列化: {type(obj)}")
            return {}
        return {}
    
    def _build_embed_info(self, kb):
        """构造embed_info对象，基于数据库模型字段"""
        embed_info = {}
        
        # 从数据库模型获取嵌入相关信息
        if hasattr(kb, 'embed_model') and kb.embed_model:
            embed_info['model_name'] = kb.embed_model
            
        if hasattr(kb, 'dimension') and kb.dimension:
            embed_info['dimension'] = kb.dimension
            
        return embed_info
    
    def _extract_kb_model_config(self, kb):
        """从知识库模型中提取模型配置信息"""
        llm_info = {}
        embed_info = {}
        
        # 获取meta_info中的模型配置
        meta_info = self._safe_serialize_metadata(getattr(kb, 'meta_info', None))
        if isinstance(meta_info, dict):
            model_config = meta_info.get('model_config', {})
            
            # 提取LLM配置
            if 'llm' in model_config:
                llm_config = model_config['llm']
                llm_info = {
                    "provider": llm_config.get('provider'),
                    "model_name": llm_config.get('model_name')
                }
            
            # 提取嵌入模型配置
            if 'embedding' in model_config:
                embed_config = model_config['embedding']
                embed_info = {
                    "provider": embed_config.get('provider'),
                    "model_name": embed_config.get('model_name'),
                    "dimension": embed_config.get('dimension')
                }
        
        # 如果meta_info中没有配置，使用数据库字段的配置
        if not embed_info and hasattr(kb, 'embed_model') and kb.embed_model:
            embed_info = {
                "model_name": kb.embed_model,
                "dimension": getattr(kb, 'dimension', None)
            }
        
        logger.debug(f"提取的知识库模型配置 - LLM: {llm_info}, 嵌入: {embed_info}")
        return llm_info, embed_info
    
    async def ensure_lightrag_sync(self, kb_id: str):
        """确保LightRAG同步 - 复用现有模式"""
        from src import knowledge_base  # 复用全局LightRagBasedKB实例
        
        if kb_id not in knowledge_base.databases_meta:
            await self._sync_kb_to_lightrag(kb_id)
    
    async def _sync_kb_to_lightrag(self, kb_id: str):
        """同步知识库信息到LightRAG - 基于现有数据库模型"""
        from src import knowledge_base
        
        try:
            # 获取新架构中的知识库信息
            kb = await self.manager.kb_repo.get_by_id(kb_id, None, check_permission=False)
            if kb:
                # 提取知识库级别的模型配置
                llm_info, embed_info = self._extract_kb_model_config(kb)
                
                # 在LightRAG中创建对应记录，复用现有metadata结构
                knowledge_base.databases_meta[kb_id] = {
                    "name": kb.name,
                    "description": kb.description or "",
                    "llm_info": llm_info,  # 知识库级别的LLM配置
                    "embed_info": embed_info,  # 知识库级别的嵌入模型配置
                    "metadata": self._safe_serialize_metadata(getattr(kb, 'meta_info', None)),  # 安全序列化meta_info
                    "created_at": kb.created_at.isoformat() if kb.created_at else datetime.now().isoformat()
                }
                knowledge_base._save_metadata()  # 复用现有保存机制
                logger.info(f"已同步知识库到LightRAG: {kb_id}")
            
        except Exception as e:
            logger.error(f"同步知识库到LightRAG失败: {e}")
    
    async def add_document_to_lightrag(self, kb_id: str, file_id: str, content: str, 
                                     filename: str = None, file_path: str = None):
        """添加文档到LightRAG - 复用现有处理机制"""
        try:
            await self.ensure_lightrag_sync(kb_id)
            
            from src import knowledge_base
            rag = await knowledge_base._get_lightrag_instance(kb_id)
            if rag:
                # 使用LightRAG原生插入方法
                await rag.ainsert(
                    input=content, 
                    ids=file_id, 
                    file_paths=file_path or f"db_{kb_id}/{filename or file_id}"
                )
                logger.info(f"文档已添加到LightRAG: {file_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"添加文档到LightRAG失败: {e}")
            return False
    
    async def query_lightrag(self, kb_id: str, query: str, **kwargs):
        """查询LightRAG - 复用现有查询机制"""
        try:
            await self.ensure_lightrag_sync(kb_id)
            
            from src import knowledge_base
            return await knowledge_base.aquery(query, kb_id, **kwargs)
            
        except Exception as e:
            logger.error(f"LightRAG查询失败: {e}")
            return ""
    
    async def set_kb_model_config(self, kb_id: str, llm_provider: str = None, llm_model: str = None, 
                                embed_provider: str = None, embed_model: str = None, user_id: str = None):
        """设置知识库级别的模型配置"""
        try:
            # 获取知识库
            kb = await self.manager.kb_repo.get_by_id(kb_id, user_id)
            if not kb:
                raise ValueError(f"知识库不存在: {kb_id}")
            
            # 获取现有的meta_info
            meta_info = self._safe_serialize_metadata(getattr(kb, 'meta_info', None))
            if not isinstance(meta_info, dict):
                meta_info = {}
            
            # 更新模型配置
            model_config = meta_info.get('model_config', {})
            
            if llm_provider and llm_model:
                model_config['llm'] = {
                    'provider': llm_provider,
                    'model_name': llm_model
                }
                logger.info(f"设置知识库LLM配置 [kb_id={kb_id}]: {llm_provider}/{llm_model}")
            
            if embed_provider and embed_model:
                # 获取嵌入模型的详细信息
                from src.core.lightrag_model_adapter import get_lightrag_model_adapter
                adapter = get_lightrag_model_adapter()
                available_models = adapter.get_available_models()
                
                embed_key = f"{embed_provider}/{embed_model}"
                if embed_key in available_models['embed_models']:
                    embed_info = adapter.config.embed_model_names[embed_key]
                    model_config['embedding'] = {
                        'provider': embed_provider,
                        'model_name': embed_model,
                        'dimension': embed_info.get('dimension', 1024)
                    }
                    logger.info(f"设置知识库嵌入模型配置 [kb_id={kb_id}]: {embed_provider}/{embed_model}")
                else:
                    logger.warning(f"嵌入模型不可用: {embed_key}")
            
            # 更新meta_info
            meta_info['model_config'] = model_config
            kb.meta_info = meta_info
            
            # 保存到数据库
            await self.manager.kb_repo.update(kb)
            
            # 清除LightRAG缓存，强制重新同步
            from src import knowledge_base
            if kb_id in knowledge_base.databases_meta:
                del knowledge_base.databases_meta[kb_id]
            if kb_id in knowledge_base.instances:
                del knowledge_base.instances[kb_id]
            
            logger.info(f"知识库模型配置已更新: {kb_id}")
            return True
            
        except Exception as e:
            logger.error(f"设置知识库模型配置失败: {e}")
            return False
    
    async def get_kb_model_config(self, kb_id: str, user_id: str = None):
        """获取知识库的模型配置信息"""
        try:
            kb = await self.manager.kb_repo.get_by_id(kb_id, user_id)
            if not kb:
                return None
            
            llm_info, embed_info = self._extract_kb_model_config(kb)
            
            # 获取可用的模型列表
            from src.core.lightrag_model_adapter import get_lightrag_model_adapter
            adapter = get_lightrag_model_adapter()
            available_models = adapter.get_available_models()
            
            return {
                "kb_id": kb_id,
                "current_config": {
                    "llm": llm_info,
                    "embedding": embed_info
                },
                "available_models": available_models,
                "using_system_default": not bool(llm_info and embed_info)
            }
            
        except Exception as e:
            logger.error(f"获取知识库模型配置失败: {e}")
            return None


class KnowledgeBaseManager:
    """知识库管理器 - 统一的业务逻辑层"""
    
    def __init__(self, connection_manager: DatabaseConnectionManager):
        self.connection_manager = connection_manager
        
        # 初始化仓储
        self.kb_repo = KnowledgeRepository(connection_manager)
        self.file_repo = KnowledgeFileRepository(connection_manager)
        self.node_repo = KnowledgeNodeRepository(connection_manager)
        
        # 设置仓储间的引用
        self.file_repo.set_kb_repository(self.kb_repo)
        self.node_repo.set_repositories(self.kb_repo, self.file_repo)
        
        # 权限验证器
        self.permission_validator = PermissionValidator()
        
        # LightRAG适配器 - 集成现有LightRAG系统
        self.lightrag_adapter = LightRAGAdapter(self)
        
        # 文件状态管理器 - 集成状态管理服务
        self.status_manager = FileStatusManager(connection_manager)
    
    # 知识库管理方法
    
    async def create_knowledge_base(self, kb_data: Dict[str, Any], 
                                  owner_id: str) -> KnowledgeDatabase:
        """创建知识库 - 完整业务流程"""
        try:
            # 数据验证
            self._validate_kb_data(kb_data)
            
            # 创建知识库
            kb = await self.kb_repo.create(kb_data, owner_id)
            
            # 在Session关闭前获取需要的属性
            kb_id = kb.db_id
            
            # 记录审计日志
            await AuditLogger.log_access_attempt(
                owner_id, 'knowledge_base', kb_id, 'create', True
            )
            
            logger.info(f"创建知识库成功: {kb_id} by {owner_id}")
            return kb
            
        except Exception as e:
            # 记录失败审计
            await AuditLogger.log_access_attempt(
                owner_id, 'knowledge_base', 'unknown', 'create', False,
                {'error': str(e)}
            )
            logger.error(f"创建知识库失败: {e}")
            raise
    
    async def get_knowledge_base(self, kb_id: str, user_id: str, 
                               include_files: bool = True) -> Optional[KnowledgeDatabase]:
        """获取知识库详情"""
        try:
            # 获取知识库
            kb = await self.kb_repo.get_by_id(kb_id, user_id, check_permission=True)
            
            if not kb:
                return None
            
            # 如果需要包含文件信息
            if include_files:
                files = await self.file_repo.get_files_by_database(kb_id, user_id)
                # 将文件信息添加到知识库对象中（如果需要）
                # kb.files = files
            
            # 记录访问审计
            await AuditLogger.log_access_attempt(
                user_id, 'knowledge_base', kb_id, 'read', True
            )
            
            return kb
            
        except Exception as e:
            await AuditLogger.log_access_attempt(
                user_id, 'knowledge_base', kb_id, 'read', False,
                {'error': str(e)}
            )
            logger.error(f"获取知识库失败: {e}")
            return None
    
    async def update_knowledge_base(self, kb_id: str, updates: Dict[str, Any], 
                                  user_id: str) -> Optional[KnowledgeDatabase]:
        """更新知识库"""
        try:
            # 数据验证
            self._validate_kb_updates(updates)
            
            # 更新知识库
            kb = await self.kb_repo.update(kb_id, updates, user_id)
            
            if kb:
                await AuditLogger.log_access_attempt(
                    user_id, 'knowledge_base', kb_id, 'update', True,
                    {'updates': list(updates.keys())}
                )
                logger.info(f"更新知识库成功: {kb_id}")
            
            return kb
            
        except Exception as e:
            await AuditLogger.log_access_attempt(
                user_id, 'knowledge_base', kb_id, 'update', False,
                {'error': str(e)}
            )
            logger.error(f"更新知识库失败: {e}")
            raise
    
    async def delete_knowledge_base(self, kb_id: str, user_id: str) -> bool:
        """删除知识库 - 完整清理流程"""
        try:
            # 首先检查权限
            has_permission = await self.kb_repo._check_kb_permission(kb_id, user_id, 'admin')
            if not has_permission:
                raise PermissionError("没有删除权限")
            
            # 获取知识库信息（用于清理）
            kb = await self.kb_repo.get_by_id(kb_id, user_id, check_permission=False)
            if not kb:
                return False
            
            # 1. 删除所有文件的节点数据
            files = await self.file_repo.get_files_by_database(kb_id, user_id)
            for file_obj in files:
                await self.node_repo.batch_delete_by_file(file_obj.file_id, user_id)
            
            # 2. 删除文件记录
            for file_obj in files:
                await self.file_repo.delete(file_obj.file_id, user_id)
            
            # 3. 删除知识库记录（会级联删除权限）
            success = await self.kb_repo.delete(kb_id, user_id)
            
            if success:
                await AuditLogger.log_access_attempt(
                    user_id, 'knowledge_base', kb_id, 'delete', True
                )
                logger.info(f"删除知识库成功: {kb_id}")
            
            return success
            
        except Exception as e:
            await AuditLogger.log_access_attempt(
                user_id, 'knowledge_base', kb_id, 'delete', False,
                {'error': str(e)}
            )
            logger.error(f"删除知识库失败: {e}")
            raise
    
    async def get_user_knowledge_bases(self, user_id: str) -> List[KnowledgeDatabase]:
        """获取用户可访问的知识库列表"""
        try:
            return await self.kb_repo.get_user_accessible_kbs(user_id)
        except Exception as e:
            logger.error(f"获取用户知识库列表失败: {e}")
            return []
    
    # 文件管理方法
    
    async def upload_document(self, kb_id: str, storage_key: str,
                            filename: str, file_type: str, user_id: str,
                            metadata: Dict[str, Any] = None, file_id: str = None,
                            file_size: int = 0) -> KnowledgeFile:
        """上传文档到MinIO"""
        try:
            # 1. 权限检查
            has_permission = await self.kb_repo._check_kb_permission(kb_id, user_id, 'write')
            if not has_permission:
                raise PermissionError("没有上传权限")
            
            # 2. 使用提供的file_id或生成新的
            if not file_id:
                file_id = str(uuid.uuid4()).replace('-', '')
            
            # 3. 创建文件记录（使用MinIO存储路径）
            file_record_data = {
                'file_id': file_id,
                'filename': filename,
                'path': storage_key,  # 使用MinIO存储键作为路径
                'file_type': file_type,
                'status': 'uploaded',  # MinIO已上传，直接设为uploaded
                'storage_type': 'minio',  # 设置主存储类型为MinIO
                'file_size': file_size,  # 设置文件大小到主记录
                'metadata': {
                    **(metadata or {}),
                    'storage_type': 'minio',
                    'file_size': file_size,
                    'storage_key': storage_key
                }
            }
            
            file_obj = await self.file_repo.create(file_record_data, kb_id, user_id)
            
            # 4. 异步启动文档处理（传递file_id而不是对象）
            asyncio.create_task(self._process_document_async(file_id, user_id))
            
            # 记录审计
            await AuditLogger.log_access_attempt(
                user_id, 'file', file_id, 'upload', True,
                {'filename': filename, 'kb_id': kb_id, 'storage_type': 'minio'}
            )
            
            logger.info(f"MinIO文档上传成功: {filename} -> {file_id}")
            return file_obj
            
        except Exception as e:
            await AuditLogger.log_access_attempt(
                user_id, 'file', 'unknown', 'upload', False,
                {'error': str(e), 'filename': filename, 'storage_type': 'minio'}
            )
            logger.error(f"MinIO文档上传失败: {e}")
            raise
    
    
    async def _process_document_async(self, file_id: str, user_id: str):
        """异步文档处理 - 增强状态管理"""
        try:
            # 更新状态为处理中（带事件发布）
            await self.status_manager.update_file_status_with_event(file_id, 'processing')
            
            # 获取文件信息
            file_obj = await self.file_repo.get_by_id(file_id, user_id, check_permission=False)
            if not file_obj:
                raise ValueError(f"文件 {file_id} 不存在")
            
            filename = file_obj.filename
            file_path = file_obj.path
            file_type = file_obj.file_type
            storage_type = getattr(file_obj, 'storage_type', 'local')
            # 获取文件元数据
            metadata = getattr(file_obj, 'file_metadata', {}) or {}
            
            # 确保metadata中有storage_type信息
            if 'storage_type' not in metadata:
                metadata['storage_type'] = storage_type
            
            logger.info(f"处理文档: {filename}, 路径: {file_path}, 存储类型: {storage_type}")
            
            # 1. 文本提取和OCR处理
            text_content = await self._extract_text_content(file_path, file_type, metadata)
            
            # 2. 文档分块
            chunks = await self._chunk_document(text_content, file_path, file_type, metadata)
            
            # 3. 向量化处理
            embeddings = await self._vectorize_chunks(chunks)
            
            # 4. 创建节点数据
            nodes_data = []
            for i, chunk in enumerate(chunks):
                node_data = {
                    'text': chunk['text'],
                    'start_char_idx': chunk.get('start_char_idx', i * 1000),
                    'end_char_idx': chunk.get('end_char_idx', (i + 1) * 1000),
                    'metadata': {
                        'chunk_index': i,
                        'chunk_size': len(chunk['text']),
                        'file_type': file_type,
                        'embedding_available': len(embeddings) > i,
                        **chunk.get('metadata', {})
                    }
                }
                nodes_data.append(node_data)
            
            # 5. 批量创建节点
            await self.node_repo.batch_create(nodes_data, file_id, user_id)
            
            # 6. 存储向量到向量数据库
            if embeddings:
                await self._store_vectors(file_id, file_obj.database_id, chunks, embeddings)
            
            # 更新文件状态为完成（带事件发布）
            await self.status_manager.update_file_status_with_event(file_id, 'completed')
            
            logger.info(f"文档处理完成: {file_id}, {len(chunks)} 个分块")
            
        except Exception as e:
            # 更新状态为失败（带事件发布和错误信息）
            await self.status_manager.update_file_status_with_event(file_id, 'failed', str(e))
            logger.error(f"文档处理失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def get_file_details(self, file_id: str, user_id: str, 
                             include_nodes: bool = False) -> Optional[KnowledgeFile]:
        """获取文件详情"""
        try:
            file_obj = await self.file_repo.get_by_id(file_id, user_id, check_permission=True)
            
            if file_obj and include_nodes:
                nodes = await self.node_repo.get_nodes_by_file(file_id, user_id)
                # 将节点信息添加到文件对象中
                # file_obj.nodes = nodes
            
            return file_obj
            
        except Exception as e:
            logger.error(f"获取文件详情失败: {e}")
            return None
    
    async def delete_document(self, file_id: str, user_id: str) -> bool:
        """删除文档"""
        try:
            # 1. 删除所有节点
            await self.node_repo.batch_delete_by_file(file_id, user_id)
            
            # 2. 删除文件记录
            success = await self.file_repo.delete(file_id, user_id)
            
            # 3. 删除物理文件（TODO: 集成文件存储）
            
            if success:
                await AuditLogger.log_access_attempt(
                    user_id, 'file', file_id, 'delete', True
                )
                logger.info(f"删除文档成功: {file_id}")
            
            return success
            
        except Exception as e:
            await AuditLogger.log_access_attempt(
                user_id, 'file', file_id, 'delete', False,
                {'error': str(e)}
            )
            logger.error(f"删除文档失败: {e}")
            raise
    
    # 查询和搜索方法
    
    async def query_knowledge_base(self, kb_id: str, query: str, 
                                 user_id: str, limit: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """查询知识库 - 使用LightRAG原生查询，获得最佳性能"""
        try:
            # 权限检查
            has_permission = await self.kb_repo._check_kb_permission(kb_id, user_id, 'read')
            if not has_permission:
                raise PermissionError("没有查询权限")
            
            # 🔑 关键改变：直接使用LightRAG原生查询（性能最优）
            response = await self.lightrag_adapter.query_lightrag(
                kb_id=kb_id, 
                query=query,
                top_k=limit,
                **kwargs
            )
            
            # 转换为新架构期望的格式，保持API兼容性
            results = []
            if response:
                # 将LightRAG的响应格式化为标准格式
                results.append({
                    'node_id': f"{kb_id}_mixed_result",
                    'text': response,
                    'file_id': 'lightrag_mixed_sources',
                    'metadata': {
                        'query': query,
                        'source': 'lightrag',
                        'result_type': 'mixed_rag',
                        'kb_id': kb_id
                    },
                    'score': 1.0
                })
            
            # 记录查询审计
            await AuditLogger.log_access_attempt(
                user_id, 'knowledge_base', kb_id, 'query', True,
                {
                    'query': query, 
                    'results_count': len(results),
                    'query_method': 'lightrag'
                }
            )
            
            return results
            
        except Exception as e:
            await AuditLogger.log_access_attempt(
                user_id, 'knowledge_base', kb_id, 'query', False,
                {'error': str(e), 'query': query}
            )
            logger.error(f"查询知识库失败: {e}")
            raise
    
    # 权限管理方法
    
    async def grant_kb_permission(self, kb_id: str, target_user_id: str, 
                                permission_type: str, granted_by: str,
                                expires_at: datetime = None) -> bool:
        """授予知识库权限"""
        try:
            success = await self.kb_repo.grant_permission(
                kb_id, target_user_id, permission_type, granted_by, expires_at
            )
            
            if success:
                await AuditLogger.log_permission_change(
                    granted_by, target_user_id, 'knowledge_base', kb_id,
                    'none', permission_type
                )
                logger.info(f"授权成功: {kb_id} -> {target_user_id} ({permission_type})")
            
            return success
            
        except Exception as e:
            logger.error(f"授权失败: {e}")
            raise
    
    async def revoke_kb_permission(self, kb_id: str, target_user_id: str, 
                                 revoked_by: str) -> bool:
        """撤销知识库权限"""
        try:
            success = await self.kb_repo.revoke_permission(kb_id, target_user_id, revoked_by)
            
            if success:
                await AuditLogger.log_permission_change(
                    revoked_by, target_user_id, 'knowledge_base', kb_id,
                    'existing', 'none'
                )
                logger.info(f"撤销权限成功: {kb_id} -> {target_user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"撤销权限失败: {e}")
            raise
    
    # 统计和监控方法
    
    async def get_knowledge_base_statistics(self, kb_id: str, 
                                          user_id: str) -> Dict[str, Any]:
        """获取知识库统计信息"""
        try:
            # 权限检查
            has_permission = await self.kb_repo._check_kb_permission(kb_id, user_id, 'read')
            if not has_permission:
                raise PermissionError("没有查看权限")
            
            # 获取文件统计
            file_stats = await self.file_repo.get_file_statistics(database_id=kb_id)
            
            # 获取节点统计
            node_stats = await self.node_repo.get_node_statistics(database_id=kb_id)
            
            # 合并统计信息
            return {
                'kb_id': kb_id,
                'files': file_stats,
                'nodes': node_stats,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {'error': str(e)}
    
    # 数据验证方法
    
    def _validate_kb_data(self, kb_data: Dict[str, Any]):
        """验证知识库数据"""
        required_fields = ['name']
        for field in required_fields:
            if field not in kb_data or not kb_data[field]:
                raise ValueError(f"缺少必需字段: {field}")
        
        # 验证名称长度
        if len(kb_data['name']) > 255:
            raise ValueError("知识库名称过长")
    
    def _validate_kb_updates(self, updates: Dict[str, Any]):
        """验证知识库更新数据"""
        # 不允许更新的字段
        forbidden_fields = ['id', 'db_id', 'created_at', 'owner_id']
        for field in forbidden_fields:
            if field in updates:
                raise ValueError(f"不允许更新字段: {field}")
        
        # 验证名称长度
        if 'name' in updates and len(updates['name']) > 255:
            raise ValueError("知识库名称过长")
    
    # 健康检查
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 检查各个仓储的健康状态
            kb_health = await self.kb_repo.health_check()
            file_health = await self.file_repo.health_check()
            node_health = await self.node_repo.health_check()
            
            return {
                'status': 'healthy',
                'components': {
                    'knowledge_repository': kb_health,
                    'file_repository': file_health,
                    'node_repository': node_health
                },
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    # 文档处理核心方法 - 直接调用现有功能
    
    async def _extract_text_content(self, file_path: str, file_type: str, metadata: Dict[str, Any]) -> str:
        """提取文档文本内容 - 调用现有indexing模块"""
        try:
            from src.core.indexing import parse_pdf_async, chunk_with_parser
            
            # 处理MinIO文件下载
            local_file_path = await self._get_local_file_path(file_path, metadata)
            file_path_obj = Path(local_file_path)
            
            if file_type.lower() == 'pdf' or file_path_obj.suffix.lower() == '.pdf':
                # PDF文件处理，支持OCR
                processing_params = metadata.get('processing_params', {})
                text_content = await parse_pdf_async(file_path_obj, processing_params)
                
            elif file_type.lower() in ['txt', 'md', 'json', 'csv', 'html', 'docx']:
                # 其他文档类型
                docs = chunk_with_parser(local_file_path, params={'chunk_size': 10000, 'chunk_overlap': 0})
                text_content = '\n\n'.join([doc.page_content for doc in docs])
                
            elif file_type.lower() in ['jpg', 'jpeg', 'png', 'bmp', 'tiff']:
                # 图片文件，使用OCR
                text_content = await self._extract_text_from_image(local_file_path, metadata)
                
            else:
                # 尝试作为文本文件读取
                with open(local_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    text_content = f.read()
            
            # 清理临时文件
            await self._cleanup_temp_file(local_file_path, file_path)
            
            logger.info(f"文本提取完成，长度: {len(text_content)}")
            return text_content
            
        except Exception as e:
            logger.error(f"文本内容提取失败: {e}")
            raise
    
    async def _get_local_file_path(self, file_path: str, metadata: Dict[str, Any]) -> str:
        """获取本地文件路径（处理MinIO下载）"""
        storage_type = metadata.get('storage_type', 'local')
        
        if storage_type == 'minio':
            try:
                # 获取MinIO适配器
                minio_adapter = await self.connection_manager.get_minio_adapter()
                if not minio_adapter:
                    raise Exception("MinIO适配器未初始化")
                
                # 创建临时文件
                temp_dir = tempfile.mkdtemp()
                filename = metadata.get('filename', 'temp_file')
                temp_file_path = os.path.join(temp_dir, filename)
                
                # 下载文件
                success = await minio_adapter.download_file(file_path, temp_file_path)
                if not success:
                    raise Exception(f"文件下载失败: {file_path}")
                
                # 验证文件是否存在
                if not os.path.exists(temp_file_path):
                    raise Exception(f"下载的文件不存在: {temp_file_path}")
                
                logger.info(f"从MinIO下载文件: {file_path} -> {temp_file_path}")
                return temp_file_path
                
            except Exception as e:
                logger.error(f"从MinIO下载文件失败: {e}")
                raise
        else:
            # 本地文件，直接返回路径
            return file_path
    
    async def _extract_text_from_image(self, image_path: str, metadata: Dict[str, Any]) -> str:
        """从图片中提取文本（OCR）- 调用现有OCR插件"""
        try:
            from src.plugins import ocr
            
            # 使用配置的OCR方法
            processing_params = metadata.get('processing_params', {})
            ocr_method = processing_params.get('enable_ocr', 'mineru_ocr')
            
            if ocr_method == 'mineru_ocr':
                text_content = await asyncio.to_thread(ocr.process_image_mineru, image_path)
            elif ocr_method == 'paddlex_ocr':
                text_content = await asyncio.to_thread(ocr.process_image_paddlex, image_path)
            else:
                text_content = await asyncio.to_thread(ocr.process_image, image_path)
            
            logger.info(f"图片OCR完成，提取文本长度: {len(text_content)}")
            return text_content
            
        except Exception as e:
            logger.warning(f"图片OCR处理失败，返回空文本: {e}")
            return ""
    
    async def _chunk_document(self, text_content: str, file_path: str, file_type: str, 
                            metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """文档分块处理 - 调用现有indexing模块"""
        try:
            from src.core.indexing import chunk_text
            
            # 获取分块参数
            processing_params = metadata.get('processing_params', {})
            chunk_size = processing_params.get('chunk_size', 1000)
            chunk_overlap = processing_params.get('chunk_overlap', 200)
            
            # 使用现有的分块功能
            text_chunks = chunk_text(text_content, {
                'chunk_size': chunk_size,
                'chunk_overlap': chunk_overlap
            })
            
            # 转换为标准格式
            chunks = []
            for i, chunk_data in enumerate(text_chunks):
                chunk_info = {
                    'text': chunk_data['text'],
                    'start_char_idx': i * (chunk_size - chunk_overlap),
                    'end_char_idx': min((i + 1) * (chunk_size - chunk_overlap), len(text_content)),
                    'metadata': {
                        'chunk_index': i,
                        'chunk_size': len(chunk_data['text']),
                        'file_type': file_type,
                        **chunk_data.get('metadata', {})
                    }
                }
                chunks.append(chunk_info)
            
            logger.info(f"文档分块完成: {len(chunks)} 个分块")
            return chunks
            
        except Exception as e:
            logger.error(f"文档分块失败: {e}")
            raise
    
    async def _vectorize_chunks(self, chunks: List[Dict[str, Any]]) -> List[List[float]]:
        """向量化分块内容 - 调用现有embedding模块"""
        try:
            from src.models.embedding import get_embedding_model
            from src import config
            
            # 获取配置的嵌入模型
            embed_model_id = None
            if hasattr(config, 'embed_model_names') and config.embed_model_names:
                available_models = list(config.embed_model_names.keys())
                if available_models:
                    embed_model_id = available_models[0]  # 使用第一个可用模型
            
            if not embed_model_id:
                logger.warning("没有可用的嵌入模型，跳过向量化")
                return []
            
            # 获取嵌入模型
            embedding_model = get_embedding_model(embed_model_id)
            
            # 提取所有分块文本
            chunk_texts = [chunk['text'] for chunk in chunks]
            
            # 批量向量化
            embeddings = await embedding_model.abatch_encode(chunk_texts)
            
            logger.info(f"向量化完成: {len(embeddings)} 个向量，模型: {embed_model_id}")
            return embeddings
            
        except Exception as e:
            logger.error(f"向量化处理失败: {e}")
            # 返回空列表，不阻断处理流程
            return []
    
    async def _store_vectors(self, file_id: str, kb_id: str, chunks: List[Dict[str, Any]], 
                           embeddings: List[List[float]]) -> bool:
        """存储向量到向量数据库 - 委托给LightRAG处理，避免集合创建问题"""
        try:
            if not chunks:
                logger.warning("没有分块数据，跳过向量数据库存储")
                return True
            
            # 🔑 关键改变：委托给现有的LightRAG系统，复用其完整的向量管理机制
            
            # 构建完整文档内容（LightRAG期望的格式）
            full_content = "\n\n".join([chunk['text'] for chunk in chunks])
            
            # 获取文件信息用于构建完整内容
            file_obj = await self.file_repo.get_by_id(file_id, None, check_permission=False)
            if file_obj:
                # 添加文档元数据
                metadata_text = f"文档: {file_obj.filename}\n"
                metadata_text += f"类型: {file_obj.file_type}\n"
                if hasattr(file_obj, 'file_size') and file_obj.file_size:
                    metadata_text += f"大小: {file_obj.file_size} bytes\n"
                metadata_text += f"上传时间: {file_obj.created_at}\n\n"
                full_content = metadata_text + full_content
            
            # 使用LightRAG适配器处理向量存储，复用现有机制
            success = await self.lightrag_adapter.add_document_to_lightrag(
                kb_id=kb_id,
                file_id=file_id,
                content=full_content,
                filename=file_obj.filename if file_obj else f"file_{file_id}",
                file_path=file_obj.path if file_obj else None
            )
            
            if success:
                logger.info(f"通过LightRAG存储向量成功: {len(chunks)} 个分块")
            
            return success
            
        except Exception as e:
            logger.error(f"向量数据库存储失败: {e}")
            return False
    
    async def _cleanup_temp_file(self, local_file_path: str, original_path: str):
        """清理临时文件"""
        try:
            import tempfile
            
            # 只清理临时文件（通过路径判断）
            if local_file_path != original_path and tempfile.gettempdir() in local_file_path:
                if os.path.exists(local_file_path):
                    os.unlink(local_file_path)
                    
                # 清理临时目录（如果为空）
                temp_dir = os.path.dirname(local_file_path)
                if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                    os.rmdir(temp_dir)
                    
                logger.debug(f"清理临时文件: {local_file_path}")
                
        except Exception as e:
            logger.warning(f"清理临时文件失败: {e}")