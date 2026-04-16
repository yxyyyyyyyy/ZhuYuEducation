const state = {
  token: localStorage.getItem("zhuyu_token") || "",
  user: null,
  topics: [],
  activePage: "dashboard",
  pendingSelectedIds: new Set(),
  documents: [],
  retrievalCases: [],
  retrievalRun: null,
  activeRagTab: "library",
  practiceReviews: [],
  schools: [],
  classrooms: [],
  studentSort: "name",
  dashboardData: null,
  analyticsData: null,
  generateTemplates: JSON.parse(localStorage.getItem("zhuyu_generate_templates") || "[]"),
};

function qs(id) {
  return document.getElementById(id);
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
    csv_import: "CSV 导入",
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
}

async function api(path, options = {}) {
  const isFormData = options.body instanceof FormData;
  const headers = { ...(isFormData ? {} : { "Content-Type": "application/json" }), ...(options.headers || {}) };
  if (state.token) headers["X-Session-Token"] = state.token;
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

function formatDateTime(value) {
  if (!value) return "暂无时间";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function leafTopics() {
  const parentIds = new Set(state.topics.map((t) => t.parent_id).filter(Boolean));
  return state.topics.filter((t) => !parentIds.has(t.id));
}

function getSubjects() {
  return [...new Set(leafTopics().map((t) => t.subject).filter(Boolean))].sort();
}

function getGradesBySubject(subject) {
  return [...new Set(leafTopics().filter((t) => t.subject === subject).map((t) => t.grade_level).filter(Boolean))].sort();
}

function getTopicsBySubjectAndGrade(subject, grade) {
  return leafTopics().filter((t) => t.subject === subject && (!grade || t.grade_level === grade));
}

function initCascade(prefix, opts = {}) {
  const subjectEl = qs(prefix + "Subject");
  const gradeEl = qs(prefix + "Grade");
  const topicEl = qs(prefix + "TopicId");
  if (!subjectEl || !gradeEl || !topicEl) {
    console.warn("initCascade skip:", prefix, !!subjectEl, !!gradeEl, !!topicEl);
    return;
  }

  const subjectPlaceholder = opts.subjectPlaceholder || "学科";
  const gradePlaceholder = opts.gradePlaceholder || "年级";
  const topicPlaceholder = opts.topicPlaceholder || "知识点";

  const subjects = getSubjects();
  subjectEl.innerHTML = `<option value="">${subjectPlaceholder}</option>` +
    subjects.map((s) => `<option value="${s}">${s}</option>`).join("");
  gradeEl.innerHTML = `<option value="">${gradePlaceholder}</option>`;
  topicEl.innerHTML = `<option value="">${topicPlaceholder}</option>`;

  subjectEl.onchange = () => {
    const subject = subjectEl.value;
    if (!subject) {
      gradeEl.innerHTML = `<option value="">${gradePlaceholder}</option>`;
      topicEl.innerHTML = `<option value="">${topicPlaceholder}</option>`;
      return;
    }
    const grades = getGradesBySubject(subject);
    gradeEl.innerHTML = `<option value="">${gradePlaceholder}</option>` +
      grades.map((g) => `<option value="${g}">${g}</option>`).join("");
    const topics = getTopicsBySubjectAndGrade(subject, "");
    topicEl.innerHTML = `<option value="">${topicPlaceholder}</option>` +
      topics.map((t) => `<option value="${t.id}">${t.name}</option>`).join("");
  };

  gradeEl.onchange = () => {
    const subject = subjectEl.value;
    const grade = gradeEl.value;
    const topics = getTopicsBySubjectAndGrade(subject, grade);
    topicEl.innerHTML = `<option value="">${topicPlaceholder}</option>` +
      topics.map((t) => `<option value="${t.id}">${t.name}</option>`).join("");
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

  renderStudentList(data);
}

function renderStudentList(data) {
  const topicMap = {};
  state.topics.forEach((t) => { topicMap[t.id] = t.name; });

  qs("studentListHeader").innerHTML = `
    <select id="studentSortSelect" style="width:auto;min-width:110px;padding:4px 8px;font-size:12px;">
      <option value="name" ${state.studentSort === "name" ? "selected" : ""}>按姓名</option>
      <option value="mastery" ${state.studentSort === "mastery" ? "selected" : ""}>按掌握度</option>
      <option value="accuracy" ${state.studentSort === "accuracy" ? "selected" : ""}>按正确率</option>
    </select>
  `;

  let students = [...(data.students || [])];
  if (state.studentSort === "mastery") students.sort((a, b) => b.overall_mastery - a.overall_mastery);
  else if (state.studentSort === "accuracy") students.sort((a, b) => b.recent_practice_accuracy - a.recent_practice_accuracy);
  else students.sort((a, b) => (a.name || "").localeCompare(b.name || "", "zh"));

  if (!students.length) {
    qs("teacherStudentsView").innerHTML = "<div class='empty-state'>暂无学生数据，创建班级后学生注册即可显示</div>";
    return;
  }

  qs("teacherStudentsView").innerHTML = students.map((item) => {
    const masteryPct = (item.overall_mastery * 100).toFixed(0);
    const accuracyPct = (item.recent_practice_accuracy * 100).toFixed(0);
    const barClass = item.overall_mastery < 0.4 ? "progress-low" : item.overall_mastery < 0.7 ? "progress-mid" : "progress-high";
    return `
      <div class="student-card" data-student-name="${item.name || ""}">
        <div class="student-left">
          <div class="student-name">${item.name || "未命名"}</div>
          <div class="student-meta">${item.grade_level || "-"} · ${topicMap[item.target_topic_id] || item.target_topic_id || "-"}</div>
        </div>
        <div class="student-right">
          <div class="student-stat">
            <div class="student-stat-value" style="color:${item.overall_mastery < 0.4 ? "#d54941" : item.overall_mastery < 0.7 ? "#f7a440" : "#2ba471"}">${masteryPct}%</div>
            <div class="student-stat-label">掌握度</div>
          </div>
          <div class="progress-bar-wrap"><div class="progress-bar-fill ${barClass}" style="width:${masteryPct}%"></div></div>
          <div class="student-stat">
            <div class="student-stat-value" style="color:#8b5cf6">${accuracyPct}%</div>
            <div class="student-stat-label">正确率</div>
          </div>
        </div>
      </div>
    `;
  }).join("");

  qs("studentSortSelect").addEventListener("change", () => {
    state.studentSort = qs("studentSortSelect").value;
    renderStudentList(state.dashboardData);
  });
}

function renderPracticeAnalytics(data) {
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
  const topicMap = {};
  state.topics.forEach((t) => { topicMap[t.id] = t.name; });
  qs("questionBankView").innerHTML = items.length ? `<table class="q-table"><thead><tr><th>知识点</th><th>题目</th><th>答案</th><th>解析</th><th>类型</th><th>难度</th><th>来源</th></tr></thead><tbody>${items.map((item) => `
    <tr>
      <td class="q-topic">${topicMap[item.topic_id] || item.topic_id}</td>
      <td class="q-stem">${item.stem}${renderQuestionPreview(item)}</td>
      <td class="q-answer">${item.answer}</td>
      <td class="q-explain">${item.explanation || "-"}</td>
      <td>${friendlyQuestionType(item.question_type)}</td>
      <td>${friendlyDifficulty(item.difficulty)}</td>
      <td>${friendlySource(item.source)}</td>
    </tr>
  `).join("")}</tbody></table>` : "<div class='empty-state'>题库为空</div>";
}

function renderPendingQuestions(items) {
  state.pendingSelectedIds = new Set();
  if (!items.length) {
    qs("pendingQuestionsView").innerHTML = "<div class='empty-state'>暂无待审核题目 🎉</div>";
    return;
  }
  const topicMap = {};
  state.topics.forEach((t) => { topicMap[t.id] = t.name; });
  qs("pendingQuestionsView").innerHTML = items.map((item) => `
    <div class="timeline-item" data-question-id="${item.id}" style="display:flex;gap:10px;align-items:flex-start;">
      <input type="checkbox" class="pending-checkbox" data-id="${item.id}" style="margin-top:4px;width:18px;height:18px;cursor:pointer;flex-shrink:0;">
      <div style="flex:1;">
        <strong>[${topicMap[item.topic_id] || item.topic_id}] ${item.stem}</strong>
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

function renderRagOverview() {
  const docs = state.documents || [];
  const docCount = docs.length;
  const chunkCount = docs.reduce((sum, item) => sum + (item.chunk_count || 0), 0);
  const readyCount = docs.reduce((sum, item) => sum + (item.embedding_ready_count || 0), 0);
  const recent = docs[0];
  const run = state.retrievalRun;
  qs("ragOverviewView").innerHTML = `
    <div class="rag-stat-grid">
      <div class="stat-card"><strong>资料总数</strong><div>${docCount}</div></div>
      <div class="stat-card"><strong>片段数量</strong><div>${chunkCount}</div></div>
      <div class="stat-card"><strong>已向量化</strong><div>${readyCount}/${chunkCount || 0}</div></div>
      <div class="stat-card"><strong>评测命中</strong><div>${run ? `${Math.round(run.hit_at_1 * 100)}%` : "未运行"}</div></div>
    </div>
    <div class="helper-card rag-overview-note">
      <strong>最近资料</strong>
      <p>${recent ? `${recent.title} · ${friendlyDocType(recent.doc_type)} · ${formatDateTime(recent.created_at)}` : "还没有导入资料，先上传一份讲义或题解。"}</p>
    </div>
  `;
}

function renderDocumentLibrary() {
  const topicFilter = qs("documentFilterTopicId").value;
  const typeFilter = qs("documentFilterDocType").value;
  const docs = (state.documents || []).filter((item) => {
    const topicOk = !topicFilter || item.topic_id === topicFilter;
    const typeOk = !typeFilter || item.doc_type === typeFilter;
    return topicOk && typeOk;
  });
  qs("documentLibraryView").innerHTML = docs.length ? docs.map((item) => {
    const ready = item.embedding_ready_count || 0;
    const total = item.chunk_count || 0;
    const preview = (item.chunk_previews || []).map((chunk) => `
      <details class="chunk-preview">
        <summary>片段 ${chunk.chunk_index + 1} · ${chunk.embedding_ready ? "已向量化" : "未向量化"}</summary>
        <div>${chunk.content}</div>
      </details>
    `).join("");
    return `
      <article class="timeline-item document-item" data-document-id="${item.id}">
        <div class="document-row-top">
          <div>
            <strong>${item.title}</strong>
            <div>${friendlyDocType(item.doc_type)} · ${topicName(item.topic_id)} · ${item.source_name}</div>
            <small>${formatDateTime(item.created_at)} · 索引 ${ready}/${total}</small>
          </div>
          ${item.can_delete
            ? `<button class="ghost-button delete-document-button" data-document-id="${item.id}">删除</button>`
            : `<span class="badge">共享资料</span>`}
        </div>
        <div class="document-preview">${item.content_preview || "暂无预览"}</div>
        ${preview}
      </article>
    `;
  }).join("") : "<div class='empty-state'>暂无符合筛选条件的资料</div>";

  qs("documentLibraryView").querySelectorAll(".delete-document-button").forEach((button) => {
    button.addEventListener("click", () => deleteDocument(Number(button.dataset.documentId)).catch(handleError));
  });
  renderRagOverview();
}

function renderDocumentSearch(items) {
  qs("documentSearchView").innerHTML = items.length ? items.map((item) => `
    <div class="timeline-item search-hit-card">
      <strong>${item.document_title}</strong>
      <div>${item.snippet}</div>
      <small>${friendlyDocType(item.doc_type)} · ${item.source_name} · 相关度 ${Number(item.score).toFixed(3)}</small>
      <div class="score-breakdown-line">
        <span>关键词 ${Number(item.lexical_score || 0).toFixed(3)}</span>
        <span>向量 ${Number(item.vector_score || 0).toFixed(3)}</span>
        <span>Dense ${Number(item.dense_score || 0).toFixed(3)}</span>
        <span>Rerank ${Number(item.rerank_score || 0).toFixed(3)}</span>
      </div>
    </div>
  `).join("") : "<div class='empty-state'>没有搜索到相关内容</div>";
}

function renderDirectoryImport(data) {
  qs("directoryImportView").innerHTML = data.files.length ? data.files.map((item) => `
    <div class="timeline-item">
      <strong>${item.title}</strong>
      <div>${item.file_path}</div>
      <small>${friendlyDocType(item.doc_type)} · ${item.imported ? "✅ 已导入" : `⏭️ 跳过：${item.reason}`}</small>
    </div>
  `).join("") : "<div class='empty-state'>没有导入记录</div>";
}

function renderRetrievalEvaluation(data) {
  qs("retrievalEvaluationView").innerHTML = `
    <div class="summary-block">
      <div class="stat-card"><strong>最优搜索方式</strong><div>${friendlyStrategy(data.best_strategy)}</div></div>
      <div class="timeline">
        ${data.strategies.map((item) => `<div class="timeline-item"><strong>${friendlyStrategy(item.strategy)}</strong><div>命中首位 ${item.hit_at_1 ? "✅" : "❌"} · 命中前三 ${item.hit_at_3 ? "✅" : "❌"} · MRR ${item.mrr.toFixed(2)}</div></div>`).join("")}
      </div>
    </div>
  `;
}

function renderRetrievalCases() {
  qs("retrievalCaseListView").innerHTML = state.retrievalCases.length ? state.retrievalCases.map((item) => `
    <div class="timeline-item retrieval-case-item">
      <div class="document-row-top">
        <div>
          <strong>${item.label}</strong>
          <div>${item.query}</div>
          <small>${topicName(item.expected_topic_id)} · ${friendlyDocType(item.expected_doc_type)} · ${formatDateTime(item.created_at)}</small>
        </div>
        <button class="ghost-button delete-case-button" data-case-id="${item.id}">删除</button>
      </div>
    </div>
  `).join("") : "<div class='empty-state'>暂无评测题</div>";

  qs("retrievalCaseListView").querySelectorAll(".delete-case-button").forEach((button) => {
    button.addEventListener("click", () => deleteRetrievalCase(Number(button.dataset.caseId)).catch(handleError));
  });
}

function renderRetrievalCaseRun(data) {
  state.retrievalRun = data;
  renderRagOverview();
  qs("retrievalEvaluationView").innerHTML = data.total_cases ? `
    <div class="summary-block">
      <div class="report-grid">
        <div class="stat-card"><strong>评测题数</strong><div>${data.total_cases}</div></div>
        <div class="stat-card"><strong>Hit@1</strong><div>${Math.round(data.hit_at_1 * 100)}%</div></div>
        <div class="stat-card"><strong>Hit@3</strong><div>${Math.round(data.hit_at_3 * 100)}%</div></div>
        <div class="stat-card"><strong>MRR</strong><div>${Number(data.mrr).toFixed(2)}</div></div>
      </div>
      <div class="timeline">
        ${data.cases.map((item) => {
          const best = item.strategies.find((strategy) => strategy.strategy === item.best_strategy) || item.strategies[0];
          return `<div class="timeline-item">
            <strong>${item.label}</strong>
            <div>${item.query}</div>
            <small>最优 ${friendlyStrategy(item.best_strategy)} · Hit@1 ${best?.hit_at_1 ? "是" : "否"} · Hit@3 ${best?.hit_at_3 ? "是" : "否"} · MRR ${Number(best?.mrr || 0).toFixed(2)}</small>
          </div>`;
        }).join("")}
      </div>
    </div>
  ` : "<div class='empty-state'>还没有评测题，先添加一条固定问题。</div>";
}

async function loadTopics() {
  try {
    state.topics = await api("/graph/topics");
  } catch (e) {
    console.error("loadTopics failed:", e);
    state.topics = [];
  }
  console.log("topics loaded:", state.topics.length, "subjects:", getSubjects());
  initCascade("generate");
  initCascade("uploadDocument");
  initCascade("documentFilter");
  initCascade("docSearch");
  initCascade("case");
  initCascade("eval");
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
    await loadClassrooms();
    await loadQuestionBank();
    await loadPendingQuestions();
    await loadPracticeReviews();
    await loadDocuments();
    await loadRetrievalCases();
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
  state.documents = await api("/teacher/documents");
  renderDocumentLibrary();
}

async function uploadDocument() {
  const fileInput = qs("uploadDocumentFile");
  if (!fileInput.files || !fileInput.files.length) {
    showToast("请先选择文件");
    return;
  }
  const form = new FormData();
  form.append("file", fileInput.files[0]);
  form.append("topic_id", qs("uploadDocumentTopicId").value || "");
  form.append("doc_type", qs("uploadDocumentDocType").value || "reference");
  form.append("title", qs("uploadDocumentTitle").value || "");
  form.append("source_name", qs("uploadDocumentSource").value || "");

  qs("uploadDocumentButton").disabled = true;
  qs("uploadDocumentButton").textContent = "上传中...";
  try {
    const document = await api("/teacher/documents/upload", { method: "POST", body: form });
    showToast(`已上传：${document.title}`);
    fileInput.value = "";
    qs("uploadDocumentTitle").value = "";
    qs("uploadDocumentSource").value = "";
    await loadDocuments();
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

async function loadRetrievalCases() {
  state.retrievalCases = await api("/teacher/retrieval-cases");
  renderRetrievalCases();
}

async function addRetrievalCase() {
  const label = qs("caseLabelInput").value.trim();
  const query = qs("caseQueryInput").value.trim();
  if (!label || !query) {
    showToast("请填写用例名称和测试问题");
    return;
  }
  await api("/teacher/retrieval-cases", {
    method: "POST",
    body: JSON.stringify({
      label,
      query,
      expected_topic_id: qs("caseTopicId").value || null,
      expected_doc_type: qs("caseDocType").value || null,
    }),
  });
  qs("caseLabelInput").value = "";
  qs("caseQueryInput").value = "";
  showToast("评测题已添加");
  await loadRetrievalCases();
}

async function deleteRetrievalCase(caseId) {
  await api(`/teacher/retrieval-cases/${caseId}`, { method: "DELETE" });
  showToast("评测题已删除");
  await loadRetrievalCases();
}

async function runRetrievalCases() {
  const result = await api("/teacher/retrieval-cases/run", { method: "POST" });
  renderRetrievalCaseRun(result);
  showToast("评测集已运行");
}

async function generateQuestions() {
  const manualTopic = qs("generateTopicManual").value.trim();
  const selectedTopic = qs("generateTopicId").value;
  const topicId = manualTopic || selectedTopic;

  if (!topicId) {
    showToast("请选择或输入知识点");
    return;
  }

  const count = parseInt(qs("generateCount").value) || 5;
  const difficulty = qs("generateDifficulty").value;
  const questionType = qs("generateQuestionType").value;
  const includeExplanation = qs("toggleExplanation").classList.contains("on");
  const includeAnswerSheet = qs("toggleAnswerSheet").classList.contains("on");

  const diffMap = { low: [1, 2], medium: [2, 4], high: [4, 5] };
  const [diffMin, diffMax] = diffMap[difficulty] || diffMap.medium;
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

function saveGenerateTemplate() {
  const name = window.prompt("请输入模板名称", `${qs("generateSubject").value || "通用"}-${qs("generateDifficulty").value}`);
  if (!name) return;
  const template = {
    name,
    subject: qs("generateSubject").value,
    grade: qs("generateGrade").value,
    topicId: qs("generateTopicId").value,
    difficulty: qs("generateDifficulty").value,
    count: qs("generateCount").value,
    questionType: qs("generateQuestionType").value,
    includeExplanation: qs("toggleExplanation").classList.contains("on"),
    includeAnswerSheet: qs("toggleAnswerSheet").classList.contains("on"),
  };
  state.generateTemplates.push(template);
  localStorage.setItem("zhuyu_generate_templates", JSON.stringify(state.generateTemplates));
  refreshTemplateSelect();
  showToast("模板已保存");
}

function applyGenerateTemplate() {
  const idx = qs("templateSelect").value;
  if (!idx) return;
  const template = state.generateTemplates[parseInt(idx)];
  if (!template) return;
  if (template.subject) qs("generateSubject").value = template.subject;
  if (template.grade) qs("generateGrade").value = template.grade;
  if (template.topicId) qs("generateTopicId").value = template.topicId;
  qs("generateDifficulty").value = template.difficulty || "medium";
  qs("generateCount").value = template.count || 5;
  qs("generateQuestionType").value = template.questionType || "blank";
  qs("toggleExplanation").classList.toggle("on", template.includeExplanation !== false);
  qs("toggleAnswerSheet").classList.toggle("on", !!template.includeAnswerSheet);
  showToast("模板已应用");
}

function deleteGenerateTemplate() {
  const idx = qs("templateSelect").value;
  if (!idx) return;
  state.generateTemplates.splice(parseInt(idx), 1);
  localStorage.setItem("zhuyu_generate_templates", JSON.stringify(state.generateTemplates));
  refreshTemplateSelect();
  showToast("模板已删除");
}

function refreshTemplateSelect() {
  const section = qs("templateSection");
  const select = qs("templateSelect");
  if (!state.generateTemplates.length) {
    section.style.display = "none";
    return;
  }
  section.style.display = "";
  select.innerHTML = "<option value=''>选择模板...</option>" + state.generateTemplates.map((t, i) => `<option value="${i}">${t.name}</option>`).join("");
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

async function downloadCsvTemplate() {
  const response = await fetch("/teacher/question-bank/csv-template", {
    headers: { "X-Session-Token": state.token },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `下载失败: ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "question_template.csv";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  showToast("模板已下载");
}

async function importCsv() {
  const fileInput = qs("csvFileInput");
  if (!fileInput.files || !fileInput.files.length) {
    showToast("请先选择 CSV 文件");
    return;
  }
  const file = fileInput.files[0];
  const csvContent = await file.text();
  try {
    const result = await api("/teacher/question-bank/import-csv", {
      method: "POST",
      body: csvContent,
      headers: { "Content-Type": "text/plain" },
    });
    qs("csvImportResult").innerHTML = `
      <div class="helper-card">
        <strong>导入结果</strong>
        <p>✅ 成功导入 ${result.imported_count} 道题目，⏭️ 跳过 ${result.skipped_count} 道</p>
      </div>
    `;
    showToast(`导入 ${result.imported_count} 道，跳过 ${result.skipped_count} 道 ✓`);
    await loadPendingQuestions();
    await loadQuestionBank();
    fileInput.value = "";
  } catch (error) {
    showToast(`导入失败: ${error.message}`);
  }
}

async function importSampleDocuments() {
  await api("/teacher/documents/import", {
    method: "POST",
    body: JSON.stringify({
      documents: [
        {
          title: "一次函数课堂笔记",
          topic_id: "linear_functions",
          doc_type: "handout",
          source_name: "课堂讲义 B2",
          content: "学习一次函数时，先认出 y=kx+b 的结构，再区分 k 控制倾斜，b 控制纵轴交点。",
        },
        {
          title: "函数概念题解模板",
          topic_id: "functions",
          doc_type: "solution",
          source_name: "题解模板集",
          content: "函数概念题先问输入和输出，再看两者是不是唯一对应。把抽象关系翻译成生活场景最容易理解。",
        },
      ],
    }),
  });
  showToast("示例文档已导入 ✓");
  await loadDocuments();
}

async function importDirectory() {
  const result = await api("/teacher/documents/import-directory", {
    method: "POST",
    body: JSON.stringify({
      directory_path: qs("directoryPathInput").value,
      doc_type: qs("directoryDocType").value || null,
      recursive: true,
      limit: 50,
    }),
  });
  renderDirectoryImport(result);
  showToast(`已导入 ${result.imported_count} 个文件 ✓`);
  await loadDocuments();
}

async function rebuildEmbeddings() {
  const updated = await api("/teacher/documents/rebuild-embeddings", { method: "POST" });
  showToast(`已重建 ${updated} 条索引 ✓`);
  await loadDocuments();
}

async function searchDocuments() {
  const hits = await api("/teacher/documents/search", {
    method: "POST",
    body: JSON.stringify({
      query: qs("docSearchInput").value,
      topic_id: qs("docSearchTopicId").value || null,
      limit: 5,
      strategy: qs("docSearchStrategy").value,
    }),
  });
  renderDocumentSearch(hits);
  showToast(`搜索到 ${hits.length} 条结果 ✓`);
}

async function evaluateRetrieval() {
  const result = await api("/teacher/documents/evaluate", {
    method: "POST",
    body: JSON.stringify({
      query: qs("evalQueryInput").value,
      topic_id: qs("evalTopicId").value || null,
      expected_topic_id: qs("evalTopicId").value || null,
      expected_doc_type: qs("evalDocType").value || null,
      limit: 5,
    }),
  });
  renderRetrievalEvaluation(result);
  showToast("对比完成 ✓");
}

function bindEvents() {
  qs("showTeacherLoginButton").addEventListener("click", () => toggleTeacherAuthForm("login"));
  qs("loginButton").addEventListener("click", () => login().catch(handleError));
  qs("reloadTeacherButton").addEventListener("click", () => loadTeacherDashboard().catch(handleError));
  qs("createClassroomButton").addEventListener("click", () => createClassroom().catch(handleError));
  qs("reloadClassroomsButton").addEventListener("click", () => loadClassrooms().catch(handleError));
  qs("teacherClassroomsView").addEventListener("click", (event) => {
    const copyButton = event.target.closest(".copy-invite-button");
    if (copyButton) { copyInviteCode(copyButton.dataset.inviteCode).catch(handleError); return; }
    const refreshButton = event.target.closest(".refresh-invite-button");
    if (refreshButton) refreshInviteCode(refreshButton.dataset.classroomId).catch(handleError);
  });
  qs("reloadAnalyticsButton").addEventListener("click", () => loadTeacherDashboard().catch(handleError));
  qs("generateQuestionsButton").addEventListener("click", () => generateQuestions().catch(handleError));
  qs("saveTemplateButton").addEventListener("click", saveGenerateTemplate);
  qs("applyTemplateButton").addEventListener("click", applyGenerateTemplate);
  qs("deleteTemplateButton").addEventListener("click", deleteGenerateTemplate);
  qs("toggleExplanation").addEventListener("click", () => qs("toggleExplanation").classList.toggle("on"));
  qs("toggleAnswerSheet").addEventListener("click", () => qs("toggleAnswerSheet").classList.toggle("on"));
  qs("analyticsTimeFilter").addEventListener("change", () => loadTeacherDashboard().catch(handleError));
  qs("loadPendingButton").addEventListener("click", () => loadPendingQuestions().catch(handleError));
  qs("selectPendingAllButton").addEventListener("click", selectAllPending);
  qs("selectPendingNoneButton").addEventListener("click", selectNonePending);
  qs("approveSelectedButton").addEventListener("click", () => reviewSelected("approve").catch(handleError));
  qs("rejectSelectedButton").addEventListener("click", () => reviewSelected("reject").catch(handleError));
  qs("importCsvButton").addEventListener("click", () => importCsv().catch(handleError));
  qs("downloadTemplateButton").addEventListener("click", () => downloadCsvTemplate().catch(handleError));
  qs("reloadPracticeReviewsButton").addEventListener("click", () => loadPracticeReviews().catch(handleError));
  qs("practiceReviewStatus").addEventListener("change", () => loadPracticeReviews().catch(handleError));
  qs("reloadQuestionBankButton").addEventListener("click", () => loadQuestionBank().catch(handleError));
  qs("importDocsButton").addEventListener("click", () => importSampleDocuments().catch(handleError));
  qs("importDirectoryButton").addEventListener("click", () => importDirectory().catch(handleError));
  qs("rebuildEmbeddingsButton").addEventListener("click", () => rebuildEmbeddings().catch(handleError));
  qs("uploadDocumentButton").addEventListener("click", () => uploadDocument().catch(handleError));
  qs("reloadDocumentsButton").addEventListener("click", () => loadDocuments().catch(handleError));
  qs("documentFilterTopicId").addEventListener("change", renderDocumentLibrary);
  qs("documentFilterGrade").addEventListener("change", renderDocumentLibrary);
  qs("documentFilterSubject").addEventListener("change", renderDocumentLibrary);
  qs("documentFilterDocType").addEventListener("change", renderDocumentLibrary);
  qs("searchDocsButton").addEventListener("click", () => searchDocuments().catch(handleError));
  qs("evaluateSearchButton").addEventListener("click", () => evaluateRetrieval().catch(handleError));
  qs("addRetrievalCaseButton").addEventListener("click", () => addRetrievalCase().catch(handleError));
  qs("runRetrievalCasesButton").addEventListener("click", () => runRetrievalCases().catch(handleError));

  qs("generateSubject").addEventListener("change", () => {});
  document.querySelectorAll(".rag-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.activeRagTab = tab.dataset.ragTab;
      document.querySelectorAll(".rag-tab").forEach((item) => item.classList.toggle("active", item.dataset.ragTab === state.activeRagTab));
      document.querySelectorAll(".rag-panel").forEach((panel) => panel.classList.toggle("active", panel.dataset.ragPanel === state.activeRagTab));
    });
  });

  qs("modalStayButton").addEventListener("click", hideModal);
  qs("modalGoReviewButton").addEventListener("click", () => {
    hideModal();
    navigateTo("question-review");
  });

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
  refreshTemplateSelect();
  if (state.token) {
    try {
      state.user = await api("/auth/me");
      qs("authStatus").textContent = `${state.user.full_name}`;
      showAppMain();
      await loadTeacherDashboard();
      await loadClassrooms();
      await loadQuestionBank();
      await loadPendingQuestions();
      await loadPracticeReviews();
      await loadDocuments();
      await loadRetrievalCases();
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
