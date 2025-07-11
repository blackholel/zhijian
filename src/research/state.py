"""
研究状态模型

定义研究工作流的状态、阶段和任务模型
"""

from enum import Enum
from typing import List, Dict, Any, Optional, Union
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from uuid import uuid4


class ResearchPhase(Enum):
    """研究阶段枚举"""
    PLANNING = "planning"
    RESEARCH = "research"
    ANALYSIS = "analysis"
    REPORTING = "reporting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class ResearchTask(BaseModel):
    """研究任务模型"""
    task_id: str = Field(default_factory=lambda: str(uuid4()), description="任务ID")
    title: str = Field(..., description="任务标题")
    description: str = Field(..., description="任务描述")
    assigned_agent: str = Field(..., description="分配的智能体")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="任务状态")
    priority: int = Field(default=0, description="任务优先级")
    input_data: Dict[str, Any] = Field(default_factory=dict, description="输入数据")
    output_data: Optional[Dict[str, Any]] = Field(default=None, description="输出数据")
    dependencies: List[str] = Field(default_factory=list, description="依赖的任务ID")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="创建时间")
    started_at: Optional[datetime] = Field(default=None, description="开始时间")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")
    error_message: Optional[str] = Field(default=None, description="错误消息")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ResearchFinding(BaseModel):
    """研究发现模型"""
    finding_id: str = Field(default_factory=lambda: str(uuid4()), description="发现ID")
    title: str = Field(..., description="发现标题")
    content: str = Field(..., description="发现内容")
    source: str = Field(..., description="来源")
    agent_id: str = Field(..., description="产生发现的智能体ID")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    tags: List[str] = Field(default_factory=list, description="标签")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="创建时间")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ResearchInsight(BaseModel):
    """研究洞察模型"""
    insight_id: str = Field(default_factory=lambda: str(uuid4()), description="洞察ID")
    title: str = Field(..., description="洞察标题")
    description: str = Field(..., description="洞察描述")
    key_points: List[str] = Field(default_factory=list, description="关键点")
    supporting_findings: List[str] = Field(default_factory=list, description="支持的发现ID")
    implications: List[str] = Field(default_factory=list, description="影响和意义")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="创建时间")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ResearchState(BaseModel):
    """研究状态模型"""
    session_id: str = Field(..., description="会话ID")
    user_id: str = Field(..., description="用户ID")
    topic: str = Field(..., description="研究主题")
    objective: str = Field(..., description="研究目标")
    current_phase: ResearchPhase = Field(default=ResearchPhase.PLANNING, description="当前阶段")
    
    # 资源配置
    agents: List[str] = Field(default_factory=list, description="参与的智能体列表")
    knowledge_bases: List[str] = Field(default_factory=list, description="使用的知识库")
    mcp_tools: List[str] = Field(default_factory=list, description="使用的MCP工具")
    
    # 任务和结果
    tasks: List[ResearchTask] = Field(default_factory=list, description="研究任务列表")
    findings: List[ResearchFinding] = Field(default_factory=list, description="研究发现")
    insights: List[ResearchInsight] = Field(default_factory=list, description="研究洞察")
    
    # 报告
    interim_reports: List[Dict[str, Any]] = Field(default_factory=list, description="中间报告")
    final_report: Optional[str] = Field(default=None, description="最终报告")
    
    # 配置和元数据
    config: Dict[str, Any] = Field(default_factory=dict, description="配置信息")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    
    # 时间戳
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="创建时间")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="更新时间")
    started_at: Optional[datetime] = Field(default=None, description="开始时间")
    completed_at: Optional[datetime] = Field(default=None, description="完成时间")
    
    # 统计信息
    total_tasks: int = Field(default=0, description="总任务数")
    completed_tasks: int = Field(default=0, description="已完成任务数")
    failed_tasks: int = Field(default=0, description="失败任务数")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
    
    def add_task(self, task: ResearchTask) -> None:
        """添加任务"""
        self.tasks.append(task)
        self.total_tasks = len(self.tasks)
        self.updated_at = datetime.now(timezone.utc)
    
    def update_task_status(self, task_id: str, status: TaskStatus, 
                          output_data: Optional[Dict[str, Any]] = None,
                          error_message: Optional[str] = None) -> bool:
        """更新任务状态"""
        for task in self.tasks:
            if task.task_id == task_id:
                task.status = status
                if output_data:
                    task.output_data = output_data
                if error_message:
                    task.error_message = error_message
                
                if status == TaskStatus.RUNNING:
                    task.started_at = datetime.now(timezone.utc)
                elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    task.completed_at = datetime.now(timezone.utc)
                
                self._update_task_counters()
                self.updated_at = datetime.now(timezone.utc)
                return True
        return False
    
    def add_finding(self, finding: ResearchFinding) -> None:
        """添加研究发现"""
        self.findings.append(finding)
        self.updated_at = datetime.now(timezone.utc)
    
    def add_insight(self, insight: ResearchInsight) -> None:
        """添加研究洞察"""
        self.insights.append(insight)
        self.updated_at = datetime.now(timezone.utc)
    
    def set_phase(self, phase: ResearchPhase) -> None:
        """设置研究阶段"""
        self.current_phase = phase
        self.updated_at = datetime.now(timezone.utc)
        
        if phase == ResearchPhase.RESEARCH and not self.started_at:
            self.started_at = datetime.now(timezone.utc)
        elif phase in [ResearchPhase.COMPLETED, ResearchPhase.FAILED, ResearchPhase.CANCELLED]:
            self.completed_at = datetime.now(timezone.utc)
    
    def get_progress(self) -> Dict[str, Any]:
        """获取进度信息"""
        total = self.total_tasks
        completed = self.completed_tasks
        failed = self.failed_tasks
        running = len([t for t in self.tasks if t.status == TaskStatus.RUNNING])
        pending = len([t for t in self.tasks if t.status == TaskStatus.PENDING])
        
        progress_percentage = (completed / total * 100) if total > 0 else 0
        
        return {
            "total_tasks": total,
            "completed_tasks": completed,
            "failed_tasks": failed,
            "running_tasks": running,
            "pending_tasks": pending,
            "progress_percentage": progress_percentage,
            "current_phase": self.current_phase.value,
            "findings_count": len(self.findings),
            "insights_count": len(self.insights)
        }
    
    def _update_task_counters(self) -> None:
        """更新任务计数器"""
        self.total_tasks = len(self.tasks)
        self.completed_tasks = len([t for t in self.tasks if t.status == TaskStatus.COMPLETED])
        self.failed_tasks = len([t for t in self.tasks if t.status == TaskStatus.FAILED])


class ResearchContext(BaseModel):
    """研究上下文模型"""
    session_id: str = Field(..., description="会话ID")
    topic: str = Field(..., description="研究主题")
    objective: str = Field(..., description="研究目标")
    constraints: List[str] = Field(default_factory=list, description="约束条件")
    requirements: List[str] = Field(default_factory=list, description="需求")
    background: Optional[str] = Field(default=None, description="背景信息")
    target_audience: Optional[str] = Field(default=None, description="目标受众")
    expected_outcomes: List[str] = Field(default_factory=list, description="预期结果")
    success_criteria: List[str] = Field(default_factory=list, description="成功标准")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# 工厂函数
def create_research_state(session_id: str, user_id: str, topic: str, 
                         objective: str, **kwargs) -> ResearchState:
    """创建研究状态"""
    return ResearchState(
        session_id=session_id,
        user_id=user_id,
        topic=topic,
        objective=objective,
        **kwargs
    )


def create_research_task(title: str, description: str, assigned_agent: str, 
                        **kwargs) -> ResearchTask:
    """创建研究任务"""
    return ResearchTask(
        title=title,
        description=description,
        assigned_agent=assigned_agent,
        **kwargs
    )


def create_research_finding(title: str, content: str, source: str, 
                           agent_id: str, **kwargs) -> ResearchFinding:
    """创建研究发现"""
    return ResearchFinding(
        title=title,
        content=content,
        source=source,
        agent_id=agent_id,
        **kwargs
    )


def create_research_insight(title: str, description: str, **kwargs) -> ResearchInsight:
    """创建研究洞察"""
    return ResearchInsight(
        title=title,
        description=description,
        **kwargs
    )