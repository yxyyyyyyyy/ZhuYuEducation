# 教师端文档上传修复计划

## 问题分析

### 问题：选择文件后上传区域没有变化

**根本原因**：
1. 点击 `dropZone` 或拖拽文件后，虽然文件已赋值到 `uploadDocumentFile` input，但 **没有任何 UI 反馈** 告诉用户文件已选中
2. `uploadDocumentFile` 的 `change` 事件没有绑定处理函数
3. `dropZone` 的文字始终显示"拖拽文件到此处，或点击选择"，选择文件后不会更新
4. 拖拽文件时只弹了一个 toast，但点击选择文件时连 toast 都没有

**用户困惑**：选了文件但界面没变化，不确定文件是否已选中，也不知道是否上传成功

---

## 实施步骤

### 步骤1：为 uploadDocumentFile 添加 change 事件处理

在 `bindEvents` 中添加：
```js
bindChange("uploadDocumentFile", onFileSelected);
```

新增 `onFileSelected()` 函数：
- 获取选中的文件名
- 更新 `dropZone` 的显示内容，显示文件名和文件大小
- 添加视觉反馈（如边框变色、图标变化）

### 步骤2：修改 dropZone 的 UI 反馈

选择文件后，`dropZone` 内容从：
```
📂 拖拽文件到此处，或点击选择
```
变为：
```
📄 已选择：filename.txt (12.3 KB)  [点击重新选择]
```

### 步骤3：上传成功后恢复 dropZone 原始状态

在 `uploadDocument()` 的成功回调中，恢复 `dropZone` 为初始状态。

---

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `app/static/teacher.js` | 新增 `onFileSelected()` 函数、绑定 change 事件、上传后恢复 dropZone |
