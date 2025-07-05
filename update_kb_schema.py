#!/usr/bin/env python3
"""
更新知识库数据库表结构
添加权限相关字段
"""

import sys
sys.path.append('.')

from server.db_manager import db_manager
from sqlalchemy import text

def update_kb_schema():
    """更新知识库表结构"""
    db = db_manager.get_session()
    try:
        print("开始更新知识库表结构...")
        
        # 添加 owner_id 字段
        try:
            db.execute(text('ALTER TABLE knowledge_databases ADD COLUMN owner_id UUID REFERENCES users(id)'))
            print('✅ 添加 owner_id 字段')
        except Exception as e:
            print(f'owner_id 字段已存在或错误: {e}')

        # 添加 is_public 字段
        try:
            db.execute(text('ALTER TABLE knowledge_databases ADD COLUMN is_public BOOLEAN DEFAULT FALSE'))
            print('✅ 添加 is_public 字段')
        except Exception as e:
            print(f'is_public 字段已存在或错误: {e}')

        # 添加 access_level 字段
        try:
            db.execute(text("ALTER TABLE knowledge_databases ADD COLUMN access_level VARCHAR(20) DEFAULT 'private'"))
            print('✅ 添加 access_level 字段')
        except Exception as e:
            print(f'access_level 字段已存在或错误: {e}')

        # 创建知识库权限表
        try:
            db.execute(text("""
                CREATE TABLE IF NOT EXISTS knowledge_database_permissions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    database_id VARCHAR NOT NULL REFERENCES knowledge_databases(db_id) ON DELETE CASCADE,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    permission_type VARCHAR(20) NOT NULL,
                    granted_by UUID REFERENCES users(id),
                    granted_at TIMESTAMP DEFAULT NOW(),
                    expires_at TIMESTAMP,
                    UNIQUE(database_id, user_id, permission_type)
                )
            """))
            print('✅ 创建知识库权限表')
        except Exception as e:
            print(f'知识库权限表已存在或错误: {e}')

        # 更新 knowledge_files 表，添加 uploaded_by 字段
        try:
            db.execute(text('ALTER TABLE knowledge_files ADD COLUMN uploaded_by UUID REFERENCES users(id)'))
            print('✅ 添加 uploaded_by 字段到文件表')
        except Exception as e:
            print(f'uploaded_by 字段已存在或错误: {e}')

        db.commit()
        print('🎉 数据库表结构更新完成!')
        
    except Exception as e:
        db.rollback()
        print(f'❌ 更新失败: {e}')
        raise
    finally:
        db.close()

if __name__ == "__main__":
    update_kb_schema()