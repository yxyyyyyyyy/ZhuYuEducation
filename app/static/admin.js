const state = {
  token: localStorage.getItem("zhuyu_token") || "",
  user: null,
  activePage: "dashboard",
  dashboard: null,
  teacher: {
    q: "",
    page: 1,
    pageSize: 12,
    totalPages: 1,
    total: 0,
    items: [],
    mode: "table",
  },
  announcement: {
    q: "",
    page: 1,
    pageSize: 8,
    totalPages: 1,
    total: 0,
    items: [],
    editingId: null,
    draftTimer: null,
    editorCollapsed: false,
  },
  question: {
    q: "",
    topicId: "",
    subject: "",
    gradeLevel: "",
    status: "",
    questionType: "",
    page: 1,
    pageSize: 20,
    totalPages: 1,
    total: 0,
    items: [],
    stats: {},
    categories: [],
    selectedIds: new Set(),
  },
  knowledge: {
    textbooks: [],
    activeTextbookId: null,
    tree: [],
    topicOptions: [],
    selectedNodeKeys: new Set(),
    editingNodeKey: null,
    dragNodeKey: "",
    dragParentKey: "",
  },
};

function qs(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

function showToast(text) {
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = text;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 1800);
}

async function api(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const headers = { ...(isFormData ? {} : { "Content-Type": "application/json" }), ...(options.headers || {}) };
  if (state.token) headers["X-Session-Token"] = state.token;
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `请求失败：${response.status}`);
  }
  if (options.responseType === "text") return response.text();
  return response.json();
}

function showLoginGate() {
  qs("loginGate").style.display = "";
  qs("appMain").style.display = "none";
}

function showAppMain() {
  qs("loginGate").style.display = "none";
  qs("appMain").style.display = "";
}

function navigateTo(page) {
  state.activePage = page;
  document.querySelectorAll(".nav-btn[data-page]").forEach((item) => {
    item.classList.toggle("active", item.dataset.page === page);
  });
  document.querySelectorAll(".page").forEach((section) => {
    section.classList.toggle("active", section.dataset.page === page);
  });
}

function formatDateTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function clearTeacherErrors() {
  qs("teacherNameError").textContent = "";
  qs("teacherEmailError").textContent = "";
  qs("teacherPasswordError").textContent = "";
}

function validateTeacherForm() {
  clearTeacherErrors();
  let ok = true;
  const name = qs("teacherNameInput").value.trim();
  const email = qs("teacherEmailInput").value.trim();
  const password = qs("teacherPasswordInput").value;
  if (!name) {
    qs("teacherNameError").textContent = "请填写姓名";
    ok = false;
  }
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    qs("teacherEmailError").textContent = "邮箱格式不正确";
    ok = false;
  }
  if ((password || "").length < 8) {
    qs("teacherPasswordError").textContent = "密码至少 8 位";
    ok = false;
  }
  return ok;
}

function renderDashboard(data) {
  state.dashboard = data;
  qs("schoolNameView").textContent = `${data.school.name}${data.school.region ? ` · ${data.school.region}` : ""}`;
  qs("adminSummaryView").innerHTML = `
    <div class="stat-card"><strong>教师</strong><div>${data.teacher_count}</div></div>
    <div class="stat-card"><strong>班级</strong><div>${data.classroom_count}</div></div>
    <div class="stat-card"><strong>学生</strong><div>${data.student_count}</div></div>
    <div class="stat-card"><strong>题目</strong><div>${data.question_count}</div></div>
    <div class="stat-card"><strong>公告</strong><div>${data.announcement_count}</div></div>
  `;
}

async function loadDashboard() {
  renderDashboard(await api("/admin/dashboard"));
}

function renderPagination(targetId, page, totalPages, total, onPrev, onNext) {
  const target = qs(targetId);
  target.innerHTML = `
    <span>共 ${total} 条</span>
    <button class="btn btn-ghost btn-sm" ${page <= 1 ? "disabled" : ""} id="${targetId}Prev">上一页</button>
    <span>${page} / ${totalPages || 1}</span>
    <button class="btn btn-ghost btn-sm" ${page >= totalPages ? "disabled" : ""} id="${targetId}Next">下一页</button>
  `;
  const prev = qs(`${targetId}Prev`);
  const next = qs(`${targetId}Next`);
  if (prev && !prev.disabled) prev.addEventListener("click", onPrev);
  if (next && !next.disabled) next.addEventListener("click", onNext);
}

function showPasswordModal(password) {
  qs("passwordModalValue").textContent = password;
  qs("passwordModal").classList.add("show");
}

function hidePasswordModal() {
  qs("passwordModal").classList.remove("show");
}

function renderTeacherTable(items) {
  return `
    <div class="list-wrap">
      <table>
        <thead>
          <tr>
            <th>姓名</th>
            <th>邮箱</th>
            <th>教师ID</th>
            <th>班级数</th>
            <th>学生数</th>
            <th>创建时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${items.map((item) => `
            <tr>
              <td class="core-info"><strong>${escapeHtml(item.full_name)}</strong></td>
              <td>${escapeHtml(item.email)}</td>
              <td>${item.id}</td>
              <td>${item.classroom_count || 0}</td>
              <td>${item.student_count || 0}</td>
              <td>${formatDateTime(item.created_at)}</td>
              <td>
                <div class="row-actions">
                  <button class="btn btn-ghost btn-sm" data-reset-teacher-id="${item.id}">重置密码</button>
                  <button class="btn btn-danger btn-sm" data-delete-teacher-id="${item.id}">删除</button>
                </div>
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function renderTeacherCards(items) {
  return `
    <div class="teacher-card-grid">
      ${items.map((item) => `
        <article class="teacher-card">
          <h4>${escapeHtml(item.full_name)}</h4>
          <div class="meta">${escapeHtml(item.email)}</div>
          <div class="meta">教师ID：${item.id}</div>
          <div class="meta">班级 ${item.classroom_count || 0} · 学生 ${item.student_count || 0}</div>
          <div class="row-actions">
            <button class="btn btn-ghost btn-sm" data-reset-teacher-id="${item.id}">重置密码</button>
            <button class="btn btn-danger btn-sm" data-delete-teacher-id="${item.id}">删除</button>
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function bindTeacherRowActions() {
  document.querySelectorAll("[data-reset-teacher-id]").forEach((button) => {
    button.addEventListener("click", () => resetTeacherPassword(Number(button.dataset.resetTeacherId)).catch(handleError));
  });
  document.querySelectorAll("[data-delete-teacher-id]").forEach((button) => {
    button.addEventListener("click", () => deleteTeacher(Number(button.dataset.deleteTeacherId)).catch(handleError));
  });
}

function renderTeacherList() {
  const target = qs("teacherListView");
  if (!state.teacher.items.length) {
    target.className = "empty-state";
    target.innerHTML = "暂无教师账号";
    return;
  }
  target.className = "";
  target.innerHTML = state.teacher.mode === "table"
    ? renderTeacherTable(state.teacher.items)
    : renderTeacherCards(state.teacher.items);
  bindTeacherRowActions();
}

async function loadTeachers() {
  const params = new URLSearchParams({
    q: state.teacher.q,
    page: String(state.teacher.page),
    page_size: String(state.teacher.pageSize),
  });
  const payload = await api(`/admin/teachers/manage?${params.toString()}`);
  state.teacher.items = payload.items || [];
  state.teacher.total = payload.total || 0;
  state.teacher.totalPages = payload.total_pages || 1;
  renderTeacherList();
  renderPagination(
    "teacherPagination",
    state.teacher.page,
    state.teacher.totalPages,
    state.teacher.total,
    () => { state.teacher.page -= 1; loadTeachers().catch(handleError); },
    () => { state.teacher.page += 1; loadTeachers().catch(handleError); },
  );
}

async function createTeacher() {
  if (!validateTeacherForm()) return;
  await api("/admin/teachers", {
    method: "POST",
    body: JSON.stringify({
      full_name: qs("teacherNameInput").value.trim(),
      email: qs("teacherEmailInput").value.trim(),
      password: qs("teacherPasswordInput").value,
    }),
  });
  qs("teacherNameInput").value = "";
  qs("teacherEmailInput").value = "";
  qs("teacherPasswordInput").value = "";
  clearTeacherErrors();
  state.teacher.page = 1;
  await Promise.all([loadTeachers(), loadDashboard()]);
  showToast("教师账号创建成功");
}

function downloadTeacherTemplate() {
  const header = "姓名,邮箱,初始密码\n";
  const example = "张老师,zhang@school.com,abc12345\n";
  const blob = new Blob(["\uFEFF" + header + example], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = "教师导入模板.csv";
  link.click();
  URL.revokeObjectURL(link.href);
}

async function importTeacherCsv() {
  const file = qs("teacherImportFile").files?.[0];
  if (!file) {
    showToast("请先选择 CSV 文件");
    return;
  }
  const text = await file.text();
  const result = await api("/admin/teachers/import-csv", {
    method: "POST",
    body: text,
    headers: { "Content-Type": "text/plain" },
  });
  qs("teacherImportResult").textContent = `导入成功 ${result.imported_count} 条，跳过 ${result.skipped_count} 条`;
  state.teacher.page = 1;
  await Promise.all([loadTeachers(), loadDashboard()]);
}

async function resetTeacherPassword(teacherId) {
  const result = await api(`/admin/teachers/${teacherId}/reset-password`, { method: "POST" });
  showPasswordModal(result.new_password || "");
}

async function deleteTeacher(teacherId) {
  const ok = window.confirm("确认删除该教师账号？若有班级或学生将无法删除。");
  if (!ok) return;
  await api(`/admin/teachers/${teacherId}`, { method: "DELETE" });
  state.teacher.page = 1;
  await Promise.all([loadTeachers(), loadDashboard()]);
  showToast("教师账号已删除");
}

function scheduleDraftSave() {
  if (state.announcement.draftTimer) {
    clearTimeout(state.announcement.draftTimer);
  }
  qs("announcementDraftHint").textContent = "草稿保存中...";
  state.announcement.draftTimer = setTimeout(() => {
    saveAnnouncementDraft().catch(handleError);
  }, 700);
}

async function saveAnnouncementDraft() {
  const title = qs("announcementTitleInput").value.trim();
  const contentHtml = qs("announcementEditorInput").innerHTML.trim();
  const draft = await api("/admin/announcement-draft", {
    method: "PUT",
    body: JSON.stringify({ title, content_html: contentHtml }),
  });
  qs("announcementDraftHint").textContent = `草稿已保存：${formatDateTime(draft.updated_at)}`;
}

async function loadAnnouncementDraft() {
  const draft = await api("/admin/announcement-draft");
  if (!draft) return;
  if (!qs("announcementTitleInput").value.trim() && !qs("announcementEditorInput").innerHTML.trim()) {
    qs("announcementTitleInput").value = draft.title || "";
    qs("announcementEditorInput").innerHTML = draft.content_html || "";
    qs("announcementDraftHint").textContent = `已加载草稿：${formatDateTime(draft.updated_at)}`;
  }
}

function announcementPayloadFromForm() {
  const title = qs("announcementTitleInput").value.trim();
  const contentHtml = qs("announcementEditorInput").innerHTML.trim();
  const contentText = qs("announcementEditorInput").textContent.trim();
  if (!title) throw new Error("公告标题不能为空");
  if (!contentText) throw new Error("公告内容不能为空");
  return {
    title,
    content: contentText,
    content_html: contentHtml,
    is_pinned: !!qs("announcementPinnedInput").checked,
  };
}

async function publishAnnouncement() {
  const payload = announcementPayloadFromForm();
  if (state.announcement.editingId) {
    await api(`/admin/announcements/${state.announcement.editingId}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    showToast("公告更新成功");
  } else {
    await api("/admin/announcements", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showToast("公告发布成功");
  }
  clearAnnouncementEditor();
  state.announcement.page = 1;
  await Promise.all([loadAnnouncements(), loadDashboard()]);
}

function clearAnnouncementEditor() {
  state.announcement.editingId = null;
  qs("announcementTitleInput").value = "";
  qs("announcementEditorInput").innerHTML = "";
  qs("announcementPinnedInput").checked = false;
  qs("announcementDraftHint").textContent = "草稿待保存";
  qs("publishAnnouncementButton").textContent = "发布公告";
}

function renderAnnouncementList() {
  const target = qs("announcementListView");
  if (!state.announcement.items.length) {
    target.className = "empty-state";
    target.innerHTML = "暂无公告";
    return;
  }
  target.className = "announcement-flow";
  target.innerHTML = state.announcement.items.map((item) => `
    <article class="announcement-card">
      ${item.is_pinned ? "<span class='pin-tag'>置顶</span>" : ""}
      <h4>${escapeHtml(item.title)}</h4>
      <div class="summary">${escapeHtml(item.summary || "")}</div>
      <div class="time">发布时间：${formatDateTime(item.created_at)}</div>
      <div class="time">更新时间：${formatDateTime(item.updated_at)}</div>
      <div class="row-actions" style="margin-top:8px;">
        <button class="btn btn-ghost btn-sm" data-edit-announcement-id="${item.id}">编辑</button>
        <button class="btn btn-ghost btn-sm" data-pin-announcement-id="${item.id}">${item.is_pinned ? "取消置顶" : "置顶"}</button>
        <button class="btn btn-danger btn-sm" data-delete-announcement-id="${item.id}">删除</button>
      </div>
    </article>
  `).join("");

  document.querySelectorAll("[data-edit-announcement-id]").forEach((button) => {
    button.addEventListener("click", () => editAnnouncement(Number(button.dataset.editAnnouncementId)).catch(handleError));
  });
  document.querySelectorAll("[data-delete-announcement-id]").forEach((button) => {
    button.addEventListener("click", () => deleteAnnouncement(Number(button.dataset.deleteAnnouncementId)).catch(handleError));
  });
  document.querySelectorAll("[data-pin-announcement-id]").forEach((button) => {
    button.addEventListener("click", () => toggleAnnouncementPin(Number(button.dataset.pinAnnouncementId)).catch(handleError));
  });
}

async function loadAnnouncements() {
  const params = new URLSearchParams({
    q: state.announcement.q,
    page: String(state.announcement.page),
    page_size: String(state.announcement.pageSize),
  });
  const payload = await api(`/admin/announcements/manage?${params.toString()}`);
  state.announcement.items = payload.items || [];
  state.announcement.total = payload.total || 0;
  state.announcement.totalPages = payload.total_pages || 1;
  renderAnnouncementList();
  renderPagination(
    "announcementPagination",
    state.announcement.page,
    state.announcement.totalPages,
    state.announcement.total,
    () => { state.announcement.page -= 1; loadAnnouncements().catch(handleError); },
    () => { state.announcement.page += 1; loadAnnouncements().catch(handleError); },
  );
}

async function editAnnouncement(id) {
  const item = await api(`/admin/announcements/${id}`);
  state.announcement.editingId = item.id;
  qs("announcementTitleInput").value = item.title || "";
  qs("announcementEditorInput").innerHTML = item.content_html || "";
  qs("announcementPinnedInput").checked = !!item.is_pinned;
  qs("publishAnnouncementButton").textContent = "保存公告";
  navigateTo("announcements");
}

async function deleteAnnouncement(id) {
  if (!window.confirm("确认删除该公告？")) return;
  await api(`/admin/announcements/${id}`, { method: "DELETE" });
  if (state.announcement.editingId === id) clearAnnouncementEditor();
  await Promise.all([loadAnnouncements(), loadDashboard()]);
  showToast("公告已删除");
}

async function toggleAnnouncementPin(id) {
  const item = state.announcement.items.find((row) => row.id === id);
  if (!item) return;
  await api(`/admin/announcements/${id}`, {
    method: "PUT",
    body: JSON.stringify({
      title: item.title,
      content: (item.content || "").trim() || (item.summary || "").trim() || " ",
      content_html: item.content_html || item.content || item.summary || "",
      is_pinned: !item.is_pinned,
    }),
  });
  await loadAnnouncements();
}

function renderQuestionStats() {
  const stats = state.question.stats || {};
  qs("questionStatsView").innerHTML = `
    <div class="stat-card"><strong>当前总题目</strong><div>${stats.total || 0}</div></div>
    <div class="stat-card"><strong>已审核</strong><div>${stats.approved || 0}</div></div>
    <div class="stat-card"><strong>待审核</strong><div>${stats.pending || 0}</div></div>
    <div class="stat-card"><strong>其他状态</strong><div>${stats.rejected || 0}</div></div>
  `;
}

function statusBadge(status) {
  if (status === "approved") return `<span class="status-badge status-approved">已审核</span>`;
  if (status === "pending") return `<span class="status-badge status-pending">待审核</span>`;
  return `<span class="status-badge status-other">${escapeHtml(status || "未知")}</span>`;
}

function questionTypeText(type) {
  const map = { choice: "选择题", judgment: "判断题", blank: "填空题", solution: "解答题", steps: "分步题" };
  return map[type] || type || "-";
}

function renderQuestionTable() {
  const target = qs("questionTableBody");
  if (!state.question.items.length) {
    target.innerHTML = "<tr><td colspan='9' class='empty-state'>暂无题目</td></tr>";
    return;
  }
  target.innerHTML = state.question.items.map((item) => `
    <tr>
      <td><input type="checkbox" class="question-row-checkbox" data-question-id="${item.id}" ${state.question.selectedIds.has(item.id) ? "checked" : ""} style="width:auto;"></td>
      <td>${escapeHtml(item.subject)}</td>
      <td>${escapeHtml(item.grade_level)}</td>
      <td class="core-info"><strong>${escapeHtml(item.topic_name)}</strong><small>${escapeHtml(item.topic_id)}</small></td>
      <td>${escapeHtml(item.stem)}</td>
      <td>${escapeHtml(item.answer)}</td>
      <td>${Number(item.difficulty || 0).toFixed(2)}</td>
      <td>${statusBadge(item.status)}</td>
      <td>${questionTypeText(item.question_type)}</td>
    </tr>
  `).join("");
  document.querySelectorAll(".question-row-checkbox").forEach((box) => {
    box.addEventListener("change", () => {
      const id = Number(box.dataset.questionId);
      if (box.checked) state.question.selectedIds.add(id);
      else state.question.selectedIds.delete(id);
    });
  });
}

function renderQuestionCategoryTree() {
  const nodeButton = (node) => {
    if (node.level === 3) {
      const active = state.question.topicId === node.topic_ref_id ? "active" : "";
      return `<button class="category-item ${active}" data-category-topic-id="${escapeHtml(node.topic_ref_id || "")}" title="${escapeHtml(node.name)}">${escapeHtml(node.name)}（${node.question_count || 0}）</button>`;
    }
    if (node.level === 2) {
      const active = state.question.gradeLevel === node.grade_level && state.question.subject === node.subject ? "active" : "";
      return `<button class="category-item ${active}" data-category-subject="${escapeHtml(node.subject || "")}" data-category-grade="${escapeHtml(node.grade_level || "")}">${escapeHtml(node.name)}（${node.question_count || 0}）</button>`;
    }
    const active = state.question.subject === node.subject ? "active" : "";
    return `<button class="category-item ${active}" data-category-subject="${escapeHtml(node.subject || "")}">${escapeHtml(node.name)}（${node.question_count || 0}）</button>`;
  };
  const renderNode = (node) => `
    <details ${node.level <= 2 ? "open" : ""}>
      <summary>${escapeHtml(node.name)} <span>${node.question_count || 0}</span></summary>
      <div class="category-list">
        ${nodeButton(node)}
        ${(node.children || []).map((child) => renderNode(child)).join("")}
      </div>
    </details>
  `;
  qs("questionCategoryTree").innerHTML = (state.question.categories || []).map((node) => renderNode(node)).join("") || "<div class='empty-state'>暂无分类</div>";

  document.querySelectorAll("[data-category-topic-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.question.topicId = button.dataset.categoryTopicId || "";
      state.question.page = 1;
      loadQuestionBank().catch(handleError);
    });
  });
  document.querySelectorAll("[data-category-grade]").forEach((button) => {
    button.addEventListener("click", () => {
      state.question.topicId = "";
      state.question.subject = button.dataset.categorySubject || "";
      state.question.gradeLevel = button.dataset.categoryGrade || "";
      state.question.page = 1;
      loadQuestionBank().catch(handleError);
    });
  });
  document.querySelectorAll("[data-category-subject]:not([data-category-grade])").forEach((button) => {
    button.addEventListener("click", () => {
      state.question.topicId = "";
      state.question.subject = button.dataset.categorySubject || "";
      state.question.gradeLevel = "";
      state.question.page = 1;
      loadQuestionBank().catch(handleError);
    });
  });
}

async function loadQuestionBank() {
  if (!state.knowledge.activeTextbookId) return;
  const params = new URLSearchParams({
    q: state.question.q,
    topic_id: state.question.topicId,
    subject: state.question.subject,
    grade_level: state.question.gradeLevel,
    status: state.question.status,
    question_type: state.question.questionType,
    page: String(state.question.page),
    page_size: String(state.question.pageSize),
    textbook_id: String(state.knowledge.activeTextbookId),
  });
  const payload = await api(`/admin/question-bank/manage?${params.toString()}`);
  state.question.items = payload.items || [];
  state.question.total = payload.total || 0;
  state.question.totalPages = payload.total_pages || 1;
  state.question.stats = payload.stats || {};
  state.question.categories = payload.categories || [];
  state.question.selectedIds = new Set();
  qs("selectAllQuestionCheckbox").checked = false;
  renderQuestionStats();
  renderQuestionCategoryTree();
  renderQuestionTable();
  renderPagination(
    "questionPagination",
    state.question.page,
    state.question.totalPages,
    state.question.total,
    () => { state.question.page -= 1; loadQuestionBank().catch(handleError); },
    () => { state.question.page += 1; loadQuestionBank().catch(handleError); },
  );
}

async function questionBatch(action) {
  const ids = [...state.question.selectedIds];
  if (!ids.length) {
    showToast("请先选择题目");
    return;
  }
  await api("/admin/question-bank/batch", {
    method: "POST",
    body: JSON.stringify({ question_ids: ids, action }),
  });
  await Promise.all([loadQuestionBank(), loadDashboard()]);
  showToast("批量操作完成");
}

async function exportQuestionBank(filtered) {
  const payload = filtered ? {
    q: state.question.q,
    topic_id: state.question.topicId,
    subject: state.question.subject,
    grade_level: state.question.gradeLevel,
    status: state.question.status,
    question_type: state.question.questionType,
    textbook_id: state.knowledge.activeTextbookId,
  } : { textbook_id: state.knowledge.activeTextbookId };
  const headers = { "Content-Type": "application/json" };
  if (state.token) headers["X-Session-Token"] = state.token;
  const response = await fetch("/admin/question-bank/export", {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filtered ? "筛选题库.csv" : "全量题库.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function flattenKnowledgeTree(nodes) {
  const result = [];
  const queue = [...(nodes || [])];
  while (queue.length) {
    const node = queue.shift();
    result.push(node);
    (node.children || []).forEach((child) => queue.push(child));
  }
  return result;
}

function refreshKnowledgeParentOptions() {
  const level = Number(qs("knowledgeLevelInput").value || 3);
  const flat = flattenKnowledgeTree(state.knowledge.tree);
  const parentRows = flat.filter((item) => item.level === level - 1);
  const current = qs("knowledgeParentInput").value;
  const options = ["<option value=''>无</option>"].concat(
    parentRows.map((item) => `<option value="${escapeHtml(item.node_key)}">${escapeHtml(item.name)}</option>`)
  ).join("");
  qs("knowledgeParentInput").innerHTML = options;
  if (current && [...qs("knowledgeParentInput").options].some((item) => item.value === current)) {
    qs("knowledgeParentInput").value = current;
  }
  qs("knowledgeTopicRefInput").disabled = level !== 3;
}

function renderKnowledgeTree() {
  const renderNode = (node) => `
    <li>
      <div class="tree-row" draggable="true" data-node-key="${escapeHtml(node.node_key)}" data-parent-key="${escapeHtml(node.parent_node_key || "")}">
        <div class="left">
          <input type="checkbox" class="knowledge-select" data-node-key="${escapeHtml(node.node_key)}" style="width:auto;" ${state.knowledge.selectedNodeKeys.has(node.node_key) ? "checked" : ""}>
          <span class="drag-handle">⋮⋮</span>
          <div>
            <div class="node-title">${escapeHtml(node.name)}</div>
            <div class="node-meta">第 ${node.level} 级 · ${escapeHtml(node.subject || "-")} · ${escapeHtml(node.grade_level || "-")} · 题目 ${node.question_count || 0}</div>
          </div>
        </div>
        <div class="row-actions">
          <button class="btn btn-ghost btn-sm" data-edit-node-key="${escapeHtml(node.node_key)}">编辑</button>
          <button class="btn btn-danger btn-sm" data-delete-node-key="${escapeHtml(node.node_key)}">删除</button>
        </div>
      </div>
      ${(node.children || []).length ? `<ul>${node.children.map((child) => renderNode(child)).join("")}</ul>` : ""}
    </li>
  `;
  const target = qs("knowledgeTreeView");
  if (!state.knowledge.tree.length) {
    target.className = "empty-state";
    target.innerHTML = "暂无知识点";
    return;
  }
  target.className = "";
  target.innerHTML = `<ul>${state.knowledge.tree.map((item) => renderNode(item)).join("")}</ul>`;

  document.querySelectorAll(".knowledge-select").forEach((box) => {
    box.addEventListener("change", () => {
      const key = box.dataset.nodeKey;
      if (box.checked) state.knowledge.selectedNodeKeys.add(key);
      else state.knowledge.selectedNodeKeys.delete(key);
    });
  });
  document.querySelectorAll("[data-edit-node-key]").forEach((button) => {
    button.addEventListener("click", () => startEditKnowledgeNode(button.dataset.editNodeKey));
  });
  document.querySelectorAll("[data-delete-node-key]").forEach((button) => {
    button.addEventListener("click", () => deleteKnowledgeNode(button.dataset.deleteNodeKey).catch(handleError));
  });
  document.querySelectorAll(".tree-row").forEach((row) => {
    row.addEventListener("dragstart", () => {
      state.knowledge.dragNodeKey = row.dataset.nodeKey || "";
      state.knowledge.dragParentKey = row.dataset.parentKey || "";
    });
    row.addEventListener("dragover", (event) => {
      event.preventDefault();
    });
    row.addEventListener("drop", (event) => {
      event.preventDefault();
      reorderByDrop(row.dataset.nodeKey || "", row.dataset.parentKey || "").catch(handleError);
    });
  });
}

async function reorderByDrop(targetNodeKey, targetParentKey) {
  const dragNodeKey = state.knowledge.dragNodeKey;
  const dragParentKey = state.knowledge.dragParentKey;
  if (!dragNodeKey || !targetNodeKey || dragNodeKey === targetNodeKey) return;
  if ((dragParentKey || "") !== (targetParentKey || "")) {
    showToast("仅支持同级拖拽排序");
    return;
  }
  const rows = [...document.querySelectorAll(`.tree-row[data-parent-key="${CSS.escape(targetParentKey || "")}"]`)];
  const keys = rows.map((row) => row.dataset.nodeKey).filter(Boolean);
  const fromIndex = keys.indexOf(dragNodeKey);
  const toIndex = keys.indexOf(targetNodeKey);
  if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return;
  keys.splice(fromIndex, 1);
  keys.splice(toIndex, 0, dragNodeKey);
  await api("/admin/knowledge/nodes/reorder", {
    method: "POST",
    body: JSON.stringify({
      textbook_id: state.knowledge.activeTextbookId,
      parent_node_key: targetParentKey || null,
      ordered_node_keys: keys,
    }),
  });
  await loadKnowledgeTree();
}

async function loadKnowledgeTopicOptions() {
  state.knowledge.topicOptions = await api("/admin/knowledge/topic-options");
  const options = ["<option value=''>请选择</option>"].concat(
    state.knowledge.topicOptions.map((item) => `
      <option value="${escapeHtml(item.id)}">${escapeHtml(item.subject)} · ${escapeHtml(item.grade_level || "通用")} · ${escapeHtml(item.name)}</option>
    `)
  ).join("");
  qs("knowledgeTopicRefInput").innerHTML = options;
}

async function loadTextbooks() {
  state.knowledge.textbooks = await api("/admin/textbooks");
  if (!state.knowledge.textbooks.length) {
    state.knowledge.activeTextbookId = null;
    qs("textbookSelect").innerHTML = "<option value=''>暂无教材</option>";
    return;
  }
  const options = state.knowledge.textbooks.map((item) => `
    <option value="${item.id}">${escapeHtml(item.name)}${item.is_default ? "（默认）" : ""}</option>
  `).join("");
  qs("textbookSelect").innerHTML = options;
  if (!state.knowledge.activeTextbookId || !state.knowledge.textbooks.some((item) => item.id === Number(state.knowledge.activeTextbookId))) {
    state.knowledge.activeTextbookId = state.knowledge.textbooks[0].id;
  }
  qs("textbookSelect").value = String(state.knowledge.activeTextbookId);
}

async function createTextbook() {
  const name = qs("newTextbookNameInput").value.trim();
  if (!name) {
    showToast("请输入教材名称");
    return;
  }
  await api("/admin/textbooks", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  qs("newTextbookNameInput").value = "";
  await loadTextbooks();
  await Promise.all([loadKnowledgeTree(), loadQuestionBank()]);
  showToast("教材创建成功");
}

async function loadKnowledgeTree() {
  if (!state.knowledge.activeTextbookId) return;
  state.knowledge.tree = await api(`/admin/knowledge/tree?textbook_id=${state.knowledge.activeTextbookId}`);
  state.knowledge.selectedNodeKeys = new Set();
  renderKnowledgeTree();
  refreshKnowledgeParentOptions();
}

function getKnowledgeFormPayload() {
  const level = Number(qs("knowledgeLevelInput").value || 3);
  const name = qs("knowledgeNameInput").value.trim();
  const payload = {
    textbook_id: state.knowledge.activeTextbookId,
    level,
    name,
    parent_node_key: qs("knowledgeParentInput").value || null,
    subject: qs("knowledgeSubjectInput").value.trim(),
    grade_level: qs("knowledgeGradeInput").value.trim(),
    topic_ref_id: qs("knowledgeTopicRefInput").value || null,
  };
  if (!name) throw new Error("请填写知识点名称");
  if (level > 1 && !payload.parent_node_key) throw new Error("请选择父节点");
  if (level === 3 && !payload.topic_ref_id) throw new Error("三级知识点必须关联题库知识点");
  return payload;
}

function resetKnowledgeForm() {
  state.knowledge.editingNodeKey = null;
  qs("knowledgeLevelInput").value = "1";
  qs("knowledgeNameInput").value = "";
  qs("knowledgeSubjectInput").value = "";
  qs("knowledgeGradeInput").value = "";
  qs("knowledgeParentInput").value = "";
  qs("knowledgeTopicRefInput").value = "";
  qs("knowledgeFormHint").textContent = "支持拖拽同级节点排序";
  refreshKnowledgeParentOptions();
}

async function createKnowledgeNode() {
  const payload = getKnowledgeFormPayload();
  await api("/admin/knowledge/nodes", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  resetKnowledgeForm();
  await Promise.all([loadKnowledgeTree(), loadQuestionBank()]);
  showToast("知识点新增成功");
}

function startEditKnowledgeNode(nodeKey) {
  const node = flattenKnowledgeTree(state.knowledge.tree).find((item) => item.node_key === nodeKey);
  if (!node) return;
  state.knowledge.editingNodeKey = node.node_key;
  qs("knowledgeLevelInput").value = String(node.level);
  refreshKnowledgeParentOptions();
  qs("knowledgeParentInput").value = node.parent_node_key || "";
  qs("knowledgeNameInput").value = node.name || "";
  qs("knowledgeSubjectInput").value = node.subject || "";
  qs("knowledgeGradeInput").value = node.grade_level || "";
  qs("knowledgeTopicRefInput").value = node.topic_ref_id || "";
  qs("knowledgeFormHint").textContent = `正在编辑：${node.name}`;
}

async function updateKnowledgeNode() {
  if (!state.knowledge.editingNodeKey) {
    showToast("请先点击某个节点的编辑");
    return;
  }
  const payload = getKnowledgeFormPayload();
  await api(`/admin/knowledge/nodes/${encodeURIComponent(state.knowledge.editingNodeKey)}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  resetKnowledgeForm();
  await Promise.all([loadKnowledgeTree(), loadQuestionBank()]);
  showToast("知识点更新成功");
}

async function deleteKnowledgeNode(nodeKey) {
  const ok = window.confirm("确认删除该节点及其下级节点？");
  if (!ok) return;
  await api(`/admin/knowledge/nodes/${encodeURIComponent(nodeKey)}?textbook_id=${state.knowledge.activeTextbookId}`, {
    method: "DELETE",
  });
  resetKnowledgeForm();
  await Promise.all([loadKnowledgeTree(), loadQuestionBank()]);
  showToast("知识点删除成功");
}

async function batchDeleteKnowledgeNodes() {
  const nodeKeys = [...state.knowledge.selectedNodeKeys];
  if (!nodeKeys.length) {
    showToast("请先勾选知识点");
    return;
  }
  const ok = window.confirm(`确认批量删除 ${nodeKeys.length} 个节点？`);
  if (!ok) return;
  await api("/admin/knowledge/nodes/batch-delete", {
    method: "POST",
    body: JSON.stringify({
      textbook_id: state.knowledge.activeTextbookId,
      node_keys: nodeKeys,
    }),
  });
  resetKnowledgeForm();
  await Promise.all([loadKnowledgeTree(), loadQuestionBank()]);
  showToast("批量删除完成");
}

async function login() {
  const data = await api("/auth/login", {
    method: "POST",
    body: JSON.stringify({
      email: qs("loginEmail").value.trim(),
      password: qs("loginPassword").value,
    }),
  });
  if (data.user.role !== "admin") throw new Error("该账号不是管理员账号");
  state.token = data.token;
  state.user = data.user;
  localStorage.setItem("zhuyu_token", state.token);
  qs("authStatus").textContent = data.user.full_name;
  showAppMain();
  await bootstrapData();
}

function logout() {
  state.token = "";
  state.user = null;
  localStorage.removeItem("zhuyu_token");
  showLoginGate();
}
window.logout = logout;

async function bootstrapData() {
  await loadDashboard();
  await loadTextbooks();
  await loadKnowledgeTopicOptions();
  await Promise.all([loadTeachers(), loadAnnouncements(), loadKnowledgeTree(), loadQuestionBank()]);
  await loadAnnouncementDraft();
}

function handleError(err) {
  const text = (err && err.message) || "操作失败";
  showToast(text.replace(/^"|"$/g, ""));
}

function bindEvents() {
  qs("loginButton").addEventListener("click", () => login().catch(handleError));
  document.querySelectorAll(".nav-btn[data-page]").forEach((button) => {
    button.addEventListener("click", () => navigateTo(button.dataset.page));
  });

  qs("createTeacherButton").addEventListener("click", () => createTeacher().catch(handleError));
  qs("importTeacherButton").addEventListener("click", () => importTeacherCsv().catch(handleError));
  qs("downloadTeacherTemplateButton").addEventListener("click", downloadTeacherTemplate);
  qs("reloadTeachersButton").addEventListener("click", () => loadTeachers().catch(handleError));
  qs("searchTeacherButton").addEventListener("click", () => {
    state.teacher.q = qs("teacherKeywordInput").value.trim();
    state.teacher.page = 1;
    loadTeachers().catch(handleError);
  });
  qs("resetTeacherFilterButton").addEventListener("click", () => {
    qs("teacherKeywordInput").value = "";
    state.teacher.q = "";
    state.teacher.page = 1;
    loadTeachers().catch(handleError);
  });
  qs("teacherModeTableButton").addEventListener("click", () => {
    state.teacher.mode = "table";
    qs("teacherModeTableButton").classList.add("active");
    qs("teacherModeCardButton").classList.remove("active");
    renderTeacherList();
  });
  qs("teacherModeCardButton").addEventListener("click", () => {
    state.teacher.mode = "card";
    qs("teacherModeCardButton").classList.add("active");
    qs("teacherModeTableButton").classList.remove("active");
    renderTeacherList();
  });

  qs("copyPasswordButton").addEventListener("click", async () => {
    await navigator.clipboard.writeText(qs("passwordModalValue").textContent || "");
    showToast("已复制");
  });
  qs("closePasswordModalButton").addEventListener("click", hidePasswordModal);
  qs("passwordModal").addEventListener("click", (event) => {
    if (event.target === qs("passwordModal")) hidePasswordModal();
  });

  document.querySelectorAll("[data-editor-cmd]").forEach((button) => {
    button.addEventListener("click", () => {
      document.execCommand(button.dataset.editorCmd, false, null);
      scheduleDraftSave();
    });
  });
  qs("insertImageButton").addEventListener("click", () => {
    const url = window.prompt("请输入图片地址");
    if (!url) return;
    document.execCommand("insertImage", false, url);
    scheduleDraftSave();
  });
  qs("announcementTitleInput").addEventListener("input", scheduleDraftSave);
  qs("announcementEditorInput").addEventListener("input", scheduleDraftSave);
  qs("publishAnnouncementButton").addEventListener("click", () => publishAnnouncement().catch(handleError));
  qs("saveAnnouncementDraftButton").addEventListener("click", () => saveAnnouncementDraft().catch(handleError));
  qs("clearAnnouncementEditorButton").addEventListener("click", clearAnnouncementEditor);
  qs("searchAnnouncementButton").addEventListener("click", () => {
    state.announcement.q = qs("announcementKeywordInput").value.trim();
    state.announcement.page = 1;
    loadAnnouncements().catch(handleError);
  });
  qs("resetAnnouncementFilterButton").addEventListener("click", () => {
    qs("announcementKeywordInput").value = "";
    state.announcement.q = "";
    state.announcement.page = 1;
    loadAnnouncements().catch(handleError);
  });
  qs("reloadAnnouncementsButton").addEventListener("click", () => loadAnnouncements().catch(handleError));
  qs("toggleEditorButton").addEventListener("click", () => {
    state.announcement.editorCollapsed = !state.announcement.editorCollapsed;
    qs("announcementEditorPanel").classList.toggle("collapsed", state.announcement.editorCollapsed);
    qs("toggleEditorButton").textContent = state.announcement.editorCollapsed ? "展开编辑区" : "折叠编辑区";
  });

  qs("searchQuestionButton").addEventListener("click", () => {
    state.question.q = qs("questionKeywordInput").value.trim();
    state.question.status = qs("questionStatusFilter").value;
    state.question.questionType = qs("questionTypeFilter").value;
    state.question.page = 1;
    loadQuestionBank().catch(handleError);
  });
  qs("resetQuestionFilterButton").addEventListener("click", () => {
    qs("questionKeywordInput").value = "";
    qs("questionStatusFilter").value = "";
    qs("questionTypeFilter").value = "";
    state.question.q = "";
    state.question.topicId = "";
    state.question.subject = "";
    state.question.gradeLevel = "";
    state.question.status = "";
    state.question.questionType = "";
    state.question.page = 1;
    loadQuestionBank().catch(handleError);
  });
  qs("clearQuestionCategoryButton").addEventListener("click", () => {
    state.question.topicId = "";
    state.question.subject = "";
    state.question.gradeLevel = "";
    state.question.page = 1;
    loadQuestionBank().catch(handleError);
  });
  qs("batchApproveQuestionButton").addEventListener("click", () => questionBatch("approve").catch(handleError));
  qs("batchPendingQuestionButton").addEventListener("click", () => questionBatch("reject").catch(handleError));
  qs("batchDeleteQuestionButton").addEventListener("click", () => questionBatch("delete").catch(handleError));
  qs("exportQuestionAllButton").addEventListener("click", () => exportQuestionBank(false).catch(handleError));
  qs("exportQuestionFilteredButton").addEventListener("click", () => exportQuestionBank(true).catch(handleError));
  qs("selectAllQuestionCheckbox").addEventListener("change", () => {
    state.question.selectedIds = new Set();
    document.querySelectorAll(".question-row-checkbox").forEach((box) => {
      box.checked = qs("selectAllQuestionCheckbox").checked;
      if (box.checked) state.question.selectedIds.add(Number(box.dataset.questionId));
    });
  });

  qs("textbookSelect").addEventListener("change", () => {
    state.knowledge.activeTextbookId = Number(qs("textbookSelect").value || 0) || null;
    Promise.all([loadKnowledgeTree(), loadQuestionBank()]).catch(handleError);
  });
  qs("createTextbookButton").addEventListener("click", () => createTextbook().catch(handleError));
  qs("reloadKnowledgeButton").addEventListener("click", () => Promise.all([loadKnowledgeTree(), loadQuestionBank()]).catch(handleError));
  qs("knowledgeLevelInput").addEventListener("change", refreshKnowledgeParentOptions);
  qs("createKnowledgeNodeButton").addEventListener("click", () => createKnowledgeNode().catch(handleError));
  qs("updateKnowledgeNodeButton").addEventListener("click", () => updateKnowledgeNode().catch(handleError));
  qs("resetKnowledgeFormButton").addEventListener("click", resetKnowledgeForm);
  qs("batchDeleteKnowledgeNodeButton").addEventListener("click", () => batchDeleteKnowledgeNodes().catch(handleError));
}

async function bootstrap() {
  bindEvents();
  if (!state.token) return;
  try {
    state.user = await api("/auth/me");
    if (state.user.role !== "admin") throw new Error("not admin");
    qs("authStatus").textContent = state.user.full_name;
    showAppMain();
    await bootstrapData();
  } catch {
    localStorage.removeItem("zhuyu_token");
    state.token = "";
    showLoginGate();
  }
}

bootstrap().catch(handleError);
