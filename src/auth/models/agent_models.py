"""
智能体权限相关数据模型

扩展现有的权限系统以支持智能体管理
"""

from sqlalchemy import Column, String, JSON, DateTime, ForeignKey, Boolean, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.database.models import Base
import uuid
from datetime import datetime


class AgentDefinition(Base):
    """智能体定义模型"""
    __tablename__ = "agent_definitions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    agent_type = Column(String(50), nullable=False)
    version = Column(String(20), default="1.0.0")
    
    # 所属信息 
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)  # 修正外键引用
    # organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)  # 暂时禁用，等待 organizations 表创建
    organization_id = Column(UUID(as_uuid=True), nullable=True)  # 临时字段，不设置外键约束
    
    # 配置信息
    config_data = Column(JSON, default=dict)  # AgentConfig 的 JSON 序列化
    
    # 状态信息
    is_active = Column(Boolean, default=True)
    is_deleted = Column(Boolean, default=False)
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    # 关系
    user = relationship("User", back_populates="agent_definitions")
    sessions = relationship("AgentSession", back_populates="agent_definition")
    permissions = relationship("AgentPermission", back_populates="agent_definition")
    
    def __repr__(self):
        return f"<AgentDefinition(id={self.agent_id}, name={self.name}, type={self.agent_type})>"


class AgentSession(Base):
    """智能体会话模型"""
    __tablename__ = "agent_sessions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    
    # 关联信息
    agent_definition_id = Column(UUID(as_uuid=True), ForeignKey("agent_definitions.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    
    # 会话信息
    title = Column(String(200))
    description = Column(Text)
    session_type = Column(String(50), default="research")  # research, chat, analysis
    
    # 配置信息
    agent_configs = Column(JSON, default=list)  # 参与的智能体配置
    research_config = Column(JSON, default=dict)  # 研究配置
    
    # 状态信息
    current_phase = Column(String(50), default="planning")  # planning, research, analysis, reporting, completed
    status = Column(String(50), default="active")  # active, paused, completed, error
    progress = Column(Integer, default=0)  # 进度百分比
    
    # 结果信息
    state_data = Column(JSON, default=dict)  # 研究状态数据
    findings = Column(JSON, default=list)  # 研究发现
    final_report = Column(Text)  # 最终报告
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    # 关系
    agent_definition = relationship("AgentDefinition", back_populates="sessions")
    user = relationship("User", back_populates="agent_sessions")
    tasks = relationship("AgentTask", back_populates="session")
    
    def __repr__(self):
        return f"<AgentSession(id={self.session_id}, type={self.session_type}, status={self.status})>"


class AgentPermission(Base):
    """智能体权限模型"""
    __tablename__ = "agent_permissions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # 关联信息
    agent_definition_id = Column(UUID(as_uuid=True), ForeignKey("agent_definitions.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    
    # 权限信息
    permission_type = Column(String(50), nullable=False)  # knowledge_base, mcp_tool, system
    resource_id = Column(String(255))  # 具体资源ID（知识库ID、工具名等）
    permission_level = Column(String(50), default="read")  # read, write, admin
    
    # 权限详情
    permissions = Column(JSON, default=list)  # 具体权限列表
    restrictions = Column(JSON, default=dict)  # 权限限制
    
    # 时间限制
    expires_at = Column(DateTime, nullable=True)  # 权限过期时间
    
    # 状态
    is_active = Column(Boolean, default=True)
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    # 关系
    agent_definition = relationship("AgentDefinition", back_populates="permissions")
    user = relationship("User")
    
    def __repr__(self):
        return f"<AgentPermission(type={self.permission_type}, resource={self.resource_id}, level={self.permission_level})>"


class AgentTask(Base):
    """智能体任务模型"""
    __tablename__ = "agent_tasks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(String(255), unique=True, nullable=False, index=True)
    
    # 关联信息
    session_id = Column(UUID(as_uuid=True), ForeignKey("agent_sessions.id"), nullable=False)
    agent_id = Column(String(255), nullable=False)  # 执行的智能体ID
    
    # 任务信息
    title = Column(String(200), nullable=False)
    description = Column(Text)
    task_type = Column(String(50), nullable=False)  # research, analysis, reporting
    priority = Column(Integer, default=0)  # 优先级
    
    # 依赖关系
    dependencies = Column(JSON, default=list)  # 依赖的任务ID列表
    
    # 输入输出
    input_data = Column(JSON, default=dict)  # 输入数据
    output_data = Column(JSON, default=dict)  # 输出数据
    
    # 状态信息
    status = Column(String(50), default="pending")  # pending, running, completed, failed, cancelled
    progress = Column(Integer, default=0)  # 进度百分比
    
    # 执行信息
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    execution_time = Column(Integer, nullable=True)  # 执行时间（秒）
    
    # 错误信息
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    # 关系
    session = relationship("AgentSession", back_populates="tasks")
    
    def __repr__(self):
        return f"<AgentTask(id={self.task_id}, type={self.task_type}, status={self.status})>"


class AgentLog(Base):
    """智能体日志模型"""
    __tablename__ = "agent_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # 关联信息
    agent_id = Column(String(255), nullable=False, index=True)
    session_id = Column(String(255), nullable=True, index=True)
    task_id = Column(String(255), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    
    # 日志信息
    log_level = Column(String(20), nullable=False)  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    message = Column(Text, nullable=False)
    category = Column(String(50), nullable=False)  # execution, permission, error, state_change
    
    # 详细信息
    details = Column(JSON, default=dict)  # 详细日志数据
    stack_trace = Column(Text, nullable=True)  # 错误堆栈
    
    # 上下文信息
    context = Column(JSON, default=dict)  # 上下文数据
    
    # 时间戳
    timestamp = Column(DateTime, default=datetime.now, nullable=False, index=True)
    
    def __repr__(self):
        return f"<AgentLog(agent_id={self.agent_id}, level={self.log_level}, category={self.category})>"


class AgentMetrics(Base):
    """智能体指标模型"""
    __tablename__ = "agent_metrics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # 关联信息
    agent_id = Column(String(255), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    
    # 指标信息
    metric_name = Column(String(100), nullable=False)  # task_count, execution_time, success_rate
    metric_value = Column(JSON, nullable=False)  # 指标值（可以是数字、字符串、对象）
    metric_type = Column(String(50), nullable=False)  # counter, gauge, histogram
    
    # 标签和维度
    labels = Column(JSON, default=dict)  # 指标标签
    dimensions = Column(JSON, default=dict)  # 指标维度
    
    # 时间信息
    time_window = Column(String(50))  # 时间窗口：hour, day, week, month
    timestamp = Column(DateTime, default=datetime.now, nullable=False, index=True)
    
    def __repr__(self):
        return f"<AgentMetrics(agent_id={self.agent_id}, metric={self.metric_name}, value={self.metric_value})>"