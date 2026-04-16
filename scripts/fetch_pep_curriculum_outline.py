from __future__ import annotations

"""
从教育部/人教公开页面抓取教材目录文本骨架，生成本地 seed 草稿。

说明：
1. 该脚本只做“在线抓取 + 粗抽取”；
2. 抓取结果需要人工校对后再写入 data/curriculum_seed_pep.json；
3. 若网络受限，可离线跳过。
"""

from dataclasses import dataclass
import json
import re
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


@dataclass
class Source:
    name: str
    url: str


SOURCES = [
    Source("教育部课程标准发布页", "https://www.moe.gov.cn/srcsite/A26/s8001/202204/t20220420_619921.html"),
    Source("人教初中数学目录示例", "https://www.pep.com.cn/czyysx/jshzhx/jszx/dzkb/202208/t20220817_1067193.shtml"),
    Source("人教初中语文目录示例", "https://www.pep.com.cn/czyyw/czyywjc/tbjxzy/dzkb/202208/t20220817_1067438.shtml"),
    Source("人教初中英语目录示例", "https://www.pep.com.cn/czyywy/jc/tbjxzy/dzkb/202208/t20220817_1067946.shtml"),
]


def fetch_html(url: str) -> str:
    with urlopen(url, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def extract_outline(html: str) -> list[str]:
    text = re.sub(r"<script[\\s\\S]*?</script>", " ", html, flags=re.I)
    text = re.sub(r"<style[\\s\\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"\s+", " ", text)
    # 抓取常见章节模式（第X章/单元/Unit）
    patterns = [
        r"第[一二三四五六七八九十0-9]+章[^。；;]{1,40}",
        r"第[一二三四五六七八九十0-9]+单元[^。；;]{1,40}",
        r"Unit\s*[0-9]+[^。；;]{1,40}",
    ]
    hits: list[str] = []
    for p in patterns:
        hits.extend(re.findall(p, text, flags=re.I))
    dedup = []
    for item in hits:
        clean = item.strip(" .，,;；")
        if clean and clean not in dedup:
            dedup.append(clean)
    return dedup[:80]


def main() -> None:
    result = {"fetched_at": __import__("datetime").datetime.utcnow().isoformat(), "sources": []}
    for source in SOURCES:
        item = {"name": source.name, "url": source.url, "outline": [], "error": ""}
        try:
            html = fetch_html(source.url)
            item["outline"] = extract_outline(html)
        except URLError as exc:
            item["error"] = f"network_error: {exc}"
        except Exception as exc:  # pragma: no cover
            item["error"] = f"unexpected_error: {exc}"
        result["sources"].append(item)

    out_path = Path("data") / "curriculum_seed_fetch_preview.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
