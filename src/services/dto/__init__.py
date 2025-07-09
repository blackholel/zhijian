"""
数据传输对象(DTO)包

单一职责：数据传输和序列化
清晰边界：与数据库模型和业务逻辑分离
可扩展接口：支持多种数据格式转换
"""

from .file_status_dto import (
    FileStatusDto,
    FileStatusSummaryDto,
    FileStatusBatchResponseDto,
    FileStatusEventDto,
    FileStatus
)

__all__ = [
    'FileStatusDto',
    'FileStatusSummaryDto', 
    'FileStatusBatchResponseDto',
    'FileStatusEventDto',
    'FileStatus'
]