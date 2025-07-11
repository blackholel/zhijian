"""
添加智能体相关数据表

数据库迁移脚本
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from datetime import datetime


def upgrade():
    """创建智能体相关表"""
    
    # 创建智能体定义表
    op.create_table(
        'agent_definitions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('agent_id', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('agent_type', sa.String(50), nullable=False),
        sa.Column('version', sa.String(20), default='1.0.0'),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('config_data', sa.JSON(), default=dict),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('is_deleted', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), default=datetime.now, nullable=False),
        sa.Column('updated_at', sa.DateTime(), default=datetime.now, nullable=False),
    )
    
    # 创建索引
    op.create_index('ix_agent_definitions_user_id', 'agent_definitions', ['user_id'])
    op.create_index('ix_agent_definitions_agent_type', 'agent_definitions', ['agent_type'])
    op.create_index('ix_agent_definitions_is_active', 'agent_definitions', ['is_active'])
    
    # 创建智能体会话表
    op.create_table(
        'agent_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('agent_definition_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(200)),
        sa.Column('description', sa.Text()),
        sa.Column('session_type', sa.String(50), default='research'),
        sa.Column('agent_configs', sa.JSON(), default=list),
        sa.Column('research_config', sa.JSON(), default=dict),
        sa.Column('current_phase', sa.String(50), default='planning'),
        sa.Column('status', sa.String(50), default='active'),
        sa.Column('progress', sa.Integer(), default=0),
        sa.Column('state_data', sa.JSON(), default=dict),
        sa.Column('findings', sa.JSON(), default=list),
        sa.Column('final_report', sa.Text()),
        sa.Column('created_at', sa.DateTime(), default=datetime.now, nullable=False),
        sa.Column('updated_at', sa.DateTime(), default=datetime.now, nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )
    
    # 创建索引
    op.create_index('ix_agent_sessions_user_id', 'agent_sessions', ['user_id'])
    op.create_index('ix_agent_sessions_status', 'agent_sessions', ['status'])
    op.create_index('ix_agent_sessions_session_type', 'agent_sessions', ['session_type'])
    
    # 创建智能体权限表
    op.create_table(
        'agent_permissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('agent_definition_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('permission_type', sa.String(50), nullable=False),
        sa.Column('resource_id', sa.String(255)),
        sa.Column('permission_level', sa.String(50), default='read'),
        sa.Column('permissions', sa.JSON(), default=list),
        sa.Column('restrictions', sa.JSON(), default=dict),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), default=datetime.now, nullable=False),
        sa.Column('updated_at', sa.DateTime(), default=datetime.now, nullable=False),
    )
    
    # 创建索引
    op.create_index('ix_agent_permissions_agent_definition_id', 'agent_permissions', ['agent_definition_id'])
    op.create_index('ix_agent_permissions_user_id', 'agent_permissions', ['user_id'])
    op.create_index('ix_agent_permissions_permission_type', 'agent_permissions', ['permission_type'])
    op.create_index('ix_agent_permissions_is_active', 'agent_permissions', ['is_active'])
    
    # 创建智能体任务表
    op.create_table(
        'agent_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('task_id', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent_id', sa.String(255), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text()),
        sa.Column('task_type', sa.String(50), nullable=False),
        sa.Column('priority', sa.Integer(), default=0),
        sa.Column('dependencies', sa.JSON(), default=list),
        sa.Column('input_data', sa.JSON(), default=dict),
        sa.Column('output_data', sa.JSON(), default=dict),
        sa.Column('status', sa.String(50), default='pending'),
        sa.Column('progress', sa.Integer(), default=0),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('execution_time', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(), default=datetime.now, nullable=False),
        sa.Column('updated_at', sa.DateTime(), default=datetime.now, nullable=False),
    )
    
    # 创建索引
    op.create_index('ix_agent_tasks_session_id', 'agent_tasks', ['session_id'])
    op.create_index('ix_agent_tasks_agent_id', 'agent_tasks', ['agent_id'])
    op.create_index('ix_agent_tasks_status', 'agent_tasks', ['status'])
    op.create_index('ix_agent_tasks_task_type', 'agent_tasks', ['task_type'])
    
    # 创建智能体日志表
    op.create_table(
        'agent_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('agent_id', sa.String(255), nullable=False, index=True),
        sa.Column('session_id', sa.String(255), nullable=True, index=True),
        sa.Column('task_id', sa.String(255), nullable=True, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('log_level', sa.String(20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('details', sa.JSON(), default=dict),
        sa.Column('stack_trace', sa.Text(), nullable=True),
        sa.Column('context', sa.JSON(), default=dict),
        sa.Column('timestamp', sa.DateTime(), default=datetime.now, nullable=False, index=True),
    )
    
    # 创建索引
    op.create_index('ix_agent_logs_user_id', 'agent_logs', ['user_id'])
    op.create_index('ix_agent_logs_log_level', 'agent_logs', ['log_level'])
    op.create_index('ix_agent_logs_category', 'agent_logs', ['category'])
    
    # 创建智能体指标表
    op.create_table(
        'agent_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('agent_id', sa.String(255), nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('metric_name', sa.String(100), nullable=False),
        sa.Column('metric_value', sa.JSON(), nullable=False),
        sa.Column('metric_type', sa.String(50), nullable=False),
        sa.Column('labels', sa.JSON(), default=dict),
        sa.Column('dimensions', sa.JSON(), default=dict),
        sa.Column('time_window', sa.String(50)),
        sa.Column('timestamp', sa.DateTime(), default=datetime.now, nullable=False, index=True),
    )
    
    # 创建索引
    op.create_index('ix_agent_metrics_user_id', 'agent_metrics', ['user_id'])
    op.create_index('ix_agent_metrics_metric_name', 'agent_metrics', ['metric_name'])
    op.create_index('ix_agent_metrics_metric_type', 'agent_metrics', ['metric_type'])
    
    # 创建外键约束
    op.create_foreign_key(
        'fk_agent_definitions_user_id',
        'agent_definitions', 'users',
        ['user_id'], ['id']
    )
    
    op.create_foreign_key(
        'fk_agent_sessions_agent_definition_id',
        'agent_sessions', 'agent_definitions',
        ['agent_definition_id'], ['id']
    )
    
    op.create_foreign_key(
        'fk_agent_sessions_user_id',
        'agent_sessions', 'users',
        ['user_id'], ['id']
    )
    
    op.create_foreign_key(
        'fk_agent_permissions_agent_definition_id',
        'agent_permissions', 'agent_definitions',
        ['agent_definition_id'], ['id']
    )
    
    op.create_foreign_key(
        'fk_agent_permissions_user_id',
        'agent_permissions', 'users',
        ['user_id'], ['id']
    )
    
    op.create_foreign_key(
        'fk_agent_tasks_session_id',
        'agent_tasks', 'agent_sessions',
        ['session_id'], ['id']
    )
    
    op.create_foreign_key(
        'fk_agent_logs_user_id',
        'agent_logs', 'users',
        ['user_id'], ['id']
    )
    
    op.create_foreign_key(
        'fk_agent_metrics_user_id',
        'agent_metrics', 'users',
        ['user_id'], ['id']
    )


def downgrade():
    """删除智能体相关表"""
    
    # 删除外键约束
    op.drop_constraint('fk_agent_metrics_user_id', 'agent_metrics', type_='foreignkey')
    op.drop_constraint('fk_agent_logs_user_id', 'agent_logs', type_='foreignkey')
    op.drop_constraint('fk_agent_tasks_session_id', 'agent_tasks', type_='foreignkey')
    op.drop_constraint('fk_agent_permissions_user_id', 'agent_permissions', type_='foreignkey')
    op.drop_constraint('fk_agent_permissions_agent_definition_id', 'agent_permissions', type_='foreignkey')
    op.drop_constraint('fk_agent_sessions_user_id', 'agent_sessions', type_='foreignkey')
    op.drop_constraint('fk_agent_sessions_agent_definition_id', 'agent_sessions', type_='foreignkey')
    op.drop_constraint('fk_agent_definitions_user_id', 'agent_definitions', type_='foreignkey')
    
    # 删除表
    op.drop_table('agent_metrics')
    op.drop_table('agent_logs')
    op.drop_table('agent_tasks')
    op.drop_table('agent_permissions')
    op.drop_table('agent_sessions')
    op.drop_table('agent_definitions')