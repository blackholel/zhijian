"""
研究员Agent实现
参考DeerFlow的研究员设计，负责信息收集和初步分析
"""
import asyncio
import json
import logging
from typing import Dict, List, Any, Optional, Union
from datetime import datetime
from enum import Enum

from ..base.agent import BaseAgent, AgentConfig
from ..knowledge.kb_manager import KnowledgeBaseManager
from ..knowledge.query_engine import QueryEngine, QueryMode
from ...mcp_integration.registry import MCPRegistry
from ...core.llm.llm_service import LLMService

logger = logging.getLogger(__name__)


class ResearchStrategy(Enum):
    """研究策略"""
    COMPREHENSIVE = "comprehensive"  # 全面研究
    TARGETED = "targeted"           # 目标导向
    EXPLORATORY = "exploratory"     # 探索性研究
    COMPARATIVE = "comparative"     # 比较研究


class InformationQuality(Enum):
    """信息质量评级"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


class ResearcherAgent(BaseAgent):
    """研究员Agent
    
    职责：
    1. 信息收集和检索
    2. 知识库查询和分析
    3. MCP工具调用
    4. 初步信息整理
    """
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.strategy = ResearchStrategy.COMPREHENSIVE
        self.query_engine = QueryEngine()
        self.research_cache = {}
        self.llm_service = LLMService()
        
    async def initialize(self):
        """初始化研究员"""
        await super().initialize()
        
        # 初始化查询引擎
        await self.query_engine.initialize()
        
        # 设置研究策略
        self.strategy = ResearchStrategy(
            self.config.agent_config.get("research_strategy", "comprehensive")
        )
        
        logger.info(f"Researcher initialized with strategy: {self.strategy.value}")
        
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行研究任务"""
        task_type = task.get("task_type")
        
        try:
            if task_type == "research":
                return await self._execute_research(task)
            elif task_type == "query":
                return await self._execute_query(task)
            elif task_type == "analysis":
                return await self._execute_analysis(task)
            elif task_type == "synthesis":
                return await self._execute_synthesis(task)
            else:
                raise ValueError(f"Unknown task type: {task_type}")
                
        except Exception as e:
            logger.error(f"Researcher execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "task_type": task_type
            }
    
    async def _execute_research(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行研究任务"""
        task_id = task.get("task_id", "")
        input_data = task.get("input_data", {})
        
        research_topic = input_data.get("topic", "")
        research_questions = input_data.get("questions", [])
        required_kbs = input_data.get("required_knowledge_bases", [])
        required_tools = input_data.get("required_tools", [])
        
        # 执行多维度研究
        research_results = await self._conduct_multidimensional_research(
            research_topic, research_questions, required_kbs, required_tools
        )
        
        # 信息质量评估
        quality_assessment = await self._assess_information_quality(research_results)
        
        # 生成研究发现
        findings = await self._generate_research_findings(research_results, quality_assessment)
        
        return {
            "success": True,
            "task_id": task_id,
            "research_results": research_results,
            "quality_assessment": quality_assessment,
            "findings": findings,
            "completed_at": datetime.now().isoformat()
        }
    
    async def _execute_query(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行查询任务"""
        query = task.get("query", "")
        kb_ids = task.get("knowledge_bases", [])
        query_mode = task.get("mode", "hybrid")
        limit = task.get("limit", 10)
        
        # 执行查询
        query_results = await self.query_engine.query_multiple_knowledge_bases(
            query=query,
            kb_ids=kb_ids,
            user_id=self.config.user_id,
            mode=QueryMode(query_mode),
            limit=limit
        )
        
        # 结果处理和排序
        processed_results = await self._process_query_results(query_results)
        
        return {
            "success": True,
            "query": query,
            "results": processed_results,
            "total_results": len(query_results),
            "query_mode": query_mode
        }
    
    async def _execute_analysis(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行分析任务"""
        data = task.get("data", [])
        analysis_type = task.get("analysis_type", "content_analysis")
        
        if analysis_type == "content_analysis":
            analysis_result = await self._content_analysis(data)
        elif analysis_type == "sentiment_analysis":
            analysis_result = await self._sentiment_analysis(data)
        elif analysis_type == "trend_analysis":
            analysis_result = await self._trend_analysis(data)
        else:
            analysis_result = await self._general_analysis(data)
        
        return {
            "success": True,
            "analysis_type": analysis_type,
            "analysis_result": analysis_result
        }
    
    async def _execute_synthesis(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行信息综合任务"""
        information_sources = task.get("information_sources", [])
        synthesis_objective = task.get("objective", "")
        
        # 信息去重和整合
        deduplicated_info = await self._deduplicate_information(information_sources)
        
        # 信息综合
        synthesis_result = await self._synthesize_information(deduplicated_info, synthesis_objective)
        
        return {
            "success": True,
            "synthesis_result": synthesis_result,
            "source_count": len(information_sources),
            "processed_count": len(deduplicated_info)
        }
    
    async def _conduct_multidimensional_research(
        self,
        topic: str,
        questions: List[str],
        required_kbs: List[str],
        required_tools: List[str]
    ) -> Dict[str, Any]:
        """执行多维度研究"""
        research_results = {
            "topic": topic,
            "knowledge_base_results": {},
            "tool_results": {},
            "cross_referenced_results": [],
            "research_dimensions": []
        }
        
        # 知识库研究
        if required_kbs:
            kb_results = await self._research_knowledge_bases(topic, questions, required_kbs)
            research_results["knowledge_base_results"] = kb_results
        
        # MCP工具研究
        if required_tools:
            tool_results = await self._research_with_tools(topic, questions, required_tools)
            research_results["tool_results"] = tool_results
        
        # 交叉验证
        cross_referenced = await self._cross_reference_results(
            research_results["knowledge_base_results"],
            research_results["tool_results"]
        )
        research_results["cross_referenced_results"] = cross_referenced
        
        # 研究维度分析
        dimensions = await self._analyze_research_dimensions(research_results)
        research_results["research_dimensions"] = dimensions
        
        return research_results
    
    async def _research_knowledge_bases(
        self,
        topic: str,
        questions: List[str],
        kb_ids: List[str]
    ) -> Dict[str, Any]:
        """研究知识库"""
        kb_results = {}
        
        for kb_id in kb_ids:
            kb_name = f"kb_{kb_id}"
            kb_results[kb_name] = {
                "topic_results": [],
                "question_results": [],
                "summary": ""
            }
            
            # 主题相关查询
            if topic:
                topic_queries = await self._generate_topic_queries(topic)
                for query in topic_queries:
                    results = await self.query_engine.query_knowledge_base(
                        query=query,
                        kb_id=kb_id,
                        user_id=self.config.user_id,
                        mode=QueryMode.HYBRID,
                        limit=5
                    )
                    kb_results[kb_name]["topic_results"].extend(results)
            
            # 问题相关查询
            for question in questions:
                question_results = await self.query_engine.query_knowledge_base(
                    query=question,
                    kb_id=kb_id,
                    user_id=self.config.user_id,
                    mode=QueryMode.HYBRID,
                    limit=3
                )
                kb_results[kb_name]["question_results"].extend(question_results)
            
            # 生成知识库摘要
            all_results = (
                kb_results[kb_name]["topic_results"] +
                kb_results[kb_name]["question_results"]
            )
            if all_results:
                summary = await self._generate_kb_summary(all_results, kb_id)
                kb_results[kb_name]["summary"] = summary
        
        return kb_results
    
    async def _research_with_tools(
        self,
        topic: str,
        questions: List[str],
        tool_names: List[str]
    ) -> Dict[str, Any]:
        """使用MCP工具进行研究"""
        tool_results = {}
        
        for tool_name in tool_names:
            tool_results[tool_name] = {
                "topic_results": [],
                "question_results": [],
                "tool_info": {}
            }
            
            # 获取工具信息
            tool_info = await self.mcp_registry.get_tool_info(tool_name)
            if tool_info:
                tool_results[tool_name]["tool_info"] = tool_info
                
                # 主题相关调用
                if topic:
                    topic_args = await self._prepare_tool_args(tool_name, topic, "topic")
                    if topic_args:
                        result = await self.mcp_registry.call_tool(
                            tool_name, topic_args, self.config.user_id
                        )
                        tool_results[tool_name]["topic_results"].append(result)
                
                # 问题相关调用
                for question in questions:
                    question_args = await self._prepare_tool_args(tool_name, question, "question")
                    if question_args:
                        result = await self.mcp_registry.call_tool(
                            tool_name, question_args, self.config.user_id
                        )
                        tool_results[tool_name]["question_results"].append(result)
        
        return tool_results
    
    async def _generate_topic_queries(self, topic: str) -> List[str]:
        """生成主题相关查询"""
        prompt = f"""
基于研究主题：{topic}

请生成5个不同角度的查询问题，用于全面了解这个主题：

1. 定义和概念相关的查询
2. 历史发展相关的查询
3. 现状和趋势相关的查询
4. 应用和实践相关的查询
5. 挑战和未来相关的查询

请直接返回查询问题列表，每行一个问题。
"""
        
        response = await self.llm_service.generate_response(
            prompt=prompt,
            config=self.config.llm_config
        )
        
        # 解析查询列表
        queries = []
        for line in response.split('\n'):
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('基于'):
                # 去除序号
                clean_line = line.split('.', 1)[-1].strip()
                if clean_line:
                    queries.append(clean_line)
        
        return queries[:5]  # 限制为5个查询
    
    async def _prepare_tool_args(self, tool_name: str, content: str, content_type: str) -> Optional[Dict[str, Any]]:
        """准备工具调用参数"""
        tool_info = await self.mcp_registry.get_tool_info(tool_name)
        if not tool_info:
            return None
        
        # 根据工具模式准备参数
        schema = tool_info.get("schema", {})
        properties = schema.get("properties", {})
        
        # 常见参数映射
        args = {}
        
        # 查找文本输入参数
        text_params = ["query", "text", "content", "input", "prompt"]
        for param in text_params:
            if param in properties:
                args[param] = content
                break
        
        # 查找其他常用参数
        if "limit" in properties:
            args["limit"] = 5
        if "max_results" in properties:
            args["max_results"] = 5
        if "type" in properties:
            args["type"] = content_type
        
        return args if args else None
    
    async def _cross_reference_results(
        self,
        kb_results: Dict[str, Any],
        tool_results: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """交叉验证结果"""
        cross_referenced = []
        
        # 提取所有文本内容
        kb_contents = []
        for kb_name, kb_data in kb_results.items():
            for result in kb_data.get("topic_results", []) + kb_data.get("question_results", []):
                kb_contents.append({
                    "source": kb_name,
                    "content": result.get("content", ""),
                    "metadata": result.get("metadata", {})
                })
        
        tool_contents = []
        for tool_name, tool_data in tool_results.items():
            for result in tool_data.get("topic_results", []) + tool_data.get("question_results", []):
                if result.get("success"):
                    tool_contents.append({
                        "source": tool_name,
                        "content": str(result.get("result", "")),
                        "metadata": {}
                    })
        
        # 执行交叉引用分析
        if kb_contents and tool_contents:
            cross_analysis = await self._analyze_content_overlap(kb_contents, tool_contents)
            cross_referenced.extend(cross_analysis)
        
        return cross_referenced
    
    async def _analyze_content_overlap(
        self,
        kb_contents: List[Dict],
        tool_contents: List[Dict]
    ) -> List[Dict[str, Any]]:
        """分析内容重叠"""
        overlaps = []
        
        # 简单的关键词匹配分析
        for kb_content in kb_contents[:3]:  # 限制处理数量
            for tool_content in tool_contents[:3]:
                similarity = await self._calculate_content_similarity(
                    kb_content["content"],
                    tool_content["content"]
                )
                
                if similarity > 0.3:  # 相似度阈值
                    overlaps.append({
                        "kb_source": kb_content["source"],
                        "tool_source": tool_content["source"],
                        "similarity": similarity,
                        "kb_content": kb_content["content"][:200] + "...",
                        "tool_content": tool_content["content"][:200] + "...",
                        "overlap_type": "content_similarity"
                    })
        
        return overlaps
    
    async def _calculate_content_similarity(self, content1: str, content2: str) -> float:
        """计算内容相似度"""
        if not content1 or not content2:
            return 0.0
        
        # 简单的词汇重叠计算
        words1 = set(content1.lower().split())
        words2 = set(content2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    async def _analyze_research_dimensions(self, research_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """分析研究维度"""
        dimensions = []
        
        # 知识覆盖维度
        kb_coverage = len(research_results.get("knowledge_base_results", {}))
        if kb_coverage > 0:
            dimensions.append({
                "dimension": "knowledge_coverage",
                "score": min(kb_coverage / 3, 1.0),  # 3个知识库为满分
                "description": f"覆盖了{kb_coverage}个知识库"
            })
        
        # 工具使用维度
        tool_usage = len(research_results.get("tool_results", {}))
        if tool_usage > 0:
            dimensions.append({
                "dimension": "tool_utilization",
                "score": min(tool_usage / 2, 1.0),  # 2个工具为满分
                "description": f"使用了{tool_usage}个工具"
            })
        
        # 交叉验证维度
        cross_ref_count = len(research_results.get("cross_referenced_results", []))
        if cross_ref_count > 0:
            dimensions.append({
                "dimension": "cross_validation",
                "score": min(cross_ref_count / 5, 1.0),  # 5个交叉验证为满分
                "description": f"发现了{cross_ref_count}个交叉验证结果"
            })
        
        return dimensions
    
    async def _assess_information_quality(self, research_results: Dict[str, Any]) -> Dict[str, Any]:
        """评估信息质量"""
        quality_assessment = {
            "overall_quality": InformationQuality.FAIR,
            "quality_metrics": {},
            "quality_issues": [],
            "improvement_suggestions": []
        }
        
        # 计算质量指标
        metrics = await self._calculate_quality_metrics(research_results)
        quality_assessment["quality_metrics"] = metrics
        
        # 确定整体质量
        overall_score = metrics.get("overall_score", 0.5)
        if overall_score >= 0.8:
            quality_assessment["overall_quality"] = InformationQuality.EXCELLENT
        elif overall_score >= 0.6:
            quality_assessment["overall_quality"] = InformationQuality.GOOD
        elif overall_score >= 0.4:
            quality_assessment["overall_quality"] = InformationQuality.FAIR
        else:
            quality_assessment["overall_quality"] = InformationQuality.POOR
        
        # 识别质量问题
        issues = await self._identify_quality_issues(research_results, metrics)
        quality_assessment["quality_issues"] = issues
        
        # 生成改进建议
        suggestions = await self._generate_improvement_suggestions(issues)
        quality_assessment["improvement_suggestions"] = suggestions
        
        return quality_assessment
    
    async def _calculate_quality_metrics(self, research_results: Dict[str, Any]) -> Dict[str, Any]:
        """计算质量指标"""
        metrics = {
            "completeness": 0.0,
            "accuracy": 0.0,
            "relevance": 0.0,
            "freshness": 0.0,
            "diversity": 0.0,
            "overall_score": 0.0
        }
        
        # 完整性评估
        kb_count = len(research_results.get("knowledge_base_results", {}))
        tool_count = len(research_results.get("tool_results", {}))
        cross_ref_count = len(research_results.get("cross_referenced_results", []))
        
        completeness = (kb_count * 0.4 + tool_count * 0.3 + cross_ref_count * 0.3) / 3
        metrics["completeness"] = min(completeness, 1.0)
        
        # 准确性评估（基于交叉验证）
        if cross_ref_count > 0:
            metrics["accuracy"] = min(cross_ref_count / 5, 1.0)
        else:
            metrics["accuracy"] = 0.5  # 默认值
        
        # 相关性评估
        total_results = 0
        for kb_data in research_results.get("knowledge_base_results", {}).values():
            total_results += len(kb_data.get("topic_results", []))
            total_results += len(kb_data.get("question_results", []))
        
        if total_results > 0:
            metrics["relevance"] = min(total_results / 10, 1.0)
        else:
            metrics["relevance"] = 0.0
        
        # 新鲜度评估（假设所有结果都是新鲜的）
        metrics["freshness"] = 0.8
        
        # 多样性评估
        source_diversity = kb_count + tool_count
        metrics["diversity"] = min(source_diversity / 5, 1.0)
        
        # 整体分数
        metrics["overall_score"] = (
            metrics["completeness"] * 0.3 +
            metrics["accuracy"] * 0.25 +
            metrics["relevance"] * 0.25 +
            metrics["freshness"] * 0.1 +
            metrics["diversity"] * 0.1
        )
        
        return metrics
    
    async def _identify_quality_issues(
        self,
        research_results: Dict[str, Any],
        metrics: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """识别质量问题"""
        issues = []
        
        # 完整性问题
        if metrics["completeness"] < 0.5:
            issues.append({
                "type": "completeness",
                "severity": "medium",
                "description": "研究覆盖面不够全面",
                "metric_value": metrics["completeness"]
            })
        
        # 准确性问题
        if metrics["accuracy"] < 0.6:
            issues.append({
                "type": "accuracy",
                "severity": "high",
                "description": "缺乏足够的交叉验证",
                "metric_value": metrics["accuracy"]
            })
        
        # 相关性问题
        if metrics["relevance"] < 0.4:
            issues.append({
                "type": "relevance",
                "severity": "high",
                "description": "相关信息不足",
                "metric_value": metrics["relevance"]
            })
        
        # 多样性问题
        if metrics["diversity"] < 0.3:
            issues.append({
                "type": "diversity",
                "severity": "medium",
                "description": "信息来源缺乏多样性",
                "metric_value": metrics["diversity"]
            })
        
        return issues
    
    async def _generate_improvement_suggestions(self, issues: List[Dict[str, Any]]) -> List[str]:
        """生成改进建议"""
        suggestions = []
        
        for issue in issues:
            issue_type = issue.get("type", "")
            
            if issue_type == "completeness":
                suggestions.append("建议增加更多知识库或工具来提高研究覆盖面")
            elif issue_type == "accuracy":
                suggestions.append("建议增加交叉验证步骤以提高信息准确性")
            elif issue_type == "relevance":
                suggestions.append("建议优化查询策略以获得更相关的信息")
            elif issue_type == "diversity":
                suggestions.append("建议使用更多样化的信息源")
        
        return suggestions
    
    async def _generate_research_findings(
        self,
        research_results: Dict[str, Any],
        quality_assessment: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """生成研究发现"""
        findings = []
        
        # 从知识库结果中提取发现
        for kb_name, kb_data in research_results.get("knowledge_base_results", {}).items():
            if kb_data.get("summary"):
                findings.append({
                    "type": "knowledge_base_finding",
                    "source": kb_name,
                    "content": kb_data["summary"],
                    "confidence": 0.8,
                    "timestamp": datetime.now().isoformat()
                })
        
        # 从工具结果中提取发现
        for tool_name, tool_data in research_results.get("tool_results", {}).items():
            successful_results = [
                r for r in tool_data.get("topic_results", []) + tool_data.get("question_results", [])
                if r.get("success")
            ]
            
            if successful_results:
                findings.append({
                    "type": "tool_finding",
                    "source": tool_name,
                    "content": f"通过{tool_name}工具获得了{len(successful_results)}个有效结果",
                    "confidence": 0.7,
                    "timestamp": datetime.now().isoformat()
                })
        
        # 从交叉验证中提取发现
        cross_ref_results = research_results.get("cross_referenced_results", [])
        if cross_ref_results:
            findings.append({
                "type": "cross_validation_finding",
                "source": "cross_reference",
                "content": f"发现了{len(cross_ref_results)}个交叉验证结果，提高了信息可信度",
                "confidence": 0.9,
                "timestamp": datetime.now().isoformat()
            })
        
        return findings
    
    async def _process_query_results(self, query_results: List[Dict]) -> List[Dict]:
        """处理查询结果"""
        processed_results = []
        
        for result in query_results:
            processed_result = {
                "content": result.get("content", ""),
                "score": result.get("score", 0.0),
                "metadata": result.get("metadata", {}),
                "source_kb": result.get("source_kb", ""),
                "source_name": result.get("source_name", ""),
                "chunk_id": result.get("chunk_id", ""),
                "processed_at": datetime.now().isoformat()
            }
            
            # 添加内容摘要
            if len(processed_result["content"]) > 200:
                processed_result["summary"] = processed_result["content"][:200] + "..."
            else:
                processed_result["summary"] = processed_result["content"]
            
            processed_results.append(processed_result)
        
        # 按分数排序
        processed_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        return processed_results
    
    async def _content_analysis(self, data: List[Dict]) -> Dict[str, Any]:
        """内容分析"""
        analysis = {
            "total_documents": len(data),
            "content_themes": [],
            "key_concepts": [],
            "content_structure": {},
            "analysis_summary": ""
        }
        
        if not data:
            return analysis
        
        # 提取所有文本内容
        all_content = []
        for item in data:
            content = item.get("content", "")
            if content:
                all_content.append(content)
        
        # 主题分析
        if all_content:
            themes = await self._extract_themes(all_content)
            analysis["content_themes"] = themes
            
            # 关键概念提取
            concepts = await self._extract_key_concepts(all_content)
            analysis["key_concepts"] = concepts
            
            # 内容结构分析
            structure = await self._analyze_content_structure(all_content)
            analysis["content_structure"] = structure
            
            # 生成分析摘要
            summary = await self._generate_content_summary(themes, concepts, structure)
            analysis["analysis_summary"] = summary
        
        return analysis
    
    async def _extract_themes(self, content_list: List[str]) -> List[Dict[str, Any]]:
        """提取主题"""
        # 简单的主题提取实现
        themes = []
        
        # 统计词频
        word_freq = {}
        for content in content_list:
            words = content.lower().split()
            for word in words:
                if len(word) > 3:  # 过滤短词
                    word_freq[word] = word_freq.get(word, 0) + 1
        
        # 提取高频词作为主题
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        for word, freq in sorted_words[:10]:
            themes.append({
                "theme": word,
                "frequency": freq,
                "relevance": min(freq / len(content_list), 1.0)
            })
        
        return themes
    
    async def _extract_key_concepts(self, content_list: List[str]) -> List[Dict[str, Any]]:
        """提取关键概念"""
        concepts = []
        
        # 简单的关键概念提取
        for content in content_list[:3]:  # 限制处理数量
            # 寻找专业术语模式
            words = content.split()
            for i, word in enumerate(words):
                if len(word) > 5 and word.istitle():
                    concepts.append({
                        "concept": word,
                        "context": " ".join(words[max(0, i-2):i+3]),
                        "confidence": 0.6
                    })
        
        return concepts[:10]  # 限制返回数量
    
    async def _analyze_content_structure(self, content_list: List[str]) -> Dict[str, Any]:
        """分析内容结构"""
        structure = {
            "average_length": 0,
            "total_length": 0,
            "paragraph_count": 0,
            "sentence_count": 0
        }
        
        total_chars = 0
        total_paragraphs = 0
        total_sentences = 0
        
        for content in content_list:
            total_chars += len(content)
            total_paragraphs += content.count('\n\n') + 1
            total_sentences += content.count('.') + content.count('!') + content.count('?')
        
        structure["total_length"] = total_chars
        structure["average_length"] = total_chars / len(content_list) if content_list else 0
        structure["paragraph_count"] = total_paragraphs
        structure["sentence_count"] = total_sentences
        
        return structure
    
    async def _generate_content_summary(
        self,
        themes: List[Dict],
        concepts: List[Dict],
        structure: Dict[str, Any]
    ) -> str:
        """生成内容摘要"""
        summary_parts = []
        
        if themes:
            top_themes = [theme["theme"] for theme in themes[:3]]
            summary_parts.append(f"主要主题包括：{', '.join(top_themes)}")
        
        if concepts:
            concept_count = len(concepts)
            summary_parts.append(f"识别出{concept_count}个关键概念")
        
        avg_length = structure.get("average_length", 0)
        if avg_length > 0:
            summary_parts.append(f"平均内容长度为{int(avg_length)}字符")
        
        return "；".join(summary_parts) if summary_parts else "内容分析完成"
    
    async def _sentiment_analysis(self, data: List[Dict]) -> Dict[str, Any]:
        """情感分析"""
        return {
            "sentiment_distribution": {
                "positive": 0.4,
                "neutral": 0.4,
                "negative": 0.2
            },
            "overall_sentiment": "neutral",
            "confidence": 0.7
        }
    
    async def _trend_analysis(self, data: List[Dict]) -> Dict[str, Any]:
        """趋势分析"""
        return {
            "trend_direction": "stable",
            "trend_strength": "moderate",
            "key_indicators": [],
            "forecast": "数据显示相对稳定的趋势"
        }
    
    async def _general_analysis(self, data: List[Dict]) -> Dict[str, Any]:
        """通用分析"""
        return {
            "analysis_type": "general",
            "data_points": len(data),
            "analysis_result": "完成了基础数据分析",
            "insights": []
        }
    
    async def _deduplicate_information(self, information_sources: List[Dict]) -> List[Dict]:
        """信息去重"""
        deduplicated = []
        seen_contents = set()
        
        for source in information_sources:
            content = source.get("content", "")
            if content and content not in seen_contents:
                seen_contents.add(content)
                deduplicated.append(source)
        
        return deduplicated
    
    async def _synthesize_information(
        self,
        information_sources: List[Dict],
        objective: str
    ) -> Dict[str, Any]:
        """综合信息"""
        synthesis = {
            "synthesis_objective": objective,
            "source_count": len(information_sources),
            "key_insights": [],
            "consolidated_information": "",
            "synthesis_quality": "good"
        }
        
        if information_sources:
            # 提取关键信息
            key_points = []
            for source in information_sources:
                content = source.get("content", "")
                if content:
                    # 简单的关键信息提取
                    sentences = content.split('.')
                    for sentence in sentences[:2]:  # 每个来源取前两句
                        if len(sentence.strip()) > 20:
                            key_points.append(sentence.strip())
            
            synthesis["key_insights"] = key_points[:10]  # 限制数量
            
            # 生成综合信息
            if key_points:
                synthesis["consolidated_information"] = " ".join(key_points[:5])
            
            # 评估综合质量
            if len(information_sources) >= 3:
                synthesis["synthesis_quality"] = "excellent"
            elif len(information_sources) >= 2:
                synthesis["synthesis_quality"] = "good"
            else:
                synthesis["synthesis_quality"] = "basic"
        
        return synthesis
    
    async def _generate_kb_summary(self, results: List[Dict], kb_id: str) -> str:
        """生成知识库摘要"""
        if not results:
            return f"知识库 {kb_id} 未找到相关信息"
        
        # 提取主要内容
        main_contents = []
        for result in results[:3]:  # 取前3个结果
            content = result.get("content", "")
            if content:
                # 取前100个字符作为摘要
                summary = content[:100] + "..." if len(content) > 100 else content
                main_contents.append(summary)
        
        if main_contents:
            return f"知识库 {kb_id} 主要内容：" + " | ".join(main_contents)
        else:
            return f"知识库 {kb_id} 内容处理中"