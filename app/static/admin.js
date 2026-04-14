const state = {
  token: localStorage.getItem("zhuyu_token") || "",
  user: null,
  topics: [],
};

function qs(id) {
  return document.getElementById(id);
}

function showToast(text) {
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = text;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 2000);
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers["X-Session-Token"] = state.token;
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
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
  document.querySelectorAll(".nav-btn[data-page]").forEach((item) => {
    item.classList.toggle("active", item.dataset.page === page);
  });
  document.querySelectorAll(".page").forEach((section) => {
    section.classList.toggle("active", section.dataset.page === page);
  });
}

function renderDashboard(data) {
  qs("schoolNameView").textContent = `${data.school.name}${data.school.region ? ` · ${data.school.region}` : ""}`;
  qs("adminSummaryView").innerHTML = `
    <div class="stat-card"><strong>教师</strong><div>${data.teacher_count}</div></div>
    <div class="stat-card"><strong>班级</strong><div>${data.classroom_count}</div></div>
    <div class="stat-card"><strong>学生</strong><div>${data.student_count}</div></div>
    <div class="stat-card"><strong>题目</strong><div>${data.question_count}</div></div>
    <div class="stat-card"><strong>公告</strong><div>${data.announcement_count}</div></div>
  `;
}

function renderTeachers(items) {
  qs("teacherListView").className = items.length ? "timeline" : "timeline empty-state";
  qs("teacherListView").innerHTML = items.length ? items.map((item) => `
    <article class="timeline-item">
      <strong>${item.full_name}</strong>
      <div>${item.email}</div>
      <small>教师 ID：${item.id}</small>
    </article>
  `).join("") : "暂无教师账号";
}

function renderAnnouncements(items) {
  qs("announcementListView").className = items.length ? "timeline" : "timeline empty-state";
  qs("announcementListView").innerHTML = items.length ? items.map((item) => `
    <article class="timeline-item">
      <strong>${item.title}</strong>
      <div>${item.content}</div>
      <small>${new Date(item.created_at).toLocaleString("zh-CN", { hour12: false })}</small>
    </article>
  `).join("") : "暂无公告";
}

function renderQuestionBank(items) {
  const topicMap = {};
  state.topics.forEach((topic) => { topicMap[topic.id] = topic; });
  qs("questionBankView").className = items.length ? "timeline" : "timeline empty-state";
  qs("questionBankView").innerHTML = items.length ? items.slice(0, 120).map((item) => {
    const topic = topicMap[item.topic_id] || {};
    return `
      <article class="timeline-item">
        <strong>${topic.subject || "未分类"} · ${topic.grade_level || "通用"} · ${topic.name || item.topic_id}</strong>
        <div>${item.stem}</div>
        <small>${item.question_type} · 难度 ${Math.round(item.difficulty * 100)} · ${item.status}</small>
      </article>
    `;
  }).join("") : "题库为空";
}

function renderTreeNode(node) {
  const open = node.level <= 1 ? " open" : "";
  return `
    <details class="admin-tree-node"${open}>
      <summary>
        <span class="tree-toggle">展开/收起</span>
        <strong>${node.name}</strong>
        <span>${node.grade_level || "总览"} · ${node.question_count} 题</span>
      </summary>
      <div class="admin-tree-children">
        ${(node.children || []).map(renderTreeNode).join("") || "<div class='empty-state'>暂无下级知识点</div>"}
      </div>
    </details>
  `;
}

function renderKnowledgeTree(items) {
  qs("knowledgeTreeView").className = "knowledge-tree-admin";
  qs("knowledgeTreeView").innerHTML = items.map(renderTreeNode).join("");
}

async function loadDashboard() {
  renderDashboard(await api("/admin/dashboard"));
}

async function loadTeachers() {
  renderTeachers(await api("/admin/teachers"));
}

async function loadAnnouncements() {
  renderAnnouncements(await api("/admin/announcements"));
}

async function loadQuestionBank() {
  state.topics = await api("/graph/topics");
  renderQuestionBank(await api("/admin/question-bank"));
}

async function loadKnowledgeTree() {
  renderKnowledgeTree(await api("/admin/knowledge-tree"));
}

async function createTeacher() {
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
  await loadTeachers();
  await loadDashboard();
  showToast("教师账号已创建");
}

async function createAnnouncement() {
  await api("/admin/announcements", {
    method: "POST",
    body: JSON.stringify({
      title: qs("announcementTitleInput").value.trim(),
      content: qs("announcementContentInput").value.trim(),
    }),
  });
  qs("announcementTitleInput").value = "";
  qs("announcementContentInput").value = "";
  await loadAnnouncements();
  await loadDashboard();
  showToast("公告已发布");
}

async function login() {
  const data = await api("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email: qs("loginEmail").value, password: qs("loginPassword").value }),
  });
  if (data.user.role !== "admin") {
    throw new Error("该账号不是管理员账号");
  }
  state.token = data.token;
  state.user = data.user;
  localStorage.setItem("zhuyu_token", state.token);
  qs("authStatus").textContent = data.user.full_name;
  showAppMain();
  await Promise.all([loadDashboard(), loadTeachers(), loadAnnouncements(), loadQuestionBank(), loadKnowledgeTree()]);
}

function logout() {
  state.token = "";
  state.user = null;
  localStorage.removeItem("zhuyu_token");
  showLoginGate();
}

function bindEvents() {
  qs("loginButton").addEventListener("click", () => login().catch((err) => showToast(err.message)));
  qs("createTeacherButton").addEventListener("click", () => createTeacher().catch((err) => showToast(err.message)));
  qs("reloadTeachersButton").addEventListener("click", () => loadTeachers().catch((err) => showToast(err.message)));
  qs("createAnnouncementButton").addEventListener("click", () => createAnnouncement().catch((err) => showToast(err.message)));
  qs("reloadAnnouncementsButton").addEventListener("click", () => loadAnnouncements().catch((err) => showToast(err.message)));
  document.querySelectorAll(".nav-btn[data-page]").forEach((item) => {
    item.addEventListener("click", () => navigateTo(item.dataset.page));
  });
}

async function bootstrap() {
  bindEvents();
  if (!state.token) return;
  try {
    state.user = await api("/auth/me");
    if (state.user.role !== "admin") throw new Error("not admin");
    qs("authStatus").textContent = state.user.full_name;
    showAppMain();
    await Promise.all([loadDashboard(), loadTeachers(), loadAnnouncements(), loadQuestionBank(), loadKnowledgeTree()]);
  } catch {
    localStorage.removeItem("zhuyu_token");
    state.token = "";
    showLoginGate();
  }
}

bootstrap().catch((err) => showToast(err.message));
