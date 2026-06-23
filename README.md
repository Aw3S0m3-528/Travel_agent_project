# Travel Agent Project

一个基于 LangGraph 的多 Agent 旅游规划原型。

我做这个项目主要是想练习多阶段 Agent workflow。旅游规划看起来像文本生成，但实际需要先理解用户需求，再检索资料、筛选景点、安排路线、估算预算，最后检查结果是否可执行。

当前项目仍然是学习和展示用原型，重点不在于替代真实旅行产品，而在于验证：Agent 流程能否被拆分、追踪、降级和复核。

## 为什么做这个项目

我希望用一个足够贴近真实生活的场景来练习 Agent 编排。旅游规划的输入通常很模糊，例如“周末去成都，两天，喜欢美食和人文，预算中等”。如果直接让大模型生成攻略，很容易出现路线不顺、时间过满、门票或开放时间不准确等问题。

所以我把它拆成多个节点，让每一步只处理一类任务，并在最后加入 Validator 做结果复核。

## 工作流

```text
Requirement -> Retrieval -> Route -> Time -> Image -> Budget -> Guide Writer -> Validator
```

Streamlit 侧边栏可以切换两种模式：

- `LangGraph`：展示多节点编排、状态流转和条件分支。
- `顺序调度`：保留一个更简单的兼容流程，方便在依赖不可用时回退。

## Agent 结构

- `Requirement Agent`：解析目的地、天数、预算、偏好、强度等信息。
- `Retrieval Agent`：检索本地资料和联网资料，补充景点开放时间、门票、预约等信息，并对来源做评分。
- `Route Agent`：按天安排景点顺序，并补充地图信息。
- `Time Agent`：生成每日时间表。
- `Image Agent`：搜索景点图片。
- `Budget Agent`：估算餐饮、交通、住宿、门票和总预算。
- `Guide Writer Agent`：生成最终攻略。
- `Validator Agent`：检查完整性和风险，并输出评分。

## 当前能力

- Streamlit 聊天式交互页面
- LangGraph / 顺序调度双编排模式
- DeepSeek / OpenAI-compatible LLM 调用
- 本地 RAG + 近两年联网资料检索
- Gemini Embedding 不可用时降级为本地关键词检索
- 高德地图 POI 定位和路线估算
- 景点图片搜索：Wikimedia Commons / DuckDuckGo / Bing
- SQLite 历史行程保存
- 图片搜索、联网搜索缓存
- 行程编辑、局部重新规划、地图可视化
- Validator 评分制复核
- Markdown 导出

## 降级策略

这个项目里外部依赖比较多，所以我尽量让核心流程在依赖缺失时也能跑起来：

- Gemini Embedding 或 Chroma 向量库不可用时，降级为本地关键词检索。
- 联网搜索失败时，使用本地资料和规则兜底，并提示动态信息需要出行前确认。
- 高德地图 API 未配置时，退化为基础路线估算。
- 图片搜索失败时，只影响展示，不影响核心行程生成。

## 运行

复制 `.env.example` 为 `.env`，按需填写 API Key。

```bash
pip install -r requirements.txt
streamlit run app.py
```

示例配置：

```env
DEEPSEEK_API_KEY=sk-your-deepseek-key
DEEPSEEK_MODEL=deepseek-v4-flash
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-v4-flash
RAG_USE_VECTOR=false
AMAP_API_KEY=your-amap-key
```

如果没有 Gemini Embedding 额度，可以保持：

```env
RAG_USE_VECTOR=false
```

系统会使用本地关键词检索作为 fallback。

## 数据目录

- `data/raw_docs/`：本地旅游资料
- `data/vector_db/`：Chroma 向量库
- `data/travel_agent.db`：SQLite 历史行程和缓存数据库

## 已知限制

- 本地知识库目前只覆盖少量城市，资料完整度有限。
- Validator 主要是规则评分，对路线体验和用户主观偏好的判断还比较粗。
- 图片搜索结果仅用于学习展示，正式使用前需要进一步确认版权和来源。
- 地图路线估算依赖高德 API，未配置时只能做基础路线安排。

