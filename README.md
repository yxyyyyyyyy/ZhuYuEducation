# Zhuyu Education Agent

一个面向教育场景的智能学习系统原型，当前已经覆盖学生端、教师端、题库、文档检索和 RAG 教辅。

## 现在这个项目做了什么

- 学生登录与学生档案
- 知识点掌握度保存
- 学习诊断与学习路径规划
- 自适应出题与练习提交
- 错题归因、错题本保存与回放
- AI 辅导对话与历史记录
- 学习报告与间隔复习计划
- 教师端多学生总览
- 题库导入与练习记录分析
- 教材、讲义、题解文档导入
- 文档检索与 RAG 证据召回
- 教师端资料/RAG 工作区：浏览器上传资料、索引状态、搜索调试、评测集
- 学生端 AI 回复结构化证据引用
- DashScope Embedding / Reranker 接入

## 大模型和检索模型接了什么

项目里现在有两条模型链路：

### 1. 对话大模型

文件：`app/services/llm_service.py`

- 走 OpenAI 兼容接口
- 默认读取：
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL`
  - `OPENAI_MODEL`
- 当前默认配置：`https://api.deepseek.com/v1`
- 当前默认模型名：`deepseek-chat`

这层用于：

- AI 辅导回复生成
- 基于检索证据的教学解释

如果没有配置 `OPENAI_API_KEY`，系统会自动退回离线辅导模式，不会报错中断。

### 2. Embedding + Reranker

文件：`app/services/dashscope_service.py`

- 接的是阿里云 DashScope
- Embedding 默认模型：`text-embedding-v4`
- Reranker 默认模型：`qwen3-rerank`

这层用于：

- 文档切块向量化
- 文档检索 dense 召回
- RAG 二次重排

如果没有配置 `DASHSCOPE_API_KEY`，系统会回退到本地混合检索，不会阻塞主流程。

## 配置文件

项目已经支持从根目录 `.env` 自动加载配置。

你需要关注这两个文件：

- `.env`
- `.env.example`

当前 `.env` 内容如下：

```env
APP_NAME=Zhuyu Education Agent
APP_VERSION=0.3.0
SESSION_TTL_HOURS=168
ALLOWED_HOSTS=
CORS_ALLOWED_ORIGINS=
DOCUMENT_IMPORT_ROOT=
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
DASHSCOPE_API_KEY=
DASHSCOPE_REGION=intl
DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4
DASHSCOPE_EMBEDDING_DIMENSIONS=1024
DASHSCOPE_RERANK_MODEL=qwen3-rerank
DASHSCOPE_EMBEDDING_URL=
DASHSCOPE_RERANK_URL=
```

说明：

- 配 `OPENAI_*` 后，AI 辅导会走真实大模型
- 配 `DASHSCOPE_*` 后，文档会支持真实 embedding 和 rerank
- 如果两者都不配，系统也能跑，但会走离线兜底
- `SESSION_TTL_HOURS` 控制登录态有效期，默认 168 小时；设为 `0` 表示不过期
- `ALLOWED_HOSTS` 和 `CORS_ALLOWED_ORIGINS` 默认留空，部署到公网时建议按域名白名单填写
- `DOCUMENT_IMPORT_ROOT` 可限制“目录批量导入”只能读取指定根目录下的文件
- `.env` 已加入 `.gitignore`，真实密钥建议只保留在本地

## 项目结构

```text
EchoEducation/
  app/
    api/              # FastAPI 路由
    core/             # 数据库、容器、环境配置
    domain/           # 领域模型
    repositories/     # 数据访问
    services/         # 业务服务与模型适配
    static/           # 前端静态资源
    templates/        # 前端页面
    main.py           # 服务入口
  data/               # SQLite 数据与知识图谱种子
  scripts/            # 验证脚本
  .env                # 运行配置
  .env.example        # 配置模板
```

## 安装依赖

```bash
cd /Users/yxy/LearningStageProject/奇思妙想/05医疗知识图谱问答机器人/EchoEducation
pip3 install -r requirements.txt
```

## 启动

```bash
cd /Users/yxy/LearningStageProject/奇思妙想/05医疗知识图谱问答机器人/EchoEducation
python3 -m uvicorn app.main:app --reload
```

打开：

- 前端工作台：`http://127.0.0.1:8000/`
- Swagger 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`
- 就绪检查：`http://127.0.0.1:8000/ready`

## 演示账号

- 邮箱：`demo@zhuyu.local`
- 密码：`demo123456`

## 验证

运行：

```bash
python3 scripts/verify_frontend.py
python3 scripts/verify_student_experience.py
python3 scripts/verify_phase3.py
python3 scripts/verify_rag_upgrade.py
python3 scripts/verify_rag_workspace.py
python3 scripts/verify_production_readiness.py
```

如果你已经配置了真实 DashScope 和 OpenAI key，建议再手动验证两项：

1. 文档中心导入文档后执行“重建向量”
2. AI 辅导里提问并观察是否引用检索证据

## 关键说明

- 当前数据库是 SQLite，适合本地开发和功能验证
- 检索链路支持本地混合检索 + DashScope dense/rerank 增强
- 对话链路支持 OpenAI 兼容接口，因此后续也可以切别的兼容模型网关
- 资料/RAG 工作区支持浏览器上传 `txt/md/pdf/docx`，单文件默认不超过 10MB
- RAG 引用已升级为结构化证据，包含资料标题、来源、类型、片段和相关度分数
- 已补基础生产化守卫：学生数据/会话跨账号隔离、会话过期与登出、基础安全响应头、可选 Host/CORS 白名单、数据库与知识图谱就绪检查
- 真正公网生产环境还建议继续补：HTTPS 终止、集中日志和监控告警、数据库迁移工具、备份恢复、限流、防刷和更细粒度教师/班级权限
