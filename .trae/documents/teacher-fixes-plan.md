# 教师端修复计划：级联跳过修复 + 难度改为题型分类 + 题库列表修复 + favicon

## 问题分析

### 问题1：initCascade skip: documentFilter true true false
- **原因**：`documentFilter` 区域只有 Grade + Subject 两个选择器，没有 TopicId，但 `initCascade` 要求三个都存在
- **修复**：`initCascade` 中 `topicEl` 为可选，不存在时跳过知识点联动

### 问题2：favicon.ico 404
- **原因**：没有 favicon 文件
- **修复**：添加一个简单的 SVG favicon 或在 main.py 中忽略该路由

### 问题3：保存的模板没有
- **原因**：模板保存在 localStorage，但 `applyGenerateTemplate` 中设置 `qs("generateSubject").value` 时，由于级联逻辑已改为先年级后学科，直接设置学科值可能不会触发联动
- **修复**：应用模板时先设年级再设学科，并手动触发 change 事件

### 问题4：难度选择改为"基础概念/常规/综合"
- **当前**：低/中/高 三个难度选项，映射到 difficulty_level 1-5
- **用户要求**：不选难度，改为选择题型分类：基础概念、常规、综合，每个分类让 AI 生成不同难度范围的题目
- **修改**：
  - HTML：`generateDifficulty` 改为 `generateCategory`，选项改为 基础概念(1-2) / 常规(2-4) / 综合(4-5)
  - JS：读取 `generateCategory` 替代 `generateDifficulty`
  - 模板保存/应用：对应字段改为 `category`

### 问题5：题库列表加载不出来
- **可能原因**：数据库重建后没有题目数据，或者 API 返回格式问题
- **修复**：检查 API 返回，确保空列表也能正常渲染

---

## 实施步骤

### 步骤1：修复 initCascade — topicEl 可选

修改 `teacher.js` 中的 `initCascade`：
- `topicEl` 为 null 时不 return，只是跳过知识点相关逻辑
- 年级/学科 onchange 时，如果 topicEl 存在才更新知识点

### 步骤2：添加 favicon

在 `teacher.html` 的 `<head>` 中添加内联 SVG favicon：
```html
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📚</text></svg>">
```

### 步骤3：难度改为题型分类

**修改 teacher.html：**
- `generateDifficulty` select 改为 `generateCategory`
- 选项：基础概念(value=basic, 1-2) / 常规(value=regular, 2-4) / 综合(value=comprehensive, 4-5)

**修改 teacher.js：**
- 生成题目时读取 `generateCategory` 替代 `generateDifficulty`
- diffMap 改为：`{ basic: [1, 2], regular: [2, 4], comprehensive: [4, 5] }`
- 模板保存/应用字段改为 `category`
- 题库列表中难度显示也改为：1-2=基础概念，3=常规，4-5=综合

### 步骤4：修复模板应用逻辑

修改 `applyGenerateTemplate`：
- 先设年级，触发 change
- 再设学科，触发 change
- 最后设知识点值（需延迟等待联动完成）

### 步骤5：确保题库列表正常

检查 `renderQuestionBank` 对空数据的处理，确保不会因 null 引用崩溃。

---

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `app/static/teacher.js` | initCascade topicEl 可选、难度改题型分类、模板修复、题库列表难度显示 |
| `app/templates/teacher.html` | favicon、难度选择器改为题型分类 |
