"""
文件管理系统异常定义
"""


class FileManagementError(Exception):
    """文件管理系统基础异常"""
    pass


class StorageError(FileManagementError):
    """存储相关异常"""
    pass


class ValidationError(FileManagementError):
    """验证相关异常"""
    pass


class DocumentNotFoundError(FileManagementError):
    """文档不存在异常"""
    pass


class ChunkNotFoundError(FileManagementError):
    """分块不存在异常"""
    pass


class ProcessingError(FileManagementError):
    """处理过程异常"""
    pass


class ConfigurationError(FileManagementError):
    """配置异常"""
    pass


class PermissionError(FileManagementError):
    """权限异常"""
    pass