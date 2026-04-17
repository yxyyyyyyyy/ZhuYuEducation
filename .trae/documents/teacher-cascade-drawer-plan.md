# 教师端修复计划：级联选择器逻辑 + 学生列表右弹窗

## 问题分析

### 问题1：级联选择器逻辑错误 — 先选学科再选年级，年级显示不出来
- **当前逻辑**：`initCascade()` 先选学科(`Subject`)，再选年级(`Grade`)，再选知识点(`TopicId`)
- **用户要求**：先选年级，再选学科，再选知识点
- **年级显示不出来的原因**：`getGradesBySubject()` 依赖学科先选，但用户希望先选年级后筛选出该年级有的学科
- **涉及位置**：
  - `teacher.js` 中的 `initCascade()`、`getSubjects()`、`getGradesBySubject()`、`getTopicsBySubjectAndGrade()`
  - `teacher.html` 中所有级联选择器的 HTML 结构（6处：generate、uploadDocument、documentFilter、docSearch、case、eval）

### 问题2：数据总览学生列表全展开，需改为按年级班级分组的右弹窗
- **当前逻辑**：`renderStudentList()` 把所有学生平铺为卡片列表
- **用户要求**：按年级-班级分组，点击班级卡片弹出右侧抽屉(Drawer)查看该班级学生详情
- **涉及位置**：
  - `teacher.js` 中的 `renderStudentList()`
  - `teacher.html` 中的 dashboard 区域和学生列表区域

---

## 实施步骤

### 步骤1：修改级联选择器逻辑 — 先年级后学科

**修改 `teacher.js`：**

1. 新增辅助函数：
   - `getGrades()` — 获取所有年级列表（从 topics 中提取去重）
   - `getSubjectsByGrade(grade)` — 根据年级筛选可选学科
   - `getTopicsByGradeAndSubject(grade, subject)` — 根据年级+学科筛选知识点

2. 重写 `initCascade(prefix, opts)`：
   - HTML 元素 ID 约定改为 `{prefix}Grade` → `{prefix}Subject` → `{prefix}TopicId`
   - 初始化时先填充年级下拉框
   - 年级 onchange → 填充学科下拉框 + 全部知识点
   - 学科 onchange → 填充知识点下拉框（按年级+学科过滤）

3. 修改 HTML 中级联选择器的顺序（6处）：
   - `generate` 区域：年级在前，学科在后
   - `uploadDocument` 区域：年级在前，学科在后
   - `documentFilter` 区域：年级在前，学科在后
   - `docSearch` 区域：年级在前，学科在后
   - `case` 区域：年级在前，学科在后
   - `eval` 区域：年级在前，学科在后

### 步骤2：学生列表改为年级-班级分组 + 右弹窗

**修改 `teacher.html`：**

1. 添加右侧抽屉(Drawer)的 CSS 样式和 HTML 结构：
   - `.drawer-overlay` — 遮罩层
   - `.drawer-panel` — 右侧滑出面板
   - 面板内容：班级名称、学生列表（含掌握度/正确率进度条）

2. 修改 dashboard 区域的学生列表面板：
   - 保留排序选择器
   - 学生列表改为按年级-班级分组的卡片

**修改 `teacher.js`：**

1. 重写 `renderStudentList(data)`：
   - 按 `grade_level` + `classroom_name` 分组
   - 每组显示为一张卡片：年级·班级名 + 学生人数 + 平均掌握度
   - 点击卡片打开右侧抽屉，显示该班级学生详情列表

2. 新增 `openStudentDrawer(grade, classroom)` 函数：
   - 显示遮罩 + 右侧面板
   - 面板内渲染该班级的学生详情（姓名、掌握度进度条、正确率）

3. 新增 `closeStudentDrawer()` 函数：
   - 隐藏遮罩 + 面板

---

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `app/static/teacher.js` | 重写级联逻辑、重写学生列表渲染、新增抽屉函数 |
| `app/templates/teacher.html` | 调整6处级联选择器顺序、添加抽屉CSS/HTML、调整学生列表区域 |
