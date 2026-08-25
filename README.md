# AI Interview Agent

## 本地热更新开发

Docker 只运行 MySQL、Elasticsearch 和 Redis；FastAPI 与 Nuxt 在本机运行，因此 Python 使用 `uvicorn --reload`，Nuxt 使用 HMR。

先执行 `docker compose up -d`，再复制 `backend/.env.example` 为 `backend/.env`。本机后端访问容器时必须使用 `localhost`：MySQL `localhost:3306`、ES `localhost:9200`、Redis `localhost:6379`。

后端：`cd backend; pip install -r requirements.txt; uvicorn app.main:app --reload --port 8010`。

前端：`cd frontend; npm install; npm run dev`。

`APP_DEBUG=true` 仅输出 SQLAlchemy SQL 调试日志；日常开发和演示建议为 `false`，避免日志中出现简历、JD 或回答等敏感参数。

`UPLOAD_DIR=uploads` 是 PDF 简历的本地保存目录，相对后端启动路径，通常为 `backend/uploads`。`CORS_ORIGINS=http://localhost:3000` 是允许 Nuxt 开发服务器跨域调用后端的来源；若前端端口或域名变化，需改为实际来源。

联网搜索使用 Tavily。在 `backend/.env` 填写 `TAVILY_API_KEY=tvly-...`；系统调用 Tavily 的公开搜索 API 发现候选网页，再按 URL 合规校验抓取和保存来源摘要。未配置 Key 时不会自动联网搜索，仍可使用用户手动提供的公开 URL。

独立的中文文字模拟面试系统，面向前端开发和 Agent 开发岗位。

## 能力

- 上传 PDF 简历，填写公司、岗位与 JD。
- <img width="1909" height="775" alt="image" src="https://github.com/user-attachments/assets/d8560135-4677-4a18-bef6-20281b9f5d5f" />
  <img width="994" height="760" alt="image" src="https://github.com/user-attachments/assets/7e9ca10f-13f3-42df-bbe2-fb92ed626023" />
- 通过可配置搜索 API 发现公开岗位/面试资料，或抓取用户提供的公开 URL；记录来源并缓存。
- <img width="1026" height="787" alt="image" src="https://github.com/user-attachments/assets/fbb00182-6ac7-4eab-b8ba-875e3469f0fc" />


- 10 道主问题、每题最多 2 次追问；SSE 实时返回进度、题目、评分与总评。
- 多维评分、面试历史、同一会话内不计分的自由问答。
- 未配置搜索、LLM、Embedding 或 Elasticsearch 时明确降级，不伪造网页来源。

## 启动

```powershell
cd backend
Copy-Item .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8010
```

另开终端：

```powershell
cd frontend
npm install
npm run dev
```

默认后端地址为 `http://localhost:8010`，前端为 `http://localhost:3000`。

## Docker 基础设施与 OpenRouter

`docker-compose.yml` 会启动 MySQL、Elasticsearch 8.17 和 Redis。容器内连接地址必须使用服务名：`mysql`、`elasticsearch`、`redis`，不要写 `localhost`。复制 `.env.example` 后，把两个 `sk-or-v1-replace_me` 替换为 OpenRouter Key；聊天模型为 `openai/gpt-4o-mini`，嵌入模型为 `openai/text-embedding-3-small`。

ES、Redis 和 Embedding 是本项目的强依赖：后端启动时会检查 Redis、ES 和 Embedding；任一不可用则启动失败。资料写入时必须成功向量化并建立 `interview_materials` 索引，查询也只走 ES 混合检索，不回退至数据库文本检索。

启动前请执行：

```powershell
Copy-Item backend/.env.example backend/.env
# 编辑 backend/.env，替换 MySQL 密码及两个 OpenRouter Key
docker compose up --build
```


网页内容只保留摘要和来源链接。请仅提供可公开访问且允许访问的网页。
