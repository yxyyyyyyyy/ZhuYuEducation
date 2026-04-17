# 教师端三问题修复计划

## 问题 1：AI 出题只显示数学 + 页面只分布在左边

### 根因
- **只显示数学**：`initCascade("generate")` 使用 `leafTopics()` 获取学科列表，而 `leafTopics()` 只返回叶子节点（没有子节点的 topic）。如果数据库中只有数学教材有知识点，其他学科没有知识点节点，就只会显示数学。
- **页面只分布在左边**：HTML 中 `<div class="panel" style="max-width:640px;">` 限制了面板宽度，没有居中

### 修复
1. **前端** `teacher.html`：移除 `max-width:640px`，改为 `max-width:720px; margin:0 auto;` 居中显示
2. **前端** `teacher.js` `initCascade`：`getSubjects()` 改为从所有 topics（不仅是叶子节点）获取学科，确保即使某学科没有知识点也能显示

## 问题 2：AI 生成题目 400 Bad Request

### 根因
前端 `generateQuestions()` 发送了 `include_explanation` 和 `include_answer_sheet` 字段，但后端 `QuestionGenerateRequest` 模型没有这两个字段。Pydantic v2 默认拒绝多余字段，导致 400 错误。

### 修复
1. **后端** `models.py` `QuestionGenerateRequest`：新增 `include_explanation: bool = True` 和 `include_answer_sheet: bool = False` 字段
2. **后端** `question_bank_service.py`：在生成逻辑中使用这两个字段（如 `include_explanation` 控制是否生成解析）

## 问题 3：学生列表按年级-班级显示 + 名字像真人

### 根因
- `TeacherStudentSummary` 模型没有 `classroom_name` 字段，前端无法显示班级
- 种子数据只有一个"小余"学生，名字不够像真人

### 修复
1. **后端** `models.py` `TeacherStudentSummary`：新增 `classroom_name: str = ""` 和 `target_subject: str = ""` 字段
2. **后端** `teacher_service.py` `dashboard()`：查询学生时 JOIN `ClassroomORM` 获取班级名称
3. **前端** `teacher.js` `renderStudentList()`：卡片 meta 改为 `年级 · 班级 · 学科` 格式
4. **后端** `container.py` 种子数据：添加更多学生（如"张明轩"、"李思涵"、"王子涵"等），分配到不同班级

---

## 涉及文件

| 文件 | 改动 |
|------|------|
| `app/templates/teacher.html` | 面板居中 |
| `app/static/teacher.js` | 学科获取逻辑 + 学生卡片显示 |
| `app/domain/models.py` | QuestionGenerateRequest 新增字段 + TeacherStudentSummary 新增字段 |
| `app/services/teacher_service.py` | dashboard 查询 JOIN 班级 |
| `app/services/question_bank_service.py` | 使用 include_explanation/include_answer_sheet |
| `app/core/container.py` | 种子数据增加学生 |

## 实施顺序

1. 修复 400 错误（后端模型 + 服务）
2. 修复 AI 出题只显示数学 + 页面布局
3. 学生列表按年级-班级显示 + 种子数据
