# 🌐 完整API调用指南

## 📋 API架构说明

### 🔧 路由结构
- **传统聊天API**: `/chat/*` - 现有的智能体聊天接口
- **企业级智能体API**: `/api/enterprise/agents/*` - 新的企业级智能体接口

### 🔐 认证说明
- 所有API都需要JWT Token认证
- 企业级API还需要特定的系统权限

## 🚀 使用流程

### 1. 获取JWT Token

```bash
# 用户登录获取Token
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "your_username",
    "password": "your_password"
  }'

# 响应示例
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user_info": {
    "id": "user123",
    "username": "your_username"
  }
}
```

## 🤖 企业级智能体API调用

### 1. 列出所有企业级智能体

```bash
curl -X GET "http://localhost:8000/api/enterprise/agents/" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# 响应示例
["enterprise_chatbot"]
```

### 2. 获取智能体详细信息

```bash
curl -X GET "http://localhost:8000/api/enterprise/agents/enterprise_chatbot/info" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# 响应示例
{
  "name": "enterprise_chatbot",
  "description": "企业级聊天机器人",
  "config_schema": {
    "system_prompt": {
      "type": "str",
      "name": "系统提示词",
      "default": "你是一个企业级智能助手..."
    }
  },
  "requirements": ["ZHIPUAI_API_KEY"],
  "enterprise_features": {
    "permission_integration": true,
    "database_integration": true,
    "knowledge_base_integration": true
  },
  "metrics": {
    "total_sessions": 0,
    "active_sessions": 0,
    "total_messages": 0
  }
}
```

### 3. 创建企业级智能体会话

```bash
curl -X POST "http://localhost:8000/api/enterprise/agents/sessions" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "enterprise_chatbot",
    "organization_id": "org_123",
    "metadata": {
      "department": "IT",
      "project": "AI_Assistant"
    }
  }'

# 响应示例
{
  "session_id": "session_456",
  "user_id": "user123",
  "agent_name": "enterprise_chatbot",
  "thread_id": "thread_789",
  "created_at": "2024-01-15T10:30:00Z",
  "last_activity": "2024-01-15T10:30:00Z",
  "organization_id": "org_123",
  "metadata": {
    "department": "IT",
    "project": "AI_Assistant"
  }
}
```

### 4. 发送消息到企业级智能体（流式响应）

```bash
curl -X POST "http://localhost:8000/api/enterprise/agents/sessions/session_456/messages" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "请帮我查询销售数据知识库中的最新报告",
    "config": {
      "enable_knowledge_retrieval": true,
      "enable_database_query": false
    }
  }'

# 流式响应示例
data: 我来帮您查询销售数据知识库中的最新报告
data: 
data: 正在搜索相关信息...
data: 
data: 找到以下相关报告：
data: 1. 2024年Q1销售总结报告
data: 2. 月度销售数据分析
data: [DONE]
```

### 5. 获取会话历史记录

```bash
curl -X GET "http://localhost:8000/api/enterprise/agents/sessions/session_456/history" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# 响应示例
{
  "session_id": "session_456",
  "history": [
    {
      "type": "human",
      "content": "请帮我查询销售数据知识库中的最新报告"
    },
    {
      "type": "ai", 
      "content": "我来帮您查询销售数据知识库中的最新报告..."
    }
  ]
}
```

### 6. 列出用户的所有会话

```bash
curl -X GET "http://localhost:8000/api/enterprise/agents/sessions" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# 响应示例
[
  {
    "session_id": "session_456",
    "user_id": "user123",
    "agent_name": "enterprise_chatbot",
    "thread_id": "thread_789",
    "created_at": "2024-01-15T10:30:00Z",
    "last_activity": "2024-01-15T10:35:00Z",
    "organization_id": "org_123",
    "metadata": {}
  }
]
```

### 7. 删除会话

```bash
curl -X DELETE "http://localhost:8000/api/enterprise/agents/sessions/session_456" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# 响应示例
{
  "message": "会话已删除"
}
```

### 8. 获取系统指标

```bash
curl -X GET "http://localhost:8000/api/enterprise/agents/metrics" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# 响应示例
{
  "total_sessions": 5,
  "active_sessions": 2,
  "total_agents": 1,
  "agent_metrics": {
    "enterprise_chatbot": {
      "total_sessions": 5,
      "active_sessions": 2,
      "total_messages": 20,
      "total_errors": 0
    }
  },
  "system_health": {
    "database_manager": "healthy",
    "permission_manager": "healthy"
  }
}
```

### 9. 健康检查

```bash
curl -X GET "http://localhost:8000/api/enterprise/agents/health"

# 响应示例
{
  "status": "healthy",
  "details": {
    "database_manager": "healthy",
    "permission_manager": "healthy",
    "audit_logger": "healthy",
    "tools_manager": "healthy"
  },
  "timestamp": "2024-01-15T10:40:00Z"
}
```

### 10. 清理过期会话（管理员功能）

```bash
curl -X POST "http://localhost:8000/api/enterprise/agents/cleanup" \
  -H "Authorization: Bearer ADMIN_JWT_TOKEN"

# 响应示例
{
  "message": "清理任务已启动"
}
```

## 💬 传统聊天API调用

### 1. 获取默认智能体

```bash
curl -X GET "http://localhost:8000/chat/default_agent" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# 响应示例
{
  "default_agent_id": "chatbot"
}
```

### 2. 获取所有可用智能体

```bash
curl -X GET "http://localhost:8000/chat/agent" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# 响应示例
{
  "agents": [
    {
      "name": "chatbot",
      "description": "基础的对话机器人",
      "config_schema": {...},
      "requirements": ["ZHIPUAI_API_KEY"]
    }
  ]
}
```

### 3. 创建对话线程

```bash
curl -X POST "http://localhost:8000/chat/thread" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "技术咨询",
    "agent_id": "chatbot",
    "description": "关于API集成的技术问题"
  }'

# 响应示例
{
  "id": "thread_123",
  "user_id": "user123",
  "agent_id": "chatbot",
  "title": "技术咨询",
  "description": "关于API集成的技术问题",
  "create_at": "2024-01-15T10:30:00Z",
  "update_at": "2024-01-15T10:30:00Z"
}
```

### 4. 与传统智能体对话

```bash
curl -X POST "http://localhost:8000/chat/agent/chatbot" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "你好，请介绍一下你的功能",
    "config": {
      "thread_id": "thread_123",
      "model": "zhipu/glm-4-plus"
    },
    "meta": {
      "request_id": "req_001"
    }
  }'

# 流式响应示例
{"request_id":"req_001","response":null,"status":"init","meta":{...},"msg":{...}}
{"request_id":"req_001","response":null,"content":"你好！","msg":{...},"metadata":{},"status":"loading"}
{"request_id":"req_001","response":null,"content":"我是一个","msg":{...},"metadata":{},"status":"loading"}
{"request_id":"req_001","response":null,"content":"智能助手","msg":{...},"metadata":{},"status":"loading"}
{"request_id":"req_001","response":null,"status":"finished","meta":{...}}
```

### 5. 获取智能体历史记录

```bash
curl -X GET "http://localhost:8000/chat/agent/chatbot/history?thread_id=thread_123" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# 响应示例
{
  "history": [
    {
      "type": "human",
      "content": "你好，请介绍一下你的功能"
    },
    {
      "type": "ai",
      "content": "你好！我是一个智能助手..."
    }
  ]
}
```

### 6. 获取线程列表

```bash
curl -X GET "http://localhost:8000/chat/threads?agent_id=chatbot" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# 响应示例
[
  {
    "id": "thread_123",
    "user_id": "user123",
    "agent_id": "chatbot",
    "title": "技术咨询",
    "description": "关于API集成的技术问题",
    "create_at": "2024-01-15T10:30:00Z",
    "update_at": "2024-01-15T10:35:00Z"
  }
]
```

### 7. 更新线程信息

```bash
curl -X PUT "http://localhost:8000/chat/thread/thread_123" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "API集成讨论",
    "description": "详细的API集成技术讨论"
  }'

# 响应示例
{
  "id": "thread_123",
  "user_id": "user123",
  "agent_id": "chatbot",
  "title": "API集成讨论",
  "description": "详细的API集成技术讨论",
  "create_at": "2024-01-15T10:30:00Z",
  "update_at": "2024-01-15T10:45:00Z"
}
```

### 8. 删除线程

```bash
curl -X DELETE "http://localhost:8000/chat/thread/thread_123" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# 响应示例
{
  "message": "删除成功"
}
```

## 🔄 完整使用示例

### 场景1：企业级智能体对话流程

```bash
# 1. 登录获取Token
TOKEN=$(curl -s -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}' \
  | jq -r '.access_token')

# 2. 创建企业级会话
SESSION_ID=$(curl -s -X POST "http://localhost:8000/api/enterprise/agents/sessions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "enterprise_chatbot"}' \
  | jq -r '.session_id')

# 3. 发送消息
curl -X POST "http://localhost:8000/api/enterprise/agents/sessions/$SESSION_ID/messages" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "请帮我查询知识库"}'

# 4. 查看历史
curl -X GET "http://localhost:8000/api/enterprise/agents/sessions/$SESSION_ID/history" \
  -H "Authorization: Bearer $TOKEN"
```

### 场景2：传统智能体对话流程

```bash
# 1. 登录获取Token
TOKEN=$(curl -s -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "password"}' \
  | jq -r '.access_token')

# 2. 创建线程
THREAD_ID=$(curl -s -X POST "http://localhost:8000/chat/thread" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "测试对话", "agent_id": "chatbot"}' \
  | jq -r '.id')

# 3. 发送消息
curl -X POST "http://localhost:8000/chat/agent/chatbot" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"你好\", \"config\": {\"thread_id\": \"$THREAD_ID\"}}"

# 4. 查看历史
curl -X GET "http://localhost:8000/chat/agent/chatbot/history?thread_id=$THREAD_ID" \
  -H "Authorization: Bearer $TOKEN"
```

## 🚨 常见错误及解决方案

### 1. 认证错误
```
HTTP 401: {"detail": "Not authenticated"}
```
**解决方案**: 检查JWT Token是否正确，是否已过期

### 2. 权限错误
```
HTTP 403: {"detail": "Permission denied"}
```
**解决方案**: 检查用户是否有相应的系统权限

### 3. 会话不存在
```
HTTP 404: {"detail": "会话不存在或已过期"}
```
**解决方案**: 重新创建会话或检查会话ID是否正确

### 4. 智能体不存在
```
HTTP 404: {"detail": "智能体 xxx 不存在"}
```
**解决方案**: 检查智能体名称是否正确，或先获取可用智能体列表

## 📊 性能建议

### 1. 连接复用
```bash
# 使用 --keepalive 保持连接
curl --keepalive-time 60 ...
```

### 2. 并发控制
```bash
# 限制并发请求数量
curl --limit-rate 100k ...
```

### 3. 超时设置
```bash
# 设置合理的超时时间
curl --connect-timeout 30 --max-time 300 ...
```

## 🎯 开发调试技巧

### 1. 启用详细输出
```bash
curl -v -X POST "http://localhost:8000/api/enterprise/agents/sessions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "enterprise_chatbot"}'
```

### 2. 保存响应到文件
```bash
curl -X GET "http://localhost:8000/api/enterprise/agents/health" \
  -o health_check.json
```

### 3. 使用环境变量
```bash
export API_BASE_URL="http://localhost:8000"
export JWT_TOKEN="your_jwt_token"

curl -X GET "$API_BASE_URL/api/enterprise/agents/" \
  -H "Authorization: Bearer $JWT_TOKEN"
```

---

🎉 **现在您可以完整使用企业级智能体系统的所有功能！** 