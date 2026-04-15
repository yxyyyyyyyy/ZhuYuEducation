from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402


def main() -> None:
    client = TestClient(app)

    homepage = client.get("/")
    assert homepage.status_code == 200
    html = homepage.text
    assert "让学习路径更清楚" in html
    assert "学生注册" in html
    assert "教师注册" not in html
    assert "管理员" in html
    assert "班级邀请码" in html
    assert "demo@zhuyu.local" not in html
    assert "demo123456" not in html
    assert "演示账号" not in html
    assert "/static/home.js" in html

    student_page = client.get("/student")
    assert student_page.status_code == 200
    student_html = student_page.text
    assert "学生学习台" in student_html
    assert "班级邀请码" in student_html
    assert "AI 推荐练习" in student_html
    assert "知识图谱" in student_html
    assert 'data-page="graph"' in student_html
    assert "knowledgeGraphPreview" in student_html
    assert "reportHistoryView" in student_html

    teacher_page = client.get("/teacher")
    assert teacher_page.status_code == 200
    teacher_html = teacher_page.text
    assert "资料/RAG 工作区" in teacher_html
    assert "教师注册" not in teacher_html
    assert "学校班级" in teacher_html
    assert "上传资料" in teacher_html
    assert "评测问题集" in teacher_html
    assert "uploadDocumentFile" in teacher_html
    assert 'data-page="practice-review"' in teacher_html
    assert "downloadTemplateButton" in teacher_html

    admin_page = client.get("/admin")
    assert admin_page.status_code == 200
    admin_html = admin_page.text
    assert "管理员后台" in admin_html
    assert "教师账号管理" in admin_html
    assert "知识图谱配置" in admin_html
    assert "/static/admin.js" in admin_html

    css = client.get("/static/styles.css")
    assert css.status_code == 200
    assert "--accent" in css.text
    assert ".immersive-practice-shell" in css.text
    assert "Enterprise UI refresh" in css.text

    home_js = client.get("/static/home.js")
    assert home_js.status_code == 200
    assert "student-register" in home_js.text
    assert "admin-login" in home_js.text
    assert "teacher-register" not in home_js.text

    js = client.get("/static/student.js")
    assert js.status_code == 200
    assert "openQuestionById" in js.text
    assert "renderPractice" in js.text
    assert "studentJudgmentOption" in js.text

    teacher_js = client.get("/static/teacher.js")
    assert teacher_js.status_code == 200
    assert "downloadCsvTemplate" in teacher_js.text
    assert "resolvePracticeReview" in teacher_js.text
    assert "/auth/register/teacher" not in teacher_js.text

    admin_js = client.get("/static/admin.js")
    assert admin_js.status_code == 200
    assert "/admin/teachers" in admin_js.text
    assert "renderKnowledgeTree" in admin_js.text

    topics = client.get("/graph/topics")
    assert topics.status_code == 200
    assert len(topics.json()) >= 3

    print("frontend verification passed")


if __name__ == "__main__":
    main()
