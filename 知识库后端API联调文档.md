# 知识库后端API联调文档

## 概述

本文档提供语析知识库系统的完整后端API接口说明，包括知识库管理和权限控制两大模块。系统已集成RBAC权限管理，支持多用户访问控制。

## 认证说明

所有API均需要JWT Token认证，通过Header传递：
```
Authorization: Bearer <JWT_TOKEN>
```

### 权限级别
- **read**: 只读权限，可查看和查询知识库
- **write**: 编辑权限，可上传和删除文档
- **admin**: 管理权限，可管理用户权限
- **create**: 创建权限，可创建新知识库
- **delete**: 删除权限，可删除知识库

## 一、知识库核心管理API

**Base URL**: `http://localhost:5050/api/data`

### 1.1 获取知识库列表

**接口**: `GET /api/data/`  
**权限**: `kb:read`  
**说明**: 获取当前用户可访问的所有知识库

**请求示例**:
```bash
curl -X GET "http://localhost:5050/api/data/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**响应示例**:
```json
{
  "databases": [
    {
      "db_id": "kb_abc123",
      "name": "我的知识库",
      "description": "知识库描述",
      "created_at": "2025-01-01T00:00:00",
      "owner_id": "user_123",
      "files": {},
      "row_count": 0,
      "status": "已连接"
    }
  ]
}
```

### 1.2 创建知识库

**接口**: `POST /api/data/`  
**权限**: `kb:create`  
**说明**: 创建新的知识库

**请求体**:
```json
{
  "database_name": "新知识库",
  "description": "知识库描述",
  "embed_model_name": "siliconflow/BAAI/bge-m3"
}
```

**请求示例**:
```bash
curl -X POST "http://localhost:5050/api/data/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "database_name": "测试知识库",
    "description": "这是一个测试知识库",
    "embed_model_name": "siliconflow/BAAI/bge-m3"
  }'
```

**响应示例**:
```json
{
  "db_id": "kb_abc123",
  "name": "测试知识库",
  "description": "这是一个测试知识库",
  "created_at": "2025-01-01T00:00:00",
  "owner_id": "user_123",
  "files": {}
}
```

### 1.3 删除知识库

**接口**: `DELETE /api/data/`  
**权限**: `kb:delete`  
**说明**: 删除指定知识库

**请求参数**:
- `db_id`: 知识库ID

**请求示例**:
```bash
curl -X DELETE "http://localhost:5050/api/data/?db_id=kb_abc123" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**响应示例**:
```json
{
  "message": "删除成功"
}
```

### 1.4 查询知识库

**接口**: `POST /api/data/query-test`  
**权限**: `kb:query`  
**说明**: 对知识库进行查询

**请求体**:
```json
{
  "query": "查询内容",
  "meta": {
    "db_id": "kb_abc123",
    "top_k": 5
  }
}
```

**请求示例**:
```bash
curl -X POST "http://localhost:5050/api/data/query-test" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "什么是人工智能？",
    "meta": {
      "db_id": "kb_abc123",
      "top_k": 5
    }
  }'
```

### 1.5 上传文件

**接口**: `POST /api/data/upload`  
**权限**: `kb:upload`  
**说明**: 上传文件到指定知识库

**请求参数**:
- `file`: 文件（multipart/form-data）
- `db_id`: 知识库ID（可选）

**请求示例**:
```bash
curl -X POST "http://localhost:5050/api/data/upload?db_id=kb_abc123" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@document.pdf"
```

**响应示例**:
```json
{
  "message": "File successfully uploaded",
  "file_path": "/path/to/uploaded/file.pdf",
  "db_id": "kb_abc123"
}
```

### 1.6 添加文件到知识库

**接口**: `POST /api/data/add-files`  
**权限**: `kb:upload`  
**说明**: 将已上传的文件添加到知识库进行处理

**请求体**:
```json
{
  "db_id": "kb_abc123",
  "items": ["/path/to/file1.pdf", "/path/to/file2.txt"],
  "params": {
    "content_type": "file",
    "chunk_size": 1000
  }
}
```

**请求示例**:
```bash
curl -X POST "http://localhost:5050/api/data/add-files" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "db_id": "kb_abc123",
    "items": ["/path/to/document.pdf"],
    "params": {
      "content_type": "file",
      "chunk_size": 1000
    }
  }'
```

**响应示例**:
```json
{
  "message": "Processed 1 files, 0 files failed",
  "items": [
    {
      "file_id": "file_123",
      "filename": "document.pdf",
      "status": "success"
    }
  ],
  "status": "success"
}
```

### 1.7 获取知识库信息

**接口**: `GET /api/data/info`  
**权限**: `kb:read`  
**说明**: 获取指定知识库的详细信息

**请求参数**:
- `db_id`: 知识库ID

**请求示例**:
```bash
curl -X GET "http://localhost:5050/api/data/info?db_id=kb_abc123" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### 1.8 删除文档

**接口**: `DELETE /api/data/document`  
**权限**: `kb:upload`  
**说明**: 从知识库删除指定文档

**请求体**:
```json
{
  "db_id": "kb_abc123",
  "file_id": "file_123"
}
```

**请求示例**:
```bash
curl -X DELETE "http://localhost:5050/api/data/document" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "db_id": "kb_abc123",
    "file_id": "file_123"
  }'
```

### 1.9 获取文档信息

**接口**: `GET /api/data/document`  
**权限**: `kb:read`  
**说明**: 获取指定文档的信息

**请求参数**:
- `db_id`: 知识库ID
- `file_id`: 文件ID

**请求示例**:
```bash
curl -X GET "http://localhost:5050/api/data/document?db_id=kb_abc123&file_id=file_123" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## 二、知识库权限管理API

**Base URL**: `http://localhost:5050/api/kb-permissions`

### 2.1 授予知识库权限

**接口**: `POST /api/kb-permissions/grant`  
**权限**: `kb:manage_users`  
**说明**: 向用户授予知识库权限

**请求体**:
```json
{
  "user_id": "target_user_id",
  "db_id": "kb_abc123",
  "permission_type": "read",
  "expires_at": "2025-12-31T23:59:59Z"
}
```

**请求示例**:
```bash
curl -X POST "http://localhost:5050/api/kb-permissions/grant" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_456",
    "db_id": "kb_abc123",
    "permission_type": "read"
  }'
```

**响应示例**:
```json
{
  "message": "权限授予成功",
  "status": "success"
}
```

### 2.2 撤销知识库权限

**接口**: `POST /api/kb-permissions/revoke`  
**权限**: `kb:manage_users`  
**说明**: 撤销用户的知识库权限

**请求体**:
```json
{
  "user_id": "target_user_id",
  "db_id": "kb_abc123",
  "permission_type": "read"
}
```

**请求示例**:
```bash
curl -X POST "http://localhost:5050/api/kb-permissions/revoke" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_456",
    "db_id": "kb_abc123",
    "permission_type": "read"
  }'
```

**响应示例**:
```json
{
  "message": "权限撤销成功",
  "status": "success"
}
```

### 2.3 获取知识库权限列表

**接口**: `GET /api/kb-permissions/database/{db_id}`  
**权限**: `kb:manage_users`  
**说明**: 获取指定知识库的所有权限信息

**请求示例**:
```bash
curl -X GET "http://localhost:5050/api/kb-permissions/database/kb_abc123" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**响应示例**:
```json
{
  "db_id": "kb_abc123",
  "permissions": [
    {
      "permission_id": "perm_123",
      "user_id": "user_456",
      "user_name": "test_user",
      "permission_type": "read",
      "granted_by": "admin",
      "granted_at": "2025-01-01T00:00:00Z",
      "expires_at": null
    }
  ],
  "status": "success"
}
```

### 2.4 获取用户知识库列表

**接口**: `GET /api/kb-permissions/user/{user_id}/databases`  
**权限**: `kb:read` (查看自己) / `kb:manage_users` (查看他人)  
**说明**: 获取指定用户的所有知识库

**请求示例**:
```bash
curl -X GET "http://localhost:5050/api/kb-permissions/user/user_123/databases" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**响应示例**:
```json
{
  "user_id": "user_123",
  "databases": [
    {
      "db_id": "kb_abc123",
      "name": "我的知识库",
      "description": "知识库描述",
      "role": "owner",
      "permission_type": "owner",
      "created_at": "2025-01-01T00:00:00Z"
    }
  ],
  "status": "success"
}
```

### 2.5 获取当前用户知识库

**接口**: `GET /api/kb-permissions/my-databases`  
**权限**: `kb:read`  
**说明**: 获取当前用户的所有知识库

**请求示例**:
```bash
curl -X GET "http://localhost:5050/api/kb-permissions/my-databases" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### 2.6 检查权限

**接口**: `POST /api/kb-permissions/check`  
**权限**: `kb:read`  
**说明**: 检查当前用户对知识库的权限

**请求体**:
```json
{
  "db_id": "kb_abc123",
  "permission": "read"
}
```

**请求示例**:
```bash
curl -X POST "http://localhost:5050/api/kb-permissions/check" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "db_id": "kb_abc123",
    "permission": "read"
  }'
```

**响应示例**:
```json
{
  "user_id": "user_123",
  "db_id": "kb_abc123",
  "permission": "read",
  "has_permission": true,
  "status": "success"
}
```

### 2.7 获取可访问的知识库

**接口**: `GET /api/kb-permissions/accessible-databases`  
**权限**: `kb:read`  
**说明**: 获取当前用户可访问的知识库ID列表

**请求参数**:
- `permission`: 权限级别（可选，默认为"read"）

**请求示例**:
```bash
curl -X GET "http://localhost:5050/api/kb-permissions/accessible-databases?permission=read" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**响应示例**:
```json
{
  "user_id": "user_123",
  "permission": "read",
  "accessible_databases": ["kb_abc123", "kb_def456"],
  "count": 2,
  "status": "success"
}
```

### 2.8 设置知识库所有者

**接口**: `POST /api/kb-permissions/set-owner`  
**权限**: `kb:manage_users`  
**说明**: 转移知识库所有权（仅所有者或超级管理员）

**请求体**:
```json
{
  "db_id": "kb_abc123",
  "new_owner_id": "new_user_id"
}
```

**请求示例**:
```bash
curl -X POST "http://localhost:5050/api/kb-permissions/set-owner" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "db_id": "kb_abc123",
    "new_owner_id": "user_789"
  }'
```

### 2.9 获取权限类型

**接口**: `GET /api/kb-permissions/permission-types`  
**权限**: `kb:read`  
**说明**: 获取系统支持的权限类型说明

**请求示例**:
```bash
curl -X GET "http://localhost:5050/api/kb-permissions/permission-types" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**响应示例**:
```json
{
  "permission_types": [
    {
      "name": "read",
      "display_name": "只读权限",
      "description": "可以查看和查询知识库内容"
    },
    {
      "name": "write",
      "display_name": "编辑权限",
      "description": "可以查看、查询、上传和删除知识库内容"
    },
    {
      "name": "admin",
      "display_name": "管理权限",
      "description": "可以进行所有操作，包括管理其他用户权限"
    }
  ],
  "permission_hierarchy": {
    "read": ["read"],
    "write": ["read", "write"],
    "admin": ["read", "write", "admin"]
  },
  "status": "success"
}
```

## 三、错误响应

所有API在出错时会返回相应的HTTP状态码和错误信息：

### 常见错误状态码
- `400`: 请求参数错误
- `401`: 未认证或Token无效
- `403`: 权限不足
- `404`: 资源不存在
- `500`: 服务器内部错误

### 错误响应格式
```json
{
  "detail": "错误描述信息"
}
```

## 四、使用示例

### 完整使用流程示例

1. **创建知识库**:
```bash
# 创建知识库
curl -X POST "http://localhost:5050/api/data/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "database_name": "技术文档库",
    "description": "存储技术文档的知识库",
    "embed_model_name": "siliconflow/BAAI/bge-m3"
  }'
```

2. **上传文件**:
```bash
# 上传文件
curl -X POST "http://localhost:5050/api/data/upload?db_id=kb_abc123" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "file=@technical_doc.pdf"
```

3. **添加文件到知识库**:
```bash
# 处理文件
curl -X POST "http://localhost:5050/api/data/add-files" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "db_id": "kb_abc123",
    "items": ["/path/to/technical_doc.pdf"],
    "params": {"content_type": "file"}
  }'
```

4. **授予权限**:
```bash
# 给其他用户授予读权限
curl -X POST "http://localhost:5050/api/kb-permissions/grant" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "colleague_user_id",
    "db_id": "kb_abc123",
    "permission_type": "read"
  }'
```

5. **查询知识库**:
```bash
# 查询内容
curl -X POST "http://localhost:5050/api/data/query-test" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "如何配置系统？",
    "meta": {"db_id": "kb_abc123"}
  }'
```

## 五、注意事项

1. **权限控制**: 用户只能访问自己拥有或被授权的知识库
2. **所有者权限**: 知识库所有者拥有该知识库的所有权限
3. **权限层级**: admin > write > read，高级权限包含低级权限
4. **Token有效期**: JWT Token需要定期更新
5. **文件大小限制**: 上传文件需要考虑系统配置的大小限制
6. **并发处理**: 文件处理是异步进行的，需要通过状态查询确认完成

## 六、联调建议

1. **开发环境**: 使用测试用户和测试知识库进行开发
2. **错误处理**: 实现完整的错误处理和重试机制
3. **日志记录**: 记录API调用日志便于调试
4. **权限测试**: 验证不同权限级别的用户访问控制
5. **性能测试**: 测试大文件上传和批量操作的性能

---

**服务器地址**: http://localhost:5050  
**API文档**: http://localhost:5050/docs  
**更新时间**: 2025-07-05