const authState = {
  token: localStorage.getItem("zhuyu_token") || "",
  user: null,
  mode: "student-login",
};

function qs(id) {
  return document.getElementById(id);
}

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (authState.token) headers["X-Session-Token"] = authState.token;
  const response = await fetch(path, { ...options, headers });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

function workspacePath(user = authState.user) {
  if (user?.role === "admin") return "/admin";
  return user?.role === "teacher" ? "/teacher" : "/student";
}

function setError(message = "") {
  const target = qs("authError");
  target.textContent = message;
  target.style.display = message ? "" : "none";
}

function setMode(mode) {
  authState.mode = mode;
  const titleMap = {
    "student-login": "学生登录",
    "student-register": "学生注册",
    "teacher-login": "教师登录",
    "admin-login": "管理员登录",
  };
  qs("authTitle").textContent = titleMap[mode] || "学生登录";
  document.querySelectorAll(".auth-tab").forEach((item) => {
    item.classList.toggle("active", item.dataset.authMode === mode);
  });
  document.querySelectorAll(".auth-form").forEach((item) => {
    item.classList.toggle("active", item.dataset.authForm === mode);
  });
  setError("");
}

function saveAuth(data) {
  authState.token = data.token;
  authState.user = data.user;
  localStorage.setItem("zhuyu_token", data.token);
}

async function login(email, password, expectedRole) {
  const data = await api("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  if (data.user.role !== expectedRole) {
    const roleName = expectedRole === "admin" ? "管理员" : expectedRole === "teacher" ? "教师" : "学生";
    throw new Error(`该账号不是${roleName}账号`);
  }
  saveAuth(data);
  window.location.href = workspacePath(data.user);
}

async function registerStudent() {
  const data = await api("/auth/register/student", {
    method: "POST",
    body: JSON.stringify({
      full_name: qs("studentRegisterName").value,
      email: qs("studentRegisterEmail").value,
      password: qs("studentRegisterPassword").value,
      invite_code: qs("studentRegisterInviteCode").value,
      target_subject: "数学",
    }),
  });
  saveAuth(data);
  window.location.href = "/student";
}

function bindEvents() {
  document.querySelectorAll(".auth-tab").forEach((tab) => {
    tab.addEventListener("click", () => setMode(tab.dataset.authMode));
  });
  qs("studentLoginButton").addEventListener("click", () => {
    login(qs("studentLoginEmail").value, qs("studentLoginPassword").value, "student").catch((error) => setError(error.message));
  });
  qs("teacherLoginButton").addEventListener("click", () => {
    login(qs("teacherLoginEmail").value, qs("teacherLoginPassword").value, "teacher").catch((error) => setError(error.message));
  });
  qs("adminLoginButton").addEventListener("click", () => {
    login(qs("adminLoginEmail").value, qs("adminLoginPassword").value, "admin").catch((error) => setError(error.message));
  });
  qs("studentRegisterButton").addEventListener("click", () => {
    registerStudent().catch((error) => setError(error.message));
  });
  qs("enterWorkspaceButton").addEventListener("click", () => {
    window.location.href = workspacePath();
  });
  document.querySelectorAll(".auth-form input").forEach((input) => {
    input.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      const activeButton = document.querySelector(".auth-form.active .primary-button");
      if (activeButton) activeButton.click();
    });
  });
}

async function bootstrap() {
  bindEvents();
  const params = new URLSearchParams(window.location.search);
  const mode = params.get("mode");
  if (mode && document.querySelector(`[data-auth-mode="${mode}"]`)) setMode(mode);
  if (!authState.token) return;
  try {
    authState.user = await api("/auth/me");
    qs("enterWorkspaceButton").style.display = "";
  } catch {
    localStorage.removeItem("zhuyu_token");
    authState.token = "";
  }
}

bootstrap().catch((error) => setError(error.message));
