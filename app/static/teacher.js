const state = {
  token: localStorage.getItem("zhuyu_token") || "",
  user: null,
  topics: [],
  activePage: "dashboard",
  pendingSelectedIds: new Set(),
  documents: [],
  activeRagTab: "library",
  practiceReviews: [],
  schools: [],
  classrooms: [],
  studentPageData: null,
  studentSearch: "",
  collapsedStudentGroups: {},
  dashboardData: null,
  analyticsData: null,
  qbSubject: "",
  qbGrade: "",
  qbType: "",
  qbStatus: "",
  qbSearch: "",
  qbItems: [],
};

function qs(id) {
  return document.getElementById(id);
}

function bindClick(id, handler) {
  const el = qs(id);
  if (el) el.addEventListener("click", handler);
}

function bindChange(id, handler) {
  const el = qs(id);
  if (el) el.addEventListener("change", handler);
}

function showToast(text) {
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = text;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 1800);
}

function showLoginGate() {
  qs("loginGate").style.display = "";
  qs("appMain").style.display = "none";
}

function showAppMain() {
  qs("loginGate").style.display = "none";
  qs("appMain").style.display = "";
}

function toggleTeacherAuthForm(mode) {
  qs("teacherLoginForm").style.display = mode === "login" ? "" : "none";
  qs("showTeacherLoginButton").className = mode === "login" ? "btn btn-primary" : "btn btn-ghost";
}

function navigateTo(page) {
  state.activePage = page;
  document.querySelectorAll(".nav-btn[data-page]").forEach((item) => {
    item.classList.toggle("active", item.dataset.page === page);
  });
  document.querySelectorAll(".page").forEach((section) => {
    section.classList.toggle("active", section.dataset.page === page);
  });
  syncSearchHelpVisibility();
}

function showModal(title, message) {
  qs("modalTitle").textContent = title;
  qs("modalMessage").textContent = message;
  const modal = qs("generateSuccessModal");
  modal.classList.add("show");
}

function hideModal() {
  qs("generateSuccessModal").classList.remove("show");
}

function friendlySource(source) {
  const map = {
    ai_generated: "AI 生成",
    seed: "系统内置",
    excel_import: "Excel 导入",
    csv_import: "CSV 导入",
    word_import: "Word 导入",
    manual: "手动添加",
  };
  return map[source] || source || "系统内置";
}

function friendlyQuestionType(type) {
  const map = {
    blank: "填空题",
    choice: "选择题",
    judgment: "判断题",
    solution: "解答题",
    steps: "分步计算题",
  };
  return map[type] || type || "填空题";
}

function friendlyDifficulty(value) {
  if (value < 0.35) return "🟢 低";
  if (value < 0.65) return "🟡 中";
  return "🔴 高";
}

function friendlyStrategy(strategy) {
  const map = {
    hybrid: "智能混合",
    keyword: "关键词搜索",
    dense: "语义搜索",
    rerank: "重排序搜索",
  };
  return map[strategy] || strategy;
}

function friendlyDocType(docType) {
  const map = {
    textbook: "教材",
    handout: "讲义",
    solution: "题解",
    reference: "参考资料",
    legacy: "旧版资料",
  };
  return map[docType] || docType || "未分类";
}

function gradeOptions() {
  return ["小学一年级", "小学二年级", "小学三年级", "小学四年级", "小学五年级", "小学六年级", "初一", "初二", "初三"];
}

function sortGrades(grades) {
  const order = gradeOptions();
  return [...grades].sort((a, b) => {
    const indexA = order.indexOf(a);
    const indexB = order.indexOf(b);
    if (indexA !== -1 || indexB !== -1) {
      if (indexA === -1) return 1;
      if (indexB === -1) return -1;
      return indexA - indexB;
    }
    return a.localeCompare(b, "zh");
  });
}

function renderQuestionPreview(item) {
  if (item.question_type === "choice" && item.options?.length) {
    return `<div class="option-preview">${item.options.map((option) => `<span>${option.key}. ${option.content}</span>`).join("")}</div>`;
  }
  if (item.question_type === "judgment") {
    return `<div class="option-preview"><span>判断答案：${item.answer}</span></div>`;
  }
  if (item.blank_count > 1) {
    return `<div class="option-preview"><span>${item.blank_count} 个填空</span>${(item.score_points || []).map((point) => `<span>${point.title}: ${(point.keywords || []).join("/")}</span>`).join("")}</div>`;
  }
  return "";
}

function renderClassroomControls() {
  const schoolOptions = state.schools.length
    ? state.schools.map((school) => `<option value="${school.id}">${school.name}</option>`).join("")
    : "<option value=''>请先创建学校</option>";
  qs("classroomSchoolSelect").innerHTML = schoolOptions;
  qs("classroomGradeSelect").innerHTML = gradeOptions().map((grade) => `<option value="${grade}">${grade}</option>`).join("");
}

function renderClassrooms() {
  const target = qs("teacherClassroomsView");
  if (!state.classrooms.length) {
    target.className = "timeline empty-state";
    target.innerHTML = "暂无班级，创建后学生注册时即可选择。";
    syncGenerateControls();
    return;
  }
  target.className = "timeline";
  target.innerHTML = state.classrooms.map((item) => `
    <article class="timeline-item">
      <strong>${item.school_name || "未绑定学校"} · ${item.grade_level} · ${item.name}</strong>
      <div>学生 ${item.student_count} 人</div>
      <div class="invite-row">
        <span>班级邀请码</span>
        <strong>${item.invite_code}</strong>
        <button class="btn btn-ghost btn-sm copy-invite-button" data-invite-code="${item.invite_code}">复制</button>
        <button class="btn btn-ghost btn-sm refresh-invite-button" data-classroom-id="${item.id}">重新生成</button>
      </div>
      <small>老师：${item.teacher_name || state.user?.full_name || "当前老师"}${item.description ? ` · ${item.description}` : ""}</small>
    </article>
  `).join("");
  syncGenerateControls();
}

async function api(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const headers = { ...(isFormData ? {} : { "Content-Type": "application/json" }), ...(options.headers || {}) };
  if (state.token) headers["X-Session-Token"] = state.token;
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response));
  }
  return response.json();
}

async function extractErrorMessage(response) {
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  if (contentType.includes("application/json")) {
    try {
      const payload = await response.json();
      if (typeof payload?.detail === "string" && payload.detail.trim()) return payload.detail.trim();
      if (typeof payload?.message === "string" && payload.message.trim()) return payload.message.trim();
    } catch {
      // fall through to plain text
    }
  }
  try {
    const text = (await response.text()).trim();
    if (!text) return `Request failed: ${response.status}`;
    try {
      const payload = JSON.parse(text);
      if (typeof payload?.detail === "string" && payload.detail.trim()) return payload.detail.trim();
      if (typeof payload?.message === "string" && payload.message.trim()) return payload.message.trim();
    } catch {
      // treat as raw text
    }
    return text;
  } catch {
    return `Request failed: ${response.status}`;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatDateTime(value) {
  if (!value) return "暂无时间";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function leafTopics() {
  const parentIds = new Set(state.topics.map((t) => t.parent_id).filter(Boolean));
  return state.topics.filter((t) => !parentIds.has(t.id));
}

function getGrades() {
  return sortGrades([...new Set(state.topics.map((t) => t.grade_level).filter(Boolean))]);
}

function getTeacherGrades() {
  return sortGrades([...new Set(state.classrooms.map((item) => item.grade_level).filter(Boolean))]);
}

function getSubjectsByGrade(grade) {
  return [...new Set(state.topics.filter((t) => !grade || t.grade_level === grade).map((t) => t.subject).filter(Boolean))].sort();
}

function getTopicsByGradeAndSubject(grade, subject) {
  return leafTopics().filter((t) => (!grade || t.grade_level === grade) && (!subject || t.subject === subject));
}

function syncSelectorGroup(prefix, options = {}) {
  const gradeEl = qs(prefix + "Grade");
  const subjectEl = qs(prefix + "Subject");
  if (!gradeEl || !subjectEl) return;
  const grades = typeof options.getGrades === "function" ? options.getGrades() : getGrades();
  const previousGrade = gradeEl.value;
  const previousSubject = subjectEl.value;
  initCascade(prefix, options);
  if (!grades.length) return;
  const autoSelectFirst = options.autoSelectFirst !== false;
  const nextGrade = grades.includes(previousGrade) ? previousGrade : (autoSelectFirst ? grades[0] : "");
  if (!nextGrade) return;
  gradeEl.value = nextGrade;
  if (typeof gradeEl.onchange === "function") gradeEl.onchange();
  const subjects = typeof options.getSubjects === "function" ? options.getSubjects(nextGrade) : getSubjectsByGrade(nextGrade);
  const nextSubject = subjects.includes(previousSubject) ? previousSubject : (autoSelectFirst && subjects.length ? subjects[0] : "");
  if (!nextSubject) return;
  subjectEl.value = nextSubject;
  if (typeof subjectEl.onchange === "function") subjectEl.onchange();
}

function syncGenerateControls() {
  const teacherGrades = getTeacherGrades();
  const hasClassrooms = teacherGrades.length > 0;
  const teacherScopeOptions = {
    gradePlaceholder: teacherGrades.length ? "年级" : "请先创建班级",
    getGrades: () => teacherGrades,
  };
  syncSelectorGroup("generate", { ...teacherScopeOptions, autoSelectFirst: false });
  syncSelectorGroup("excelImport", teacherScopeOptions);
  syncSelectorGroup("uploadDocument", teacherScopeOptions);
  syncSelectorGroup("documentFilter", teacherScopeOptions);
  syncSelectorGroup("docSearch", teacherScopeOptions);

  ["generateGrade", "generateSubject", "generateTopicId", "generateCategory", "generateCount", "generateQuestionType"].forEach((id) => {
    const el = qs(id);
    if (el) el.disabled = !hasClassrooms;
  });
  ["excelImportGrade", "excelImportSubject", "excelFileInput", "downloadExcelTemplateButton", "importExcelButton"].forEach((id) => {
    const el = qs(id);
    if (el) el.disabled = !hasClassrooms;
  });
  ["uploadDocumentGrade", "uploadDocumentSubject", "uploadDocumentFile", "uploadDocumentDocType", "uploadDocumentButton", "docSearchGrade", "docSearchSubject", "docSearchStrategy", "searchDocsButton", "documentFilterGrade", "documentFilterSubject"].forEach((id) => {
    const el = qs(id);
    if (el) el.disabled = !hasClassrooms;
  });

  const hint = qs("generateGradeHint");
  if (hint) {
    hint.textContent = hasClassrooms
      ? `当前可选年级来自你已创建的班级：${teacherGrades.join("、")}`
      : "请先创建班级，系统会根据已有班级所属年级提供出题范围。";
  }
  const excelHint = qs("excelImportHint");
  if (excelHint) {
    excelHint.textContent = hasClassrooms
      ? "先选择年级和学科，再下载对应 Excel 模板或上传已填写模板。"
      : "请先创建班级，系统只会开放你所教班级对应年级的 Excel 导题模板。";
  }
  const generateButton = qs("generateQuestionsButton");
  if (generateButton) generateButton.disabled = !hasClassrooms;
}

function initCascade(prefix, opts = {}) {
  const gradeEl = qs(prefix + "Grade");
  const subjectEl = qs(prefix + "Subject");
  const topicEl = qs(prefix + "TopicId");
  if (!gradeEl || !subjectEl) {
    console.warn("initCascade skip:", prefix, !!gradeEl, !!subjectEl, !!topicEl);
    return;
  }

  const gradePlaceholder = opts.gradePlaceholder || "年级";
  const subjectPlaceholder = opts.subjectPlaceholder || "学科";
  const topicPlaceholder = opts.topicPlaceholder || "知识点";

  const grades = typeof opts.getGrades === "function" ? opts.getGrades() : getGrades();
  gradeEl.innerHTML = `<option value="">${gradePlaceholder}</option>` +
    grades.map((g) => `<option value="${g}">${g}</option>`).join("");
  subjectEl.innerHTML = `<option value="">${subjectPlaceholder}</option>`;
  if (topicEl) topicEl.innerHTML = `<option value="">${topicPlaceholder}</option>`;

  gradeEl.onchange = () => {
    const grade = gradeEl.value;
    if (!grade) {
      subjectEl.innerHTML = `<option value="">${subjectPlaceholder}</option>`;
      if (topicEl) topicEl.innerHTML = `<option value="">${topicPlaceholder}</option>`;
      return;
    }
    const subjects = typeof opts.getSubjects === "function" ? opts.getSubjects(grade) : getSubjectsByGrade(grade);
    subjectEl.innerHTML = `<option value="">${subjectPlaceholder}</option>` +
      subjects.map((s) => `<option value="${s}">${s}</option>`).join("");
    if (topicEl) {
      const topics = typeof opts.getTopics === "function" ? opts.getTopics(grade, "") : getTopicsByGradeAndSubject(grade, "");
      topicEl.innerHTML = `<option value="">${topicPlaceholder}</option>` +
        topics.map((t) => `<option value="${t.id}">${t.name}</option>`).join("");
    }
  };

  subjectEl.onchange = () => {
    const grade = gradeEl.value;
    const subject = subjectEl.value;
    if (topicEl) {
      const topics = typeof opts.getTopics === "function" ? opts.getTopics(grade, subject) : getTopicsByGradeAndSubject(grade, subject);
      topicEl.innerHTML = `<option value="">${topicPlaceholder}</option>` +
        topics.map((t) => `<option value="${t.id}">${t.name}</option>`).join("");
    }
  };
}

function renderTeacherDashboard(data) {
  state.dashboardData = data;
  const masteryPct = (data.average_mastery * 100).toFixed(0);
  const accuracyPct = (data.average_accuracy * 100).toFixed(0);
  const activeRatio = data.total_students > 0 ? ((data.active_students / data.total_students) * 100).toFixed(0) : 0;

  qs("teacherKpiView").innerHTML = `
    <div class="kpi-card kpi-blue" aria-label="学生总数">
      <div class="kpi-icon">👤</div>
      <div><div class="kpi-value">${data.total_students}</div><div class="kpi-label">学生总数</div></div>
    </div>
    <div class="kpi-card kpi-green" aria-label="活跃学生">
      <div class="kpi-icon">🟢</div>
      <div><div class="kpi-value">${data.active_students}</div><div class="kpi-label">活跃学生</div><div class="kpi-sub">占比 ${activeRatio}%</div></div>
    </div>
    <div class="kpi-card kpi-orange" aria-label="平均掌握度">
      <div class="kpi-icon">📊</div>
      <div><div class="kpi-value">${masteryPct}%</div><div class="kpi-label">平均掌握度</div></div>
    </div>
    <div class="kpi-card kpi-purple" aria-label="平均正确率">
      <div class="kpi-icon">🎯</div>
      <div><div class="kpi-value">${accuracyPct}%</div><div class="kpi-label">平均正确率</div></div>
    </div>
  `;

  renderPracticeAnalytics(data);
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "暂无";
  return `${Math.round(Number(value) * 100)}%`;
}

function renderStudentList(data) {
  state.studentPageData = data;
  const keyword = (qs("studentSearchInput")?.value || "").trim().toLowerCase();
  state.studentSearch = keyword;
  const students = [...(data.students || [])].filter((item) => {
    if (!keyword) return true;
    return (item.name || "").toLowerCase().includes(keyword);
  });

  if (!students.length) {
    qs("studentPageView").innerHTML = keyword
      ? "<div class='empty-state'>没有匹配的学生</div>"
      : "<div class='empty-state'>暂无学生数据，创建班级后学生注册即可显示</div>";
    return;
  }

  const groups = {};
  students.forEach((item) => {
    const key = `${item.grade_level || "未分年级"}|${item.classroom_name || "未分班"}`;
    if (!groups[key]) groups[key] = [];
    groups[key].push(item);
  });

  const sortedKeys = Object.keys(groups).sort((a, b) => {
    const [gradeA, classA] = a.split("|");
    const [gradeB, classB] = b.split("|");
    const gradeRank = sortGrades([gradeA, gradeB]);
    if (gradeRank[0] !== gradeRank[1]) {
      return gradeRank[0] === gradeA ? -1 : 1;
    }
    return classA.localeCompare(classB, "zh");
  });

  qs("studentPageView").innerHTML = sortedKeys.map((key) => {
    const [grade, classroom] = key.split("|");
    const group = groups[key];
    const avgMastery = group.reduce((s, i) => s + (i.overall_mastery || 0), 0) / group.length;
    const avgAccuracy = group.reduce((s, i) => s + (i.recent_practice_accuracy || 0), 0) / group.length;
    const masteryPct = (avgMastery * 100).toFixed(0);
    const accuracyPct = (avgAccuracy * 100).toFixed(0);
    const barClass = avgMastery < 0.4 ? "progress-low" : avgMastery < 0.7 ? "progress-mid" : "progress-high";
    const collapsed = !keyword && !!state.collapsedStudentGroups[key];
    return `
      <section class="class-group-card">
        <div class="class-group-head">
          <div>
            <div class="class-group-title">${grade} · ${classroom}</div>
            <div class="class-group-meta">
              <span>👤 ${group.length} 人</span>
              <span>📊 掌握度 ${masteryPct}%</span>
              <span>🎯 正确率 ${accuracyPct}%</span>
            </div>
          </div>
          <div class="class-group-actions">
            <button class="btn btn-ghost btn-sm student-group-toggle" data-group-key="${key}">
              ${collapsed ? "展开学生" : "收起学生"}
            </button>
            <div class="class-group-badge">班级视图</div>
          </div>
        </div>
        <div class="progress-bar-wrap" style="margin-top:8px;"><div class="progress-bar-fill ${barClass}" style="width:${masteryPct}%"></div></div>
        <div class="student-inline-list" style="${collapsed ? "display:none;" : ""}">
          ${group.sort((a, b) => (a.name || "").localeCompare(b.name || "", "zh")).map((item) => `
            <article class="student-inline-card" data-student-id="${item.student_profile_id}">
              <div class="student-inline-main">
                <div class="student-inline-top">
                  <div>
                    <div class="student-inline-name">${item.name || "未命名"}</div>
                    <div class="student-inline-meta">${item.grade_level || "未分年级"} · ${item.classroom_name || "未分班"}${item.latest_report_at ? ` · 最近报告 ${formatDateTime(item.latest_report_at)}` : ""}</div>
                  </div>
                  <div class="student-inline-stats">
                    <div class="student-inline-stat">
                      <strong>${formatPercent(item.overall_mastery)}</strong>
                      <span>掌握度</span>
                    </div>
                    <div class="student-inline-stat">
                      <strong>${formatPercent(item.recent_practice_accuracy)}</strong>
                      <span>正确率</span>
                    </div>
                  </div>
                </div>
                <div class="student-inline-footer">点击查看各科学习掌握度</div>
              </div>
            </article>
          `).join("")}
        </div>
      </section>
    `;
  }).join("");

  const studentMap = new Map(students.map((item) => [String(item.student_profile_id), item]));
  qs("studentPageView").querySelectorAll(".student-inline-card[data-student-id]").forEach((card) => {
    card.addEventListener("click", () => {
      const student = studentMap.get(card.dataset.studentId);
      if (student) openStudentDrawer(student);
    });
  });
  qs("studentPageView").querySelectorAll(".student-group-toggle[data-group-key]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.groupKey;
      state.collapsedStudentGroups[key] = !state.collapsedStudentGroups[key];
      renderStudentList(state.studentPageData || { students: [] });
    });
  });
}

function openStudentDrawer(student) {
  qs("studentDrawerTitle").textContent = student.name || "学生详情";
  const summaries = student.subject_summaries || [];
  qs("studentDrawerBody").innerHTML = `
    <div class="drawer-student-overview">
      <div class="drawer-student-overview-main">
        <div class="drawer-student-name">${student.name || "未命名"}</div>
        <div class="drawer-student-subject">${student.grade_level || "未分年级"} · ${student.classroom_name || "未分班"}${student.latest_report_at ? ` · 最近报告 ${formatDateTime(student.latest_report_at)}` : ""}</div>
      </div>
      <div class="drawer-student-right">
        <div class="drawer-stat">
          <div class="drawer-stat-value">${formatPercent(student.overall_mastery)}</div>
          <div class="drawer-stat-label">整体掌握度</div>
        </div>
        <div class="drawer-stat">
          <div class="drawer-stat-value" style="color:#8b5cf6">${formatPercent(student.recent_practice_accuracy)}</div>
          <div class="drawer-stat-label">整体正确率</div>
        </div>
      </div>
    </div>
    <div class="drawer-section-title">各科学习情况</div>
    <div class="drawer-subject-list">
      ${summaries.length ? summaries.map((item) => `
        <div class="drawer-subject-card">
          <div class="drawer-subject-head">
            <strong>${item.subject}</strong>
            <span>${item.practice_count ? `${item.practice_count} 次练习` : "暂无练习"}</span>
          </div>
          <div class="drawer-subject-metrics">
            <span>掌握度 ${formatPercent(item.mastery)}</span>
            <span>正确率 ${formatPercent(item.accuracy)}</span>
          </div>
        </div>
      `).join("") : `<div class="empty-state">暂无学科练习数据</div>`}
    </div>
  `;

  qs("studentDrawerOverlay").classList.add("open");
  qs("studentDrawerPanel").classList.add("open");
}

function closeStudentDrawer() {
  qs("studentDrawerOverlay").classList.remove("open");
  qs("studentDrawerPanel").classList.remove("open");
}

function renderPracticeAnalytics(data) {
  if (!data || typeof data.total_attempts === "undefined") {
    qs("practiceAnalyticsView").innerHTML = `<div class="kpi-grid" style="grid-template-columns:1fr 1fr 1fr;">
      <div class="kpi-card kpi-blue"><div class="kpi-icon">📝</div><div><div class="kpi-value">0</div><div class="kpi-label">总练习数</div></div></div>
      <div class="kpi-card kpi-green"><div class="kpi-icon">✅</div><div><div class="kpi-value">0</div><div class="kpi-label">总正确数</div></div></div>
      <div class="kpi-card kpi-purple"><div class="kpi-icon">🎯</div><div><div class="kpi-value">0%</div><div class="kpi-label">整体正确率</div></div></div>
    </div>
    <div class="empty-state">暂无练习记录，学生完成练习后即可查看分析</div>`;
    return;
  }
  state.analyticsData = data;
  const accuracyPct = (data.accuracy * 100).toFixed(0);

  let html = `
    <div class="kpi-grid" style="grid-template-columns:1fr 1fr 1fr;">
      <div class="kpi-card kpi-blue" aria-label="总练习数">
        <div class="kpi-icon">📝</div>
        <div><div class="kpi-value">${data.total_attempts}</div><div class="kpi-label">总练习数</div></div>
      </div>
      <div class="kpi-card kpi-green" aria-label="总正确数">
        <div class="kpi-icon">✅</div>
        <div><div class="kpi-value">${data.correct_attempts}</div><div class="kpi-label">总正确数</div></div>
      </div>
      <div class="kpi-card kpi-purple" aria-label="整体正确率">
        <div class="kpi-icon">🎯</div>
        <div><div class="kpi-value">${accuracyPct}%</div><div class="kpi-label">整体正确率</div></div>
      </div>
    </div>
  `;

  const topicMap = {};
  state.topics.forEach((t) => { topicMap[t.id] = t.name; });

  if (data.topics && data.topics.length) {
    html += `<table class="topic-table"><thead><tr><th>知识点</th><th>练习数</th><th>正确率</th><th>掌握度</th></tr></thead><tbody>`;
    html += data.topics.map((item) => {
      const accPct = (item.accuracy * 100).toFixed(0);
      const masteryPct = item.mastery != null ? (item.mastery * 100).toFixed(0) : "-";
      const accColor = item.accuracy < 0.4 ? "#d54941" : item.accuracy < 0.7 ? "#f7a440" : "#2ba471";
      return `<tr><td><strong>${topicMap[item.topic_id] || item.topic_id}</strong></td><td>${item.attempt_count}</td><td style="color:${accColor};font-weight:700">${accPct}%</td><td>${masteryPct}${masteryPct !== "-" ? "%" : ""}</td></tr>`;
    }).join("");
    html += `</tbody></table>`;
  } else {
    html += `<div class="empty-state">暂无练习记录，学生完成练习后即可查看分析</div>`;
  }

  qs("practiceAnalyticsView").innerHTML = html;
}

function renderQuestionBank(items) {
  state.qbItems = items;
  const subjects = [...new Set(items.map((item) => item.subject).filter(Boolean))].sort();
  const grades = sortGrades([...new Set(items.map((item) => item.grade_level).filter(Boolean))]);

  qs("qbTabs").innerHTML = ["全部", ...subjects].map((s) => {
    const val = s === "全部" ? "" : s;
    const active = state.qbSubject === val ? "active" : "";
    const count = s === "全部" ? items.length : items.filter((i) => i.subject === s).length;
    return `<button class="qb-tab ${active}" data-qb-subject="${val}">${s}（${count}）</button>`;
  }).join("");

  qs("qbGradeFilter").innerHTML = "<option value=''>全部年级</option>" + grades.map((g) => `<option value="${g}" ${state.qbGrade === g ? "selected" : ""}>${g}</option>`).join("");
  qs("qbTypeFilter").value = state.qbType;
  qs("qbStatusFilter").value = state.qbStatus;
  qs("qbSearchInput").value = state.qbSearch;

  qs("qbTabs").querySelectorAll("[data-qb-subject]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.qbSubject = btn.dataset.qbSubject;
      renderQuestionBank(state.qbItems);
    });
  });

  let filtered = items;
  if (state.qbSubject) filtered = filtered.filter((i) => i.subject === state.qbSubject);
  if (state.qbGrade) filtered = filtered.filter((i) => i.grade_level === state.qbGrade);
  if (state.qbType) filtered = filtered.filter((i) => i.question_type === state.qbType);
  if (state.qbStatus) filtered = filtered.filter((i) => i.status === state.qbStatus);
  if (state.qbSearch) {
    const kw = state.qbSearch.toLowerCase();
    filtered = filtered.filter((i) => (i.stem || "").toLowerCase().includes(kw) || (i.answer || "").toLowerCase().includes(kw));
  }

  const approvedCount = filtered.filter((i) => i.status === "approved").length;
  const pendingCount = filtered.filter((i) => i.status === "pending").length;
  qs("qbStatsBar").innerHTML = `共 <strong>${filtered.length}</strong> 题 · 已审核 <strong>${approvedCount}</strong> · 待审核 <strong>${pendingCount}</strong>`;

  if (!filtered.length) {
    qs("questionBankView").innerHTML = "<div class='qb-empty'>暂无题目，可通过 AI 生成或 Excel 导入添加</div>";
    return;
  }

  qs("questionBankView").innerHTML = filtered.map((item) => {
    const topicName = item.knowledge_l2_name || item.topic_name || item.topic_id;
    const parentName = item.knowledge_l1_name || "";
    const subjectLabel = [item.grade_level, item.subject, topicName].filter(Boolean).join(" · ");
    const statusBadge = item.status === "approved" ? "badge-approved" : item.status === "pending" ? "badge-pending" : "badge-rejected";
    const statusText = item.status === "approved" ? "已审核" : item.status === "pending" ? "待审核" : "已拒绝";
    const diffLevel = item.difficulty_level || (item.difficulty < 0.3 ? 1 : item.difficulty < 0.5 ? 2 : item.difficulty < 0.7 ? 3 : item.difficulty < 0.85 ? 4 : 5);
    const diffBadge = diffLevel <= 2 ? "badge-low" : diffLevel <= 3 ? "badge-mid" : "badge-high";
    const diffText = diffLevel <= 2 ? "基础概念" : diffLevel <= 3 ? "常规" : "综合";
    const tagsHtml = (item.tags || []).map((t) => `<span class="badge">${t}</span>`).join("");

    return `
      <div class="qb-card">
        <div class="qb-card-head">
          <div>
            <div class="qb-card-topic">${subjectLabel || "未分类题目"}</div>
            ${parentName ? `<div class="qb-card-topic-path">一级知识点：${parentName}</div>` : ""}
          </div>
          <div class="qb-card-badges">
            <span class="badge ${statusBadge}">${statusText}</span>
            <span class="badge ${diffBadge}">${diffText}</span>
            <span class="badge badge-type">${friendlyQuestionType(item.question_type)}</span>
            ${item.source ? `<span class="badge badge-source">${friendlySource(item.source)}</span>` : ""}
          </div>
        </div>
        <div class="qb-card-stem">${item.stem || ""}${renderQuestionPreview(item)}</div>
        <div class="qb-card-answer">答案：${item.answer || "-"}</div>
        ${item.explanation ? `<div class="qb-card-explain">解析：${item.explanation}</div>` : ""}
        ${tagsHtml ? `<div class="qb-card-tags">${tagsHtml}</div>` : ""}
      </div>
    `;
  }).join("");
}

function renderPendingQuestions(items) {
  state.pendingSelectedIds = new Set();
  if (!items.length) {
    qs("pendingQuestionsView").innerHTML = "<div class='empty-state'>暂无待审核题目 🎉</div>";
    return;
  }
  qs("pendingQuestionsView").innerHTML = items.map((item) => `
    <div class="timeline-item" data-question-id="${item.id}" style="display:flex;gap:10px;align-items:flex-start;">
      <input type="checkbox" class="pending-checkbox" data-id="${item.id}" style="margin-top:4px;width:18px;height:18px;cursor:pointer;flex-shrink:0;">
      <div style="flex:1;">
        <strong>[${item.knowledge_l2_name || item.topic_name || item.topic_id}] ${item.stem}</strong>
        ${renderQuestionPreview(item)}
        <div>答案：${item.answer}</div>
        <div>解析：${item.explanation}</div>
        <small>${friendlyDifficulty(item.difficulty)} 难度 · ${friendlyQuestionType(item.question_type)} · 来源 ${friendlySource(item.source)}</small>
        <div class="actions" style="margin-top:6px;">
          <button class="btn btn-primary btn-sm approve-btn" data-id="${item.id}">✅ 通过</button>
          <button class="btn btn-danger btn-sm reject-btn" data-id="${item.id}">❌ 拒绝</button>
        </div>
      </div>
    </div>
  `).join("");

  qs("pendingQuestionsView").querySelectorAll(".pending-checkbox").forEach((cb) => {
    cb.addEventListener("change", () => {
      const id = parseInt(cb.dataset.id);
      if (cb.checked) state.pendingSelectedIds.add(id);
      else state.pendingSelectedIds.delete(id);
    });
  });
  qs("pendingQuestionsView").querySelectorAll(".approve-btn").forEach((btn) => {
    btn.addEventListener("click", () => reviewQuestion(parseInt(btn.dataset.id), "approve"));
  });
  qs("pendingQuestionsView").querySelectorAll(".reject-btn").forEach((btn) => {
    btn.addEventListener("click", () => reviewQuestion(parseInt(btn.dataset.id), "reject"));
  });
}

function selectAllPending() {
  qs("pendingQuestionsView").querySelectorAll(".pending-checkbox").forEach((cb) => {
    cb.checked = true;
    state.pendingSelectedIds.add(parseInt(cb.dataset.id));
  });
}

function selectNonePending() {
  qs("pendingQuestionsView").querySelectorAll(".pending-checkbox").forEach((cb) => {
    cb.checked = false;
  });
  state.pendingSelectedIds.clear();
}

function renderPracticeReviews(items) {
  state.practiceReviews = items || [];
  if (!state.practiceReviews.length) {
    qs("practiceReviewsView").innerHTML = "<div class='empty-state'>暂无待复核答案</div>";
    return;
  }
  qs("practiceReviewsView").innerHTML = state.practiceReviews.map((item) => `
    <article class="timeline-item review-item" data-review-id="${item.record_id}">
      <div class="document-row-top">
        <div>
          <strong>${item.student_name} · ${topicName(item.topic_id)}</strong>
          <div>${item.question_stem}</div>
          <small>${formatDateTime(item.created_at)} · ${item.evaluation_status === "reviewed" ? "已复核" : "待复核"} · ${item.review_reason || "等待教师确认"}</small>
        </div>
        <span class="badge">${item.evaluation_method === "teacher_review" ? "教师复核" : "待复核"}</span>
      </div>
      <div class="review-answer-grid">
        <div class="note-card"><strong>学生答案</strong><div>${item.student_answer || "未填写"}</div></div>
        <div class="note-card"><strong>参考答案</strong><div>${item.correct_answer || "暂无"}</div></div>
      </div>
      ${item.explanation ? `<div class="helper-card"><strong>解析</strong><p>${item.explanation}</p></div>` : ""}
      ${item.evaluation_status === "reviewed" ? `
        <div class="helper-card"><strong>复核结果</strong><p>${item.is_correct ? "判定正确" : "判定需订正"} · 得分 ${Math.round((item.score || 0) * 100)}% · ${item.feedback || "无补充反馈"}</p></div>
      ` : `
        <label><span>教师反馈</span><textarea id="reviewFeedback${item.record_id}" rows="2" placeholder="给学生一句明确的订正建议"></textarea></label>
        <div class="inline-actions">
          <button class="primary-button review-resolve-button" data-review-id="${item.record_id}" data-score="1" data-correct="true">判对</button>
          <button class="ghost-button review-resolve-button" data-review-id="${item.record_id}" data-score="0.5" data-correct="false">半分</button>
          <button class="ghost-button review-resolve-button danger-action" data-review-id="${item.record_id}" data-score="0" data-correct="false">判错</button>
        </div>
      `}
    </article>
  `).join("");
  qs("practiceReviewsView").querySelectorAll(".review-resolve-button").forEach((button) => {
    button.addEventListener("click", () => resolvePracticeReview(
      Number(button.dataset.reviewId),
      button.dataset.correct === "true",
      Number(button.dataset.score),
    ).catch(handleError));
  });
}

function topicName(topicId) {
  return state.topics.find((topic) => topic.id === topicId)?.name || topicId || "全部知识点";
}

function renderRagOverview(docs = state.documents || []) {
  const docCount = docs.length;
  const chunkCount = docs.reduce((sum, item) => sum + (item.chunk_count || 0), 0);
  const readyCount = docs.reduce((sum, item) => sum + (item.embedding_ready_count || 0), 0);
  const recent = docs[0];
  const scopeGrade = qs("documentFilterGrade")?.value || "全部年级";
  const scopeSubject = qs("documentFilterSubject")?.value || "全部学科";
  const recentText = recent
    ? `${recent.title} · ${friendlyDocType(recent.doc_type)} · ${formatDateTime(recent.created_at)}`
    : "还没有导入资料，先上传一份讲义或题解。";
  const recentTitle = recentText.replace(/"/g, "&quot;");
  qs("ragOverviewView").innerHTML = `
    <div class="rag-overview-strip">
      <div class="rag-stat-inline">
        <span class="rag-stat-chip"><strong>资料总数</strong><em>${docCount}</em></span>
        <span class="rag-stat-chip"><strong>片段数量</strong><em>${chunkCount}</em></span>
        <span class="rag-stat-chip"><strong>已向量化</strong><em>${readyCount}/${chunkCount || 0}</em></span>
        <span class="rag-stat-chip"><strong>当前范围</strong><em>${scopeGrade} · ${scopeSubject}</em></span>
      </div>
      <div class="rag-overview-latest" title="${recentTitle}">
        <strong>最近资料</strong>
        <span>${recentText}</span>
      </div>
    </div>
  `;
}

function renderDocumentLibrary() {
  const typeFilter = qs("documentFilterDocType")?.value || "";
  const docs = (state.documents || []).filter((item) => {
    const typeOk = !typeFilter || item.doc_type === typeFilter;
    return typeOk;
  });
  if (!docs.length) {
    qs("documentLibraryView").innerHTML = "<div class='empty-state'>当前年级学科下暂无资料</div>";
    renderRagOverview(docs);
    return;
  }
  qs("documentLibraryView").innerHTML = docs.map((item) => {
    const ready = item.embedding_ready_count || 0;
    const total = item.chunk_count || 0;
    const iconMap = { textbook: "📕", handout: "📝", solution: "💡", reference: "📋" };
    const icon = iconMap[item.doc_type] || "📄";
    const indexStatus = ready >= total && total > 0 ? "badge-approved" : "badge-pending";
    const indexText = ready >= total && total > 0 ? "已索引" : `${ready}/${total}`;
    return `
      <div class="doc-card" data-document-id="${item.id}">
        <div class="doc-card-icon">${icon}</div>
        <div class="doc-card-info">
          <div class="doc-card-title">${item.title}</div>
          <div class="doc-card-meta">${item.grade_level || "未绑定年级"} · ${item.subject || "未绑定学科"} · ${friendlyDocType(item.doc_type)}</div>
          <div class="doc-card-meta">${item.source_name || "-"}</div>
          <div class="doc-card-meta">${formatDateTime(item.created_at)} · <span class="badge ${indexStatus}">${indexText}</span></div>
        </div>
        <div class="doc-card-actions">
          ${item.can_delete
            ? `<button class="btn btn-danger btn-sm delete-document-button" data-document-id="${item.id}">删除</button>`
            : `<span class="badge badge-source">共享</span>`}
        </div>
      </div>
    `;
  }).join("");

  qs("documentLibraryView").querySelectorAll(".delete-document-button").forEach((button) => {
    button.addEventListener("click", () => deleteDocument(Number(button.dataset.documentId)).catch(handleError));
  });
  renderRagOverview(docs);
}

function renderDocumentSearch(items) {
  qs("documentSearchView").innerHTML = items.length ? items.map((item) => `
    <div class="timeline-item search-hit-card">
      <strong>${item.document_title}</strong>
      <div>${item.snippet}</div>
      <small>${item.grade_level || "未绑定年级"} · ${item.subject || "未绑定学科"} · ${friendlyDocType(item.doc_type)} · ${item.source_name} · 相关度 ${Number(item.score).toFixed(3)}</small>
      <div class="score-breakdown-line">
        <span>关键词 ${Number(item.lexical_score || 0).toFixed(3)}</span>
        <span>向量 ${Number(item.vector_score || 0).toFixed(3)}</span>
        <span>Dense ${Number(item.dense_score || 0).toFixed(3)}</span>
        <span>Rerank ${Number(item.rerank_score || 0).toFixed(3)}</span>
      </div>
    </div>
  `).join("") : "<div class='empty-state'>没有搜索到相关内容</div>";
}

function syncSearchHelpVisibility() {
  const fab = qs("searchStrategyHelpFab");
  const modal = qs("searchStrategyHelpModal");
  if (!fab || !modal) return;
  const visible = state.activePage === "documents" && state.activeRagTab === "search";
  fab.style.display = visible ? "flex" : "none";
  if (!visible) modal.classList.remove("show");
}

function toggleSearchHelp() {
  const modal = qs("searchStrategyHelpModal");
  if (modal) modal.classList.toggle("show");
}

async function loadTopics() {
  try {
    state.topics = await api("/graph/topics");
  } catch (e) {
    console.error("loadTopics failed:", e);
    state.topics = [];
  }
  console.log("topics loaded:", state.topics.length, "grades:", getGrades());
  syncGenerateControls();
}

async function loadSchools() {
  state.schools = await api("/teacher/schools");
  renderClassroomControls();
}

async function loadClassrooms() {
  state.classrooms = await api("/teacher/classrooms");
  renderClassrooms();
}

async function createClassroom() {
  const schoolId = Number(qs("classroomSchoolSelect").value);
  const name = qs("classroomNameInput").value.trim();
  if (!schoolId || !name) {
    showToast("请选择学校并填写班级名称");
    return;
  }
  await api("/teacher/classrooms", {
    method: "POST",
    body: JSON.stringify({
      school_id: schoolId,
      grade_level: qs("classroomGradeSelect").value,
      name,
      description: qs("classroomDescriptionInput").value.trim(),
    }),
  });
  qs("classroomNameInput").value = "";
  qs("classroomDescriptionInput").value = "";
  await loadClassrooms();
  showToast("班级已创建 ✓");
}

async function refreshInviteCode(classroomId) {
  await api(`/teacher/classrooms/${classroomId}/refresh-invite-code`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  await loadClassrooms();
  showToast("邀请码已更新 ✓");
}

async function copyInviteCode(code) {
  if (navigator.clipboard) {
    await navigator.clipboard.writeText(code);
    showToast("邀请码已复制 ✓");
    return;
  }
  showToast(`邀请码：${code}`);
}

async function login() {
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: qs("loginEmail").value, password: qs("loginPassword").value }),
    });
    if (data.user.role !== "teacher") {
      throw new Error("该账号不是教师账号");
    }
    state.token = data.token;
    state.user = data.user;
    localStorage.setItem("zhuyu_token", state.token);
    qs("authStatus").textContent = `${data.user.full_name}`;
    showToast("登录成功 ✓");
    showAppMain();
    await loadTopics();
    await loadSchools();
    await loadTeacherDashboard();
    await loadStudentPage();
    await loadClassrooms();
    await loadQuestionBank();
    await loadPendingQuestions();
    await loadPracticeReviews();
    await loadDocuments();
    syncSearchHelpVisibility();
  } catch (err) {
    showToast(`登录失败: ${err.message}`);
  }
}

function logout() {
  state.token = "";
  state.user = null;
  localStorage.removeItem("zhuyu_token");
  showLoginGate();
}

async function loadTeacherDashboard() {
  const spinner = qs("dashboardSpinner");
  if (spinner) spinner.innerHTML = '<span class="spinner"></span>';
  try {
    const dashboard = await api("/teacher/dashboard");
    renderTeacherDashboard(dashboard);
    try {
      const analytics = await api("/teacher/analytics/practice");
      renderPracticeAnalytics(analytics);
    } catch { }
  } finally {
    if (spinner) spinner.innerHTML = '';
  }
}

async function loadStudentPage() {
  qs("studentPageView").innerHTML = '<div class="empty-state"><span class="spinner"></span> 加载中...</div>';
  try {
    const dashboard = await api("/teacher/dashboard");
    state.studentPageData = dashboard;
    renderStudentList(dashboard);
  } catch (e) {
    qs("studentPageView").innerHTML = '<div class="empty-state">加载失败</div>';
  }
}

async function loadQuestionBank() {
  const items = await api("/teacher/question-bank");
  renderQuestionBank(items);
}

async function loadPendingQuestions() {
  try {
    const items = await api("/teacher/question-bank/pending");
    renderPendingQuestions(items);
  } catch { }
}

async function loadPracticeReviews() {
  const status = qs("practiceReviewStatus")?.value || "pending";
  const items = await api(`/teacher/practice-reviews?status=${encodeURIComponent(status)}`);
  renderPracticeReviews(items);
}

async function loadDocuments() {
  const grade = qs("documentFilterGrade")?.value || "";
  const subject = qs("documentFilterSubject")?.value || "";
  if (!grade || !subject) {
    state.documents = [];
    renderDocumentLibrary();
    return;
  }
  const query = new URLSearchParams({ grade_level: grade, subject });
  state.documents = await api(`/teacher/documents?${query.toString()}`);
  renderDocumentLibrary();
}

function onFileSelected() {
  const input = qs("uploadDocumentFile");
  const dropZone = qs("dropZone");
  if (!input || !dropZone) return;
  if (input.files && input.files.length) {
    const file = input.files[0];
    const sizeKB = (file.size / 1024).toFixed(1);
    const sizeMB = (file.size / 1024 / 1024).toFixed(1);
    const sizeText = file.size > 1024 * 1024 ? `${sizeMB} MB` : `${sizeKB} KB`;
    dropZone.classList.add("has-file");
    dropZone.innerHTML = `
      <div class="drop-zone-icon">📄</div>
      <div><strong>${escapeHtml(file.name)}</strong> (${sizeText})</div>
      <div style="font-size:12px;color:#8f959e;margin-top:4px;">点击重新选择</div>
      <input id="uploadDocumentFile" type="file" accept=".txt,.md,.markdown,.pdf,.docx" style="display:none;">
    `;
    const newInput = dropZone.querySelector("#uploadDocumentFile");
    const dt = new DataTransfer();
    dt.items.add(file);
    newInput.files = dt.files;
    newInput.addEventListener("change", onFileSelected);
  }
}

function resetDropZone() {
  const dropZone = qs("dropZone");
  if (!dropZone) return;
  dropZone.classList.remove("has-file");
  dropZone.innerHTML = `
    <div class="drop-zone-icon">📂</div>
    <div>拖拽文件到此处，或点击选择</div>
    <input id="uploadDocumentFile" type="file" accept=".txt,.md,.markdown,.pdf,.docx" style="display:none;">
  `;
  const newInput = dropZone.querySelector("#uploadDocumentFile");
  if (newInput) newInput.addEventListener("change", onFileSelected);
}

async function uploadDocument() {
  const fileInput = qs("uploadDocumentFile");
  const resultEl = qs("uploadDocumentResult");
  if (resultEl) resultEl.innerHTML = "";
  if (!fileInput.files || !fileInput.files.length) {
    showToast("请先选择文件");
    return;
  }
  const grade = qs("uploadDocumentGrade").value;
  const subject = qs("uploadDocumentSubject").value;
  if (!grade || !subject) {
    showToast("请先选择年级和学科");
    return;
  }
  const form = new FormData();
  form.append("file", fileInput.files[0]);
  form.append("grade_level", grade);
  form.append("subject", subject);
  form.append("doc_type", qs("uploadDocumentDocType").value || "reference");
  form.append("title", qs("uploadDocumentTitle").value || "");
  form.append("source_name", qs("uploadDocumentSource").value || "");

  qs("uploadDocumentButton").disabled = true;
  qs("uploadDocumentButton").textContent = "上传中...";
  try {
    const document = await api("/teacher/documents/upload", { method: "POST", body: form });
    if (resultEl) {
      resultEl.innerHTML = `
        <div class="helper-card">
          <strong>资料上传成功</strong>
          <p>《${escapeHtml(document.title)}》已完成上传和索引。</p>
          <p>范围：${escapeHtml(document.grade_level || grade)} · ${escapeHtml(document.subject || subject)} · ${escapeHtml(friendlyDocType(document.doc_type))}</p>
        </div>
      `;
    }
    showToast(`已上传：${document.title}`);
    resetDropZone();
    qs("uploadDocumentTitle").value = "";
    qs("uploadDocumentSource").value = "";
    const filterGrade = qs("documentFilterGrade");
    const filterSubject = qs("documentFilterSubject");
    if (filterGrade && filterSubject) {
      filterGrade.value = grade;
      if (typeof filterGrade.onchange === "function") filterGrade.onchange();
      filterSubject.value = subject;
      if (typeof filterSubject.onchange === "function") filterSubject.onchange();
    }
    await loadDocuments();
  } catch (error) {
    if (resultEl) {
      resultEl.innerHTML = `
        <div class="helper-card">
          <strong>资料上传失败</strong>
          <p>${escapeHtml(error.message)}</p>
        </div>
      `;
    }
    showToast(error.message);
  } finally {
    qs("uploadDocumentButton").disabled = false;
    qs("uploadDocumentButton").textContent = "上传并索引";
  }
}

async function deleteDocument(documentId) {
  await api(`/teacher/documents/${documentId}`, { method: "DELETE" });
  showToast("资料已删除");
  await loadDocuments();
}

async function generateQuestions() {
  if (!getTeacherGrades().length) {
    showToast("请先创建班级后再生成题目");
    return;
  }
  const selectedTopic = qs("generateTopicId").value;
  const topicId = selectedTopic;

  if (!topicId) {
    showToast("请选择知识点");
    return;
  }

  const count = parseInt(qs("generateCount").value) || 5;
  const category = qs("generateCategory").value;
  const questionType = qs("generateQuestionType").value;
  const includeExplanation = qs("toggleExplanation").classList.contains("on");
  const includeAnswerSheet = qs("toggleAnswerSheet").classList.contains("on");

  const diffMap = { basic: [1, 2], regular: [2, 4], comprehensive: [4, 5] };
  const [diffMin, diffMax] = diffMap[category] || diffMap.regular;
  const topic = state.topics.find((item) => item.id === topicId);
  const parentL1Id = topic?.parent_id || null;

  qs("generateQuestionsButton").disabled = true;
  qs("generateQuestionsButton").innerHTML = '<span class="spinner"></span> 生成中...';

  try {
    const result = await api("/teacher/question-bank/generate", {
      method: "POST",
      body: JSON.stringify({
        knowledge_l2_id: topicId,
        knowledge_l1_id: parentL1Id,
        count: count,
        difficulty_level_min: diffMin,
        difficulty_level_max: diffMax,
        question_type: questionType,
        include_explanation: includeExplanation,
        include_answer_sheet: includeAnswerSheet,
      }),
    });
    await loadPendingQuestions();
    await loadQuestionBank();
    showToast(`${result.generated_count} 道题目已生成，待审核`);
    navigateTo("question-review");
  } catch (error) {
    showToast(`生成失败: ${error.message}`);
  } finally {
    qs("generateQuestionsButton").disabled = false;
    qs("generateQuestionsButton").innerHTML = '🤖 开始生成';
  }
}

async function reviewQuestion(questionId, action) {
  try {
    await api("/teacher/question-bank/review", {
      method: "POST",
      body: JSON.stringify({ question_ids: [questionId], action: action }),
    });
    showToast(action === "approve" ? "已通过 ✓" : "已拒绝");
    await loadPendingQuestions();
    await loadQuestionBank();
  } catch (error) {
    showToast(`操作失败: ${error.message}`);
  }
}

async function reviewSelected(action) {
  const ids = [...state.pendingSelectedIds];
  if (!ids.length) {
    showToast("请先选择题目");
    return;
  }
  try {
    await api("/teacher/question-bank/review", {
      method: "POST",
      body: JSON.stringify({ question_ids: ids, action: action }),
    });
    showToast(`${action === "approve" ? "通过" : "拒绝"} ${ids.length} 道题目 ✓`);
    await loadPendingQuestions();
    await loadQuestionBank();
  } catch (error) {
    showToast(`操作失败: ${error.message}`);
  }
}

async function resolvePracticeReview(recordId, isCorrect, score) {
  const feedback = qs(`reviewFeedback${recordId}`)?.value?.trim() || "";
  await api(`/teacher/practice-reviews/${recordId}`, {
    method: "POST",
    body: JSON.stringify({ is_correct: isCorrect, score, feedback }),
  });
  showToast("复核已保存，掌握度已更新");
  await loadPracticeReviews();
  await loadTeacherDashboard();
}

async function downloadExcelTemplate() {
  const grade = qs("excelImportGrade").value;
  const subject = qs("excelImportSubject").value;
  if (!grade || !subject) {
    showToast("请先选择年级和学科");
    return;
  }
  const response = await fetch(`/teacher/question-bank/excel-template?grade_level=${encodeURIComponent(grade)}&subject=${encodeURIComponent(subject)}`, {
    headers: { "X-Session-Token": state.token },
  });
  if (!response.ok) {
    throw new Error(await extractErrorMessage(response));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `题目导入模板_${grade}_${subject}.xlsx`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  showToast("模板已下载");
}

async function importExcel() {
  const grade = qs("excelImportGrade").value;
  const subject = qs("excelImportSubject").value;
  const fileInput = qs("excelFileInput");
  if (!grade || !subject) {
    showToast("请先选择年级和学科");
    return;
  }
  if (!fileInput.files || !fileInput.files.length) {
    showToast("请先选择 Excel 文件");
    return;
  }
  const form = new FormData();
  form.append("file", fileInput.files[0]);
  form.append("grade_level", grade);
  form.append("subject", subject);
  qs("importExcelButton").disabled = true;
  qs("importExcelButton").textContent = "导入中...";
  const resultEl = qs("excelImportResult");
  if (resultEl) resultEl.innerHTML = "";
  try {
    const result = await api("/teacher/question-bank/import-excel", {
      method: "POST",
      body: form,
    });
    const failedRows = Array.isArray(result.failed_rows) ? result.failed_rows : [];
    const visibleFailures = failedRows.slice(0, 8);
    const failureList = visibleFailures.length
      ? `
        <div style="margin-top:10px;">
          <strong style="display:block;margin-bottom:6px;">失败明细</strong>
          <ul style="margin:0;padding-left:18px;color:#646a73;">
            ${visibleFailures.map((item) => `
              <li style="margin:4px 0;">第 ${item.row_number} 行：${escapeHtml(item.reason)}${item.stem_preview ? `（${escapeHtml(item.stem_preview)}）` : ""}</li>
            `).join("")}
          </ul>
          ${failedRows.length > visibleFailures.length ? `<p style="margin-top:6px;">仅显示前 ${visibleFailures.length} 条失败记录。</p>` : ""}
        </div>
      `
      : "<p>所有非空题目行都已通过校验。</p>";
    if (resultEl) {
      resultEl.innerHTML = `
        <div class="helper-card">
          <strong>Excel 导入结果</strong>
          <p>成功导入 ${result.imported_count} 道题目，失败 ${result.skipped_count} 道。</p>
          ${failureList}
        </div>
      `;
    }
    showToast(`Excel 导入成功 ${result.imported_count} 道，失败 ${result.skipped_count} 道`);
    fileInput.value = "";
    await loadPendingQuestions();
    await loadQuestionBank();
  } catch (error) {
    if (resultEl) {
      resultEl.innerHTML = `
        <div class="helper-card">
          <strong>Excel 导入失败</strong>
          <p>${escapeHtml(error.message)}</p>
        </div>
      `;
    }
    showToast(error.message);
  } finally {
    qs("importExcelButton").disabled = false;
    qs("importExcelButton").textContent = "导入 Excel";
  }
}

async function rebuildEmbeddings() {
  const updated = await api("/teacher/documents/rebuild-embeddings", { method: "POST" });
  showToast(`已重建 ${updated} 条索引 ✓`);
  await loadDocuments();
}

async function searchDocuments() {
  const grade = qs("docSearchGrade").value;
  const subject = qs("docSearchSubject").value;
  if (!grade || !subject) {
    showToast("请先选择年级和学科");
    return;
  }
  const hits = await api("/teacher/documents/search", {
    method: "POST",
    body: JSON.stringify({
      query: qs("docSearchInput").value,
      grade_level: grade,
      subject: subject,
      limit: 5,
      strategy: qs("docSearchStrategy").value,
    }),
  });
  renderDocumentSearch(hits);
  showToast(`搜索到 ${hits.length} 条结果 ✓`);
}

function bindEvents() {
  bindClick("showTeacherLoginButton", () => toggleTeacherAuthForm("login"));
  bindClick("loginButton", () => login().catch(handleError));
  bindClick("reloadTeacherButton", () => loadTeacherDashboard().catch(handleError));
  bindClick("reloadStudentsButton", () => loadStudentPage().catch(handleError));
  bindChange("studentSearchInput", () => renderStudentList(state.studentPageData || { students: [] }));
  bindClick("createClassroomButton", () => createClassroom().catch(handleError));
  bindClick("reloadClassroomsButton", () => loadClassrooms().catch(handleError));
  const classroomsView = qs("teacherClassroomsView");
  if (classroomsView) {
    classroomsView.addEventListener("click", (event) => {
      const copyButton = event.target.closest(".copy-invite-button");
      if (copyButton) { copyInviteCode(copyButton.dataset.inviteCode).catch(handleError); return; }
      const refreshButton = event.target.closest(".refresh-invite-button");
      if (refreshButton) refreshInviteCode(refreshButton.dataset.classroomId).catch(handleError);
    });
  }
  bindClick("reloadAnalyticsButton", () => loadTeacherDashboard().catch(handleError));
  bindClick("generateQuestionsButton", () => generateQuestions().catch(handleError));
  bindClick("toggleExplanation", () => qs("toggleExplanation").classList.toggle("on"));
  bindClick("toggleAnswerSheet", () => qs("toggleAnswerSheet").classList.toggle("on"));
  bindChange("analyticsTimeFilter", () => loadTeacherDashboard().catch(handleError));
  bindClick("loadPendingButton", () => loadPendingQuestions().catch(handleError));
  bindClick("selectPendingAllButton", selectAllPending);
  bindClick("selectPendingNoneButton", selectNonePending);
  bindClick("approveSelectedButton", () => reviewSelected("approve").catch(handleError));
  bindClick("rejectSelectedButton", () => reviewSelected("reject").catch(handleError));
  bindClick("downloadExcelTemplateButton", () => downloadExcelTemplate().catch(handleError));
  bindClick("importExcelButton", () => importExcel().catch(handleError));
  bindClick("reloadPracticeReviewsButton", () => loadPracticeReviews().catch(handleError));
  bindChange("practiceReviewStatus", () => loadPracticeReviews().catch(handleError));
  bindClick("reloadQuestionBankButton", () => loadQuestionBank().catch(handleError));
  bindChange("qbGradeFilter", () => { state.qbGrade = qs("qbGradeFilter").value; renderQuestionBank(state.qbItems); });
  bindChange("qbTypeFilter", () => { state.qbType = qs("qbTypeFilter").value; renderQuestionBank(state.qbItems); });
  bindChange("qbStatusFilter", () => { state.qbStatus = qs("qbStatusFilter").value; renderQuestionBank(state.qbItems); });
  bindClick("qbSearchButton", () => { state.qbSearch = qs("qbSearchInput").value.trim(); renderQuestionBank(state.qbItems); });
  bindClick("qbResetButton", () => {
    state.qbSubject = ""; state.qbGrade = ""; state.qbType = ""; state.qbStatus = ""; state.qbSearch = "";
    const searchInput = qs("qbSearchInput");
    if (searchInput) searchInput.value = "";
    if (qs("qbGradeFilter")) qs("qbGradeFilter").value = "";
    if (qs("qbTypeFilter")) qs("qbTypeFilter").value = "";
    if (qs("qbStatusFilter")) qs("qbStatusFilter").value = "";
    renderQuestionBank(state.qbItems);
  });
  bindClick("rebuildEmbeddingsButton", () => rebuildEmbeddings().catch(handleError));
  bindClick("uploadDocumentButton", () => uploadDocument().catch(handleError));
  bindChange("uploadDocumentFile", onFileSelected);
  const dropZone = qs("dropZone");
  if (dropZone) {
    dropZone.addEventListener("click", () => {
      const input = qs("uploadDocumentFile");
      if (input) input.click();
    });
    dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.classList.add("drag-over"); });
    dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.classList.remove("drag-over");
      const file = e.dataTransfer.files[0];
      if (file) {
        const input = qs("uploadDocumentFile");
        const dt = new DataTransfer();
        dt.items.add(file);
        input.files = dt.files;
        onFileSelected();
      }
    });
  }
  bindClick("reloadDocumentsButton", () => loadDocuments().catch(handleError));
  bindChange("documentFilterGrade", () => loadDocuments().catch(handleError));
  bindChange("documentFilterSubject", () => loadDocuments().catch(handleError));
  bindChange("documentFilterDocType", renderDocumentLibrary);
  bindClick("searchDocsButton", () => searchDocuments().catch(handleError));
  bindClick("searchStrategyHelpFab", toggleSearchHelp);
  bindClick("searchStrategyHelpClose", toggleSearchHelp);
  const searchHelpModal = qs("searchStrategyHelpModal");
  if (searchHelpModal) {
    searchHelpModal.addEventListener("click", (event) => {
      if (event.target === searchHelpModal) toggleSearchHelp();
    });
  }

  document.querySelectorAll(".rag-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.activeRagTab = tab.dataset.ragTab;
      document.querySelectorAll(".rag-tab").forEach((item) => item.classList.toggle("active", item.dataset.ragTab === state.activeRagTab));
      document.querySelectorAll(".rag-panel").forEach((panel) => panel.classList.toggle("active", panel.dataset.ragPanel === state.activeRagTab));
      syncSearchHelpVisibility();
    });
  });

  bindClick("modalStayButton", hideModal);
  bindClick("modalGoReviewButton", () => {
    hideModal();
    navigateTo("question-review");
  });

  bindClick("studentDrawerClose", closeStudentDrawer);
  const drawerOverlay = qs("studentDrawerOverlay");
  if (drawerOverlay) drawerOverlay.addEventListener("click", closeStudentDrawer);

  document.querySelectorAll(".nav-btn[data-page]").forEach((item) => {
    item.addEventListener("click", () => navigateTo(item.dataset.page));
  });
}

function handleError(error) {
  console.error(error);
  showToast(`操作失败: ${error.message}`);
}

async function bootstrap() {
  bindEvents();
  const mode = new URLSearchParams(window.location.search).get("mode");
  if (mode === "register") toggleTeacherAuthForm("register");
  await loadTopics();
  await loadSchools();
  if (state.token) {
    try {
      state.user = await api("/auth/me");
      qs("authStatus").textContent = `${state.user.full_name}`;
      showAppMain();
      await loadTeacherDashboard();
      await loadStudentPage();
      await loadClassrooms();
      await loadQuestionBank();
      await loadPendingQuestions();
      await loadPracticeReviews();
      await loadDocuments();
      syncSearchHelpVisibility();
    } catch {
      localStorage.removeItem("zhuyu_token");
      state.token = "";
      showLoginGate();
    }
  } else {
    showLoginGate();
  }
}

bootstrap().catch(handleError);
