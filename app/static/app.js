const state = {
  token: localStorage.getItem("zhuyu_token") || "",
  user: null,
  topics: [],
  students: [],
  currentStudentId: null,
  dashboard: null,
  lastQuestion: null,
  currentSessionId: null,
  activeStep: "auth",
  teacherDashboard: null,
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

function setStep(step) {
  state.activeStep = step;
  document.querySelectorAll(".step-chip").forEach((item) => {
    item.classList.toggle("active", item.dataset.step === step);
  });
  document.querySelectorAll(".stage").forEach((item) => {
    item.classList.toggle("active", item.dataset.stage === step);
  });
  const hints = {
    teacher: "现在重点看：老师如何管理多个学生",
    auth: "从“登录与学生”开始",
    diagnosis: "现在重点看：当前学生先补什么",
    practice: "现在重点看：推荐题、讲题卡片和相似题",
    tutor: "现在重点看：连续对话是否能回看",
    report: "现在重点看：报告是否适合学生回看",
    history: "现在重点看：错题和会话是否被持久化",
    resources: "现在重点看：题库、资料导入和检索评测是否可用",
  };
  qs("currentStepHint").textContent = hints[step] || "";
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

function currentStudent() {
  return state.students.find((item) => item.id === Number(state.currentStudentId));
}

function masteryPayloadFromCards() {
  const payload = {};
  document.querySelectorAll(".mastery-card").forEach((card) => {
    const topicId = card.dataset.topicId;
    payload[topicId] = {
      topic_id: topicId,
      mastery: Number(card.querySelector(".mastery-input").value),
      practice_count: Number(card.querySelector(".practice-input").value),
      correct_count: Number(card.querySelector(".correct-input").value),
      last_practiced_at: "2026-04-06",
      recent_errors: [],
    };
  });
  return payload;
}

function renderStudentHeader(profile) {
  qs("studentNameHeading").textContent = `${profile.name} 的学习工作台`;
  qs("studentMeta").textContent = `${profile.grade_level} · ${profile.target_subject} · 目标知识点 ${profile.target_topic_id}`;
}

function renderMastery(profile) {
  const container = qs("masteryCards");
  const mastery = profile.mastery || {};
  container.innerHTML = state.topics.map((topic) => {
    const row = mastery[topic.id] || {
      mastery: 0.5,
      practice_count: 0,
      correct_count: 0,
    };
    return `
      <article class="mastery-card" data-topic-id="${topic.id}">
        <div class="mastery-top">
          <div>
            <strong>${topic.name}</strong>
            <div class="hint">${topic.subject} · 目标：${topic.learning_objectives[0] || "概念掌握"}</div>
          </div>
          <div class="badge">当前掌握度 ${(row.mastery * 100).toFixed(0)}%</div>
        </div>
        <div class="progress-track"><div class="progress-fill" style="width:${row.mastery * 100}%"></div></div>
        <div class="stats-row">
          <label><span>掌握度</span><input class="mastery-input" type="number" min="0" max="1" step="0.01" value="${row.mastery}"></label>
          <label><span>练习数</span><input class="practice-input" type="number" min="0" value="${row.practice_count}"></label>
          <label><span>正确数</span><input class="correct-input" type="number" min="0" value="${row.correct_count}"></label>
        </div>
      </article>
    `;
  }).join("");
}

function renderDiagnosis(data) {
  qs("diagnosisView").innerHTML = `
    <div class="summary-block">
      <div class="stat-card"><strong>准备度</strong><div>${(data.readiness_score * 100).toFixed(0)}%</div></div>
      <div class="stat-card"><strong>总结</strong><div>${data.summary}</div></div>
      <div>
        <strong>薄弱点</strong>
        <div class="action-list">${data.weak_topics.map((item) => `<span class="badge">${item}</span>`).join("") || "<span class='hint'>暂无</span>"}</div>
      </div>
      <div>
        <strong>学习路径</strong>
        <div class="timeline">
          ${data.learning_path.map((item) => `
            <div class="timeline-item">
              <strong>${item.topic_name}</strong>
              <div>${item.reason}</div>
              <small>${item.recommended_action}</small>
            </div>
          `).join("")}
        </div>
      </div>
    </div>
  `;
  setStep("diagnosis");
}

function renderPractice(data) {
  state.lastQuestion = data.question;
  qs("practiceView").innerHTML = `
    <div class="summary-block">
      <div class="badge">推荐难度 ${data.recommended_band}</div>
      <div class="stat-card"><strong>推荐原因</strong><div>${data.selection_reason}</div></div>
      <div class="stat-card"><strong>题目</strong><div>${data.question.stem}</div></div>
      <div class="report-grid">
        <div class="note-card"><strong>正确答案</strong><div>${data.question.answer}</div></div>
        <div class="note-card"><strong>题目解析</strong><div>${data.question.explanation}</div></div>
      </div>
    </div>
  `;
  setStep("practice");
}

function renderCoachCard(data) {
  qs("coachCardView").innerHTML = `
    <div class="summary-block">
      <div class="stat-card"><strong>解题主线</strong><div>${data.strategy_summary}</div></div>
      <div>
        <strong>分步提示</strong>
        <div class="timeline">
          ${data.step_cards.map((item) => `
            <div class="timeline-item">
              <strong>${item.title}</strong>
              <div>${item.content}</div>
            </div>
          `).join("")}
        </div>
      </div>
      <div>
        <strong>易错提醒</strong>
        <div class="action-list">${data.misconception_alerts.map((item) => `<span class="badge">${item}</span>`).join("") || "<span class='hint'>暂无</span>"}</div>
      </div>
      <div>
        <strong>相似题</strong>
        <div class="timeline">
          ${data.similar_questions.map((item) => `
            <div class="timeline-item">
              <strong>${item.stem}</strong>
              <small>${item.recommendation_reason} · 难度 ${item.difficulty}</small>
            </div>
          `).join("") || "<div class='empty-state'>当前题库里暂无更多相似题</div>"}
        </div>
      </div>
      <div>
        <strong>下一轮刷题建议</strong>
        <div class="timeline">${data.next_drills.map((item) => `<div class="timeline-item">${item}</div>`).join("")}</div>
      </div>
    </div>
  `;
}

function renderMistake(data) {
  qs("mistakeView").innerHTML = `
    <div class="summary-block">
      <div class="badge">${data.category}</div>
      <div class="stat-card"><strong>错因说明</strong><div>${data.explanation}</div></div>
      <div>
        <strong>纠正建议</strong>
        <div class="timeline">
          ${data.correction_advice.map((item) => `<div class="timeline-item">${item}</div>`).join("")}
        </div>
      </div>
    </div>
  `;
  setStep("practice");
}

function renderNotebook(records) {
  qs("mistakeNotebook").innerHTML = records.length ? records.map((item) => `
    <div class="timeline-item">
      <strong>${item.topic_name}</strong>
      <div>${item.question_stem}</div>
      <small>错误类型：${item.category}</small>
      <div class="hint">学生作答：${item.student_answer}</div>
    </div>
  `).join("") : "<div class='empty-state'>还没有错题记录</div>";
}

function renderReport(report) {
  if (!report) {
    qs("reportView").innerHTML = "还没有学习报告";
    return;
  }
  qs("reportView").innerHTML = `
    <div class="summary-block">
      <div class="report-grid">
        <div class="stat-card"><strong>整体掌握度</strong><div>${(report.overall_mastery * 100).toFixed(0)}%</div></div>
        <div class="stat-card"><strong>生成时间</strong><div>${new Date(report.created_at).toLocaleString()}</div></div>
      </div>
      <div class="stat-card"><strong>诊断摘要</strong><div>${report.diagnostic_summary}</div></div>
      <div class="report-grid">
        <div class="note-card"><strong>优势主题</strong><div>${report.strong_topics.join("、") || "暂无"}</div></div>
        <div class="note-card"><strong>薄弱主题</strong><div>${report.weak_topics.join("、") || "暂无"}</div></div>
      </div>
      <div>
        <strong>下一步动作</strong>
        <div class="timeline">${report.next_actions.map((item) => `<div class="timeline-item">${item}</div>`).join("")}</div>
      </div>
      <div>
        <strong>复习计划</strong>
        <div class="review-list">
          ${report.review_plan.map((item) => `<div class="timeline-item"><strong>${item.review_date}</strong><div>${item.activity}</div></div>`).join("")}
        </div>
      </div>
    </div>
  `;
  setStep("report");
}

function renderSessions(sessions) {
  qs("sessionList").innerHTML = sessions.length ? sessions.map((item) => `
    <div class="timeline-item">
      <strong>${item.title}</strong>
      <small>${new Date(item.updated_at).toLocaleString()}</small>
    </div>
  `).join("") : "<div class='empty-state'>还没有对话历史</div>";

  qs("chatSessionSelect").innerHTML = sessions.map((item) => `
    <option value="${item.id}">${item.title}</option>
  `).join("");
  if (!state.currentSessionId && sessions[0]) state.currentSessionId = sessions[0].id;
  if (state.currentSessionId) qs("chatSessionSelect").value = state.currentSessionId;
}

function renderChat(history) {
  qs("chatHistory").innerHTML = history.length ? history.map((item) => `
    <article class="message ${item.role}">
      <div class="message-role">${item.role === "assistant" ? "AI 导师" : "学生"}</div>
      <div>${item.content}</div>
      ${item.citations?.length ? `<div class="evidence-list">${item.citations.map((c) => `<span class="badge">${c}</span>`).join("")}</div>` : ""}
    </article>
  `).join("") : "<div class='empty-state'>新建一个对话开始辅导</div>";
}

async function loadTopics() {
  state.topics = await api("/graph/topics");
  const options = state.topics.map((topic) => `<option value="${topic.id}">${topic.name}</option>`).join("");
  qs("targetTopicId").innerHTML = options;
  qs("chatTopicId").innerHTML = options;
  qs("docSearchTopicId").innerHTML = `<option value="">全部主题</option>${options}`;
  qs("evalTopicId").innerHTML = `<option value="">全部主题</option>${options}`;
}

async function login() {
  const data = await api("/auth/login", {
    method: "POST",
    body: JSON.stringify({
      email: qs("loginEmail").value,
      password: qs("loginPassword").value,
    }),
  });
  state.token = data.token;
  state.user = data.user;
  localStorage.setItem("zhuyu_token", state.token);
  qs("authStatus").textContent = `已登录：${data.user.full_name}`;
  showToast("登录成功");
  await loadStudents();
  setStep("auth");
}

async function loadStudents() {
  state.students = await api("/students");
  if (!state.students.length) return;
  qs("studentSelect").innerHTML = state.students.map((item) => `<option value="${item.id}">${item.name}</option>`).join("");
  state.currentStudentId = state.currentStudentId || state.students[0].id;
  qs("studentSelect").value = state.currentStudentId;
  await loadDashboard();
  await loadTeacherDashboard();
}

async function loadDashboard() {
  if (!state.currentStudentId) return;
  const dashboard = await api(`/students/${state.currentStudentId}/dashboard`);
  state.dashboard = dashboard;
  renderStudentHeader(dashboard.profile);
  renderMastery(dashboard.profile);
  renderNotebook(dashboard.recent_mistakes);
  renderReport(dashboard.latest_report);
  renderSessions(dashboard.recent_sessions);
  qs("targetTopicId").value = dashboard.profile.target_topic_id;
  qs("chatTopicId").value = dashboard.profile.target_topic_id;
  if (state.currentSessionId) {
    await loadHistory(state.currentSessionId);
  } else {
    renderChat([]);
  }
}

function renderTeacherDashboard(data) {
  qs("teacherSummaryView").innerHTML = `
    <div class="summary-block">
      <div class="report-grid">
        <div class="stat-card"><strong>学生总数</strong><div>${data.total_students}</div></div>
        <div class="stat-card"><strong>活跃学生</strong><div>${data.active_students}</div></div>
        <div class="stat-card"><strong>平均掌握度</strong><div>${(data.average_mastery * 100).toFixed(0)}%</div></div>
        <div class="stat-card"><strong>平均正确率</strong><div>${(data.average_accuracy * 100).toFixed(0)}%</div></div>
      </div>
    </div>
  `;
  qs("teacherStudentsView").innerHTML = data.students.length ? data.students.map((item) => `
    <div class="timeline-item">
      <strong>${item.name}</strong>
      <div>${item.grade_level} · 目标 ${item.target_topic_id}</div>
      <small>掌握度 ${(item.overall_mastery * 100).toFixed(0)}% · 正确率 ${(item.recent_practice_accuracy * 100).toFixed(0)}% · 错题 ${item.recent_mistake_count}</small>
    </div>
  `).join("") : "<div class='empty-state'>暂无学生</div>";
}

function renderPracticeAnalytics(data) {
  qs("practiceAnalyticsView").innerHTML = `
    <div class="summary-block">
      <div class="report-grid">
        <div class="stat-card"><strong>总练习数</strong><div>${data.total_attempts}</div></div>
        <div class="stat-card"><strong>总正确数</strong><div>${data.correct_attempts}</div></div>
        <div class="stat-card"><strong>整体正确率</strong><div>${(data.accuracy * 100).toFixed(0)}%</div></div>
      </div>
      <div class="timeline">
        ${data.topics.map((item) => `
          <div class="timeline-item">
            <strong>${item.topic_id}</strong>
            <div>练习 ${item.attempt_count} 次 · 正确率 ${(item.accuracy * 100).toFixed(0)}%</div>
            <small>平均作答时长 ${item.avg_duration_seconds} 秒</small>
          </div>
        `).join("") || "<div class='empty-state'>暂无练习记录</div>"}
      </div>
    </div>
  `;
}

function renderRetrievalQuality(data) {
  qs("retrievalQualityView").innerHTML = `
    <div class="summary-block">
      <div class="report-grid">
        ${data.strategies.map((item) => `
          <div class="stat-card">
            <strong>${item.strategy}</strong>
            <div>Hit@1 ${(item.hit_at_1 * 100).toFixed(0)}%</div>
            <div>Hit@3 ${(item.hit_at_3 * 100).toFixed(0)}%</div>
            <div>MRR ${item.mrr.toFixed(2)}</div>
          </div>
        `).join("")}
      </div>
      <div class="timeline">
        ${data.cases.map((item) => `
          <div class="timeline-item">
            <strong>${item.label}</strong>
            <div>${item.query}</div>
            <small>目标 ${item.expected_topic_id || "全部"} / ${item.expected_doc_type || "全部"} · 最优 ${item.best_strategy}</small>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

async function loadTeacherDashboard() {
  const dashboard = await api("/teacher/dashboard");
  state.teacherDashboard = dashboard;
  renderTeacherDashboard(dashboard);
  const analytics = await api("/teacher/analytics/practice");
  renderPracticeAnalytics(analytics);
  const quality = await api("/teacher/retrieval-quality");
  renderRetrievalQuality(quality);
}

async function saveMastery() {
  const profile = await api(`/students/${state.currentStudentId}/mastery`, {
    method: "PUT",
    body: JSON.stringify({ mastery: masteryPayloadFromCards() }),
  });
  if (state.dashboard) state.dashboard.profile = profile;
  renderMastery(profile);
  showToast("掌握度已保存");
  setStep("auth");
}

async function runDiagnosis() {
  const data = await api(`/students/${state.currentStudentId}/diagnosis`, {
    method: "POST",
    body: JSON.stringify({ target_topic_id: qs("targetTopicId").value }),
  });
  renderDiagnosis(data);
  showToast("诊断完成");
}

async function runPractice() {
  const data = await api(`/students/${state.currentStudentId}/practice`, {
    method: "POST",
    body: JSON.stringify({ topic_id: qs("targetTopicId").value }),
  });
  renderPractice(data);
  await loadCoachCard();
  showToast("已推荐下一题");
}

async function loadCoachCard() {
  if (!state.lastQuestion) {
    showToast("请先推荐题目");
    return;
  }
  const card = await api(`/students/${state.currentStudentId}/practice/coach-card`, {
    method: "POST",
    body: JSON.stringify({
      question_id: state.lastQuestion.id,
      student_answer: qs("mistakeAnswer").value || null,
    }),
  });
  renderCoachCard(card);
}

async function submitPracticeResult(answer = null) {
  if (!state.lastQuestion) {
    showToast("请先推荐题目");
    return;
  }
  return api(`/students/${state.currentStudentId}/practice/submit`, {
    method: "POST",
    body: JSON.stringify({
      question_id: state.lastQuestion.id,
      student_answer: answer ?? qs("mistakeAnswer").value,
      duration_seconds: 75,
    }),
  });
}

async function analyzeMistake() {
  if (!state.lastQuestion) {
    showToast("请先推荐题目");
    return;
  }
  await submitPracticeResult();
  const record = await api(`/students/${state.currentStudentId}/mistakes/analyze`, {
    method: "POST",
    body: JSON.stringify({
      question_id: state.lastQuestion.id,
      student_answer: qs("mistakeAnswer").value,
      scratchpad: "页面回放输入",
    }),
  });
  renderMistake(record);
  await reloadMistakes();
  await loadTeacherDashboard();
  showToast("错题已保存");
}

async function reloadMistakes() {
  const records = await api(`/students/${state.currentStudentId}/mistakes`);
  renderNotebook(records);
}

async function createSession() {
  const session = await api(`/students/${state.currentStudentId}/chat/sessions`, {
    method: "POST",
    body: JSON.stringify({ title: "函数辅导对话" }),
  });
  state.currentSessionId = session.id;
  await reloadSessions();
  renderChat([]);
  showToast("已创建新对话");
  setStep("tutor");
}

async function reloadSessions() {
  const sessions = await api(`/students/${state.currentStudentId}/chat/sessions`);
  renderSessions(sessions);
}

async function loadHistory(sessionId) {
  const history = await api(`/chat/sessions/${sessionId}`);
  renderChat(history);
  setStep("tutor");
}

async function sendChat() {
  if (!state.currentSessionId) {
    await createSession();
  }
  const turn = await api(`/chat/sessions/${state.currentSessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({
      topic_id: qs("chatTopicId").value,
      content: qs("chatInput").value,
      difficulty_signal: Number(qs("difficultySignal").value),
    }),
  });
  renderChat(turn.history);
  await reloadSessions();
  qs("chatInput").value = "";
  showToast("辅导回复已生成");
  setStep("tutor");
}

async function generateReport() {
  const report = await api(`/students/${state.currentStudentId}/reports/generate`, {
    method: "POST",
    body: JSON.stringify({ target_topic_id: qs("targetTopicId").value }),
  });
  renderReport(report);
  showToast("学习报告已保存");
}

async function reloadReport() {
  const report = await api(`/students/${state.currentStudentId}/reports/latest`);
  renderReport(report);
}

function renderQuestionBank(items) {
  qs("questionBankView").innerHTML = items.length ? items.map((item) => `
    <div class="timeline-item">
      <strong>${item.topic_id}</strong>
      <div>${item.stem}</div>
      <small>难度 ${item.difficulty} · 题号 ${item.external_id}</small>
    </div>
  `).join("") : "<div class='empty-state'>题库为空</div>";
}

function renderDocumentSearch(items) {
  qs("documentSearchView").innerHTML = items.length ? items.map((item) => `
    <div class="timeline-item">
      <strong>${item.document_title}</strong>
      <div>${item.snippet}</div>
      <small>${item.doc_type} · ${item.source_name} · 综合分 ${item.score}</small>
      <div class="hint">lexical=${item.lexical_score ?? 0} · sparse=${item.vector_score ?? 0} · dense=${item.dense_score ?? 0} · rerank=${item.rerank_score ?? 0}</div>
    </div>
  `).join("") : "<div class='empty-state'>没有检索到结果</div>";
}

function renderDirectoryImport(data) {
  qs("directoryImportView").innerHTML = data.files.length ? data.files.map((item) => `
    <div class="timeline-item">
      <strong>${item.title}</strong>
      <div>${item.file_path}</div>
      <small>${item.doc_type} · ${item.topic_id || "未识别主题"} · ${item.imported ? "已导入" : `跳过：${item.reason}`}</small>
    </div>
  `).join("") : "<div class='empty-state'>没有导入记录</div>";
}

function renderRetrievalEvaluation(data) {
  qs("retrievalEvaluationView").innerHTML = `
    <div class="summary-block">
      <div class="stat-card"><strong>当前最优策略</strong><div>${data.best_strategy}</div></div>
      <div class="timeline">
        ${data.strategies.map((item) => `
          <div class="timeline-item">
            <strong>${item.strategy}</strong>
            <div>Hit@1 ${item.hit_at_1 ? "命中" : "未命中"} · Hit@3 ${item.hit_at_3 ? "命中" : "未命中"} · MRR ${item.mrr}</div>
            <small>${item.hits[0] ? `${item.hits[0].document_title} / ${item.hits[0].doc_type} / 分数 ${item.hits[0].score}` : "没有结果"}</small>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

async function loadQuestionBank() {
  const items = await api("/teacher/question-bank");
  renderQuestionBank(items);
}

async function importSampleQuestions() {
  const payload = {
    questions: [
      {
        id: "q_lf_02",
        topic_id: "linear_functions",
        stem: "已知一次函数 y=-2x+5，写出它的斜率和截距。",
        difficulty: 0.68,
        answer: "斜率是-2，截距是5",
        explanation: "与 y=kx+b 对照即可。",
        tags: ["斜率", "截距"]
      },
      {
        id: "q_fun_04",
        topic_id: "functions",
        stem: "函数关系中，哪一个量先确定，另一个量再随之变化？",
        difficulty: 0.42,
        answer: "先确定自变量",
        explanation: "自变量的取值确定后，因变量才跟着确定。",
        tags: ["概念"]
      }
    ]
  };
  const items = await api("/teacher/question-bank/import", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  renderQuestionBank(items);
  showToast("示例题库已导入");
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
          content: "学习一次函数时，先认出 y=kx+b 的结构，再区分 k 控制倾斜，b 控制纵轴交点。"
        },
        {
          title: "函数概念题解模板",
          topic_id: "functions",
          doc_type: "solution",
          source_name: "题解模板集",
          content: "函数概念题先问输入和输出，再看两者是不是唯一对应。把抽象关系翻译成生活场景最容易理解。"
        }
      ]
    }),
  });
  showToast("示例文档已导入");
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
  showToast(`已导入 ${result.imported_count} 个文件`);
}

async function rebuildEmbeddings() {
  const updated = await api("/teacher/documents/rebuild-embeddings", {
    method: "POST",
  });
  showToast(`已重建 ${updated} 条向量`);
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
  setStep("resources");
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
  setStep("resources");
}

function bindEvents() {
  document.querySelectorAll(".step-chip").forEach((item) => {
    item.addEventListener("click", () => setStep(item.dataset.step));
  });
  qs("loginButton").addEventListener("click", () => login().catch(handleError));
  qs("studentSelect").addEventListener("change", async (event) => {
    state.currentStudentId = Number(event.target.value);
    state.currentSessionId = null;
    await loadDashboard().catch(handleError);
  });
  qs("reloadDashboardButton").addEventListener("click", () => loadDashboard().catch(handleError));
  qs("saveMasteryButton").addEventListener("click", () => saveMastery().catch(handleError));
  qs("diagnosisButton").addEventListener("click", () => runDiagnosis().catch(handleError));
  qs("practiceButton").addEventListener("click", () => runPractice().catch(handleError));
  qs("mistakeButton").addEventListener("click", () => analyzeMistake().catch(handleError));
  qs("createSessionButton").addEventListener("click", () => createSession().catch(handleError));
  qs("sendChatButton").addEventListener("click", () => sendChat().catch(handleError));
  qs("generateReportButton").addEventListener("click", () => generateReport().catch(handleError));
  qs("reloadReportButton").addEventListener("click", () => reloadReport().catch(handleError));
  qs("reloadMistakesButton").addEventListener("click", () => reloadMistakes().catch(handleError));
  qs("reloadSessionsButton").addEventListener("click", () => reloadSessions().catch(handleError));
  qs("reloadTeacherButton").addEventListener("click", () => loadTeacherDashboard().catch(handleError));
  qs("reloadAnalyticsButton").addEventListener("click", () => loadTeacherDashboard().catch(handleError));
  qs("reloadRetrievalQualityButton").addEventListener("click", () => loadTeacherDashboard().catch(handleError));
  qs("importQuestionsButton").addEventListener("click", () => importSampleQuestions().catch(handleError));
  qs("importDocsButton").addEventListener("click", () => importSampleDocuments().catch(handleError));
  qs("importDirectoryButton").addEventListener("click", () => importDirectory().catch(handleError));
  qs("rebuildEmbeddingsButton").addEventListener("click", () => rebuildEmbeddings().catch(handleError));
  qs("searchDocsButton").addEventListener("click", () => searchDocuments().catch(handleError));
  qs("evaluateSearchButton").addEventListener("click", () => evaluateRetrieval().catch(handleError));
  qs("coachCardButton").addEventListener("click", () => loadCoachCard().catch(handleError));
  qs("chatSessionSelect").addEventListener("change", (event) => {
    state.currentSessionId = Number(event.target.value);
    loadHistory(state.currentSessionId).catch(handleError);
  });
}

function handleError(error) {
  console.error(error);
  showToast("操作失败，请查看控制台");
}

async function bootstrap() {
  bindEvents();
  setStep("auth");
  await loadTopics();
  if (state.token) {
    try {
      state.user = await api("/auth/me");
      qs("authStatus").textContent = `已登录：${state.user.full_name}`;
      await loadStudents();
      await loadQuestionBank();
    } catch {
      localStorage.removeItem("zhuyu_token");
      state.token = "";
    }
  }
}

bootstrap().catch(handleError);
