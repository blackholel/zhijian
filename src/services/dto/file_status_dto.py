"""
文件状态数据传输对象（DTO）
单一职责：数据传输和序列化
清晰边界：与数据库模型和业务逻辑分离
可扩展接口：支持多种数据格式转换
"""

from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class FileStatus(Enum):
    """文件状态枚举"""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PENDING = "pending"
    CANCELLED = "cancelled"


@dataclass
class FileStatusDto:
    """文件状态数据传输对象 - 标准化数据格式"""
    file_id: str
    filename: str
    status: str
    file_type: str
    file_size: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_processed_at: Optional[str] = None
    processing_progress: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    storage_type: str = "local"
    node_count: int = 0
    database_id: Optional[str] = None
    uploaded_by: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)
    
    @classmethod
    def from_knowledge_file(cls, file_obj: Any) -> 'FileStatusDto':
        """从KnowledgeFile对象创建DTO"""
        try:
            # 安全获取时间字段
            created_at = cls._safe_get_datetime_iso(file_obj, 'created_at')
            updated_at = cls._safe_get_datetime_iso(file_obj, 'updated_at')
            last_processed_at = cls._safe_get_datetime_iso(file_obj, 'last_processed_at')
            
            return cls(
                file_id=getattr(file_obj, 'file_id', ''),
                filename=getattr(file_obj, 'filename', 'Unknown'),
                status=getattr(file_obj, 'status', 'unknown'),
                file_type=getattr(file_obj, 'file_type', 'unknown'),
                file_size=getattr(file_obj, 'file_size', None),
                created_at=created_at,
                updated_at=updated_at,
                last_processed_at=last_processed_at,
                processing_progress=None,  # 动态获取
                error_message=cls._extract_error_message(file_obj),
                storage_type=getattr(file_obj, 'storage_type', 'local'),
                node_count=getattr(file_obj, 'computed_node_count', 0) if hasattr(file_obj, 'computed_node_count') else 0,
                database_id=getattr(file_obj, 'database_id', None),
                uploaded_by=str(getattr(file_obj, 'uploaded_by', None)) if getattr(file_obj, 'uploaded_by', None) else None,
                metadata=getattr(file_obj, 'file_metadata', None) or {}
            )
        except Exception as e:
            # 降级处理，返回基本信息
            return cls(
                file_id=getattr(file_obj, 'file_id', ''),
                filename=getattr(file_obj, 'filename', 'Unknown'),
                status=getattr(file_obj, 'status', 'unknown'),
                file_type=getattr(file_obj, 'file_type', 'unknown'),
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                error_message=f"DTO转换失败: {str(e)}"
            )
    
    @staticmethod
    def _safe_get_datetime_iso(obj: Any, field_name: str) -> Optional[str]:
        """安全获取ISO格式时间字符串"""
        time_field = getattr(obj, field_name, None)
        if time_field is None:
            return None
        
        # 如果是datetime对象，转换为ISO字符串
        if hasattr(time_field, 'isoformat'):
            return time_field.isoformat()
        
        # 如果已经是字符串，直接返回
        if isinstance(time_field, str):
            return time_field
        
        # 如果是数字，转换为datetime再转ISO
        if isinstance(time_field, (int, float)):
            try:
                return datetime.fromtimestamp(time_field).isoformat()
            except:
                pass
        
        # 默认返回None
        return None
    
    @staticmethod
    def _extract_error_message(file_obj: Any) -> Optional[str]:
        """提取错误信息"""
        try:
            if getattr(file_obj, 'status', None) == 'failed':
                # 从元数据中提取错误信息
                metadata = getattr(file_obj, 'file_metadata', {}) or {}
                return metadata.get('error_message')
            return None
        except Exception:
            return None


@dataclass
class FileStatusSummaryDto:
    """文件状态摘要数据传输对象"""
    kb_id: str
    total_files: int
    uploaded_files: int
    processing_files: int
    completed_files: int
    failed_files: int
    pending_files: int = 0
    cancelled_files: int = 0
    success_rate: float = 0.0
    last_updated: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)
    
    @classmethod
    def from_statistics(cls, kb_id: str, stats: Dict[str, Any]) -> 'FileStatusSummaryDto':
        """从统计数据创建摘要DTO"""
        total_files = stats.get('total_files', 0)
        status_stats = stats.get('status_statistics', {})
        
        uploaded_files = status_stats.get('uploaded', 0)
        processing_files = status_stats.get('processing', 0)
        completed_files = status_stats.get('completed', 0)
        failed_files = status_stats.get('failed', 0)
        pending_files = status_stats.get('pending', 0)
        cancelled_files = status_stats.get('cancelled', 0)
        
        # 计算成功率
        success_rate = 0.0
        if total_files > 0:
            success_rate = (completed_files / total_files) * 100
        
        return cls(
            kb_id=kb_id,
            total_files=total_files,
            uploaded_files=uploaded_files,
            processing_files=processing_files,
            completed_files=completed_files,
            failed_files=failed_files,
            pending_files=pending_files,
            cancelled_files=cancelled_files,
            success_rate=round(success_rate, 2),
            last_updated=datetime.now().isoformat()
        )


@dataclass
class FileStatusBatchResponseDto:
    """文件状态批量响应数据传输对象"""
    files: List[FileStatusDto]
    pagination: Dict[str, Any]
    filter: str
    summary: Optional[FileStatusSummaryDto] = None
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        result = {
            'files': [file_dto.to_dict() for file_dto in self.files],
            'pagination': self.pagination,
            'filter': self.filter,
            'timestamp': self.timestamp
        }
        if self.summary:
            result['summary'] = self.summary.to_dict()
        return result
    
    @classmethod
    def create_pagination_info(cls, page: int, page_size: int, total: int) -> Dict[str, Any]:
        """创建分页信息"""
        return {
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': (total + page_size - 1) // page_size if total > 0 else 0,
            'has_next': page * page_size < total,
            'has_prev': page > 1
        }


@dataclass
class FileStatusEventDto:
    """文件状态事件数据传输对象"""
    event_type: str
    file_id: str
    kb_id: str
    old_status: Optional[str] = None
    new_status: Optional[str] = None
    timestamp: str = ""
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return asdict(self)
    
    @classmethod
    def create_status_change_event(cls, file_id: str, kb_id: str, 
                                 old_status: str, new_status: str) -> 'FileStatusEventDto':
        """创建状态变化事件"""
        return cls(
            event_type="file_status_change",
            file_id=file_id,
            kb_id=kb_id,
            old_status=old_status,
            new_status=new_status
        )
    
    @classmethod
    def create_processing_progress_event(cls, file_id: str, kb_id: str, 
                                       progress: Dict[str, Any]) -> 'FileStatusEventDto':
        """创建处理进度事件"""
        return cls(
            event_type="processing_progress",
            file_id=file_id,
            kb_id=kb_id,
            metadata=progress
        )