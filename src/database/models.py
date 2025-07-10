"""
统一数据库模型基类
"""

from sqlalchemy.ext.declarative import declarative_base

# 统一的Base类，所有模型都应该继承自这个Base
Base = declarative_base()