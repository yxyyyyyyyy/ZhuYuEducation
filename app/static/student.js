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
  activeGraphSubject: "",
  expandedGraphSubjects: new Set(), // Track which subjects are expanded independently
  chatHistory: [],
  chatTyping: false,
};

const topicSelectContexts = {
  diagnosis: { subjectId: "targetSubjectId", topicId: "targetTopicId" },
  practice: { subjectId: "practiceSubjectId", topicId: "practiceTopicId" },
  report: { subjectId: "reportSubjectId", topicId: "reportTopicId" },
};

const subjectOrder = ["语文", "数学", "英语", "物理", "化学", "生物", "历史", "地理", "道德与法治", "其他"];

function qs(id) {
  return document.getElementById(id);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
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
  const view = qs("knowledgeGraphPreview");
  if (!view) return;
  view.classList.toggle("kg-network-compact", !expanded);
}

function openGraphSubject(subject) {
  // Toggle the subject in the expanded set instead of replacing
  if (state.expandedGraphSubjects.has(subject)) {
    state.expandedGraphSubjects.delete(subject);
  } else {
    state.expandedGraphSubjects.add(subject);
  }
  state.activeGraphSubject = state.expandedGraphSubjects.has(subject) ? subject : "";
  setSubjectAcrossSelectors(subject);
  renderKnowledgeGraph(state.dashboard?.profile?.mastery || {});
  navigateTo("profile");
  let firstActive = null;
  document.querySelectorAll("#knowledgeGraphPreview [data-graph-subject]").forEach((node) => {
    const active = state.expandedGraphSubjects.has(node.dataset.graphSubject);
    node.classList.toggle("highlight", active);
    if (active && !firstActive) firstActive = node;
  });
  if (firstActive) firstActive.scrollIntoView({ behavior: "smooth", block: "center" });
}

function setStep(step) {
  const pageMap = { auth: "profile", graph: "profile", diagnosis: "diagnosis", practice: "practice", mistakes: "mistakes", tutor: "tutor", report: "report" };
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
  const grade = state.dashboard?.profile?.grade_level || "";
  const parentIds = new Set(state.topics.map((topic) => topic.parent_id).filter(Boolean));
  const leafTopics = state.topics.filter((topic) => !parentIds.has(topic.id));
  const filtered = grade
    ? leafTopics.filter((topic) => !topic.grade_level || topic.grade_level === grade)
    : leafTopics;
  const groups = [];
  const groupMap = {};
  filtered.forEach((topic) => {
    const subject = topic.subject || "其他";
    if (!groupMap[subject]) {
      groupMap[subject] = { subject, topics: [] };
      groups.push(groupMap[subject]);
    }
    groupMap[subject].topics.push(topic);
  });
  groups.sort((a, b) => {
    const ai = subjectOrder.indexOf(a.subject);
    const bi = subjectOrder.indexOf(b.subject);
    const ar = ai >= 0 ? ai : subjectOrder.length;
    const br = bi >= 0 ? bi : subjectOrder.length;
    return ar - br || a.subject.localeCompare(b.subject, "zh-Hans-CN");
  });
  groups.forEach((group) => {
    group.topics.sort((a, b) =>
      (a.sort_order || 0) - (b.sort_order || 0) ||
      (a.name || "").localeCompare(b.name || "", "zh-Hans-CN")
    );
  });
  return groups;
}

function sortTopicList(topics) {
  return topics.slice().sort((a, b) =>
    (a.sort_order || 0) - (b.sort_order || 0) ||
    (a.name || "").localeCompare(b.name || "", "zh-Hans-CN")
  );
}

function sortSubjectGroups(groups) {
  return groups.sort((a, b) => {
    const ai = subjectOrder.indexOf(a.subject);
    const bi = subjectOrder.indexOf(b.subject);
    const ar = ai >= 0 ? ai : subjectOrder.length;
    const br = bi >= 0 ? bi : subjectOrder.length;
    return ar - br || a.subject.localeCompare(b.subject, "zh-Hans-CN");
  });
}

function _isGradeSubjectNode(name, subject) {
  if (!name || !subject) return false;
  const gradePatterns = ["小学一年级","小学二年级","小学三年级","小学四年级","小学五年级","小学六年级","初一","初二","初三","高一","高二","高三"];
  return gradePatterns.some((g) => name === `${g}${subject}`);
}

function graphGroupsBySubject() {
  const grade = state.dashboard?.profile?.grade_level || "";
  const filtered = grade
    ? state.topics.filter((topic) => !topic.grade_level || topic.grade_level === grade)
    : state.topics.slice();
  const bySubject = {};
  filtered.forEach((topic) => {
    const subject = topic.subject || "其他";
    if (!bySubject[subject]) bySubject[subject] = { subject, topics: [], branches: [] };
    bySubject[subject].topics.push(topic);
  });

  return sortSubjectGroups(Object.values(bySubject)).map((group) => {
    const topicIds = new Set(group.topics.map((topic) => topic.id));
    const topicMap = new Map(group.topics.map((topic) => [topic.id, topic]));

    const promoted = [];
    group.topics.forEach((topic) => {
      if (!_isGradeSubjectNode(topic.name, group.subject)) return;
      const children = group.topics.filter((child) => child.parent_id === topic.id);
      children.forEach((child) => {
        if (!promoted.some((p) => p.id === child.id)) {
          promoted.push({ ...child, _promoted: true });
        }
      });
    });

    const promotedIds = new Set(promoted.map((p) => p.id));
    const effectiveTopics = group.topics
      .filter((topic) => !_isGradeSubjectNode(topic.name, group.subject) && !promotedIds.has(topic.id))
      .concat(promoted);

    const effectiveTopicIds = new Set(effectiveTopics.map((t) => t.id));
    const childIds = new Set(effectiveTopics.map((topic) => topic.parent_id).filter(Boolean).filter((pid) => effectiveTopicIds.has(pid)));
    const roots = sortTopicList(effectiveTopics.filter((topic) =>
      topic.level === 1 || !topic.parent_id || !effectiveTopicIds.has(topic.parent_id)
    ));
    const leafTopics = sortTopicList(effectiveTopics.filter((topic) => !childIds.has(topic.id)));
    const rootIds = new Set(roots.map((topic) => topic.id));
    const orphanLeaves = leafTopics.filter((topic) =>
      (!topic.parent_id || !effectiveTopicIds.has(topic.parent_id)) && !rootIds.has(topic.id)
    );
    const branches = roots.map((root) => {
      const children = sortTopicList(leafTopics.filter((topic) => topic.parent_id === root.id && topic.id !== root.id));
      return { parent: root, topics: children, isLeaf: !children.length };
    });

    if (orphanLeaves.length && !branches.some((branch) => branch.parent.id === `${group.subject}-fallback`)) {
      branches.push({
        parent: {
          id: `${group.subject}-fallback`,
          name: "综合知识",
          subject: group.subject,
          grade_level: grade,
          sort_order: 9999,
        },
        topics: orphanLeaves,
        isLeaf: false,
      });
    }

    return { subject: group.subject, topics: leafTopics, branches: branches.filter((branch) => branch.topics.length || branch.isLeaf) };
  });
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

const graphPalette = ["#2f80ed", "#27ae60", "#f2c94c", "#eb5757", "#56ccf2", "#9b51e0", "#f2994a", "#219653"];

function graphColor(index) {
  return graphPalette[index % graphPalette.length];
}

function pointOnEllipse(angleDeg, radiusX, radiusY, centerX = 600, centerY = 350) {
  const angle = (angleDeg * Math.PI) / 180;
  return {
    x: centerX + Math.cos(angle) * radiusX,
    y: centerY + Math.sin(angle) * radiusY,
  };
}

function localGraphBounds(center) {
  return {
    minX: Math.max(70, center.x - 285),
    maxX: Math.min(1130, center.x + 285),
    minY: Math.max(70, center.y - 220),
    maxY: Math.min(630, center.y + 220),
  };
}

function localGraphAngles(count, center, ringIndex = 0) {
  if (count <= 0) return [];
  // Keep the original logic to ensure nodes expand radially from the subject node position
  // The radial angle is calculated relative to the global center (600, 350) to establish a consistent direction
  const radialAngle = Math.atan2(center.y - 350, center.x - 600) * 180 / Math.PI;
  const start = radialAngle - 90 + ringIndex * 18;
  return Array.from({ length: count }, (_, index) => start + (360 / count) * index);
}

function pointOnLocalEllipse(center, angleDeg, radiusX, radiusY, bounds) {
  const point = pointOnEllipse(angleDeg, radiusX, radiusY, center.x, center.y);
  return {
    x: clamp(point.x, bounds.minX, bounds.maxX),
    y: clamp(point.y, bounds.minY, bounds.maxY),
  };
}

function topicAnglesAroundBranch(subjectPoint, branchPoint, count) {
  if (count <= 0) return [];
  const outwardAngle = Math.atan2(branchPoint.y - subjectPoint.y, branchPoint.x - subjectPoint.x) * 180 / Math.PI;
  if (count === 1) return [{ angle: outwardAngle, ring: 0 }];

  const spread = Math.min(120, Math.max(70, 42 + count * 16));
  const innerCount = Math.min(count, 5);
  const outerCount = Math.max(count - innerCount, 0);
  const innerStep = innerCount <= 1 ? 0 : spread / (innerCount - 1);
  const slots = Array.from({ length: innerCount }, (_, index) => ({
    angle: outwardAngle - spread / 2 + innerStep * index,
    ring: 0,
  }));

  if (outerCount) {
    const outerSpread = Math.min(140, spread + 20);
    const outerStep = outerCount <= 1 ? 0 : outerSpread / (outerCount - 1);
    Array.from({ length: outerCount }, (_, index) => {
      slots.push({
        angle: outwardAngle - outerSpread / 2 + outerStep * index + 10,
        ring: 1,
      });
    });
  }

  return slots;
}

function topicBoundsAroundBranch(branchPoint, count) {
  const extra = Math.max(count - 3, 0) * 14;
  return {
    minX: Math.max(70, branchPoint.x - 235 - extra),
    maxX: Math.min(1130, branchPoint.x + 235 + extra),
    minY: Math.max(70, branchPoint.y - 180 - extra),
    maxY: Math.min(630, branchPoint.y + 180 + extra),
  };
}

function expandedTopicItems(group) {
  const byId = new Map();
  (group.branches || []).forEach((branch) => {
    sortTopicList(branch.topics).forEach((topic) => {
      if (!byId.has(topic.id)) byId.set(topic.id, { topic, parentName: branch.parent.name });
    });
  });
  if (!byId.size) {
    sortTopicList(group.topics || []).forEach((topic) => {
      if (!byId.has(topic.id)) byId.set(topic.id, { topic, parentName: "" });
    });
  }
  return [...byId.values()];
}

function masteryToneClass(value) {
  if (value >= 0.75) return "tone-strong";
  if (value >= 0.45) return "tone-progress";
  return "tone-weak";
}

function masteryStatus(value) {
  if (value < 0.4) return "薄弱";
  if (value < 0.7) return "良好";
  return "熟练";
}

function masteryColor(value) {
  if (value < 0.4) return "#eb5757";
  if (value < 0.7) return "#f2c94c";
  return "#27ae60";
}

function masteryRadius(value, base = 34) {
  if (value < 0.4) return base;
  if (value < 0.7) return base + 7;
  return base + 13;
}

function topicMasteryRow(topicId, masteryMap) {
  return masteryMap[topicId] || { mastery: 0, practice_count: 0, correct_count: 0, recent_errors: [] };
}

function topicWeakReason(topic, row) {
  if (!row.practice_count) return "还没有练习记录，系统暂时按薄弱项处理。";
  if ((row.mastery || 0) < 0.4) return (row.recent_errors || [])[0] || "近期正确率偏低，需要先补概念再做题。";
  if ((row.mastery || 0) < 0.7) return "掌握度还不稳定，建议继续做同类题巩固。";
  return "当前表现较稳定，可以进入综合应用。";
}

function topicStudyAdvice(topic, row) {
  if ((row.mastery || 0) < 0.4) return `先复习「${topic.name}」的核心概念，再完成 2 道基础题。`;
  if ((row.mastery || 0) < 0.7) return `围绕「${topic.name}」做一组标准练习，并整理错因。`;
  return `尝试「${topic.name}」的提升题，训练迁移应用。`;
}

function graphLabelLines(text, maxChars = 7, maxLines = 2) {
  const chars = Array.from(String(text || ""));
  const lines = [];
  for (let i = 0; i < chars.length && lines.length < maxLines; i += maxChars) {
    lines.push(chars.slice(i, i + maxChars).join(""));
  }
  if (chars.length > maxChars * maxLines && lines.length) {
    lines[lines.length - 1] = `${Array.from(lines[lines.length - 1]).slice(0, Math.max(maxChars - 1, 1)).join("")}...`;
  }
  return lines.length ? lines : ["未命名"];
}

function svgTextLines(text, x, y, options = {}) {
  const lines = graphLabelLines(text, options.maxChars || 7, options.maxLines || 2);
  const lineHeight = options.lineHeight || 18;
  const startY = y - ((lines.length - 1) * lineHeight) / 2;
  return `
    <text x="${x}" y="${startY}" class="${options.className || ""}" text-anchor="middle">
      ${lines.map((line, index) => `<tspan x="${x}" dy="${index === 0 ? 0 : lineHeight}">${escapeHtml(line)}</tspan>`).join("")}
    </text>
  `;
}

function renderSvgKnowledgeGraph(groups, masteryMap, options = {}) {
  const compact = !!options.compact;
  const profile = state.dashboard?.profile || {};
  const center = { x: 600, y: 350 };
  const selectedSubject = state.activeGraphSubject || "";
  const safeGroups = groups.slice(0, 8);
  const subjectNodes = [];
  const branchNodes = [];
  const topicNodes = [];
  const links = [];
  const groupCount = Math.max(safeGroups.length, 1);

  safeGroups.forEach((group, index) => {
    const summary = subjectSummary(group.topics, masteryMap);
    const angle = -90 + (360 / groupCount) * index;
    const subjectPoint = pointOnEllipse(angle, 330, 205);
    const color = graphColor(index);
    subjectNodes.push({ ...subjectPoint, angle, group, summary, color, index });
    links.push({ from: center, to: subjectPoint, color, soft: false, label: "学科" });

    const isSubjectExpanded = state.expandedGraphSubjects.has(group.subject);
    if (isSubjectExpanded) {
      const branches = (group.branches || [])
        .slice()
        .sort((a, b) => (a.parent.sort_order || 0) - (b.parent.sort_order || 0))
        .slice(0, 6);
      const localBounds = localGraphBounds(subjectPoint);
      const branchAngles = localGraphAngles(branches.length, subjectPoint);
      branches.forEach((branch, branchIndex) => {
        const branchAngle = branchAngles[branchIndex] ?? 90;
        const branchPoint = pointOnLocalEllipse(subjectPoint, branchAngle, 138, 102, localBounds);
        const branchMasteryTopics = branch.topics.length ? branch.topics : [branch.parent];
        const branchSummary = subjectSummary(branchMasteryTopics, masteryMap);
        branchNodes.push({ ...branchPoint, branch, group, color, summary: branchSummary, isLeaf: branch.isLeaf });
        links.push({ from: subjectPoint, to: branchPoint, color, soft: false, label: "一级" });

        const topics = sortTopicList(branch.topics).slice(0, 5);
        const topicSlots = topicAnglesAroundBranch(subjectPoint, branchPoint, topics.length);
        const topicBounds = topicBoundsAroundBranch(branchPoint, topics.length);
        topics.forEach((topic, topicIndex) => {
          const slot = topicSlots[topicIndex] || { angle: branchAngle, ring: 0 };
          const topicPoint = pointOnLocalEllipse(
            branchPoint,
            slot.angle,
            162 + slot.ring * 44,
            112 + slot.ring * 28,
            topicBounds
          );
          const masteryValueForTopic = masteryValue(topic.id, masteryMap);
          topicNodes.push({ ...topicPoint, topic, group, color, mastery: masteryValueForTopic, parentName: branch.parent.name });
          links.push({ from: branchPoint, to: topicPoint, color, soft: true, label: "二级" });
        });
      });
    }
  });

  const linkHtml = links.map((link) => `
    <line
      x1="${link.from.x.toFixed(1)}" y1="${link.from.y.toFixed(1)}"
      x2="${link.to.x.toFixed(1)}" y2="${link.to.y.toFixed(1)}"
      stroke="${link.color}" class="kg-svg-link ${link.soft ? "kg-topic-link soft" : "solid"}"
    />
    ${!link.soft ? `
      <text x="${((link.from.x + link.to.x) / 2).toFixed(1)}" y="${((link.from.y + link.to.y) / 2 - 8).toFixed(1)}" class="kg-link-label" text-anchor="middle">${escapeHtml(link.label)}</text>
    ` : ""}
  `).join("");

  const subjectHtml = subjectNodes.map((node) => {
    const color = masteryColor(node.summary.mastery);
    const radius = compact ? masteryRadius(node.summary.mastery, 42) : 62;
    const active = node.group.subject === selectedSubject;
    return `
    <g
      class="kg-svg-node kg-subject-node ${masteryToneClass(node.summary.mastery)} ${active ? "highlight" : ""}"
      data-mindmap-subject="${node.group.subject}"
      data-graph-subject="${node.group.subject}"
      data-tooltip-title="${escapeHtml(node.group.subject)}"
      data-tooltip-mastery="${Math.round(node.summary.mastery * 100)}%"
      data-tooltip-reason="${escapeHtml(node.summary.practiceCount ? "该学科按二级知识点平均掌握度统计。" : "暂无练习记录。")}"
      data-tooltip-advice="${escapeHtml(`点击查看${node.group.subject}二级知识点。`)}"
      tabindex="0"
    >
      <circle cx="${node.x.toFixed(1)}" cy="${node.y.toFixed(1)}" r="${radius}" fill="${node.color}" />
      ${svgTextLines(node.group.subject, node.x, node.y - 7, { className: "kg-node-label light", maxChars: 5, maxLines: 2, lineHeight: 17 })}
      <text x="${node.x.toFixed(1)}" y="${(node.y + 35).toFixed(1)}" class="kg-node-meta light" text-anchor="middle">${Math.round(node.summary.mastery * 100)}% · ${masteryStatus(node.summary.mastery)}</text>
    </g>
  `; }).join("");

  const branchHtml = branchNodes.map((node) => {
    const isLeaf = node.isLeaf;
    const radius = isLeaf ? masteryRadius(node.summary.mastery, 38) : 46;
    const masteryCol = isLeaf ? masteryColor(node.summary.mastery) : node.color;
    const status = isLeaf ? masteryStatus(node.summary.mastery) : "";
    const row = isLeaf ? topicMasteryRow(node.branch.parent.id, masteryMap) : null;
    return `
    <g
      class="kg-svg-node kg-branch-node ${masteryToneClass(node.summary.mastery)} ${isLeaf ? "kg-leaf-branch" : ""}"
      data-graph-subject="${node.group.subject}"
      ${isLeaf ? `data-topic-id="${node.branch.parent.id}"` : ""}
      data-tooltip-title="${escapeHtml(node.branch.parent.name)}"
      data-tooltip-mastery="${Math.round(node.summary.mastery * 100)}%${isLeaf ? ` · ${status}` : ""}"
      data-tooltip-reason="${escapeHtml(isLeaf ? (topicWeakReason(node.branch.parent, row || { mastery: 0, practice_count: 0, correct_count: 0, recent_errors: [] })) : `${node.group.subject}下的一级知识点，二级知识点围绕它展开。`)}"
      data-tooltip-advice="${escapeHtml(isLeaf ? topicStudyAdvice(node.branch.parent, row || { mastery: 0, practice_count: 0, correct_count: 0 }) : `继续查看${node.branch.parent.name}相关二级知识点。`)}"
      tabindex="0"
    >
      <circle cx="${node.x.toFixed(1)}" cy="${node.y.toFixed(1)}" r="${radius}" fill="#ffffff" stroke="${masteryCol}" stroke-width="${isLeaf ? 4 : 3}" />
      <circle cx="${node.x.toFixed(1)}" cy="${node.y.toFixed(1)}" r="${Math.max(radius - (isLeaf ? 8 : 9), 20)}" fill="${masteryCol}" opacity="${isLeaf ? 0.14 : 0.12}" />
      ${svgTextLines(node.branch.parent.name, node.x, node.y - 5, { className: "kg-node-label", maxChars: 5, maxLines: 2, lineHeight: 15 })}
      <text x="${node.x.toFixed(1)}" y="${(node.y + 28).toFixed(1)}" class="kg-node-meta" text-anchor="middle">${isLeaf ? `${Math.round(node.summary.mastery * 100)}% · ${status}` : `一级 · ${Math.round(node.summary.mastery * 100)}%`}</text>
    </g>
  `; }).join("");

  const topicHtml = topicNodes.map((node) => {
    const row = topicMasteryRow(node.topic.id, masteryMap);
    const color = masteryColor(node.mastery);
    const radius = masteryRadius(node.mastery);
    const status = masteryStatus(node.mastery);
    const weak = node.mastery < 0.4;
    return `
    <g
      class="kg-svg-node kg-topic-node ${masteryToneClass(node.mastery)}"
      data-graph-subject="${node.group.subject}"
      data-topic-id="${node.topic.id}"
      data-tooltip-title="${escapeHtml(node.topic.name)}"
      data-tooltip-mastery="${Math.round(node.mastery * 100)}% · ${status}"
      data-tooltip-reason="${escapeHtml(topicWeakReason(node.topic, row))}"
      data-tooltip-advice="${escapeHtml(topicStudyAdvice(node.topic, row))}"
      tabindex="0"
    >
      ${weak ? `<circle cx="${node.x.toFixed(1)}" cy="${node.y.toFixed(1)}" r="${radius + 8}" fill="none" stroke="#eb5757" stroke-width="3" stroke-dasharray="5 5" />` : ""}
      <circle cx="${node.x.toFixed(1)}" cy="${node.y.toFixed(1)}" r="${radius}" fill="#ffffff" stroke="${color}" stroke-width="4" />
      <circle cx="${node.x.toFixed(1)}" cy="${node.y.toFixed(1)}" r="${Math.max(radius - 8, 20)}" fill="${color}" opacity="0.14" />
      ${svgTextLines(node.topic.name, node.x, node.y - 8, { className: "kg-node-label", maxChars: 5, maxLines: 2, lineHeight: 15 })}
      <text x="${node.x.toFixed(1)}" y="${(node.y + radius - 6).toFixed(1)}" class="kg-node-meta" text-anchor="middle">${Math.round(node.mastery * 100)}% · ${status}</text>
    </g>
  `; }).join("");

  const activeGroup = safeGroups.find((group) => group.subject === selectedSubject);
  const activeTopicCount = activeGroup
    ? topicNodes.filter((node) => node.group.subject === activeGroup.subject).length
    : topicNodes.length;
  const hiddenTopicText = activeGroup && activeGroup.topics.length > activeTopicCount
    ? `<div class="kg-network-note">当前学科按一级知识点分组展示部分二级知识点，其余节点可在下方掌握度列表查看。</div>`
    : "";
  const graphTitle = `${profile.grade_level || "当前年级"}知识图谱`;

  return `
    <div class="kg-network-shell ${compact ? "preview" : "full"}">
      <div class="kg-network-scroll">
        <svg class="kg-network-svg" viewBox="0 0 1200 700" role="img" aria-label="${escapeHtml(profile.grade_level || "当前年级")}知识图谱">
          <rect x="0" y="0" width="1200" height="700" rx="8" class="kg-svg-bg" />
          ${linkHtml}
          <g class="kg-svg-node kg-center-node">
            <circle cx="${center.x}" cy="${center.y}" r="78" fill="#f2c94c" />
            ${svgTextLines(graphTitle, center.x, center.y - 8, { className: "kg-center-label", maxChars: 6, maxLines: 2, lineHeight: 22 })}
            <text x="${center.x}" y="${center.y + 42}" class="kg-center-meta" text-anchor="middle">${escapeHtml(profile.name || "我的学习")}</text>
          </g>
          ${subjectHtml}
          ${branchHtml}
          ${topicHtml}
        </svg>
      </div>
      ${hiddenTopicText}
      <div class="kg-network-legend">
        <span><i class="legend-dot weak"></i>低于 45%</span>
        <span><i class="legend-dot progress"></i>45% 到 74%</span>
        <span><i class="legend-dot strong"></i>75% 以上</span>
      </div>
    </div>
  `;
}

function renderMastery(profile) {
  const mastery = profile.mastery || {};
  const groups = graphGroupsBySubject();
  qs("masteryCards").innerHTML = groups.map((group) => {
    const summary = subjectSummary(group.topics, mastery);
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
          ${group.branches.map((branch) => {
            const branchMasteryTopics = branch.topics.length ? branch.topics : [branch.parent];
            const gradeSummary = subjectSummary(branchMasteryTopics, mastery);
            return `
              <details class="mastery-grade-block" open>
                <summary>
                  <span>${branch.parent.name}</span>
                  <span>${Math.round(gradeSummary.mastery * 100)}%</span>
                </summary>
                <div class="subject-topic-grid">
                  ${branchMasteryTopics.map((topic) => {
                    const row = mastery[topic.id] || { mastery: 0, practice_count: 0, correct_count: 0 };
                    const correctRate = row.practice_count ? `${Math.round((row.correct_count / row.practice_count) * 100)}%` : "暂无记录";
                    return `
                      <article class="mastery-card mastery-card-readonly" data-topic-id="${topic.id}">
                        <div class="mastery-top">
                          <div>
                            <div class="subject-kicker">${topic.grade_level || branch.parent.grade_level || "通用"} · 二级知识点</div>
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
  const groups = graphGroupsBySubject();
  const html = renderSvgKnowledgeGraph(groups, masteryMap, { compact: false });
  const preview = qs("knowledgeGraphPreview");
  if (preview) preview.innerHTML = html;
}

function ensureGraphTooltip() {
  let tooltip = qs("kgTooltip");
  if (!tooltip) {
    tooltip = document.createElement("div");
    tooltip.id = "kgTooltip";
    tooltip.className = "kg-tooltip";
    document.body.appendChild(tooltip);
  }
  return tooltip;
}

function showGraphTooltip(node, event) {
  const tooltip = ensureGraphTooltip();
  tooltip.innerHTML = `
    <strong>${node.dataset.tooltipTitle || "知识点"}</strong>
    <span>${node.dataset.tooltipMastery || "0%"}</span>
    <div>${node.dataset.tooltipReason || "暂无薄弱原因"}</div>
    <small>${node.dataset.tooltipAdvice || "继续完成针对性练习。"}</small>
  `;
  tooltip.style.left = `${event.clientX + 14}px`;
  tooltip.style.top = `${event.clientY + 14}px`;
  tooltip.classList.add("visible");
}

function hideGraphTooltip() {
  qs("kgTooltip")?.classList.remove("visible");
}

function ensureTopicDetailModal() {
  let modal = qs("topicDetailModal");
  if (!modal) {
    modal = document.createElement("div");
    modal.id = "topicDetailModal";
    modal.className = "modal-backdrop topic-detail-modal";
    document.body.appendChild(modal);
  }
  return modal;
}

function showTopicDetail(topicId) {
  const topic = currentTopic(topicId);
  if (!topic) return;
  const masteryMap = state.dashboard?.profile?.mastery || {};
  const row = topicMasteryRow(topic.id, masteryMap);
  const value = row.mastery || 0;
  const modal = ensureTopicDetailModal();
  modal.innerHTML = `
    <div class="modal-card topic-detail-card">
      <button class="modal-close" data-topic-modal-close type="button">关闭</button>
      <div class="subject-kicker">${escapeHtml(topic.grade_level || state.dashboard?.profile?.grade_level || "当前年级")} · ${escapeHtml(topic.subject || "学科")}</div>
      <h3>${escapeHtml(topic.name)}</h3>
      <div class="topic-detail-score" style="--topic-color:${masteryColor(value)};">
        <strong>${Math.round(value * 100)}%</strong>
        <span>${masteryStatus(value)}</span>
      </div>
      <div class="report-grid">
        <div class="note-card"><strong>薄弱原因</strong><div>${escapeHtml(topicWeakReason(topic, row))}</div></div>
        <div class="note-card"><strong>学习建议</strong><div>${escapeHtml(topicStudyAdvice(topic, row))}</div></div>
      </div>
      <div class="subtopic-list">
        ${(topic.subtopics || []).map((item) => `<span>${escapeHtml(item)}</span>`).join("") || "<span>综合应用</span>"}
      </div>
      <div class="inline-actions">
        <button class="primary-button" data-topic-action="practice" data-topic-id="${escapeHtml(topic.id)}" type="button">前往练习</button>
        <button class="ghost-button" data-topic-action="tutor" data-topic-id="${escapeHtml(topic.id)}" type="button">打开 AI 辅导</button>
      </div>
    </div>
  `;
  modal.classList.add("visible");
}

function closeTopicDetail() {
  qs("topicDetailModal")?.classList.remove("visible");
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
  return Math.min(Math.max(value, min), max);
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

function tutorKeywords() {
  const topic = currentTopic(qs("practiceTopicId")?.value || "");
  return [
    topic?.name,
    topic?.subject,
    "关键", "步骤", "原因", "方法", "概念", "公式", "翻译", "阅读理解", "错题", "练习",
  ].filter(Boolean);
}

function highlightTutorText(text) {
  let html = escapeHtml(stripMarkdown(text));
  tutorKeywords().forEach((keyword) => {
    const safe = escapeHtml(keyword);
    if (!safe || safe.length < 2) return;
    html = html.split(safe).join(`<mark>${safe}</mark>`);
  });
  return html;
}

function stripMarkdown(text) {
  return String(text || "")
    .replace(/```[\s\S]*?```/g, (block) => block.replace(/```[a-zA-Z0-9_-]*\n?/g, "").replace(/```/g, ""))
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/^\s*[-*+]\s+/gm, "")
    .replace(/^\s*>\s?/gm, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function splitTutorSteps(content) {
  const normalized = stripMarkdown(content).replace(/\r/g, "\n");
  const explicit = normalized.split(/\n+/).map((item) => item.trim()).filter(Boolean);
  if (explicit.length > 1) return explicit.slice(0, 8);
  return normalized
    .split(/(?<=[。！？；])\s*/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 8);
}

function renderAssistantContent(content) {
  const steps = splitTutorSteps(content);
  if (steps.length < 2) return `<div class="chat-text">${highlightTutorText(content)}</div>`;
  return `
    <div class="chat-step-list">
      ${steps.map((step, index) => `
        <article class="chat-step-card">
          <span>${index + 1}</span>
          <div>${highlightTutorText(step)}</div>
        </article>
      `).join("")}
    </div>
    <div class="chat-guide-actions">
      <button class="ghost-button quick-prompt" data-prompt="请帮我翻译一段文言文，并说明重点字词。">试试翻译一段</button>
      <button class="ghost-button quick-prompt" data-prompt="请总结阅读理解题的审题和答题技巧。">阅读理解技巧</button>
      <button class="primary-button" data-chat-action="practice">前往练习</button>
    </div>
  `;
}

function renderChat(history) {
  state.chatHistory = history || [];
  const rows = [...state.chatHistory];
  if (state.chatTyping) rows.push({ id: "typing", role: "assistant", content: "", typing: true, citations: [] });
  qs("chatHistory").innerHTML = rows.length ? rows.map((item) => {
    const assistant = item.role === "assistant";
    return `
      <article class="chat-row ${assistant ? "assistant" : "user"}" data-message-id="${item.id}">
        <div class="chat-avatar">${assistant ? "AI" : "我"}</div>
        <div class="chat-bubble">
          <div class="message-role">${assistant ? "AI 导师" : "学生"}</div>
          ${item.typing ? `<div class="typing-dots"><i></i><i></i><i></i></div>` : (assistant ? renderAssistantContent(item.content) : `<div class="chat-text">${highlightTutorText(item.content)}</div>`)}
          ${assistant && !item.typing ? renderCitationEvidence(item.citations) : ""}
          ${assistant && !item.typing ? `
            <div class="chat-message-actions">
              <button class="subtle-button" data-chat-copy="${item.id}" type="button">复制</button>
              <button class="subtle-button ${item.is_favorite ? "active" : ""}" data-chat-favorite="${item.id}" type="button">${item.is_favorite ? "已收藏" : "收藏"}</button>
            </div>
          ` : ""}
        </div>
      </article>
    `;
  }).join("") : "<div class='empty-state'>发送消息后开始对话</div>";
  qs("chatHistory").scrollTop = qs("chatHistory").scrollHeight;
}

async function loadTopics() {
  state.topics = await api("/graph/topics");
  renderTopicSelects(state.dashboard?.profile || null);
}

function topicOptionLabel(topic) {
  const grade = topic.grade_level ? `${topic.grade_level} · ` : "";
  return `${grade}${topic.subject} · ${topic.name}`;
}

function fillTopicContext(contextName, profile, preferred = {}) {
  const config = topicSelectContexts[contextName];
  const subjectSelect = qs(config.subjectId);
  const topicSelect = qs(config.topicId);
  if (!subjectSelect || !topicSelect) return;

  const groups = topicsBySubject();
  if (!groups.length) {
    subjectSelect.innerHTML = "<option value=''>暂无学科</option>";
    topicSelect.innerHTML = "<option value=''>暂无知识点</option>";
    return;
  }

  const currentTopicId = preferred.topicId || topicSelect.value || profile?.target_topic_id || "";
  const currentTopicItem = currentTopic(currentTopicId);
  const candidateSubject = preferred.subject || subjectSelect.value || currentTopicItem?.subject || profile?.target_subject || groups[0].subject;
  const selectedSubject = groups.some((group) => group.subject === candidateSubject) ? candidateSubject : groups[0].subject;
  const selectedGroup = groups.find((group) => group.subject === selectedSubject) || groups[0];
  const topicStillValid = selectedGroup.topics.some((topic) => topic.id === currentTopicId);
  const selectedTopicId = topicStillValid ? currentTopicId : selectedGroup.topics[0]?.id || "";

  subjectSelect.innerHTML = groups
    .map((group) => `<option value="${escapeHtml(group.subject)}">${escapeHtml(group.subject)}（${group.topics.length}）</option>`)
    .join("");
  subjectSelect.value = selectedSubject;
  topicSelect.innerHTML = selectedGroup.topics
    .map((topic) => `<option value="${escapeHtml(topic.id)}">${escapeHtml(topicOptionLabel(topic))}</option>`)
    .join("");
  topicSelect.value = selectedTopicId;
}

function renderTopicSelects(profile) {
  Object.keys(topicSelectContexts).forEach((contextName) => {
    fillTopicContext(contextName, profile);
  });
}

function setSubjectForContext(contextName, subject) {
  const config = topicSelectContexts[contextName];
  if (!config) return;
  fillTopicContext(contextName, state.dashboard?.profile || null, { subject });
}

function setSubjectAcrossSelectors(subject) {
  Object.keys(topicSelectContexts).forEach((contextName) => setSubjectForContext(contextName, subject));
}

function selectTopicAcrossSelectors(topicId) {
  const topic = currentTopic(topicId);
  Object.keys(topicSelectContexts).forEach((contextName) => {
    fillTopicContext(contextName, state.dashboard?.profile || null, { subject: topic?.subject || "", topicId });
  });
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
  if (state.user?.role && state.user.role !== "student") {
    qs("loginError").textContent = "请使用学生账号登录学生端。教师请进入教师端。";
    qs("loginError").style.display = "";
    showLoginGate();
    return;
  }
  state.students = await api("/students");
  if (!state.students.length) {
    if (qs("studentScopeLabel")) qs("studentScopeLabel").textContent = "暂无学习档案";
    qs("quickStatsContent").innerHTML = "<div class='empty-state'>当前账号还没有学习档案，请使用老师提供的邀请码重新注册。</div>";
    return;
  }
  state.currentStudentId = state.students[0].id;
  const profile = state.students[0];
  if (qs("studentScopeLabel")) {
    qs("studentScopeLabel").innerHTML = `<strong>${profile.name}</strong><span>${profile.grade_level} · 全学科</span>`;
  }
  await loadDashboard();
}

async function loadDashboard() {
  if (!state.currentStudentId) return;
  const dashboard = await api(`/students/${state.currentStudentId}/dashboard`);
  state.dashboard = dashboard;
  if (dashboard.available_topics?.length) state.topics = dashboard.available_topics;
  renderQuickStats(dashboard.profile);
  renderTopicSelects(dashboard.profile);
  renderKnowledgeGraph(dashboard.profile.mastery);
  renderMastery(dashboard.profile);
  renderMistakeNotebook(dashboard.recent_mistakes);
  renderReport(dashboard.latest_report);
  await loadReportHistory();
  renderSessions(dashboard.recent_sessions);
  if ([...qs("targetTopicId").options].some((item) => item.value === dashboard.profile.target_topic_id)) {
    selectTopicAcrossSelectors(dashboard.profile.target_topic_id);
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
  try {
    const topicId = qs("practiceTopicId").value || qs("targetTopicId").value;
    if (!topicId) {
      showToast("请先选择知识点");
      return;
    }

    const data = await api(`/students/${state.currentStudentId}/practice`, {
      method: "POST",
      body: JSON.stringify({
        topic_id: topicId
      }),
    });
    renderPractice(data);
    showToast("已推荐下一题 ✓");
  } catch (err) {
    const message = readableError(err);
    // 显示更友好的错误信息，如果是404错误提示用户检查所选知识点
    const errorMessage = message.includes("404") || message.toLowerCase().includes("not found")
      ? "当前知识点暂无可用题目，请切换知识点或联系老师补题"
      : message || "当前知识点暂无可用题目，请切换知识点或联系老师补题";
    qs("practiceView").innerHTML = `<div class="empty-state">${escapeHtml(errorMessage)}</div>`;
    qs("answerWorkspace").innerHTML = "<div class='empty-state'>推荐题目后显示输入框</div>";
    showToast("获取题目失败，请稍后再试");
  }
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
  let result;
  try {
    result = await api(`/students/${state.currentStudentId}/practice/submit`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  } catch (err) {
    const message = readableError(err);
    state.lastQuestion = null;
    state.lastPracticeMeta = null;
    qs("submissionResultView").innerHTML = `<div class="empty-state">${escapeHtml(message === "question not found" ? "该题已不可用，请重新推荐题目。" : message)}</div>`;
    qs("answerWorkspace").innerHTML = "<div class='empty-state'>推荐题目后显示输入框</div>";
    showToast("该题已不可用，请重新推荐");
    return null;
  }
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
  const submitted = await submitPracticeResult(finalAnswer);
  if (!submitted) return;
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
  state.chatHistory = [];
  renderChat(state.chatHistory);
  showToast("已创建新对话 ✓");
  setStep("tutor");
}

async function reloadSessions() {
  const sessions = await api(`/students/${state.currentStudentId}/chat/sessions`);
  renderSessions(sessions);
}

async function loadHistory(sessionId) {
  const history = await api(`/chat/sessions/${sessionId}`);
  state.chatHistory = history;
  renderChat(state.chatHistory);
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
  const content = qs("chatInput").value.trim();
  if (!content) {
    showToast("请先输入问题");
    return;
  }
  state.chatHistory = [
    ...state.chatHistory,
    { id: `local-${Date.now()}`, role: "user", content, created_at: new Date().toISOString(), citations: [] },
  ];
  state.chatTyping = true;
  renderChat(state.chatHistory);
  try {
    const payload = {
      content,
      difficulty_signal: 0.45,
    };

    const turn = await api(`/chat/sessions/${state.currentSessionId}/messages`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.chatHistory = turn.history;
    await reloadSessions();
    qs("chatInput").value = "";
    showToast("AI 回复已生成 ✓");
  } finally {
    state.chatTyping = false;
    renderChat(state.chatHistory);
  }
}

async function copyChatMessage(messageId) {
  const message = state.chatHistory.find((item) => String(item.id) === String(messageId));
  if (!message) return;
  await navigator.clipboard.writeText(stripMarkdown(message.content));
  showToast("已复制");
}

async function favoriteChatMessage(messageId) {
  const message = state.chatHistory.find((item) => String(item.id) === String(messageId));
  if (!message) return;
  const updated = await api(`/chat/messages/${messageId}/favorite`, {
    method: "PUT",
    body: JSON.stringify({ is_favorite: !message.is_favorite }),
  });
  state.chatHistory = state.chatHistory.map((item) => String(item.id) === String(messageId) ? updated : item);
  renderChat(state.chatHistory);
  showToast(updated.is_favorite ? "已收藏" : "已取消收藏");
}

function fillQuickPrompt(text) {
  qs("chatInput").value = text;
  qs("chatInput").focus();
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

function handleGraphClick(event) {
  const topicNode = event.target.closest("[data-topic-id]");
  if (topicNode) {
    showTopicDetail(topicNode.dataset.topicId);
    return;
  }
  const subjectNode = event.target.closest("[data-mindmap-subject]");
  if (subjectNode) openGraphSubject(subjectNode.dataset.mindmapSubject);
}

function handleGraphPointerMove(event) {
  const node = event.target.closest("[data-tooltip-title]");
  if (!node) {
    hideGraphTooltip();
    return;
  }
  showGraphTooltip(node, event);
}

function handleTopicModalClick(event) {
  if (event.target.closest("[data-topic-modal-close]") || event.target.id === "topicDetailModal") {
    closeTopicDetail();
    return;
  }
  const action = event.target.closest("[data-topic-action]");
  if (!action) return;
  const topicId = action.dataset.topicId;
  selectTopicAcrossSelectors(topicId);
  closeTopicDetail();
  if (action.dataset.topicAction === "practice") {
    navigateTo("practice");
    return;
  }
  navigateTo("tutor");
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
  qs("knowledgeGraphPreview").addEventListener("click", handleGraphClick);
  qs("knowledgeGraphPreview").addEventListener("mousemove", handleGraphPointerMove);
  qs("knowledgeGraphPreview").addEventListener("mouseleave", hideGraphTooltip);
  document.addEventListener("click", handleTopicModalClick);
  Object.keys(topicSelectContexts).forEach((contextName) => {
    const config = topicSelectContexts[contextName];
    qs(config.subjectId)?.addEventListener("change", (event) => {
      fillTopicContext(contextName, state.dashboard?.profile || null, { subject: event.target.value });
    });
  });
  qs("diagnosisButton").addEventListener("click", () => runDiagnosis().catch(handleError));
  qs("practiceButton").addEventListener("click", () => runPractice().catch(handleError));
  qs("submitAnswerButton").addEventListener("click", () => submitPracticeResult().catch(handleError));
  qs("coachCardButton").addEventListener("click", () => loadCoachCard().catch(handleError));
  qs("mistakeButton").addEventListener("click", () => analyzeMistake().catch(handleError));
  qs("refreshMistakesButton").addEventListener("click", () => loadMistakes().then(() => showToast("错题本已刷新 ✓")).catch(handleError));
  qs("createSessionButton").addEventListener("click", () => createSession().catch(handleError));
  qs("sendChatButton").addEventListener("click", () => sendChat().catch(handleError));
  qs("chatInput").addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    sendChat().catch(handleError);
  });
  qs("chatHistory").addEventListener("click", (event) => {
    const copyButton = event.target.closest("[data-chat-copy]");
    if (copyButton) { copyChatMessage(copyButton.dataset.chatCopy).catch(handleError); return; }
    const favoriteButton = event.target.closest("[data-chat-favorite]");
    if (favoriteButton) { favoriteChatMessage(favoriteButton.dataset.chatFavorite).catch(handleError); return; }
    const practiceButton = event.target.closest("[data-chat-action='practice']");
    if (practiceButton) navigateTo("practice");
    const promptButton = event.target.closest(".quick-prompt");
    if (promptButton) fillQuickPrompt(promptButton.dataset.prompt || "");
  });
  document.querySelectorAll(".quick-prompt-bar .quick-prompt").forEach((button) => {
    button.addEventListener("click", () => fillQuickPrompt(button.dataset.prompt || ""));
  });
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
  showToast(`操作失败: ${readableError(error)}`);
}

function readableError(error) {
  const raw = error?.message || String(error || "");
  try {
    const parsed = JSON.parse(raw);
    return parsed.detail || raw;
  } catch {
    return raw;
  }
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
