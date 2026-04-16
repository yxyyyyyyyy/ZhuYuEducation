# 教师端 UI 改造计划

## 需求概述

两大模块改造：**数据总览** 和 **AI 生成题目**，涉及视觉升级、交互优化、布局重构。

---

## 一、数据总览改造

### 1.1 核心指标卡片重构（2×2 网格 + 差异化主题色 + 图标）

**CSS 改动** (`teacher.html` style 区域)
- 修改 `.stat-grid` 为 `grid-template-columns: 1fr 1fr`（2×2 固定网格）
- 新增 `.kpi-card` 样式：`图标 + 大数字 + 小标签` 经典看板布局
- 四色主题：蓝(`#1456f0`) / 绿(`#2ba471`) / 橙(`#f7a440`) / 紫(`#8b5cf6`)
- hover 上浮 + 阴影加深效果
- 数字 28px 加粗主题色，标签 12px 浅灰

**JS 改动** (`teacher.js` → `renderTeacherDashboard`)
- 重构 4 个 stat-card 为 `.kpi-card`，结构：`<div class="kpi-icon">👤</div><div class="kpi-value">42</div><div class="kpi-label">学生总数</div>`
- 分配图标：学生总数👤 / 活跃学生🟢 / 掌握度📊 / 正确率🎯
- 分配主题色 class：`kpi-blue` / `kpi-green` / `kpi-orange` / `kpi-purple`
- 可选：补充对比数据（活跃占比 = active/total）

### 1.2 学生列表卡片改造（左右分栏 + 进度条 + 排序筛选）

**CSS 改动**
- 新增 `.student-card` 样式：左右分栏，左侧姓名+年级/知识点，右侧掌握度进度条+正确率
- 新增 `.progress-bar` 样式：分色标注（<40%红 / <70%橙 / ≥70%绿）
- 新增 `.student-list-header` 排序/筛选栏样式
- 斑马纹效果：`.student-card:nth-child(even)` 微灰背景

**JS 改动** (`teacher.js` → `renderTeacherDashboard` 中学生列表部分)
- 重构学生列表为 `.student-card` 左右分栏布局
- 掌握度用进度条可视化（分色）
- 列表顶部增加排序/筛选功能（按掌握度/正确率/姓名排序）
- 点击学生卡片跳转学生详细学习报告（`navigateTo` 或链接）

### 1.3 练习分析改造（指标对齐 + 知识点明细 + 时间筛选）

**CSS 改动**
- 练习分析核心指标复用 `.kpi-card` 样式，与总览风格对齐
- 新增 `.topic-table` 知识点明细表格样式

**JS 改动** (`teacher.js` → `renderPracticeAnalytics`)
- 核心指标（总练习数/总正确数/整体正确率）改为 `.kpi-card` 样式
- 知识点明细改为表格/卡片展示（练习数、正确率、掌握度）
- 增加时间筛选功能（本周/本月/自定义）

### 1.4 顶部操作栏调整

**HTML/CSS 改动**
- 模块标题与刷新按钮同排，按钮右对齐
- 刷新按钮改为「图标 + 文字」样式，增加加载动画（spinner）

### 1.5 全局字体层级统一

**CSS 改动**
- 标题 16px 加粗（`.panel-header h3`）
- 正文 14px 常规
- 辅助文字 12px 浅灰（`#8f959e`）

### 1.6 空状态 + 响应式 + 可访问性

- 补充空状态提示（无学生/无练习时的友好提示）
- 响应式：2×2 网格在小屏变为 1 列，左右分栏变为上下
- 图标补充 `aria-label`，确保文字对比度合规

---

## 二、AI 生成题目改造

### 2.1 按钮升级（加载状态 + 防重复点击）

**JS 改动** (`teacher.js` → `generateQuestions`)
- 点击后按钮变为「⏳ 生成中...」并 `disabled`
- 生成成功后显示全局提示「X 道题目已生成，待审核」
- 生成失败显示错误提示
- 当前已有此逻辑，优化文案和动画

### 2.2 增加可选配置项

**HTML 改动** (`teacher.html` → question-generate section)
- 新增「题目来源」下拉（AI 生成 / 混合来源）
- 新增「是否包含解析」开关
- 新增「是否生成答题卡」开关

**JS 改动**
- `generateQuestions()` 提交时携带新配置参数

### 2.3 生成模板功能

**HTML 改动**
- 新增「保存为模板」按钮
- 新增「使用模板」下拉选择

**JS 改动**
- 模板存储在 `localStorage`
- 保存/加载/删除模板逻辑

### 2.4 状态反馈优化

**JS 改动**
- 生成完成后自动跳转至待审核列表
- 提示「X 道题目已生成，待审核」

### 2.5 表单布局重构（2 行布局）

**HTML 改动**
- 学科/年级/知识点 3 个下拉框从横向并排改为 2 行：
  - 第一行：学科 + 年级
  - 第二行：知识点（通栏）
- 解决小屏幕下挤压问题

**CSS 改动**
- 新增 `.form-row` 样式：`display: grid; grid-template-columns: 1fr 1fr; gap: 12px;`
- 知识点单独一行通栏

---

## 涉及文件

| 文件 | 改动类型 |
|------|---------|
| `app/templates/teacher.html` | HTML 结构 + CSS 样式 |
| `app/static/teacher.js` | JS 渲染逻辑 + 交互 |

不涉及后端改动，所有变更均为前端 UI 调整。

## 实施顺序

1. CSS 基础样式（kpi-card、student-card、progress-bar、form-row 等）
2. 数据总览 HTML 结构调整
3. 数据总览 JS 渲染逻辑重构
4. AI 生成题目 HTML 布局重构
5. AI 生成题目 JS 逻辑增强
6. 响应式适配 + 空状态 + 可访问性
