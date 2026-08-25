# AI Interview Agent

面向技术岗位的中文文字模拟面试系统：上传 PDF 简历、填写岗位 JD 后，系统采集公开资料、分析候选人与岗位、动态生成问题、评估回答，并在面试结束后生成综合报告。

## 当前实现边界

当前项目是函数式多阶段 Agent 编排，并未使用 LangGraph 的 `StateGraph` 执行工作流。`backend/app/agents/state.py` 中的 `InterviewState` 只是预留类型；真实编排由 `backend/app/api/interviews.py`、`backend/app/services/interview_service.py` 和 `backend/app/agents/nodes.py` 完成。本文中的“Agent 节点”表示职责独立的模型/规则函数，不表示已经接入 LangGraph。

## 组件与依赖

| 组件 | 作用 | 必需性 |
| --- | --- | --- |
| Nuxt 3 | 配置、会话、历史、结果页面 | 必需 |
| FastAPI | REST API、SSE 事件和业务编排 | 必需 |
| MySQL | 会话、题目、回答、评分和资料元数据 | 必需 |
| Redis | 答题互斥锁，TTL 120 秒 | 必需 |
| Elasticsearch | 资料文本与向量混合检索 | 必需 |
| Embedding API | 资料和查询向量化 | 必需 |
| LLM API | 简历/岗位分析、出题、回答评估 | 启动配置必填；运行失败时节点规则降级 |
| Tavily | 发现公开网页资料 | 可选；未配置时仍支持用户 URL |

后端启动会检查数据库、Redis、Elasticsearch 和 Embedding。缺失时启动失败。LLM 请求超时、网络失败或返回非法 JSON 时，相关节点使用规则结果并标记 `degraded`；这不等于 LLM 配置可以不填。

## Agent 工作流

### 1. 创建会话和采集资料

`POST /api/v1/interviews`

1. 校验岗位、JD、PDF 和 URL。
2. 保存并解析 PDF，创建 `created` 状态的会话。
3. 抓取用户提供的公开 URL。
4. 配置 Tavily 时搜索“岗位 + 面试题 + 职位要求”；正文抓取失败但摘要可用时保存为 `summary_only`。
5. 资料按内容哈希去重，保存到 MySQL，并分块向量化到 Elasticsearch。

公开网页只作参考，不能当作公司内部事实。

### 2. 初始化面试

`POST /api/v1/interviews/{session_id}/start`

```text
简历/JD 入库 → 简历分析 Agent → 岗位分析 Agent → 首题生成 Agent
                                               ↓
                                  保存第 1 轮题目，状态改为 in_progress
```

历史会话已有题目时不会重新初始化，只返回已有首题。

### 3. 提交回答和路由

`POST /api/v1/interviews/{session_id}/answer`

```text
提交回答 → Redis 互斥锁 → 回答评估 → 持久化回答/评分 → plan_next
                                      ├─ 低于 65 且追问少于 2 次：生成追问
                                      ├─ 未到第 10 个主问题：生成下一主问题
                                      └─ 已到第 10 个主问题：生成最终总评并完成
```

`current_round` 只统计主问题轮次，追问不增加轮次。阶段为：背景与经历核验、岗位核心能力、项目与工作情景、回答质量追问。会话完成后不能继续提交。

### 4. 评分和总评

评分维度：正确性、完整性、技术深度、项目证据、表达、工程风险意识。权重依次为 `20% / 20% / 15% / 20% / 10% / 15%`。无证据时总分上限 59。评分输出优势、证据缺口、事实错误、风险提示、改进建议和学习用示例答案；示例使用占位符，不代表用户事实。

第 10 轮完成后汇总综合分、能力均分、薄弱点、学习计划、风险提示和覆盖率，并声明不代表真实招聘结论。

## SSE 与异常恢复

事件包括 `workflow_node_enter`、`workflow_node_leave`、`evaluation`、`question`、`interview_completed` 和 `workflow_error`。评估期间每 10 秒发送 SSE 心跳，避免代理空闲超时产生假性 `network error`。浏览器断开后，服务端会继续保存评估并尝试生成下一题；锁在生成器 `finally` 和响应结束回调中幂等释放。

前端只有确认数据库已保存回答后才清空草稿；失败且未保存时恢复原输入。工作流日志目前只在页面内存中，重新打开历史会话不会恢复旧日志。

历史会话使用相同逻辑：已保存回答但下一题缺失时可恢复后续流程，不会重复评分；从未写入数据库的旧回答无法找回。修改代码后必须重启 FastAPI，刷新浏览器不会更新旧后端进程。

## 检索和自由问答

资料按约 1200 字符分块，使用 Embedding 写入 `interview_materials`。查询评分为 `0.3 × 文本相关性 + 0.7 × 向量余弦相似度`。检索异常时出题回退到 MySQL 中的简历、JD 和公开资料，但首次写入仍要求 ES 与 Embedding 可用。

`POST /api/v1/interviews/{session_id}/ask` 是不计分的会话自由问答：基于检索摘要生成模板回答，保存消息和引用，不改变面试轮次。

## 本地启动

当前 `docker-compose.yml` 只启动 MySQL、Elasticsearch、Redis，不包含前后端：

```powershell
docker compose up -d
Copy-Item backend/.env.example backend/.env
```

宿主机端口：MySQL `3307`（容器内 3306）、Elasticsearch `9200`、Redis `6379`。`backend/.env` 应使用：

```dotenv
DATABASE_URL=mysql+aiomysql://interview:123456_mysql@localhost:3307/interview_agent?charset=utf8mb4
ES_HOST=http://localhost:9200
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=http://localhost:3000
```

然后启动：

```powershell
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

另开终端：

```powershell
cd frontend
npm install
npm.cmd run dev
```

默认后端为 `http://localhost:8010`，前端为 `http://localhost:3000`。如前端端口改变，必须同步修改 `CORS_ORIGINS`。`APP_DEBUG=true` 会输出可能包含简历、JD、回答的 SQL 参数，日常应保持 `false`。

## 数据与安全

- URL 抓取前拒绝回环和私网地址，降低 SSRF 风险。
- 简历、JD、回答和评分存于数据库/本地上传目录，生产环境需要访问控制、加密、备份和保留期限策略。
- 删除会话会删除关联数据库记录、本地简历、ES 分块和该会话 Redis 临时锁。
- 输出是模拟面试辅助信息，不代表真实招聘结论。

## 测试

```powershell
cd backend
python -m pytest -q
```

测试覆盖规则评分、相似问题识别、追问上限、URL 安全和 SSE 断流后的锁清理。
