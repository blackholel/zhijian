from dotenv import load_dotenv

load_dotenv("src/.env")

from concurrent.futures import ThreadPoolExecutor  # noqa: E402
executor = ThreadPoolExecutor()

from src.config import Config  # noqa: E402
config = Config()

from src.core.unified_lightrag_kb import get_unified_lightrag_kb  # noqa: E402
# 初始化知识库（暂不集成权限管理器，避免循环依赖）
knowledge_base = get_unified_lightrag_kb()

from src.core import GraphDatabase  # noqa: E402
graph_base = GraphDatabase()
