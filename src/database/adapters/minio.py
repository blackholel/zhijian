"""
MinIO对象存储适配器
"""

import asyncio
import io
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, AsyncGenerator
from urllib.parse import urlparse

try:
    from minio import Minio
    from minio.error import S3Error, InvalidResponseError
    from minio.commonconfig import CopySource
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False

from ..base import FileStorageAdapter, ConnectionStatus, ConnectionError

logger = logging.getLogger(__name__)


class MinIOAdapter(FileStorageAdapter):
    """MinIO对象存储适配器"""
    
    def __init__(self, config: Dict[str, Any], db_name: str = None):
        """
        初始化MinIO适配器
        
        Args:
            config: 数据库配置
            db_name: 数据库名称
        """
        if not MINIO_AVAILABLE:
            raise ConnectionError("MinIO not available. Please install: pip install minio")
        
        super().__init__(config, db_name)
        
        self._minio_client = None
        self.default_bucket = config.get('bucket_name', 'yuxi-know')
        
        # 连接配置
        self.endpoint = self._parse_endpoint(config.get('endpoint', 'localhost:9000'))
        self.access_key = config.get('access_key', 'minioadmin')
        self.secret_key = config.get('secret_key', 'minioadmin')
        self.secure = config.get('secure', False)
        self.region = config.get('region', 'us-east-1')
        
        logger.debug(f"MinIO adapter initialized for {self.db_name}")
    
    def _parse_endpoint(self, endpoint: str) -> str:
        """解析endpoint，移除协议前缀"""
        if endpoint.startswith(('http://', 'https://')):
            parsed = urlparse(endpoint)
            if parsed.port:
                return f"{parsed.hostname}:{parsed.port}"
            else:
                return parsed.hostname
        return endpoint
    
    async def connect(self) -> bool:
        """建立数据库连接"""
        if self.status == ConnectionStatus.CONNECTED:
            return True
        
        self.status = ConnectionStatus.CONNECTING
        
        try:
            # 创建MinIO客户端
            def _create_client():
                return Minio(
                    endpoint=self.endpoint,
                    access_key=self.access_key,
                    secret_key=self.secret_key,
                    secure=self.secure,
                    region=self.region
                )
            
            self._minio_client = await asyncio.get_event_loop().run_in_executor(None, _create_client)
            
            # 测试连接并确保默认bucket存在
            await self._test_connection()
            await self._ensure_bucket_exists(self.default_bucket)
            
            self._client = self._minio_client
            self.status = ConnectionStatus.CONNECTED
            
            logger.info(f"MinIO connection established for {self.db_name} at {self.endpoint}")
            return True
            
        except Exception as e:
            self.status = ConnectionStatus.ERROR
            logger.error(f"Failed to connect to MinIO {self.db_name}: {e}")
            return False
    
    async def _test_connection(self):
        """测试数据库连接"""
        def _sync_test():
            # 尝试列出buckets来测试连接
            list(self._minio_client.list_buckets())
        
        await asyncio.get_event_loop().run_in_executor(None, _sync_test)
    
    async def _ensure_bucket_exists(self, bucket_name: str):
        """确保bucket存在"""
        def _sync_ensure():
            if not self._minio_client.bucket_exists(bucket_name):
                self._minio_client.make_bucket(bucket_name, location=self.region)
                logger.info(f"Created bucket: {bucket_name}")
        
        await asyncio.get_event_loop().run_in_executor(None, _sync_ensure)
    
    async def disconnect(self) -> bool:
        """断开数据库连接"""
        try:
            # MinIO客户端不需要显式关闭连接
            self._minio_client = None
            self._client = None
            self.status = ConnectionStatus.DISCONNECTED
            
            logger.info(f"MinIO connection closed for {self.db_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from MinIO {self.db_name}: {e}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            if not self.is_connected:
                return {
                    'status': 'disconnected',
                    'database_name': self.db_name,
                    'timestamp': datetime.now().isoformat()
                }
            
            def _sync_health_check():
                # 列出buckets来测试连接
                buckets = list(self._minio_client.list_buckets())
                bucket_info = []
                
                for bucket in buckets:
                    try:
                        # 获取bucket中的对象数量（最多1000个用于统计）
                        objects = list(self._minio_client.list_objects(bucket.name, recursive=True))
                        object_count = len(objects)
                        
                        bucket_info.append({
                            'name': bucket.name,
                            'creation_date': bucket.creation_date.isoformat() if bucket.creation_date else None,
                            'object_count': object_count
                        })
                    except Exception as e:
                        bucket_info.append({
                            'name': bucket.name,
                            'creation_date': bucket.creation_date.isoformat() if bucket.creation_date else None,
                            'error': str(e)
                        })
                
                return {
                    'status': 'healthy',
                    'database_name': self.db_name,
                    'endpoint': self.endpoint,
                    'secure': self.secure,
                    'region': self.region,
                    'default_bucket': self.default_bucket,
                    'buckets': bucket_info,
                    'timestamp': datetime.now().isoformat()
                }
            
            result = await asyncio.get_event_loop().run_in_executor(None, _sync_health_check)
            return result
            
        except Exception as e:
            return {
                'status': 'error',
                'database_name': self.db_name,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    async def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        return {
            'database_name': self.db_name,
            'type': 'minio',
            'endpoint': self.endpoint,
            'access_key': self.access_key,
            'secure': self.secure,
            'region': self.region,
            'default_bucket': self.default_bucket,
            'status': self.status.value
        }
    
    def _sanitize_key(self, key: str) -> str:
        """清理对象键，移除不安全字符"""
        import re
        # 移除或替换不安全字符
        safe_key = re.sub(r'[^\w\-_\./]', '_', key)
        # 移除开头的斜杠
        safe_key = safe_key.lstrip('/')
        return safe_key[:1000]  # 限制长度
    
    def _guess_content_type(self, file_path: str) -> str:
        """根据文件扩展名推断内容类型"""
        extension = Path(file_path).suffix.lower()
        content_types = {
            '.pdf': 'application/pdf',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.doc': 'application/msword',
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.html': 'text/html',
            '.htm': 'text/html',
            '.json': 'application/json',
            '.csv': 'text/csv',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.bmp': 'image/bmp',
            '.zip': 'application/zip',
            '.tar': 'application/x-tar',
            '.gz': 'application/gzip'
        }
        return content_types.get(extension, 'application/octet-stream')
    
    async def upload_file(self, file_path: str, storage_key: str, 
                         bucket_name: str = None, content_type: str = None) -> str:
        """
        上传文件到MinIO
        
        Args:
            file_path: 本地文件路径
            storage_key: 存储键
            bucket_name: bucket名称，默认使用default_bucket
            content_type: 内容类型，自动推断如果未提供
            
        Returns:
            存储键
        """
        await self.ensure_connected()
        
        bucket = bucket_name or self.default_bucket
        clean_key = self._sanitize_key(storage_key)
        
        try:
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            
            if content_type is None:
                content_type = self._guess_content_type(file_path)
            
            file_size = file_path_obj.stat().st_size
            
            def _sync_upload():
                # 确保bucket存在
                if not self._minio_client.bucket_exists(bucket):
                    self._minio_client.make_bucket(bucket, location=self.region)
                
                # 上传文件
                result = self._minio_client.fput_object(
                    bucket_name=bucket,
                    object_name=clean_key,
                    file_path=str(file_path_obj),
                    content_type=content_type
                )
                return result
            
            await asyncio.get_event_loop().run_in_executor(None, _sync_upload)
            
            logger.info(f"File uploaded successfully: {bucket}/{clean_key} ({file_size} bytes)")
            return clean_key
            
        except Exception as e:
            logger.error(f"File upload failed {storage_key}: {e}")
            raise
    
    async def upload_bytes(self, data: bytes, storage_key: str, 
                          bucket_name: str = None, content_type: str = None) -> str:
        """
        上传二进制数据到MinIO
        
        Args:
            data: 二进制数据
            storage_key: 存储键
            bucket_name: bucket名称
            content_type: 内容类型
            
        Returns:
            存储键
        """
        await self.ensure_connected()
        
        bucket = bucket_name or self.default_bucket
        clean_key = self._sanitize_key(storage_key)
        
        try:
            if content_type is None:
                content_type = "application/octet-stream"
            
            data_stream = io.BytesIO(data)
            data_size = len(data)
            
            def _sync_upload():
                # 确保bucket存在
                if not self._minio_client.bucket_exists(bucket):
                    self._minio_client.make_bucket(bucket, location=self.region)
                
                result = self._minio_client.put_object(
                    bucket_name=bucket,
                    object_name=clean_key,
                    data=data_stream,
                    length=data_size,
                    content_type=content_type
                )
                return result
            
            await asyncio.get_event_loop().run_in_executor(None, _sync_upload)
            
            logger.info(f"Data uploaded successfully: {bucket}/{clean_key} ({data_size} bytes)")
            return clean_key
            
        except Exception as e:
            logger.error(f"Data upload failed {storage_key}: {e}")
            raise
    
    async def download_file(self, storage_key: str, local_path: str, 
                           bucket_name: str = None) -> bool:
        """
        下载文件到本地
        
        Args:
            storage_key: 存储键
            local_path: 本地文件路径
            bucket_name: bucket名称
            
        Returns:
            下载成功返回True
        """
        await self.ensure_connected()
        
        bucket = bucket_name or self.default_bucket
        
        try:
            def _sync_download():
                self._minio_client.fget_object(
                    bucket_name=bucket,
                    object_name=storage_key,
                    file_path=local_path
                )
            
            await asyncio.get_event_loop().run_in_executor(None, _sync_download)
            
            logger.info(f"File downloaded successfully: {bucket}/{storage_key} -> {local_path}")
            return True
            
        except Exception as e:
            logger.error(f"File download failed {storage_key}: {e}")
            return False
    
    async def get_file_stream(self, storage_key: str, 
                             bucket_name: str = None) -> AsyncGenerator[bytes, None]:
        """
        获取文件流
        
        Args:
            storage_key: 存储键
            bucket_name: bucket名称
            
        Yields:
            文件数据块
        """
        await self.ensure_connected()
        
        bucket = bucket_name or self.default_bucket
        
        try:
            def _get_object():
                return self._minio_client.get_object(
                    bucket_name=bucket,
                    object_name=storage_key
                )
            
            response = await asyncio.get_event_loop().run_in_executor(None, _get_object)
            
            try:
                chunk_size = 8192
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
            finally:
                response.close()
                response.release_conn()
                
        except Exception as e:
            logger.error(f"Get file stream failed {storage_key}: {e}")
            raise
    
    async def get_file_bytes(self, storage_key: str, bucket_name: str = None) -> bytes:
        """
        获取文件二进制数据
        
        Args:
            storage_key: 存储键
            bucket_name: bucket名称
            
        Returns:
            文件二进制数据
        """
        await self.ensure_connected()
        
        bucket = bucket_name or self.default_bucket
        
        try:
            def _get_object():
                response = self._minio_client.get_object(
                    bucket_name=bucket,
                    object_name=storage_key
                )
                try:
                    return response.read()
                finally:
                    response.close()
                    response.release_conn()
            
            data = await asyncio.get_event_loop().run_in_executor(None, _get_object)
            
            logger.debug(f"Retrieved file data: {bucket}/{storage_key} ({len(data)} bytes)")
            return data
            
        except Exception as e:
            logger.error(f"Get file bytes failed {storage_key}: {e}")
            raise
    
    async def delete_file(self, storage_key: str, bucket_name: str = None) -> bool:
        """
        删除文件
        
        Args:
            storage_key: 存储键
            bucket_name: bucket名称
            
        Returns:
            删除成功返回True
        """
        await self.ensure_connected()
        
        bucket = bucket_name or self.default_bucket
        
        try:
            def _sync_delete():
                self._minio_client.remove_object(
                    bucket_name=bucket,
                    object_name=storage_key
                )
            
            await asyncio.get_event_loop().run_in_executor(None, _sync_delete)
            
            logger.info(f"File deleted successfully: {bucket}/{storage_key}")
            return True
            
        except Exception as e:
            logger.error(f"File deletion failed {storage_key}: {e}")
            return False
    
    async def file_exists(self, storage_key: str, bucket_name: str = None) -> bool:
        """
        检查文件是否存在
        
        Args:
            storage_key: 存储键
            bucket_name: bucket名称
            
        Returns:
            文件存在返回True
        """
        await self.ensure_connected()
        
        bucket = bucket_name or self.default_bucket
        
        try:
            def _sync_stat():
                self._minio_client.stat_object(
                    bucket_name=bucket,
                    object_name=storage_key
                )
            
            await asyncio.get_event_loop().run_in_executor(None, _sync_stat)
            return True
            
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            logger.error(f"File exists check failed {storage_key}: {e}")
            return False
        except Exception as e:
            logger.error(f"File exists check failed {storage_key}: {e}")
            return False
    
    async def get_file_info(self, storage_key: str, bucket_name: str = None) -> Dict[str, Any]:
        """
        获取文件信息
        
        Args:
            storage_key: 存储键
            bucket_name: bucket名称
            
        Returns:
            文件信息字典
        """
        await self.ensure_connected()
        
        bucket = bucket_name or self.default_bucket
        
        try:
            def _sync_stat():
                return self._minio_client.stat_object(
                    bucket_name=bucket,
                    object_name=storage_key
                )
            
            stat = await asyncio.get_event_loop().run_in_executor(None, _sync_stat)
            
            return {
                'bucket': bucket,
                'storage_key': storage_key,
                'size': stat.size,
                'last_modified': stat.last_modified.isoformat() if stat.last_modified else None,
                'etag': stat.etag,
                'content_type': stat.content_type,
                'metadata': stat.metadata or {}
            }
            
        except Exception as e:
            logger.error(f"Get file info failed {storage_key}: {e}")
            raise
    
    async def list_objects(self, prefix: str = "", bucket_name: str = None, 
                          recursive: bool = True) -> List[Dict[str, Any]]:
        """
        列出对象
        
        Args:
            prefix: 对象键前缀
            bucket_name: bucket名称
            recursive: 是否递归列出
            
        Returns:
            对象信息列表
        """
        await self.ensure_connected()
        
        bucket = bucket_name or self.default_bucket
        
        try:
            def _sync_list():
                objects = self._minio_client.list_objects(
                    bucket_name=bucket,
                    prefix=prefix,
                    recursive=recursive
                )
                
                object_list = []
                for obj in objects:
                    object_list.append({
                        'key': obj.object_name,
                        'size': obj.size,
                        'last_modified': obj.last_modified.isoformat() if obj.last_modified else None,
                        'etag': obj.etag,
                        'is_dir': obj.is_dir
                    })
                
                return object_list
            
            result = await asyncio.get_event_loop().run_in_executor(None, _sync_list)
            
            logger.debug(f"Listed objects: bucket={bucket}, prefix={prefix}, count={len(result)}")
            return result
            
        except Exception as e:
            logger.error(f"List objects failed: bucket={bucket}, prefix={prefix}: {e}")
            return []
    
    async def copy_object(self, source_key: str, dest_key: str, 
                         source_bucket: str = None, dest_bucket: str = None) -> bool:
        """
        复制对象
        
        Args:
            source_key: 源对象键
            dest_key: 目标对象键
            source_bucket: 源bucket名称
            dest_bucket: 目标bucket名称
            
        Returns:
            复制成功返回True
        """
        await self.ensure_connected()
        
        src_bucket = source_bucket or self.default_bucket
        dst_bucket = dest_bucket or self.default_bucket
        
        try:
            def _sync_copy():
                copy_source = CopySource(src_bucket, source_key)
                self._minio_client.copy_object(
                    bucket_name=dst_bucket,
                    object_name=dest_key,
                    source=copy_source
                )
            
            await asyncio.get_event_loop().run_in_executor(None, _sync_copy)
            
            logger.info(f"Object copied: {src_bucket}/{source_key} -> {dst_bucket}/{dest_key}")
            return True
            
        except Exception as e:
            logger.error(f"Object copy failed {source_key} -> {dest_key}: {e}")
            return False
    
    async def get_presigned_url(self, storage_key: str, bucket_name: str = None, 
                               expires: timedelta = None, method: str = "GET") -> str:
        """
        获取预签名URL
        
        Args:
            storage_key: 存储键
            bucket_name: bucket名称
            expires: 过期时间
            method: HTTP方法
            
        Returns:
            预签名URL
        """
        await self.ensure_connected()
        
        bucket = bucket_name or self.default_bucket
        
        try:
            if expires is None:
                expires = timedelta(hours=1)
            
            def _get_url():
                return self._minio_client.get_presigned_url(
                    method=method,
                    bucket_name=bucket,
                    object_name=storage_key,
                    expires=expires
                )
            
            url = await asyncio.get_event_loop().run_in_executor(None, _get_url)
            
            logger.debug(f"Generated presigned URL: {bucket}/{storage_key}")
            return url
            
        except Exception as e:
            logger.error(f"Get presigned URL failed {storage_key}: {e}")
            raise
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        base_metrics = super().get_metrics()
        
        base_metrics.update({
            'storage_type': 'minio',
            'endpoint': self.endpoint,
            'secure': self.secure,
            'region': self.region,
            'default_bucket': self.default_bucket
        })
        
        return base_metrics