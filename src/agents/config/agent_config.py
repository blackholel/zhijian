"""
智能体配置模型定义

结合 DeerFlow 和 Suna 的配置管理最佳实践
"""

from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field, validator
from enum import Enum
from datetime import datetime
import uuid


class AgentType(str, Enum):
    """智能体类型"""
    COORDINATOR = "coordinator"      # 协调器 - 任务分解和流程控制
    RESEARCHER = "researcher"        # 研究员 - 信息收集和分析
    ANALYZER = "analyzer"           # 分析员 - 数据分析和洞察
    REPORTER = "reporter"           # 报告员 - 报告生成和总结
    SPECIALIST = "specialist"       # 专家 - 特定领域专家
    CUSTOM = "custom"              # 自定义类型


class LLMProvider(str, Enum):
    """LLM 提供商"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    ZHIPU = "zhipu"
    QWEN = "qwen"
    LOCAL = "local"


class LLMConfig(BaseModel):
    """LLM 配置"""
    provider: LLMProvider
    model: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, gt=0)
    timeout: int = Field(default=30, gt=0)
    retry_attempts: int = Field(default=3, ge=1)
    
    # 高级参数
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    frequency_penalty: Optional[float] = Field(default=None, ge=-2.0, le=2.0)
    presence_penalty: Optional[float] = Field(default=None, ge=-2.0, le=2.0)
    
    class Config:
        use_enum_values = True


class AgentCapability(BaseModel):
    """智能体能力定义"""
    name: str = Field(..., description="能力名称")
    description: str = Field(..., description="能力描述")
    required_permissions: List[str] = Field(default_factory=list, description="所需权限")
    supported_knowledge_bases: List[str] = Field(default_factory=list, description="支持的知识库类型")
    supported_mcp_tools: List[str] = Field(default_factory=list, description="支持的MCP工具")
    config_schema: Optional[Dict[str, Any]] = Field(default=None, description="配置模式")
    
    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("能力名称不能为空")
        return v.strip()


class ResourceLimit(BaseModel):
    """资源限制配置"""
    max_knowledge_bases: int = Field(default=10, ge=1, description="最大知识库数量")
    max_mcp_tools: int = Field(default=20, ge=1, description="最大MCP工具数量")
    max_concurrent_tasks: int = Field(default=5, ge=1, description="最大并发任务数")
    max_execution_time: int = Field(default=300, ge=30, description="最大执行时间(秒)")
    max_memory_usage: int = Field(default=1024, ge=256, description="最大内存使用(MB)")


class SecurityConfig(BaseModel):
    """安全配置"""
    enable_sandbox: bool = Field(default=True, description="启用沙箱模式")
    allowed_domains: List[str] = Field(default_factory=list, description="允许访问的域名")
    blocked_domains: List[str] = Field(default_factory=list, description="禁止访问的域名")
    max_file_size: int = Field(default=10485760, description="最大文件大小(字节)")  # 10MB
    allowed_file_types: List[str] = Field(
        default_factory=lambda: [".txt", ".md", ".pdf", ".doc", ".docx"],
        description="允许的文件类型"
    )


class PromptTemplate(BaseModel):
    """提示词模板"""
    name: str = Field(..., description="模板名称")
    template: str = Field(..., description="模板内容")
    variables: List[str] = Field(default_factory=list, description="模板变量")
    description: Optional[str] = Field(default=None, description="模板描述")
    
    @validator('template')
    def validate_template(cls, v):
        if not v or not v.strip():
            raise ValueError("模板内容不能为空")
        return v.strip()


class AgentConfig(BaseModel):
    """智能体配置模型"""
    
    # 基础信息
    agent_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="智能体ID")
    name: str = Field(..., min_length=1, max_length=100, description="智能体名称")
    description: str = Field(..., min_length=1, max_length=500, description="智能体描述")
    agent_type: AgentType = Field(..., description="智能体类型")
    version: str = Field(default="1.0.0", description="版本号")
    
    # 用户和权限
    user_id: str = Field(..., description="所属用户ID")
    organization_id: Optional[str] = Field(default=None, description="所属组织ID")
    
    # 能力配置
    capabilities: List[AgentCapability] = Field(default_factory=list, description="智能体能力")
    
    # 资源配置
    selected_knowledge_bases: List[str] = Field(default_factory=list, description="选中的知识库")
    selected_mcp_tools: List[str] = Field(default_factory=list, description="选中的MCP工具")
    
    # LLM 配置
    llm_config: LLMConfig = Field(..., description="LLM配置")
    
    # 提示词模板
    prompt_templates: Dict[str, PromptTemplate] = Field(default_factory=dict, description="提示词模板")
    
    # 限制和安全
    resource_limits: ResourceLimit = Field(default_factory=ResourceLimit, description="资源限制")
    security_config: SecurityConfig = Field(default_factory=SecurityConfig, description="安全配置")
    
    # 运行时配置
    auto_start: bool = Field(default=False, description="自动启动")
    enable_logging: bool = Field(default=True, description="启用日志")
    log_level: str = Field(default="INFO", description="日志级别")
    
    # 元数据
    tags: List[str] = Field(default_factory=list, description="标签")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    
    # 时间戳
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    
    @validator('name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("智能体名称不能为空")
        return v.strip()
    
    @validator('selected_knowledge_bases')
    def validate_knowledge_bases(cls, v, values):
        resource_limits = values.get('resource_limits', ResourceLimit())
        if len(v) > resource_limits.max_knowledge_bases:
            raise ValueError(f"知识库数量不能超过 {resource_limits.max_knowledge_bases}")
        return v
    
    @validator('selected_mcp_tools')
    def validate_mcp_tools(cls, v, values):
        resource_limits = values.get('resource_limits', ResourceLimit())
        if len(v) > resource_limits.max_mcp_tools:
            raise ValueError(f"MCP工具数量不能超过 {resource_limits.max_mcp_tools}")
        return v
    
    def update_timestamp(self):
        """更新时间戳"""
        self.updated_at = datetime.now()
    
    def add_capability(self, capability: AgentCapability):
        """添加能力"""
        self.capabilities.append(capability)
        self.update_timestamp()
    
    def remove_capability(self, capability_name: str):
        """移除能力"""
        self.capabilities = [cap for cap in self.capabilities if cap.name != capability_name]
        self.update_timestamp()
    
    def add_knowledge_base(self, kb_id: str):
        """添加知识库"""
        if kb_id not in self.selected_knowledge_bases:
            if len(self.selected_knowledge_bases) >= self.resource_limits.max_knowledge_bases:
                raise ValueError(f"知识库数量不能超过 {self.resource_limits.max_knowledge_bases}")
            self.selected_knowledge_bases.append(kb_id)
            self.update_timestamp()
    
    def remove_knowledge_base(self, kb_id: str):
        """移除知识库"""
        if kb_id in self.selected_knowledge_bases:
            self.selected_knowledge_bases.remove(kb_id)
            self.update_timestamp()
    
    def add_mcp_tool(self, tool_name: str):
        """添加MCP工具"""
        if tool_name not in self.selected_mcp_tools:
            if len(self.selected_mcp_tools) >= self.resource_limits.max_mcp_tools:
                raise ValueError(f"MCP工具数量不能超过 {self.resource_limits.max_mcp_tools}")
            self.selected_mcp_tools.append(tool_name)
            self.update_timestamp()
    
    def remove_mcp_tool(self, tool_name: str):
        """移除MCP工具"""
        if tool_name in self.selected_mcp_tools:
            self.selected_mcp_tools.remove(tool_name)
            self.update_timestamp()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self.dict()
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentConfig":
        """从字典创建"""
        return cls(**data)
    
    class Config:
        use_enum_values = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }