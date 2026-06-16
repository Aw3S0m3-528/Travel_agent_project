# 基于多 Agent 辅助的旅游规划系统

一个面向学习和展示的智能旅游规划原型系统。用户输入自然语言旅行需求后，系统会通过多个 Agent 协作完成需求解析、资料检索、路线规划、时间安排、图片搜索、预算估算、攻略生成和结果复核。

## 当前能力

- Streamlit 聊天式交互页面
- LangGraph / 顺序调度双编排模式与阶段进度展示
- DeepSeek/OpenAI-compatible LLM 调用
- 本地 RAG + 近两年联网资料检索
- Gemini Embedding 不可用时自动降级为本地关键词检索
- 高德地图 POI 定位和路线估算
- 景点图片搜索：Wikimedia Commons / DuckDuckGo / Bing
- SQLite 历史行程保存
- 通用 SQLite 缓存：图片搜索、联网搜索
- 交互式行程编辑器与局部重新规划
- 路线地图可视化
- 预算 Agent
- Validator 评分制复核
- Markdown 导出

## LangGraph 工作流

项目新增 `graph/` 编排层，用 LangGraph 将现有 Agent 封装为可追踪节点：

```text
Requirement -> Retrieval -> Route -> Time -> Image -> Budget -> Guide Writer -> Validator
```

Streamlit 侧边栏可切换：

- `LangGraph`：适合展示多 Agent 图编排、节点扩展和后续条件分支能力
- `顺序调度`：保留原有兼容流程，便于在依赖不可用时回退

## Agent 结构

- `Requirement Agent`：解析目的地、天数、预算、偏好、强度等信息
- `Retrieval Agent`：本地 RAG、联网检索、景点开放/门票属性补充
- `Route Agent`：景点分天、路线顺序、地图信息补充
- `Time Agent`：生成每日时间表
- `Image Agent`：搜索景点图片
- `Budget Agent`：估算餐饮、交通、住宿、门票和总预算
- `Guide Writer Agent`：生成最终攻略
- `Validator Agent`：检查完整性、风险，并输出评分

## 环境配置

复制 `.env.example` 为 `.env`，填写自己的 API Key。

```env
DEEPSEEK_API_KEY=sk-your-deepseek-key
DEEPSEEK_MODEL=deepseek-v4-flash
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-v4-flash
RAG_USE_VECTOR=false
AMAP_API_KEY=your-amap-key
```

如果没有 Gemini Embedding 额度，保持：

```env
RAG_USE_VECTOR=false
```

系统会自动使用本地关键词检索和联网搜索资料。

## 运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 数据目录

- `data/raw_docs/`：本地旅游资料
- `data/vector_db/`：Chroma 向量库
- `data/travel_agent.db`：SQLite 历史行程和缓存数据库

## 说明

本项目用于学习、课程项目或原型展示。联网搜索图片和网页资料仅适合学习演示；正式发布前需要确认图片授权、来源标注和动态旅游信息的官方准确性。
