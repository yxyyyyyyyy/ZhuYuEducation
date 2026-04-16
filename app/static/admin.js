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
    subject: "",
    gradeLevel: "",
    textbookId: null,
    knowledgeL1Id: "",
    knowledgeL2Id: "",
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
    selectedNodeKeys: new Set(),
    editingNodeKey: null,
    dragNodeKey: "",
    dragParentKey: "",
    gradeFilter: "",
    subjectFilter: "",
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
      <div class="summary">${item.content_html || escapeHtml(item.summary || "")}</div>
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
    target.innerHTML = "<tr><td colspan='10' class='empty-state'>暂无题目</td></tr>";
    return;
  }
  target.innerHTML = state.question.items.map((item) => {
    const tierTags = item.knowledge_tiers || [];
    const tagsHtml = tierTags.length
      ? tierTags.map((t) => `<span style=\"display:inline-block;background:#e8efff;color:#1456f0;border-radius:4px;padding:1px 6px;font-size:11px;margin-right:3px;\">${escapeHtml(t)}</span>`).join("")
      : "<span style='color:#8f959e'>-</span>";
    return `
    <tr>
      <td><input type="checkbox" class="question-row-checkbox" data-question-id="${item.id}" ${state.question.selectedIds.has(item.id) ? "checked" : ""} style="width:auto;"></td>
      <td>${escapeHtml(item.grade_level)}</td>
      <td>${escapeHtml(item.subject)}</td>
      <td class="core-info"><strong>${escapeHtml(item.topic_name)}</strong><small>${escapeHtml(item.knowledge_l2_id || item.topic_id)}</small></td>
      <td>${tagsHtml}</td>
      <td>${escapeHtml(item.stem)}</td>
      <td>${escapeHtml(item.answer)}</td>
      <td>L${Number(item.difficulty_level || 3)}</td>
      <td>${statusBadge(item.status)}</td>
      <td>${questionTypeText(item.question_type)}</td>
    </tr>
  `;
  }).join("");
  document.querySelectorAll(".question-row-checkbox").forEach((box) => {
    box.addEventListener("change", () => {
      const id = Number(box.dataset.questionId);
      if (box.checked) state.question.selectedIds.add(id);
      else state.question.selectedIds.delete(id);
    });
  });
}

function openCategoryDrawer() {
  qs("categoryDrawerMask").classList.add("show");
  qs("categoryDrawer").classList.add("show");
}

function closeCategoryDrawer() {
  qs("categoryDrawerMask").classList.remove("show");
  qs("categoryDrawer").classList.remove("show");
}

function isQuestionTextbookScope() {
  return !!state.question.textbookId;
}

function flattenQuestionCategories(nodes) {
  const result = [];
  const queue = [...(nodes || [])];
  while (queue.length) {
    const node = queue.shift();
    if (!node) continue;
    result.push(node);
    (node.children || []).forEach((child) => queue.push(child));
  }
  return result;
}

function questionCategoryNameByKey(nodeKey) {
  if (!nodeKey) return "";
  const node = flattenQuestionCategories(state.question.categories).find(
    (item) => (item.node_key || item.topic_ref_id || item.id || "") === nodeKey,
  );
  return node ? node.name : nodeKey;
}

function renderQuestionCategoryTags() {
  const categories = state.question.categories || [];
  const target = qs("questionCategoryTags");
  if (!categories.length) {
    target.innerHTML = "";
    return;
  }
  if (isQuestionTextbookScope()) {
    target.innerHTML = categories.map((node) => {
      const l1Id = node.node_key || node.id || "";
      const active = state.question.knowledgeL1Id === l1Id && !state.question.knowledgeL2Id ? "active" : "";
      return `<button class="category-tag ${active}" data-tag-l1-id="${escapeHtml(l1Id)}">${escapeHtml(node.name)}<span class="count">（${node.question_count || 0}）</span></button>`;
    }).join("");
    target.querySelectorAll("[data-tag-l1-id]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const l1Id = btn.dataset.tagL1Id || "";
        if (state.question.knowledgeL1Id === l1Id && !state.question.knowledgeL2Id) {
          state.question.knowledgeL1Id = "";
        } else {
          state.question.knowledgeL1Id = l1Id;
        }
        state.question.knowledgeL2Id = "";
        state.question.page = 1;
        loadQuestionBank().catch(handleError);
      });
    });
    return;
  }

  target.innerHTML = categories.map((node) => {
    const subject = node.subject || "";
    const active = state.question.subject === subject && !state.question.gradeLevel ? "active" : "";
    return `<button class="category-tag ${active}" data-tag-subject="${escapeHtml(subject)}">${escapeHtml(node.name)}<span class="count">（${node.question_count || 0}）</span></button>`;
  }).join("");
  target.querySelectorAll("[data-tag-subject]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const subject = btn.dataset.tagSubject || "";
      state.question.textbookId = null;
      if (state.question.subject === subject && !state.question.gradeLevel) {
        state.question.subject = "";
      } else {
        state.question.subject = subject;
      }
      state.question.gradeLevel = "";
      state.question.knowledgeL1Id = "";
      state.question.knowledgeL2Id = "";
      state.question.page = 1;
      refreshQuestionScopeFilters();
      loadQuestionBank().catch(handleError);
    });
  });
}

function renderCategoryDrawerContent() {
  const categories = state.question.categories || [];
  const body = qs("categoryDrawerBody");
  if (!categories.length) {
    body.innerHTML = "<div class='empty-state'>暂无分类</div>";
    return;
  }
  const activeSubject = state.question.subject;
  const activeGrade = state.question.gradeLevel;
  const activeL1 = state.question.knowledgeL1Id;
  const activeL2 = state.question.knowledgeL2Id;
  const textbookScope = isQuestionTextbookScope();
  let html = "";
  categories.forEach((node) => {
    html += `<div class="drawer-section">`;
    if (textbookScope) {
      const l1Id = node.node_key || node.id || "";
      const l1Active = activeL1 === l1Id && !activeL2 ? "active" : "";
      html += `<button class="drawer-item ${l1Active}" data-drawer-l1-id="${escapeHtml(l1Id)}">${escapeHtml(node.name)}<span class="count">${node.question_count || 0}</span></button>`;
      if (node.children && node.children.length) {
        html += `<div class="drawer-sub-list">`;
        node.children.forEach((leaf) => {
          const l2Id = leaf.topic_ref_id || leaf.node_key || leaf.id || "";
          const leafActive = activeL2 === l2Id ? "active" : "";
          html += `<button class="drawer-item ${leafActive}" data-drawer-l2-id="${escapeHtml(l2Id)}" data-drawer-l1-id="${escapeHtml(l1Id)}">${escapeHtml(leaf.name)}<span class="count">${leaf.question_count || 0}</span></button>`;
        });
        html += `</div>`;
      }
    } else {
      const subject = node.subject || "";
      const subjectActive = activeSubject === subject && !activeGrade ? "active" : "";
      html += `<button class="drawer-item ${subjectActive}" data-drawer-subject="${escapeHtml(subject)}">${escapeHtml(node.name)}<span class="count">${node.question_count || 0}</span></button>`;
      if (node.children && node.children.length) {
        html += `<div class="drawer-sub-list">`;
        node.children.forEach((gradeNode) => {
          const grade = gradeNode.grade_level || "";
          const gradeActive = activeSubject === subject && activeGrade === grade ? "active" : "";
          html += `<button class="drawer-item ${gradeActive}" data-drawer-subject="${escapeHtml(subject)}" data-drawer-grade="${escapeHtml(grade)}">${escapeHtml(gradeNode.name)}<span class="count">${gradeNode.question_count || 0}</span></button>`;
        });
        html += `</div>`;
      }
    }
    html += `</div>`;
  });
  body.innerHTML = html;

  if (textbookScope) {
    body.querySelectorAll("[data-drawer-l2-id]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.question.knowledgeL1Id = btn.dataset.drawerL1Id || "";
        state.question.knowledgeL2Id = btn.dataset.drawerL2Id || "";
        state.question.page = 1;
        closeCategoryDrawer();
        loadQuestionBank().catch(handleError);
      });
    });
    body.querySelectorAll("[data-drawer-l1-id]:not([data-drawer-l2-id])").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.question.knowledgeL1Id = btn.dataset.drawerL1Id || "";
        state.question.knowledgeL2Id = "";
        state.question.page = 1;
        closeCategoryDrawer();
        loadQuestionBank().catch(handleError);
      });
    });
    return;
  }

  body.querySelectorAll("[data-drawer-grade]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.question.textbookId = null;
      state.question.subject = btn.dataset.drawerSubject || "";
      state.question.gradeLevel = btn.dataset.drawerGrade || "";
      state.question.knowledgeL1Id = "";
      state.question.knowledgeL2Id = "";
      state.question.page = 1;
      refreshQuestionScopeFilters();
      closeCategoryDrawer();
      loadQuestionBank().catch(handleError);
    });
  });
  body.querySelectorAll("[data-drawer-subject]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.question.textbookId = null;
      state.question.subject = btn.dataset.drawerSubject || "";
      state.question.gradeLevel = "";
      state.question.knowledgeL1Id = "";
      state.question.knowledgeL2Id = "";
      state.question.page = 1;
      refreshQuestionScopeFilters();
      closeCategoryDrawer();
      loadQuestionBank().catch(handleError);
    });
  });
}

function renderQuestionCurrentFilter() {
  const el = qs("questionCurrentFilter");
  const parts = [];
  if (state.question.textbookId) {
    const textbook = state.knowledge.textbooks.find((item) => item.id === Number(state.question.textbookId));
    parts.push(`教材：${textbook ? textbook.name : state.question.textbookId}`);
  } else {
    parts.push("教材：全教材");
  }
  if (state.question.subject) parts.push(`学科：${state.question.subject}`);
  if (state.question.gradeLevel) parts.push(`年级：${state.question.gradeLevel}`);
  if (state.question.knowledgeL1Id) parts.push(`一级知识点：${questionCategoryNameByKey(state.question.knowledgeL1Id)}`);
  if (state.question.knowledgeL2Id) parts.push(`二级知识点：${questionCategoryNameByKey(state.question.knowledgeL2Id)}`);
  el.textContent = parts.length ? `当前筛选：${parts.join(" / ")}` : "";
}

async function loadQuestionBank() {
  const params = new URLSearchParams({
    q: state.question.q,
    knowledge_l1_id: state.question.knowledgeL1Id,
    knowledge_l2_id: state.question.knowledgeL2Id,
    topic_id: state.question.knowledgeL2Id,
    subject: state.question.subject,
    grade_level: state.question.gradeLevel,
    status: state.question.status,
    question_type: state.question.questionType,
    page: String(state.question.page),
    page_size: String(state.question.pageSize),
  });
  if (state.question.textbookId) {
    params.set("textbook_id", String(state.question.textbookId));
  }
  const payload = await api(`/admin/question-bank/manage?${params.toString()}`);
  state.question.items = payload.items || [];
  state.question.total = payload.total || 0;
  state.question.totalPages = payload.total_pages || 1;
  state.question.stats = payload.stats || {};
  state.question.categories = payload.categories || [];
  state.question.selectedIds = new Set();
  qs("selectAllQuestionCheckbox").checked = false;
  renderQuestionStats();
  renderQuestionCategoryTags();
  renderCategoryDrawerContent();
  renderQuestionCurrentFilter();
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
    knowledge_l1_id: state.question.knowledgeL1Id,
    knowledge_l2_id: state.question.knowledgeL2Id,
    topic_id: state.question.knowledgeL2Id,
    subject: state.question.subject,
    grade_level: state.question.gradeLevel,
    status: state.question.status,
    question_type: state.question.questionType,
    textbook_id: state.question.textbookId,
  } : { textbook_id: state.question.textbookId };
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
  const parentRows = (state.knowledge.tree || []).filter((item) => item.level === 1);
  const current = qs("knowledgeParentInput").value;
  const options = ["<option value=''>请选择一级知识点</option>"].concat(
    parentRows.map((item) => `<option value="${escapeHtml(item.node_key)}">${escapeHtml(item.name)}</option>`)
  ).join("");
  qs("knowledgeParentInput").innerHTML = options;
  if (current && [...qs("knowledgeParentInput").options].some((item) => item.value === current)) {
    qs("knowledgeParentInput").value = current;
  } else if (parentRows.length) {
    qs("knowledgeParentInput").value = parentRows[0].node_key;
  }
}

function renderKnowledgeTree() {
  const renderNode = (node) => {
    const isLevel1 = node.level === 1;
    return `
    <li>
      <div class="tree-row" draggable="true" data-node-key="${escapeHtml(node.node_key)}" data-parent-key="${escapeHtml(node.parent_node_key || "")}">
        <div class="left">
          <input type="checkbox" class="knowledge-select" data-node-key="${escapeHtml(node.node_key)}" style="width:auto;" ${state.knowledge.selectedNodeKeys.has(node.node_key) ? "checked" : ""}>
          <span class="drag-handle">⋮⋮</span>
          <div>
            <div class="node-title">${isLevel1 ? "📚 " : "· "}${escapeHtml(node.name)}</div>
            <div class="node-meta">${isLevel1 ? "一级大知识点" : `二级小知识点 · 题目 ${node.question_count || 0}`}</div>
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
  };
  const target = qs("knowledgeTreeView");
  if (!state.knowledge.tree.length) {
    target.className = "empty-state";
    target.innerHTML = "暂无知识点，请先选择教材后新增";
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

async function loadTextbooks() {
  state.knowledge.textbooks = await api("/admin/textbooks");
  if (!state.knowledge.textbooks.length) {
    state.knowledge.activeTextbookId = null;
    state.question.textbookId = null;
    state.question.subject = "";
    state.question.gradeLevel = "";
    qs("textbookGradeFilter").innerHTML = "<option value=''>选择年级</option>";
    qs("textbookSubjectFilter").innerHTML = "<option value=''>选择学科</option>";
    qs("textbookSelect").innerHTML = "<option value=''>暂无教材</option>";
    qs("questionGradeFilter").innerHTML = "<option value=''>全部年级</option>";
    qs("questionSubjectFilter").innerHTML = "<option value=''>全部学科</option>";
    qs("questionTextbookFilter").innerHTML = "<option value=''>全部教材（跨学科）</option>";
    return;
  }
  const grades = [...new Set(state.knowledge.textbooks.map((t) => t.grade_level).filter(Boolean))].sort();
  qs("textbookGradeFilter").innerHTML = "<option value=''>选择年级</option>" + grades.map((g) => `<option value="${escapeHtml(g)}">${escapeHtml(g)}</option>`).join("");
  if (state.knowledge.gradeFilter && grades.includes(state.knowledge.gradeFilter)) {
    qs("textbookGradeFilter").value = state.knowledge.gradeFilter;
  } else {
    state.knowledge.gradeFilter = "";
  }
  refreshSubjectFilter();
  refreshTextbookSelect();
  refreshQuestionScopeFilters();
}

function refreshSubjectFilter() {
  const grade = state.knowledge.gradeFilter;
  const filtered = grade ? state.knowledge.textbooks.filter((t) => t.grade_level === grade) : state.knowledge.textbooks;
  const subjects = [...new Set(filtered.map((t) => t.subject).filter(Boolean))].sort();
  qs("textbookSubjectFilter").innerHTML = "<option value=''>选择学科</option>" + subjects.map((s) => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join("");
  if (state.knowledge.subjectFilter && subjects.includes(state.knowledge.subjectFilter)) {
    qs("textbookSubjectFilter").value = state.knowledge.subjectFilter;
  } else {
    state.knowledge.subjectFilter = "";
  }
}

function refreshTextbookSelect() {
  const grade = state.knowledge.gradeFilter;
  const subject = state.knowledge.subjectFilter;
  let filtered = state.knowledge.textbooks;
  if (grade) filtered = filtered.filter((t) => t.grade_level === grade);
  if (subject) filtered = filtered.filter((t) => t.subject === subject);
  qs("textbookSelect").innerHTML = filtered.length
    ? filtered.map((item) => `<option value="${item.id}">${escapeHtml(item.grade_level || "通用")} · ${escapeHtml(item.subject || "综合")} · ${escapeHtml(item.name)}${item.is_default ? "（默认）" : ""}</option>`).join("")
    : "<option value=''>无匹配教材</option>";
  if (filtered.length) {
    if (!state.knowledge.activeTextbookId || !filtered.some((item) => item.id === Number(state.knowledge.activeTextbookId))) {
      const defaultBook = filtered.find((item) => item.is_default) || filtered[0];
      state.knowledge.activeTextbookId = defaultBook.id;
    }
    qs("textbookSelect").value = String(state.knowledge.activeTextbookId);
  } else {
    state.knowledge.activeTextbookId = null;
  }
}

function refreshQuestionScopeFilters() {
  refreshQuestionGradeFilterOptions();
  refreshQuestionSubjectFilterOptions();
  refreshQuestionTextbookFilterOptions();
}

function refreshQuestionGradeFilterOptions() {
  const grades = [...new Set(state.knowledge.textbooks.map((item) => item.grade_level).filter(Boolean))].sort();
  qs("questionGradeFilter").innerHTML = "<option value=''>全部年级</option>" + grades.map((grade) => `<option value="${escapeHtml(grade)}">${escapeHtml(grade)}</option>`).join("");
  if (state.question.gradeLevel && grades.includes(state.question.gradeLevel)) {
    qs("questionGradeFilter").value = state.question.gradeLevel;
    return;
  }
  state.question.gradeLevel = "";
}

function refreshQuestionSubjectFilterOptions() {
  const grade = state.question.gradeLevel;
  const filtered = grade
    ? state.knowledge.textbooks.filter((item) => item.grade_level === grade)
    : state.knowledge.textbooks;
  const subjects = [...new Set(filtered.map((item) => item.subject).filter(Boolean))].sort();
  qs("questionSubjectFilter").innerHTML = "<option value=''>全部学科</option>" + subjects.map((subject) => `<option value="${escapeHtml(subject)}">${escapeHtml(subject)}</option>`).join("");
  if (state.question.subject && subjects.includes(state.question.subject)) {
    qs("questionSubjectFilter").value = state.question.subject;
    return;
  }
  state.question.subject = "";
}

function refreshQuestionTextbookFilterOptions() {
  const grade = state.question.gradeLevel;
  const subject = state.question.subject;
  let filtered = state.knowledge.textbooks;
  if (grade) filtered = filtered.filter((item) => item.grade_level === grade);
  if (subject) filtered = filtered.filter((item) => item.subject === subject);
  const options = ["<option value=''>全部教材（跨学科）</option>"];
  options.push(...filtered.map((item) => `<option value="${item.id}">${escapeHtml(item.grade_level || "通用")} · ${escapeHtml(item.subject || "综合")} · ${escapeHtml(item.name)}${item.is_default ? "（默认）" : ""}</option>`));
  qs("questionTextbookFilter").innerHTML = options.join("");
  if (state.question.textbookId && filtered.some((item) => item.id === Number(state.question.textbookId))) {
    qs("questionTextbookFilter").value = String(state.question.textbookId);
    return;
  }
  state.question.textbookId = null;
  qs("questionTextbookFilter").value = "";
}

async function createTextbook() {
  const name = qs("newTextbookNameInput").value.trim();
  const gradeLevel = qs("newTextbookGradeInput").value.trim();
  const subject = qs("newTextbookSubjectInput").value.trim();
  if (!name) {
    showToast("请输入教材名称");
    return;
  }
  if (!gradeLevel) {
    showToast("请输入教材年级");
    return;
  }
  if (!subject) {
    showToast("请输入教材学科");
    return;
  }
  await api("/admin/textbooks", {
    method: "POST",
    body: JSON.stringify({ name, grade_level: gradeLevel, subject }),
  });
  qs("newTextbookNameInput").value = "";
  qs("newTextbookGradeInput").value = "";
  qs("newTextbookSubjectInput").value = "";
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
  const name = qs("knowledgeNameInput").value.trim();
  const level = Number(qs("knowledgeLevelInput").value || 1);
  const parentNodeKey = qs("knowledgeParentInput").value || null;
  const payload = {
    textbook_id: state.knowledge.activeTextbookId,
    level,
    name,
    parent_node_key: level === 2 ? parentNodeKey : null,
  };
  if (!name) throw new Error("请填写知识点名称");
  if (level === 2 && !payload.parent_node_key) throw new Error("请选择一级知识点");
  return payload;
}

function resetKnowledgeForm() {
  state.knowledge.editingNodeKey = null;
  qs("knowledgeLevelInput").value = "1";
  qs("knowledgeNameInput").value = "";
  qs("knowledgeParentInput").value = "";
  qs("knowledgeFormHint").textContent = "先建一级大知识点，再在其下创建二级小知识点。";
  refreshKnowledgeParentOptions();
  updateKnowledgeParentVisibility();
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
  refreshKnowledgeParentOptions();
  qs("knowledgeLevelInput").value = String(node.level || 1);
  qs("knowledgeParentInput").value = node.parent_node_key || "";
  qs("knowledgeNameInput").value = node.name || "";
  updateKnowledgeParentVisibility();
  qs("knowledgeFormHint").textContent = `正在编辑：${node.name}`;
}

function updateKnowledgeParentVisibility() {
  const level = Number(qs("knowledgeLevelInput").value || 1);
  qs("knowledgeParentInput").disabled = level !== 2;
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
      const value = button.dataset.editorValue || null;
      document.execCommand(button.dataset.editorCmd, false, value);
      scheduleDraftSave();
    });
  });
  qs("insertImageButton").addEventListener("click", () => {
    const url = window.prompt("请输入图片地址");
    if (!url) return;
    document.execCommand("insertImage", false, url);
    scheduleDraftSave();
  });
  qs("insertLinkButton").addEventListener("click", () => {
    const url = window.prompt("请输入链接地址", "https://");
    if (!url) return;
    document.execCommand("createLink", false, url);
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
    state.question.knowledgeL1Id = "";
    state.question.knowledgeL2Id = "";
    state.question.subject = "";
    state.question.gradeLevel = "";
    state.question.textbookId = null;
    state.question.status = "";
    state.question.questionType = "";
    state.question.page = 1;
    refreshQuestionScopeFilters();
    loadQuestionBank().catch(handleError);
  });
  qs("clearQuestionCategoryButton").addEventListener("click", () => {
    state.question.knowledgeL1Id = "";
    state.question.knowledgeL2Id = "";
    if (!isQuestionTextbookScope()) {
      state.question.subject = "";
      state.question.gradeLevel = "";
      refreshQuestionScopeFilters();
    }
    state.question.page = 1;
    loadQuestionBank().catch(handleError);
  });
  qs("reloadQuestionBankButton").addEventListener("click", () => loadQuestionBank().catch(handleError));
  qs("openCategoryDrawerButton").addEventListener("click", () => {
    renderCategoryDrawerContent();
    openCategoryDrawer();
  });
  qs("closeCategoryDrawerButton").addEventListener("click", closeCategoryDrawer);
  qs("categoryDrawerMask").addEventListener("click", closeCategoryDrawer);
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
  qs("questionGradeFilter").addEventListener("change", () => {
    state.question.gradeLevel = qs("questionGradeFilter").value;
    state.question.subject = "";
    state.question.textbookId = null;
    state.question.knowledgeL1Id = "";
    state.question.knowledgeL2Id = "";
    state.question.page = 1;
    refreshQuestionSubjectFilterOptions();
    refreshQuestionTextbookFilterOptions();
    loadQuestionBank().catch(handleError);
  });
  qs("questionSubjectFilter").addEventListener("change", () => {
    state.question.subject = qs("questionSubjectFilter").value;
    state.question.textbookId = null;
    state.question.knowledgeL1Id = "";
    state.question.knowledgeL2Id = "";
    state.question.page = 1;
    refreshQuestionTextbookFilterOptions();
    loadQuestionBank().catch(handleError);
  });
  qs("questionTextbookFilter").addEventListener("change", () => {
    state.question.textbookId = Number(qs("questionTextbookFilter").value || 0) || null;
    if (state.question.textbookId) {
      const textbook = state.knowledge.textbooks.find((item) => item.id === Number(state.question.textbookId));
      if (textbook) {
        state.question.gradeLevel = textbook.grade_level || "";
        state.question.subject = textbook.subject || "";
      }
    }
    state.question.knowledgeL1Id = "";
    state.question.knowledgeL2Id = "";
    state.question.page = 1;
    refreshQuestionScopeFilters();
    loadQuestionBank().catch(handleError);
  });

  qs("textbookGradeFilter").addEventListener("change", () => {
    state.knowledge.gradeFilter = qs("textbookGradeFilter").value;
    state.knowledge.subjectFilter = "";
    refreshSubjectFilter();
    refreshTextbookSelect();
    loadKnowledgeTree().catch(handleError);
  });
  qs("textbookSubjectFilter").addEventListener("change", () => {
    state.knowledge.subjectFilter = qs("textbookSubjectFilter").value;
    refreshTextbookSelect();
    loadKnowledgeTree().catch(handleError);
  });
  qs("textbookSelect").addEventListener("change", () => {
    state.knowledge.activeTextbookId = Number(qs("textbookSelect").value || 0) || null;
    loadKnowledgeTree().catch(handleError);
  });
  qs("createTextbookButton").addEventListener("click", () => createTextbook().catch(handleError));
  qs("reloadKnowledgeButton").addEventListener("click", () => loadKnowledgeTree().catch(handleError));
  qs("knowledgeLevelInput").addEventListener("change", updateKnowledgeParentVisibility);
  qs("createKnowledgeNodeButton").addEventListener("click", () => createKnowledgeNode().catch(handleError));
  qs("updateKnowledgeNodeButton").addEventListener("click", () => updateKnowledgeNode().catch(handleError));
  qs("resetKnowledgeFormButton").addEventListener("click", resetKnowledgeForm);
  qs("batchDeleteKnowledgeNodeButton").addEventListener("click", () => batchDeleteKnowledgeNodes().catch(handleError));
  updateKnowledgeParentVisibility();
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
