const state = {
  token: localStorage.getItem("zhuyu_token") || "",
  user: null,
  topics: [],
  students: [],
  currentStudentId: null,
  dashboard: null,
  lastQuestion: null,
  lastPracticeMeta: null,
  lastSubmission: null,
  lastCoachCard: null,
  currentSessionId: null,
  reportHistory: [],
  mistakeRecords: [],
  similarQuestionIndex: 0,
  similarSwipeStartX: null,
  activePage: "profile",
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

function toggleAuthForm(mode) {
  qs("loginForm").style.display = mode === "login" ? "" : "none";
  qs("registerForm").style.display = mode === "register" ? "" : "none";
  qs("showLoginFormButton").className = mode === "login" ? "primary-button" : "ghost-button";
  qs("showRegisterFormButton").className = mode === "register" ? "primary-button" : "ghost-button";
}

function navigateTo(page) {
  state.activePage = page;
  document.querySelectorAll(".nav-item[data-page]").forEach((item) => {
    item.classList.toggle("active", item.dataset.page === page);
  });
  document.querySelectorAll(".page-section").forEach((section) => {
    section.classList.toggle("active", section.dataset.page === page);
  });
  if (page === "mistakes" && state.currentStudentId) {
    loadMistakes().catch(handleError);
  }
}

function setGraphExpanded(expanded) {
  document.querySelectorAll("#knowledgeGraphView details").forEach((item) => {
    item.open = expanded;
  });
}

function openGraphSubject(subject) {
  navigateTo("graph");
  document.querySelectorAll("#knowledgeGraphView .kg-subject-block").forEach((block) => {
    const title = block.querySelector("h3")?.textContent || "";
    block.open = title === subject;
    if (title === subject) {
      block.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
}

function setStep(step) {
  const pageMap = { auth: "profile", graph: "graph", diagnosis: "diagnosis", practice: "practice", mistakes: "mistakes", tutor: "tutor", report: "report" };
  navigateTo(pageMap[step] || step);
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

function renderQuickStats(profile) {
  const topic = currentTopic(profile.target_topic_id);
  const masteryValues = Object.values(profile.mastery || {});
  const overallMastery = masteryValues.length
    ? `${Math.round((masteryValues.reduce((sum, item) => sum + item.mastery, 0) / masteryValues.length) * 100)}%`
    : "0%";
  const totalPractice = masteryValues.reduce((sum, item) => sum + (item.practice_count || 0), 0);
  const totalCorrect = masteryValues.reduce((sum, item) => sum + (item.correct_count || 0), 0);
  qs("quickStatsContent").innerHTML = `
    <div class="report-grid">
      <div class="stat-card"><strong>学生</strong><div>${profile.name}</div></div>
      <div class="stat-card"><strong>年级</strong><div>${profile.grade_level}</div></div>
      <div class="stat-card"><strong>目标</strong><div>${topic?.name || profile.target_topic_id}</div></div>
      <div class="stat-card"><strong>平均掌握度</strong><div>${overallMastery}</div></div>
      <div class="stat-card"><strong>累计练习</strong><div>${totalPractice} 题</div></div>
      <div class="stat-card"><strong>答对</strong><div>${totalCorrect} 题</div></div>
    </div>
  `;
  qs("quickStatsCard").style.display = "";
}

function topicsBySubject() {
  const groups = [];
  const groupMap = {};
  state.topics.forEach((topic) => {
    const subject = topic.subject || "其他";
    if (!groupMap[subject]) {
      groupMap[subject] = { subject, topics: [] };
      groups.push(groupMap[subject]);
    }
    groupMap[subject].topics.push(topic);
  });
  return groups;
}

function masteryValue(topicId, masteryMap) {
  return (masteryMap[topicId] && masteryMap[topicId].mastery) || 0;
}

function subjectSummary(topics, masteryMap) {
  const rows = topics.map((topic) => masteryMap[topic.id] || { mastery: 0, practice_count: 0, correct_count: 0 });
  const mastery = rows.length ? rows.reduce((sum, row) => sum + (row.mastery || 0), 0) / rows.length : 0;
  const practiceCount = rows.reduce((sum, row) => sum + (row.practice_count || 0), 0);
  const correctCount = rows.reduce((sum, row) => sum + (row.correct_count || 0), 0);
  const correctRate = practiceCount ? Math.round((correctCount / practiceCount) * 100) : null;
  return { mastery, practiceCount, correctCount, correctRate };
}

function renderMastery(profile) {
  const mastery = profile.mastery || {};
  qs("masteryCards").innerHTML = topicsBySubject().map((group) => {
    const summary = subjectSummary(group.topics, mastery);
    const parentTopics = group.topics
      .filter((topic) => topic.level === 2 || !topic.parent_id)
      .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
    return `
      <details class="subject-mastery-block" open>
        <summary class="subject-mastery-head">
          <div>
            <div class="subject-kicker">一级知识点</div>
            <h3>${group.subject}</h3>
            <div class="hint">${group.topics.length} 个二级知识点 · 练习 ${summary.practiceCount} 题 · 正确率 ${summary.correctRate === null ? "暂无记录" : `${summary.correctRate}%`}</div>
          </div>
          <div class="subject-score">${Math.round(summary.mastery * 100)}%</div>
        </summary>
        <div class="progress-track"><div class="progress-fill" style="width:${summary.mastery * 100}%"></div></div>
        <div class="subject-grade-list">
          ${parentTopics.map((parent) => {
            const children = group.topics
              .filter((topic) => topic.parent_id === parent.id || (parent.id === group.subject && topic.parent_id === group.subject))
              .filter((topic) => topic.id !== parent.id)
              .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
            const gradeTopics = children.length ? children : [parent];
            const gradeSummary = subjectSummary(gradeTopics, mastery);
            return `
              <details class="mastery-grade-block" open>
                <summary>
                  <span>${parent.name}</span>
                  <span>${Math.round(gradeSummary.mastery * 100)}%</span>
                </summary>
                <div class="subject-topic-grid">
                  ${gradeTopics.map((topic) => {
                    const row = mastery[topic.id] || { mastery: 0, practice_count: 0, correct_count: 0 };
                    const correctRate = row.practice_count ? `${Math.round((row.correct_count / row.practice_count) * 100)}%` : "暂无记录";
                    return `
                      <article class="mastery-card mastery-card-readonly" data-topic-id="${topic.id}">
                        <div class="mastery-top">
                          <div>
                            <div class="subject-kicker">${topic.grade_level || parent.grade_level || "通用"} · 二级知识点</div>
                            <strong>${topic.name}</strong>
                            <div class="hint">目标：${topic.learning_objectives[0] || "概念掌握"}</div>
                          </div>
                          <div class="badge">掌握度 ${(row.mastery * 100).toFixed(0)}%</div>
                        </div>
                        <div class="progress-track"><div class="progress-fill" style="width:${row.mastery * 100}%"></div></div>
                        <div class="subtopic-list">
                          ${(topic.subtopics || []).map((item) => `<span>三级：${item}</span>`).join("") || "<span>三级：综合应用</span>"}
                        </div>
                        <div class="metric-grid">
                          <div class="metric-item"><span>练习</span><strong>${row.practice_count}</strong></div>
                          <div class="metric-item"><span>答对</span><strong>${row.correct_count}</strong></div>
                          <div class="metric-item"><span>正确率</span><strong>${correctRate}</strong></div>
                        </div>
                      </article>
                    `;
                  }).join("")}
                </div>
              </details>
            `;
          }).join("")}
        </div>
      </details>
    `;
  }).join("");
}

function renderKnowledgeGraph(mastery) {
  if (!state.topics.length) return;
  const masteryMap = mastery || {};
  const topicMap = {};
  state.topics.forEach((t) => { topicMap[t.id] = t; });

  const childMap = {};
  state.topics.forEach((topic) => {
    if (!topic.parent_id) return;
    childMap[topic.parent_id] = childMap[topic.parent_id] || [];
    childMap[topic.parent_id].push(topic.id);
  });
  let visited = new Set();

  function renderTreeNode(topicId, depth = 0) {
    if (visited.has(topicId)) return "";
    visited.add(topicId);
    const topic = topicMap[topicId];
    if (!topic) return "";
    const mv = masteryValue(topicId, masteryMap);
    const tone = mv >= 0.75 ? "#27ae60" : mv >= 0.45 ? "#f39c12" : "#e74c3c";
    const children = (childMap[topicId] || []).sort((a, b) => (topicMap[a].sort_order || 0) - (topicMap[b].sort_order || 0))
      .map((childId) => renderTreeNode(childId, depth + 1))
      .join("");
    return `
      <details class="kg-node kg-depth-${Math.min(depth, 3)}" ${depth < 1 ? "open" : ""}>
        <summary>
          <span class="tree-toggle-icon"></span>
          <span class="tree-node-title">${topic.name}</span>
          <span class="badge" style="background:${tone}22;color:${tone};">${Math.round(mv * 100)}%</span>
          <span class="tree-toggle-text"></span>
        </summary>
        <div class="kg-node-card" style="border-left-color:${tone};">
          <div class="kg-node-main">
            <div class="subject-kicker">${topic.grade_level || "通用"} · ${topic.term || "全年"}</div>
            <strong>${topic.name}</strong>
            <div class="hint">${topic.learning_objectives?.[0] || "核心知识点"}</div>
          </div>
          <div class="subtopic-list kg-subtopics">
            ${(topic.subtopics || []).map((item) => `<span>三级：${item}</span>`).join("") || "<span>三级：综合应用</span>"}
          </div>
        </div>
        ${children ? `<div class="kg-children">${children}</div>` : ""}
      </details>
    `;
  }

  const mindMapHtml = `
    <div class="mindmap-overview">
      <div class="mindmap-center">知识图谱总览</div>
      <div class="mindmap-branches mindmap-count-${topicsBySubject().length}">
        ${topicsBySubject().map((group) => {
          const summary = subjectSummary(group.topics, masteryMap);
          return `<button class="mindmap-branch" data-mindmap-subject="${group.subject}"><strong>${group.subject}</strong><span>${group.topics.length} 个节点 · ${Math.round(summary.mastery * 100)}%</span></button>`;
        }).join("")}
      </div>
    </div>
  `;

  const html = `
    <div class="knowledge-graph">
      ${topicsBySubject().map((group) => {
        const summary = subjectSummary(group.topics, masteryMap);
        visited = new Set();
        const roots = group.topics
          .filter((topic) => !topic.parent_id || !topicMap[topic.parent_id] || topic.parent_id === group.subject)
          .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
        const nodes = roots.map((topic) => renderTreeNode(topic.id)).join("");
        const remaining = group.topics
          .filter((topic) => !visited.has(topic.id))
          .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
          .map((topic) => renderTreeNode(topic.id))
          .join("");
        return `
          <details class="kg-subject-block" open>
            <summary class="kg-subject-head">
              <span class="tree-toggle-icon"></span>
              <div>
                <div class="subject-kicker">一级知识点</div>
                <h3>${group.subject}</h3>
                <div class="hint">${group.topics.length} 个二级知识点 · 平均掌握 ${Math.round(summary.mastery * 100)}%</div>
              </div>
              <div class="subject-score">${Math.round(summary.mastery * 100)}%</div>
              <span class="tree-toggle-text"></span>
            </summary>
            <div class="progress-track"><div class="progress-fill" style="width:${summary.mastery * 100}%"></div></div>
            <div class="kg-subject-tree">${nodes}${remaining}</div>
          </details>
        `;
      }).join("")}
    </div>
    <div class="kg-legend" style="display:flex;gap:16px;margin-top:8px;flex-wrap:wrap;">
      <span style="font-size:12px;"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#27ae60;margin-right:4px;"></span>掌握 ≥75%</span>
      <span style="font-size:12px;"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#f39c12;margin-right:4px;"></span>掌握 45~74%</span>
      <span style="font-size:12px;"><span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#e74c3c;margin-right:4px;"></span>掌握 &lt;45%</span>
    </div>
  `;
  const preview = qs("knowledgeGraphPreview");
  const full = qs("knowledgeGraphView");
  if (preview) preview.innerHTML = mindMapHtml;
  if (full) full.innerHTML = html;
}

function formatMasteryText(row, emptyText = "待开始") {
  if (!row) return emptyText;
  return `${Math.round((row.mastery || 0) * 100)}%`;
}

function masteryTone(value) {
  if (value >= 0.75) return "strong";
  if (value >= 0.45) return "progress";
  return "weak";
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min, max));
}

function renderSimilarQuestionDeck(items, activeIndex) {
  if (!items.length) {
    return "<div class='empty-state'>当前题库里暂无更多相似题</div>";
  }
  const safeIndex = clamp(activeIndex, 0, items.length - 1);
  return `
    <div class="similar-question-deck">
      <div class="similar-deck-top">
        <div>
          <div class="graph-title">相似题连刷</div>
          <strong>第 ${safeIndex + 1} 题 / 共 ${items.length} 题</strong>
        </div>
        <div class="similar-deck-navs">
          <button class="ghost-button similar-deck-nav" data-similar-nav="-1" ${items.length < 2 ? "disabled" : ""}>上一题</button>
          <button class="ghost-button similar-deck-nav" data-similar-nav="1" ${items.length < 2 ? "disabled" : ""}>下一题</button>
        </div>
      </div>
      <div class="similar-deck-viewport" data-swipe-zone="similar">
        <div class="similar-deck-track" style="transform: translateX(-${safeIndex * 100}%);">
          ${items.map((item, index) => `
            <article class="similar-question-slide ${index === safeIndex ? "active" : ""}">
              <div class="similar-question-slide-shell">
                <div class="action-list">
                  <span class="badge">${friendlyQuestionType(normalizedQuestionType(item))}</span>
                  <span class="badge">难度 ${Number(item.difficulty).toFixed(2)}</span>
                  <span class="badge">${currentTopic(item.topic_id)?.name || item.topic_id}</span>
                </div>
                <strong>${item.stem}</strong>
                <div class="similar-question-reason">${item.recommendation_reason}</div>
                <div class="similar-question-slide-actions">
                  <button class="primary-button load-similar-question" data-question-id="${item.question_id}">刷这道相似题</button>
                </div>
              </div>
            </article>
          `).join("")}
        </div>
      </div>
      <div class="similar-deck-dots">
        ${items.map((item, index) => `
          <button class="similar-deck-dot ${index === safeIndex ? "active" : ""}" data-similar-index="${index}" aria-label="切换到第 ${index + 1} 道相似题"></button>
        `).join("")}
      </div>
      <div class="hint">支持左右滑动切题，选中后可直接进入下一轮同类练习。</div>
    </div>
  `;
}

function renderDiagnosis(data) {
  qs("diagnosisView").innerHTML = `
    <div class="summary-block">
      <div class="report-grid">
        <div class="stat-card"><strong>准备度</strong><div>${(data.readiness_score * 100).toFixed(0)}%</div></div>
        <div class="stat-card"><strong>当前判断</strong><div>${data.summary}</div></div>
      </div>
      <div><strong>当前最需要补的知识点</strong><div class="action-list">${data.weak_topics.map((item) => `<span class="badge">${item}</span>`).join("") || "<span class='hint'>暂无</span>"}</div></div>
      <div><strong>当前优势主题</strong><div class="action-list">${(data.strengths || []).map((item) => `<span class="badge success-badge">${item}</span>`).join("") || "<span class='hint'>暂无</span>"}</div></div>
      <div><strong>建议学习路径</strong><div class="timeline">${data.learning_path.map((item) => `<div class="timeline-item"><strong>${item.topic_name}</strong><div>${item.reason}</div><small>${item.recommended_action}</small></div>`).join("")}</div></div>
    </div>
  `;
  setStep("diagnosis");
}

function renderPractice(data) {
  state.lastQuestion = data.question;
  state.lastPracticeMeta = data;
  state.lastSubmission = null;
  state.lastCoachCard = null;
  state.similarQuestionIndex = 0;
  state.similarSwipeStartX = null;
  qs("practiceView").innerHTML = `
    <div class="summary-block immersive-question-card">
      <div class="practice-hero">
        <div class="badge">推荐难度 ${friendlyBand(data.recommended_band)}</div>
        <div class="stat-card"><strong>推荐理由</strong><div>${data.selection_reason}</div></div>
      </div>
      <div class="question-card">
        <div class="question-meta-row">
          <div class="question-label">本轮题目</div>
          <div class="action-list">
            <span class="badge">${friendlyQuestionType(normalizedQuestionType(data.question))}</span>
            <span class="badge">知识点 ${currentTopic(data.question.topic_id)?.name || data.question.topic_id}</span>
            ${data.question.score_points?.length ? `<span class="badge">${data.question.score_points.length} 个得分点</span>` : ""}
          </div>
        </div>
        <div class="question-stem">${data.question.stem}</div>
        ${renderQuestionSupplement(data.question)}
      </div>
    </div>
  `;
  renderAnswerWorkspace(data.question);
  qs("coachCardView").innerHTML = "<div class='empty-state'>提交答案后可生成讲题卡片</div>";
  qs("submissionResultView").innerHTML = "<div class='empty-state'>提交后显示批改结果</div>";
  qs("mistakeView").innerHTML = "<div class='empty-state'>做错后可分析错因</div>";
  setStep("practice");
}

function renderAnswerWorkspace(question) {
  const type = normalizedQuestionType(question);
  const input = renderAnswerInput(question, type);
  qs("answerWorkspace").innerHTML = `
    <div class="summary-block answer-sheet">
      <div class="answer-sheet-top">
        <div class="answer-mode-chip">${friendlyQuestionType(type)}</div>
        <div class="hint">${answerModeHint(type, question)}</div>
      </div>
      ${input}
    </div>
  `;
}

function renderSubmissionResult(result) {
  const scorePercent = Math.round((result.score || 0) * 100);
  const breakdown = result.breakdown || [];
  const pendingReview = result.review_status === "pending_review";
  qs("submissionResultView").innerHTML = `
    <div class="summary-block submission-shell">
      <div class="submission-hero">
        <div class="submission-score ${pendingReview ? "pending" : (result.is_correct ? "success" : "warning")}">
          <span>${pendingReview ? "待教师复核" : (result.is_correct ? "本题通过" : "继续订正")}</span>
          <strong>${result.score_label || `${scorePercent}%`}</strong>
          <small>${pendingReview ? "暂不计入掌握度" : `得分率 ${scorePercent}%`}</small>
        </div>
        <div class="report-grid">
          <div class="stat-card"><strong>判题方式</strong><div>${evaluationMethodLabel(result.evaluation_method)}</div></div>
          <div class="stat-card"><strong>掌握度变化</strong><div>${result.mastery_delta > 0 ? `+${Math.round(result.mastery_delta * 100)}%` : `${Math.round(result.mastery_delta * 100)}%`}</div></div>
        </div>
      </div>
      <div class="stat-card"><strong>批改说明</strong><div>${result.feedback || "系统已完成本题判定。"}</div></div>
      ${pendingReview ? `<div class="helper-card"><strong>复核原因</strong><p>${result.review_reason || "规则和模型暂时无法可靠判定。"}</p></div>` : ""}
      <div class="score-breakdown-grid">
        ${breakdown.map((item) => `
          <article class="score-breakdown-card">
            <div class="score-breakdown-top">
              <strong>${item.title}</strong>
              <span>${item.earned_points}/${item.points}</span>
            </div>
            <div class="hint">${item.status}</div>
            <small>${item.evidence}</small>
          </article>
        `).join("") || "<div class='empty-state'>当前没有更细分的得分点。</div>"}
      </div>
      <div class="report-grid">
        <div class="note-card"><strong>参考答案</strong><div>${result.correct_answer}</div></div>
        <div class="note-card"><strong>题目解析</strong><div>${result.explanation}</div></div>
      </div>
    </div>
  `;
}

function renderCoachCard(data, preserveDeckIndex = false) {
  state.lastCoachCard = data;
  const disclosure = document.querySelector(".secondary-disclosure");
  if (disclosure) disclosure.open = true;
  const similarQuestions = data.similar_questions || [];
  state.similarQuestionIndex = preserveDeckIndex
    ? clamp(state.similarQuestionIndex, 0, Math.max(similarQuestions.length - 1, 0))
    : 0;
  qs("coachCardView").innerHTML = `
    <div class="summary-block coach-stream">
      <div class="stat-card"><strong>解题主线</strong><div>${data.strategy_summary}</div></div>
      <div><strong>分步讲解</strong><div class="coach-step-flow">${data.step_cards.map((item, index) => `
        <article class="coach-step-card">
          <div class="coach-step-index">0${index + 1}</div>
          <div>
            <strong>${item.title}</strong>
            <div>${item.content}</div>
          </div>
        </article>
      `).join("")}</div></div>
      <div><strong>易错提醒</strong><div class="action-list">${data.misconception_alerts.map((item) => `<span class="badge">${item}</span>`).join("") || "<span class='hint'>暂无</span>"}</div></div>
      <div><strong>相似题推荐</strong>${renderSimilarQuestionDeck(similarQuestions, state.similarQuestionIndex)}</div>
      <div><strong>下一轮建议</strong><div class="timeline">${data.next_drills.map((item) => `<div class="timeline-item">${item}</div>`).join("")}</div></div>
    </div>
  `;
}

function setSimilarQuestionIndex(index) {
  if (!state.lastCoachCard?.similar_questions?.length) return;
  state.similarQuestionIndex = clamp(index, 0, state.lastCoachCard.similar_questions.length - 1);
  renderCoachCard(state.lastCoachCard, true);
}

function shiftSimilarQuestion(step) {
  if (!state.lastCoachCard?.similar_questions?.length) return;
  const total = state.lastCoachCard.similar_questions.length;
  state.similarQuestionIndex = (state.similarQuestionIndex + step + total) % total;
  renderCoachCard(state.lastCoachCard, true);
}

function renderMistake(data) {
  const disclosure = document.querySelector(".secondary-disclosure");
  if (disclosure) disclosure.open = true;
  qs("mistakeView").innerHTML = `
    <div class="summary-block">
      <div class="badge">${data.category}</div>
      <div class="stat-card"><strong>错因说明</strong><div>${data.explanation}</div></div>
      <div><strong>纠正建议</strong><div class="timeline">${data.correction_advice.map((item) => `<div class="timeline-item">${item}</div>`).join("")}</div></div>
    </div>
  `;
}

function renderMistakeNotebook(records) {
  state.mistakeRecords = records || [];
  const target = qs("mistakeNotebookView");
  if (!target) return;
  if (!state.mistakeRecords.length) {
    target.classList.add("empty-state");
    target.innerHTML = "还没有错题记录。在练习页提交答案后点击「加入错题本」即可保存。";
    return;
  }
  target.classList.remove("empty-state");
  target.innerHTML = `
    <div class="mistake-notebook-list">
      ${state.mistakeRecords.map((item) => `
        <article class="mistake-record-card">
          <div class="mistake-record-top">
            <div>
              <strong>${item.topic_name}</strong>
              <div class="hint">${new Date(item.created_at).toLocaleString()}</div>
            </div>
            <span class="badge">${item.category}</span>
          </div>
          <div class="mistake-question">${item.question_stem}</div>
          <div class="mistake-answer-grid">
            <div class="note-card"><strong>我的答案</strong><div>${item.student_answer || "未填写"}</div></div>
            <div class="note-card"><strong>参考答案</strong><div>${item.correct_answer}</div></div>
          </div>
          <div class="stat-card"><strong>错因说明</strong><div>${item.explanation}</div></div>
          <div>
            <strong>订正建议</strong>
            <div class="timeline">
              ${(item.correction_advice || []).map((advice) => `<div class="timeline-item">${advice}</div>`).join("") || "<div class='empty-state'>暂无订正建议</div>"}
            </div>
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function renderReport(report) {
  if (!report) {
    qs("reportView").innerHTML = "<div class='empty-state'>还没有学习报告，选择知识点后点击生成；生成后会保存在下方历史报告里。</div>";
    return;
  }
  qs("reportView").innerHTML = `
    <div class="summary-block">
      <div class="report-grid">
        <div class="stat-card"><strong>整体掌握度</strong><div>${(report.overall_mastery * 100).toFixed(0)}%</div></div>
        <div class="stat-card"><strong>生成时间</strong><div>${new Date(report.created_at).toLocaleString()}</div></div>
      </div>
      <div class="stat-card"><strong>阶段总结</strong><div>${report.diagnostic_summary}</div></div>
      <div class="report-grid">
        <div class="note-card"><strong>优势主题</strong><div>${report.strong_topics.join("、") || "暂无"}</div></div>
        <div class="note-card"><strong>薄弱主题</strong><div>${report.weak_topics.join("、") || "暂无"}</div></div>
      </div>
      <div><strong>下一步动作</strong><div class="timeline">${report.next_actions.map((item) => `<div class="timeline-item">${item}</div>`).join("")}</div></div>
      <div><strong>复习计划</strong><div class="review-list">${report.review_plan.map((item) => `<div class="timeline-item"><strong>${item.review_date}</strong><div>${item.activity}</div></div>`).join("")}</div></div>
    </div>
  `;
}

function renderReportHistory(reports) {
  state.reportHistory = reports || [];
  const target = qs("reportHistoryView");
  if (!target) return;
  if (!state.reportHistory.length) {
    target.innerHTML = "<div class='empty-state'>暂无历史报告，生成后会自动保存到这里。</div>";
    return;
  }
  target.innerHTML = `
    <div class="timeline">
      ${state.reportHistory.map((report) => `
        <article class="timeline-item report-history-item">
          <strong>${new Date(report.created_at).toLocaleString()} · 掌握度 ${(report.overall_mastery * 100).toFixed(0)}%</strong>
          <div>${report.diagnostic_summary}</div>
          <small>薄弱主题：${report.weak_topics.join("、") || "暂无"} · 复习任务 ${report.review_plan.length} 项</small>
        </article>
      `).join("")}
    </div>
  `;
}

function renderSessions(sessions) {
  qs("chatSessionSelect").innerHTML = sessions.length ? sessions.map((item) => `<option value="${item.id}">${item.title}</option>`).join("") : "<option value=''>暂无对话</option>";
  if (!state.currentSessionId && sessions[0]) state.currentSessionId = sessions[0].id;
  if (state.currentSessionId && sessions.length) qs("chatSessionSelect").value = state.currentSessionId;
}

function renderCitationEvidence(citations) {
  if (!citations || !citations.length) return "";
  const items = citations.map((citation) => {
    const data = typeof citation === "string" ? { document_title: citation } : citation;
    return `
      <details class="citation-card">
        <summary>${data.document_title || "引用资料"} <span>${data.score ? `相关度 ${Number(data.score).toFixed(3)}` : ""}</span></summary>
        <div class="citation-meta">${data.doc_type || "资料"} · ${data.source_name || "未知来源"} · ${data.topic_id || "通用"}</div>
        <div>${data.snippet || "暂无片段预览"}</div>
      </details>
    `;
  }).join("");
  return `<div class="citation-list"><strong>依据来源</strong>${items}</div>`;
}

function renderChat(history) {
  qs("chatHistory").innerHTML = history.length ? history.map((item) => `
    <article class="message ${item.role}">
      <div class="message-role">${item.role === "assistant" ? "🤖 AI 导师" : "👤 学生"}</div>
      <div>${item.content}</div>
      ${renderCitationEvidence(item.citations)}
    </article>
  `).join("") : "<div class='empty-state'>发送消息后开始对话</div>";
}

async function loadTopics() {
  state.topics = await api("/graph/topics");
  const options = state.topics.map((topic) => `<option value="${topic.id}">${topic.name}</option>`).join("");
  qs("targetTopicId").innerHTML = options;
  qs("chatTopicId").innerHTML = options;
  qs("reportTopicId").innerHTML = options;
}

function renderTopicSelects(profile) {
  const grade = profile?.grade_level || "";
  const subject = profile?.target_subject || "";
  const topics = state.topics.filter((topic) =>
    (!subject || topic.subject === subject) &&
    (!grade || !topic.grade_level || topic.grade_level === grade) &&
    topic.level >= 3
  );
  const rows = topics.length ? topics : state.topics;
  const options = rows
    .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
    .map((topic) => `<option value="${topic.id}">${topic.grade_level ? `${topic.grade_level} · ` : ""}${topic.subject} · ${topic.name}</option>`)
    .join("");
  qs("targetTopicId").innerHTML = options;
  qs("chatTopicId").innerHTML = options;
  qs("reportTopicId").innerHTML = options;
}

async function login() {
  qs("loginError").style.display = "none";
  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: qs("loginEmail").value, password: qs("loginPassword").value }),
    });
    state.token = data.token;
    state.user = data.user;
    localStorage.setItem("zhuyu_token", state.token);
    showToast("登录成功！");
    showAppMain();
    qs("authStatus").textContent = `${data.user.full_name}`;
    await loadTopics();
    await loadStudents();
  } catch (err) {
    qs("loginError").textContent = err.message || "登录失败，请检查邮箱和密码";
    qs("loginError").style.display = "";
  }
}

async function registerStudent() {
  qs("loginError").style.display = "none";
  const inviteCode = qs("registerInviteCode").value.trim();
  if (!inviteCode) {
    qs("loginError").textContent = "请填写老师提供的班级邀请码";
    qs("loginError").style.display = "";
    return;
  }
  try {
    const data = await api("/auth/register/student", {
      method: "POST",
      body: JSON.stringify({
        full_name: qs("registerName").value,
        email: qs("registerEmail").value,
        password: qs("registerPassword").value,
        invite_code: inviteCode,
        target_subject: "数学",
      }),
    });
    state.token = data.token;
    state.user = data.user;
    localStorage.setItem("zhuyu_token", state.token);
    showToast("注册成功 ✓");
    showAppMain();
    qs("authStatus").textContent = `${data.user.full_name}`;
    await loadTopics();
    await loadStudents();
  } catch (err) {
    qs("loginError").textContent = err.message || "注册失败，请检查信息";
    qs("loginError").style.display = "";
  }
}

function logout() {
  state.token = "";
  state.user = null;
  state.students = [];
  state.currentStudentId = null;
  state.dashboard = null;
  localStorage.removeItem("zhuyu_token");
  showLoginGate();
}

async function loadStudents() {
  state.students = await api("/students");
  if (!state.students.length) return;
  qs("studentSelect").innerHTML = state.students.map((item) => `<option value="${item.id}">${item.name}</option>`).join("");
  state.currentStudentId = state.currentStudentId || state.students[0].id;
  qs("studentSelect").value = state.currentStudentId;
  await loadDashboard();
}

async function loadDashboard() {
  if (!state.currentStudentId) return;
  const dashboard = await api(`/students/${state.currentStudentId}/dashboard`);
  state.dashboard = dashboard;
  renderQuickStats(dashboard.profile);
  renderTopicSelects(dashboard.profile);
  renderKnowledgeGraph(dashboard.profile.mastery);
  renderMastery(dashboard.profile);
  renderMistakeNotebook(dashboard.recent_mistakes);
  renderReport(dashboard.latest_report);
  await loadReportHistory();
  renderSessions(dashboard.recent_sessions);
  if ([...qs("targetTopicId").options].some((item) => item.value === dashboard.profile.target_topic_id)) {
    qs("targetTopicId").value = dashboard.profile.target_topic_id;
    qs("chatTopicId").value = dashboard.profile.target_topic_id;
    qs("reportTopicId").value = dashboard.profile.target_topic_id;
  }
  if (state.currentSessionId) {
    await loadHistory(state.currentSessionId);
  } else {
    renderChat([]);
  }
}

async function loadReportHistory() {
  if (!state.currentStudentId) return;
  const reports = await api(`/students/${state.currentStudentId}/reports`);
  renderReportHistory(reports);
}

async function loadMistakes() {
  if (!state.currentStudentId) return;
  const records = await api(`/students/${state.currentStudentId}/mistakes`);
  renderMistakeNotebook(records);
}

async function runDiagnosis() {
  const data = await api(`/students/${state.currentStudentId}/diagnosis`, {
    method: "POST",
    body: JSON.stringify({ target_topic_id: qs("targetTopicId").value }),
  });
  renderDiagnosis(data);
  showToast("诊断完成 ✓");
}

async function runPractice() {
  const data = await api(`/students/${state.currentStudentId}/practice`, {
    method: "POST",
    body: JSON.stringify({ topic_id: qs("targetTopicId").value }),
  });
  renderPractice(data);
  showToast("已推荐下一题 ✓");
}

async function loadCoachCard(answerOverride = null) {
  if (!state.lastQuestion) {
    showToast("请先推荐题目");
    return;
  }
  const card = await api(`/students/${state.currentStudentId}/practice/coach-card`, {
    method: "POST",
    body: JSON.stringify({ question_id: state.lastQuestion.id, student_answer: answerOverride ?? getCurrentStudentAnswer() }),
  });
  renderCoachCard(card);
}

async function submitPracticeResult(answer = null) {
  if (!state.lastQuestion) {
    showToast("请先推荐题目");
    return;
  }
  const finalAnswer = answer ?? getCurrentStudentAnswer();
  const blankAnswers = answer === null ? getCurrentBlankAnswers() : null;
  const hasAnswer = blankAnswers ? blankAnswers.some((item) => item) : Boolean(finalAnswer);
  if (!hasAnswer) {
    showToast("请先完成作答");
    return;
  }
  const payload = { question_id: state.lastQuestion.id, student_answer: finalAnswer, duration_seconds: 75 };
  if (blankAnswers) payload.blank_answers = blankAnswers;
  const result = await api(`/students/${state.currentStudentId}/practice/submit`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.lastSubmission = result;
  renderSubmissionResult(result);
  await loadCoachCard(finalAnswer);
  await loadDashboard();
  showToast("批改完成 ✓");
  return result;
}

async function analyzeMistake() {
  if (!state.lastQuestion) {
    showToast("请先推荐题目");
    return;
  }
  const finalAnswer = getCurrentStudentAnswer();
  if (!finalAnswer) {
    showToast("请先完成作答");
    return;
  }
  await submitPracticeResult(finalAnswer);
  const record = await api(`/students/${state.currentStudentId}/mistakes/analyze`, {
    method: "POST",
    body: JSON.stringify({ question_id: state.lastQuestion.id, student_answer: finalAnswer, scratchpad: "页面回放输入" }),
  });
  renderMistake(record);
  await loadDashboard();
  await loadMistakes();
  showToast("错题已保存 ✓");
}

async function createSession() {
  const session = await api(`/students/${state.currentStudentId}/chat/sessions`, {
    method: "POST",
    body: JSON.stringify({ title: "辅导对话" }),
  });
  state.currentSessionId = session.id;
  await reloadSessions();
  renderChat([]);
  showToast("已创建新对话 ✓");
  setStep("tutor");
}

async function reloadSessions() {
  const sessions = await api(`/students/${state.currentStudentId}/chat/sessions`);
  renderSessions(sessions);
}

async function loadHistory(sessionId) {
  const history = await api(`/chat/sessions/${sessionId}`);
  renderChat(history);
}

async function openQuestionById(questionId) {
  const question = await api(`/questions/${questionId}`);
  renderPractice({
    question,
    recommended_band: deriveBandByDifficulty(question.difficulty),
    selection_reason: "来自讲题卡的相似题推荐，适合连续刷同类题巩固。",
  });
  await loadCoachCard();
  showToast("已切换到相似题");
}

async function sendChat() {
  if (!state.currentSessionId) await createSession();
  const turn = await api(`/chat/sessions/${state.currentSessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({
      topic_id: qs("chatTopicId").value,
      content: qs("chatInput").value,
      difficulty_signal: 0.45,
    }),
  });
  renderChat(turn.history);
  await reloadSessions();
  qs("chatInput").value = "";
  showToast("AI 回复已生成 ✓");
}

async function generateReport() {
  const report = await api(`/students/${state.currentStudentId}/reports/generate`, {
    method: "POST",
    body: JSON.stringify({ target_topic_id: qs("reportTopicId").value || qs("targetTopicId").value }),
  });
  renderReport(report);
  await loadReportHistory();
  navigateTo("report");
  showToast("学习报告已生成 ✓");
}

function bindEvents() {
  document.querySelectorAll(".nav-item[data-page]").forEach((item) => {
    item.addEventListener("click", () => navigateTo(item.dataset.page));
  });
  qs("showLoginFormButton").addEventListener("click", () => toggleAuthForm("login"));
  qs("showRegisterFormButton").addEventListener("click", () => toggleAuthForm("register"));
  qs("loginButton").addEventListener("click", () => login().catch(handleError));
  qs("registerButton").addEventListener("click", () => registerStudent().catch(handleError));
  qs("loginPassword").addEventListener("keydown", (e) => { if (e.key === "Enter") login().catch(handleError); });
  qs("logoutButton").addEventListener("click", () => logout());
  qs("openGraphButton").addEventListener("click", () => navigateTo("graph"));
  qs("expandGraphButton").addEventListener("click", () => setGraphExpanded(true));
  qs("collapseGraphButton").addEventListener("click", () => setGraphExpanded(false));
  qs("knowledgeGraphPreview").addEventListener("click", (event) => {
    const branch = event.target.closest("[data-mindmap-subject]");
    if (branch) openGraphSubject(branch.dataset.mindmapSubject);
  });
  qs("studentSelect").addEventListener("change", async (event) => {
    state.currentStudentId = Number(event.target.value);
    state.currentSessionId = null;
    await loadDashboard().catch(handleError);
  });
  qs("diagnosisButton").addEventListener("click", () => runDiagnosis().catch(handleError));
  qs("practiceButton").addEventListener("click", () => runPractice().catch(handleError));
  qs("submitAnswerButton").addEventListener("click", () => submitPracticeResult().catch(handleError));
  qs("coachCardButton").addEventListener("click", () => loadCoachCard().catch(handleError));
  qs("mistakeButton").addEventListener("click", () => analyzeMistake().catch(handleError));
  qs("refreshMistakesButton").addEventListener("click", () => loadMistakes().then(() => showToast("错题本已刷新 ✓")).catch(handleError));
  qs("createSessionButton").addEventListener("click", () => createSession().catch(handleError));
  qs("sendChatButton").addEventListener("click", () => sendChat().catch(handleError));
  qs("generateReportButton").addEventListener("click", () => generateReport().catch(handleError));
  qs("chatSessionSelect").addEventListener("change", (event) => {
    state.currentSessionId = Number(event.target.value);
    loadHistory(state.currentSessionId).catch(handleError);
  });
  qs("coachCardView").addEventListener("click", (event) => {
    const navButton = event.target.closest("[data-similar-nav]");
    if (navButton) { shiftSimilarQuestion(Number(navButton.dataset.similarNav)); return; }
    const dotButton = event.target.closest("[data-similar-index]");
    if (dotButton) { setSimilarQuestionIndex(Number(dotButton.dataset.similarIndex)); return; }
    const button = event.target.closest(".load-similar-question");
    if (button) openQuestionById(button.dataset.questionId).catch(handleError);
  });
  qs("coachCardView").addEventListener("pointerdown", (event) => {
    if (!event.target.closest("[data-swipe-zone='similar']")) return;
    state.similarSwipeStartX = event.clientX;
  });
  qs("coachCardView").addEventListener("pointerup", (event) => {
    if (!event.target.closest("[data-swipe-zone='similar']")) return;
    if (state.similarSwipeStartX === null) return;
    const delta = event.clientX - state.similarSwipeStartX;
    state.similarSwipeStartX = null;
    if (Math.abs(delta) < 48) return;
    shiftSimilarQuestion(delta < 0 ? 1 : -1);
  });
  qs("coachCardView").addEventListener("pointercancel", () => { state.similarSwipeStartX = null; });
}

function handleError(error) {
  console.error(error);
  showToast(`操作失败: ${error.message}`);
}

async function bootstrap() {
  bindEvents();
  const mode = new URLSearchParams(window.location.search).get("mode");
  if (mode === "register") toggleAuthForm("register");
  if (state.token) {
    try {
      state.user = await api("/auth/me");
      showAppMain();
      qs("authStatus").textContent = state.user.full_name;
      await loadTopics();
      await loadStudents();
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

function inferAnswerMode(question) {
  const type = normalizedQuestionType(question);
  if (type === "choice") return "choice";
  if (type === "judgment") return "judgment";
  if (type === "solution" || type === "steps") return "long_text";
  return question?.blank_count > 1 ? "blank_group" : "short_text";
}

function answerModeLabel(mode) {
  if (mode === "choice") return "选择作答";
  if (mode === "judgment") return "判断作答";
  if (mode === "long_text") return "长文本作答";
  return "简答 / 填空作答";
}

function friendlyBand(band) {
  if (band === "foundation") return "基础巩固";
  if (band === "standard") return "标准练习";
  if (band === "challenge") return "提升挑战";
  return band;
}

function currentTopic(topicId) {
  return state.topics.find((item) => item.id === topicId);
}

function normalizedQuestionType(question) {
  if (question?.question_type) return question.question_type;
  const answer = question?.answer || "";
  const stem = question?.stem || "";
  if (/^(正确|错误|对|错|true|false)$/i.test(answer.trim()) || /判断|正确|错误|对错/.test(stem)) return "judgment";
  if (/^[ABCD]$/.test(answer.trim()) || /[A-D][.．、]/.test(stem)) return "choice";
  if (/说明|证明|分析|解答|为什么|理由/.test(stem)) return "solution";
  if (question?.score_points?.length) return "steps";
  return "blank";
}

function friendlyQuestionType(type) {
  if (type === "choice") return "选择题";
  if (type === "judgment") return "判断题";
  if (type === "solution") return "解答题";
  if (type === "steps") return "步骤分题";
  return "填空题";
}

function answerModeHint(type, question) {
  if (type === "choice") return "直接选择正确选项即可提交。";
  if (type === "judgment") return "判断题支持“正确/错误、对/错、true/false”等写法。";
  if (type === "steps") return `按得分点分步作答（${question.score_points?.length ? `${question.score_points.length} 个得分点` : ""}）。`;
  if (type === "solution") return "请写出完整思路或关键推理过程。";
  return question.blank_count > 1 ? `本题包含 ${question.blank_count} 个填空位置。` : "直接填写答案即可。";
}

function blankInputLabel(label, index) {
  if (!label) return `第 ${index + 1} 空`;
  if (typeof label === "string") return label;
  return label.title || `第 ${index + 1} 空`;
}

function renderAnswerInput(question, type) {
  if (type === "choice") {
    const options = (question.options || []).length ? question.options : inferChoiceOptionsFromStem(question.stem);
    return `
      <div class="choice-list">
        ${options.map((option) => `
          <label class="choice-option">
            <input type="radio" name="studentChoiceOption" value="${option.key}">
            <div><strong>${option.key}</strong><span>${option.content}</span></div>
          </label>
        `).join("")}
      </div>
    `;
  }
  if (type === "judgment") {
    return `
      <div class="choice-list judgment-list">
        <label class="choice-option judgment-option">
          <input type="radio" name="studentJudgmentOption" value="正确">
          <div><strong>正确</strong><span>题干表述成立</span></div>
        </label>
        <label class="choice-option judgment-option">
          <input type="radio" name="studentJudgmentOption" value="错误">
          <div><strong>错误</strong><span>题干表述不成立</span></div>
        </label>
      </div>
    `;
  }
  if (question.blank_count > 1) {
    const labels = (question.score_points || question.tags || []).slice(0, question.blank_count);
    return `
      <div class="blank-grid">
        ${Array.from({ length: question.blank_count }).map((_, index) => {
          const label = blankInputLabel(labels[index], index);
          return `
          <label class="blank-field">
            <span>${label}</span>
            <input id="studentBlankInput${index}" type="text" placeholder="请输入${label}">
          </label>
        `;
        }).join("")}
      </div>
    `;
  }
  if (type === "solution" || type === "steps") {
    return `
      <textarea id="studentAnswerInput" rows="8" placeholder="请写出解题过程或完整答案"></textarea>
      ${question.score_points?.length ? `
        <div class="rubric-hints">
          ${question.score_points.map((item) => `<div class="rubric-hint-item"><strong>${item.title}</strong><small>${item.points} 分</small></div>`).join("")}
        </div>
      ` : ""}
    `;
  }
  return `<input id="studentAnswerInput" type="text" placeholder="请输入答案">`;
}

function getCurrentStudentAnswer() {
  const question = state.lastQuestion;
  if (!question) return "";
  const type = normalizedQuestionType(question);
  if (type === "choice") return document.querySelector('input[name="studentChoiceOption"]:checked')?.value || "";
  if (type === "judgment") return document.querySelector('input[name="studentJudgmentOption"]:checked')?.value || "";
  if (question.blank_count > 1) {
    return getCurrentBlankAnswers().join("，");
  }
  return qs("studentAnswerInput")?.value?.trim() || "";
}

function getCurrentBlankAnswers() {
  const question = state.lastQuestion;
  if (!question || question.blank_count <= 1) return null;
  return Array.from({ length: question.blank_count })
    .map((_, i) => qs(`studentBlankInput${i}`)?.value?.trim() || "");
}

function renderQuestionSupplement(question) {
  const type = normalizedQuestionType(question);
  const tags = question.tags || [];
  return `
    ${type === "choice" ? `
      <div class="choice-preview">
        ${(question.options || inferChoiceOptionsFromStem(question.stem)).map((opt) => `
          <div class="choice-preview-item"><strong>${opt.key}</strong><span>${opt.content}</span></div>
        `).join("")}
      </div>
    ` : ""}
    ${type === "judgment" ? `
      <div class="choice-preview">
        <div class="choice-preview-item"><strong>正确</strong><span>题干表述成立</span></div>
        <div class="choice-preview-item"><strong>错误</strong><span>题干表述不成立</span></div>
      </div>
    ` : ""}
    ${question.score_points?.length ? `
      <div class="score-point-preview">
        ${question.score_points.map((item) => `<div class="score-point-chip">${item.title} · ${item.points} 分</div>`).join("")}
      </div>
    ` : ""}
    ${tags.length ? `<div class="action-list">${tags.map((tag) => `<span class="badge">${tag}</span>`).join("")}</div>` : ""}
  `;
}

function inferChoiceOptionsFromStem(stem) {
  const matches = stem.match(/([A-D])[.．、]\s*([^A-D]+?)(?=(?:[A-D][.．、])|$)/g) || [];
  return matches.map((item) => {
    const [, key, content] = item.match(/([A-D])[.．、]\s*(.+)/) || [];
    return { key, content };
  }).filter((item) => item.key && item.content);
}

function deriveBandByDifficulty(difficulty) {
  if (difficulty <= 0.45) return "foundation";
  if (difficulty >= 0.75) return "challenge";
  return "standard";
}

function evaluationMethodLabel(method) {
  if (method === "choice") return "选项匹配";
  if (method === "judgment") return "判断匹配";
  if (method === "pending_teacher_review") return "教师复核中";
  if (method === "llm_semantic") return "AI 语义判分";
  if (method === "keyword_match") return "关键词命中";
  if (method === "multi_blank") return "分空判定";
  if (method === "rubric_solution") return "解答题得分点";
  if (method === "rubric_steps") return "步骤分判定";
  if (method === "rubric") return "关键词覆盖";
  return "精确匹配";
}
