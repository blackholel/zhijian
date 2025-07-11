"""
研究工作流数据模型
定义工作流相关的数据结构和请求响应模型
"""
from typing import Dict, List, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum

from .state import ResearchPhase


class WorkflowType(Enum):
    """工作流类型"""
    STANDARD = "standard_research"
    QUICK = "quick_research"
    DEEP = "deep_research"
    CUSTOM = "custom"


class ResearchRequest(BaseModel):
    """研究请求模型"""
    topic: str = Field(..., description="研究主题")
    objective: str = Field(..., description="研究目标")
    knowledge_bases: List[str] = Field(default_factory=list, description="选择的知识库")
    mcp_tools: List[str] = Field(default_factory=list, description="选择的MCP工具")
    workflow_type: WorkflowType = Field(default=WorkflowType.STANDARD, description="工作流类型")
    config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="配置参数")
    
    class Config:
        use_enum_values = True


class ResearchResponse(BaseModel):
    """研究响应模型"""
    session_id: str = Field(..., description="会话ID")
    execution_id: str = Field(..., description="执行ID")
    status: str = Field(..., description="执行状态")
    message: str = Field(..., description="响应消息")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class WorkflowConfig(BaseModel):
    """工作流配置"""
    timeout: Optional[int] = Field(default=3600, description="超时时间(秒)")
    max_retries: int = Field(default=3, description="最大重试次数")
    parallel_execution: bool = Field(default=True, description="是否支持并行执行")
    enable_checkpoints: bool = Field(default=True, description="是否启用检查点")
    notification_settings: Dict[str, bool] = Field(
        default_factory=lambda: {
            "on_start": True,
            "on_complete": True,
            "on_error": True,
            "phase_transitions": False
        },
        description="通知设置"
    )
    quality_thresholds: Dict[str, float] = Field(
        default_factory=lambda: {
            "min_findings": 5.0,
            "min_confidence": 0.7,
            "min_completeness": 0.8
        },
        description="质量阈值"
    )


class WorkflowEvent(BaseModel):
    """工作流事件"""
    event_id: str = Field(..., description="事件ID")
    execution_id: str = Field(..., description="执行ID")
    event_type: str = Field(..., description="事件类型")
    timestamp: str = Field(..., description="时间戳")
    data: Dict[str, Any] = Field(default_factory=dict, description="事件数据")


class WorkflowTransition(BaseModel):
    """工作流转换"""
    transition_id: str = Field(..., description="转换ID")
    execution_id: str = Field(..., description="执行ID")
    from_node: str = Field(..., description="源节点")
    to_node: str = Field(..., description="目标节点")
    condition_met: str = Field(..., description="满足的条件")
    timestamp: str = Field(..., description="转换时间")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="转换元数据")


class ExecutionStatusResponse(BaseModel):
    """执行状态响应"""
    execution_id: str = Field(..., description="执行ID")
    session_id: str = Field(..., description="会话ID")
    workflow_id: str = Field(..., description="工作流ID")
    status: str = Field(..., description="执行状态")
    current_node: Optional[str] = Field(None, description="当前节点")
    current_phase: Optional[str] = Field(None, description="当前阶段")
    progress: float = Field(..., description="执行进度 (0-1)")
    events_count: int = Field(..., description="事件数量")
    transitions_count: int = Field(..., description="转换数量")
    created_at: str = Field(..., description="创建时间")
    started_at: Optional[str] = Field(None, description="开始时间")
    completed_at: Optional[str] = Field(None, description="完成时间")
    error: Optional[str] = Field(None, description="错误信息")
    estimated_completion: Optional[str] = Field(None, description="预计完成时间")


class ExecutionResultResponse(BaseModel):
    """执行结果响应"""
    execution_info: Dict[str, Any] = Field(..., description="执行信息")
    research_state: Optional[Dict[str, Any]] = Field(None, description="研究状态")
    workflow_events: List[Dict[str, Any]] = Field(default_factory=list, description="工作流事件")
    workflow_transitions: List[Dict[str, Any]] = Field(default_factory=list, description="工作流转换")
    orchestrator_results: Dict[str, Any] = Field(..., description="编排器结果")
    quality_metrics: Optional[Dict[str, Any]] = Field(None, description="质量指标")
    performance_metrics: Optional[Dict[str, Any]] = Field(None, description="性能指标")


class WorkflowDefinition(BaseModel):
    """工作流定义"""
    workflow_id: str = Field(..., description="工作流ID")
    name: str = Field(..., description="工作流名称")
    description: str = Field(..., description="工作流描述")
    version: str = Field(default="1.0", description="版本号")
    nodes: List[Dict[str, Any]] = Field(default_factory=list, description="节点定义")
    edges: List[Dict[str, Any]] = Field(default_factory=list, description="边定义")
    start_node: str = Field(..., description="开始节点")
    end_nodes: List[str] = Field(..., description="结束节点")
    config: Optional[WorkflowConfig] = Field(None, description="工作流配置")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")


class WorkflowListResponse(BaseModel):
    """工作流列表响应"""
    workflows: List[WorkflowDefinition] = Field(..., description="工作流列表")
    total: int = Field(..., description="总数")


class AgentCapabilityInfo(BaseModel):
    """Agent能力信息"""
    agent_type: str = Field(..., description="Agent类型")
    name: str = Field(..., description="Agent名称")
    description: str = Field(..., description="Agent描述")
    capabilities: List[str] = Field(..., description="能力列表")
    supported_knowledge_bases: List[str] = Field(..., description="支持的知识库")
    supported_mcp_tools: List[str] = Field(..., description="支持的MCP工具")
    performance_metrics: Dict[str, Any] = Field(default_factory=dict, description="性能指标")


class KnowledgeBaseInfo(BaseModel):
    """知识库信息"""
    kb_id: str = Field(..., description="知识库ID")
    name: str = Field(..., description="知识库名称")
    description: str = Field(..., description="知识库描述")
    type: str = Field(..., description="知识库类型")
    file_count: int = Field(..., description="文件数量")
    node_count: int = Field(..., description="节点数量")
    last_updated: str = Field(..., description="最后更新时间")
    permissions: List[str] = Field(..., description="用户权限")
    size_info: Dict[str, Any] = Field(default_factory=dict, description="大小信息")


class MCPToolInfo(BaseModel):
    """MCP工具信息"""
    tool_name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")
    schema: Dict[str, Any] = Field(..., description="工具模式")
    required_permissions: List[str] = Field(..., description="所需权限")
    server_info: Dict[str, Any] = Field(default_factory=dict, description="服务器信息")
    usage_stats: Dict[str, Any] = Field(default_factory=dict, description="使用统计")


class ResourcesResponse(BaseModel):
    """资源响应"""
    knowledge_bases: List[KnowledgeBaseInfo] = Field(..., description="可用知识库")
    mcp_tools: List[MCPToolInfo] = Field(..., description="可用MCP工具")
    agent_capabilities: List[AgentCapabilityInfo] = Field(..., description="Agent能力")


class SessionListResponse(BaseModel):
    """会话列表响应"""
    sessions: List[Dict[str, Any]] = Field(..., description="会话列表")
    total: int = Field(..., description="总数")
    page: int = Field(default=1, description="页码")
    page_size: int = Field(default=20, description="页面大小")


class HealthCheckResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(..., description="服务状态")
    version: str = Field(..., description="版本信息")
    uptime: float = Field(..., description="运行时间(秒)")
    active_sessions: int = Field(..., description="活跃会话数")
    active_executions: int = Field(..., description="活跃执行数")
    system_metrics: Dict[str, Any] = Field(default_factory=dict, description="系统指标")
    dependencies: Dict[str, str] = Field(default_factory=dict, description="依赖状态")


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str = Field(..., description="错误类型")
    message: str = Field(..., description="错误消息")
    details: Optional[Dict[str, Any]] = Field(None, description="错误详情")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="错误时间")
    request_id: Optional[str] = Field(None, description="请求ID")


class StreamEvent(BaseModel):
    """流事件"""
    event_type: str = Field(..., description="事件类型")
    data: Dict[str, Any] = Field(..., description="事件数据")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(), description="时间戳")
    execution_id: Optional[str] = Field(None, description="执行ID")
    session_id: Optional[str] = Field(None, description="会话ID")


class QualityMetrics(BaseModel):
    """质量指标"""
    completeness_score: float = Field(..., description="完整性分数")
    accuracy_score: float = Field(..., description="准确性分数")
    relevance_score: float = Field(..., description="相关性分数")
    consistency_score: float = Field(..., description="一致性分数")
    overall_quality: float = Field(..., description="总体质量")
    findings_count: int = Field(..., description="发现数量")
    high_confidence_findings: int = Field(..., description="高置信度发现数量")
    knowledge_base_coverage: float = Field(..., description="知识库覆盖率")
    tool_utilization: float = Field(..., description="工具利用率")


class PerformanceMetrics(BaseModel):
    """性能指标"""
    total_execution_time: float = Field(..., description="总执行时间(秒)")
    planning_time: float = Field(..., description="规划时间(秒)")
    research_time: float = Field(..., description="研究时间(秒)")
    analysis_time: float = Field(..., description="分析时间(秒)")
    reporting_time: float = Field(..., description="报告时间(秒)")
    average_response_time: float = Field(..., description="平均响应时间(秒)")
    throughput: float = Field(..., description="吞吐量(任务/秒)")
    resource_utilization: Dict[str, float] = Field(..., description="资源利用率")
    error_rate: float = Field(..., description="错误率")


class WorkflowAnalytics(BaseModel):
    """工作流分析"""
    execution_id: str = Field(..., description="执行ID")
    workflow_id: str = Field(..., description="工作流ID")
    quality_metrics: QualityMetrics = Field(..., description="质量指标")
    performance_metrics: PerformanceMetrics = Field(..., description="性能指标")
    node_performance: List[Dict[str, Any]] = Field(..., description="节点性能")
    transition_analysis: List[Dict[str, Any]] = Field(..., description="转换分析")
    bottleneck_analysis: Dict[str, Any] = Field(..., description="瓶颈分析")
    optimization_suggestions: List[str] = Field(..., description="优化建议")


class ConfigUpdateRequest(BaseModel):
    """配置更新请求"""
    workflow_config: Optional[WorkflowConfig] = Field(None, description="工作流配置")
    agent_configs: Optional[Dict[str, Dict[str, Any]]] = Field(None, description="Agent配置")
    system_config: Optional[Dict[str, Any]] = Field(None, description="系统配置")


class BatchExecutionRequest(BaseModel):
    """批量执行请求"""
    executions: List[ResearchRequest] = Field(..., description="执行请求列表")
    batch_config: Dict[str, Any] = Field(default_factory=dict, description="批量配置")
    execution_strategy: str = Field(default="parallel", description="执行策略")


class BatchExecutionResponse(BaseModel):
    """批量执行响应"""
    batch_id: str = Field(..., description="批次ID")
    execution_ids: List[str] = Field(..., description="执行ID列表")
    status: str = Field(..., description="批次状态")
    created_at: str = Field(..., description="创建时间")


class WorkflowTemplate(BaseModel):
    """工作流模板"""
    template_id: str = Field(..., description="模板ID")
    name: str = Field(..., description="模板名称")
    description: str = Field(..., description="模板描述")
    category: str = Field(..., description="模板类别")
    workflow_definition: WorkflowDefinition = Field(..., description="工作流定义")
    parameters: List[Dict[str, Any]] = Field(..., description="参数定义")
    usage_examples: List[Dict[str, Any]] = Field(..., description="使用示例")
    tags: List[str] = Field(default_factory=list, description="标签")


class TemplateListResponse(BaseModel):
    """模板列表响应"""
    templates: List[WorkflowTemplate] = Field(..., description="模板列表")
    categories: List[str] = Field(..., description="类别列表")
    total: int = Field(..., description="总数")


class ExecutionPauseRequest(BaseModel):
    """执行暂停请求"""
    reason: Optional[str] = Field(None, description="暂停原因")
    save_checkpoint: bool = Field(default=True, description="是否保存检查点")


class ExecutionResumeRequest(BaseModel):
    """执行恢复请求"""
    from_checkpoint: bool = Field(default=True, description="是否从检查点恢复")
    modified_config: Optional[Dict[str, Any]] = Field(None, description="修改的配置")


class ExecutionCancelRequest(BaseModel):
    """执行取消请求"""
    reason: Optional[str] = Field(None, description="取消原因")
    force: bool = Field(default=False, description="是否强制取消")


class NotificationSettings(BaseModel):
    """通知设置"""
    email_enabled: bool = Field(default=False, description="邮件通知")
    webhook_enabled: bool = Field(default=False, description="Webhook通知")
    webhook_url: Optional[str] = Field(None, description="Webhook URL")
    notification_events: List[str] = Field(default_factory=list, description="通知事件")
    filters: Dict[str, Any] = Field(default_factory=dict, description="通知过滤器")


class UserPreferences(BaseModel):
    """用户偏好"""
    default_workflow_type: WorkflowType = Field(default=WorkflowType.STANDARD, description="默认工作流类型")
    preferred_knowledge_bases: List[str] = Field(default_factory=list, description="偏好知识库")
    preferred_mcp_tools: List[str] = Field(default_factory=list, description="偏好MCP工具")
    notification_settings: NotificationSettings = Field(default_factory=NotificationSettings, description="通知设置")
    ui_preferences: Dict[str, Any] = Field(default_factory=dict, description="界面偏好")
    
    class Config:
        use_enum_values = True


class SystemStatus(BaseModel):
    """系统状态"""
    agent_manager_status: str = Field(..., description="Agent管理器状态")
    orchestrator_status: str = Field(..., description="编排器状态")
    workflow_engine_status: str = Field(..., description="工作流引擎状态")
    knowledge_base_status: str = Field(..., description="知识库状态")
    mcp_service_status: str = Field(..., description="MCP服务状态")
    database_status: str = Field(..., description="数据库状态")
    llm_service_status: str = Field(..., description="LLM服务状态")
    resource_usage: Dict[str, Any] = Field(..., description="资源使用情况")
    error_counts: Dict[str, int] = Field(..., description="错误计数")
    performance_stats: Dict[str, Any] = Field(..., description="性能统计")


class ExportRequest(BaseModel):
    """导出请求"""
    execution_ids: List[str] = Field(..., description="执行ID列表")
    export_format: str = Field(default="json", description="导出格式")
    include_raw_data: bool = Field(default=False, description="是否包含原始数据")
    include_analytics: bool = Field(default=True, description="是否包含分析数据")
    compression: Optional[str] = Field(None, description="压缩格式")


class ExportResponse(BaseModel):
    """导出响应"""
    export_id: str = Field(..., description="导出ID")
    download_url: str = Field(..., description="下载URL")
    file_size: int = Field(..., description="文件大小")
    expires_at: str = Field(..., description="过期时间")
    created_at: str = Field(..., description="创建时间")