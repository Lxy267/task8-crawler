# -*- coding: utf-8 -*-
"""合规爬虫：从 quotes.toscrape.com 采集名言数据。

字段：text 名言全文 / author 作者 / author_url 作者主页 / tags 标签(| 连接) / page 页码
合规：每次请求后 sleep 1.5 秒；自报身份的 User-Agent；只采前 5 页；403 立即终止。

用法：
    python crawler.py          抽样模式：仅第 1 页前 5 条，打印表格供人工核对
    python crawler.py --full   全量模式：翻页采集前 5 页，保存 CSV
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://quotes.toscrape.com"
MAX_PAGES = 5          # 合规：只采前 5 页
SLEEP_SECONDS = 1.5    # 合规：每次请求后休息 1.5 秒
TIMEOUT = 10
FIELDS = ["text", "author", "author_url", "tags", "page"]
STATE_FILE = "state.json"  # 断点续爬进度文件
# 合规：自报身份的 UA。注意：HTTP 头只允许 ASCII，不能出现中文
HEADERS = {"User-Agent": "VibeCodingCourse/1.0 (student project; contact: 1871134843@qq.com)"}

START = time.time()
total_requests = 0
failed_pages = []


def report_stats():
    """结束时打印总请求数与总耗时。"""
    print(f"\n总请求数：{total_requests}，总耗时：{time.time() - START:.1f} 秒")


def generate_report(rows):
    """基于已采集数据生成 Markdown 格式的数据质量报告 report.md。"""
    elapsed = time.time() - START
    total = len(rows)

    # 字段完整率
    completeness_rows = []
    for col in FIELDS:
        non_empty = sum(1 for r in rows if str(r.get(col, "")).strip() != "")
        pct = (non_empty / total * 100) if total else 0
        completeness_rows.append(f"| {col:12s} | {non_empty}/{total} | {pct:.1f}% |")

    # 去重条数
    unique_texts = set(str(r.get("text", "")).strip() for r in rows)
    deduped = len(unique_texts)
    dup_deleted = total - deduped

    # 极值（按 text 长度）
    text_items = [(len(str(r.get("text", "")).strip()), r) for r in rows if str(r.get("text", "")).strip()]
    if text_items:
        longest = max(text_items, key=lambda x: x[0])
        shortest = min(text_items, key=lambda x: x[0])
    else:
        longest = shortest = (0, {})

    # 可疑值：text 长度 < 10
    suspicious = [r for r in rows if len(str(r.get("text", "")).strip()) < 10]

    # 各字段极值：page（转 int 后 min/max）、tags 最多的那条、author 出现次数 Top3
    def to_int_page(r):
        try:
            return int(r.get("page") or 0)
        except ValueError:
            return 0

    pages = [to_int_page(r) for r in rows]
    page_min, page_max = (min(pages), max(pages)) if pages else (0, 0)

    # author 频次 Top3
    from collections import Counter
    author_counts = Counter((r.get("author") or "").strip() for r in rows if (r.get("author") or "").strip())
    author_top3 = author_counts.most_common(3)

    # tags 最多的那条
    def tag_count(r):
        t = (r.get("tags") or "").strip()
        return len(t.split("|")) if t else 0
    most_tags_row = max(rows, key=tag_count) if rows else {}

    lines = [
        "# 数据质量报告",
        "",
        f"生成时间：{date.today():%Y-%m-%d}  ",
        f"数据源：{f'data_quotes_{date.today():%Y%m%d}.csv'}  ",
        f"生成方式：`python crawler.py --full` 自动产出",
        "",
        "## 一、采集概况",
        "",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 采集总条数 | {total} |",
        f"| 去重后条数 | {deduped}（删除 {dup_deleted} 条） |",
        f"| 爬虫总请求数 | {total_requests} |",
        f"| 爬虫总耗时 | {elapsed:.1f} 秒 |",
        f"| 采集页码范围 | 第 {page_min} ~ {page_max} 页 |",
        "",
        "## 二、字段完整率",
        "",
        "| 字段 | 非空数/总数 | 完整率 |",
        "|------|------------|--------|",
        *completeness_rows,
        "",
        "## 三、去重统计",
        "",
        f"- 去重规则：按 `text`（名言全文）唯一键，保留首条",
        f"- 原始条数：**{total}** 条 → 去重后：**{deduped}** 条（删除 {dup_deleted} 条）",
        "",
        "## 四、字段极值与可疑值",
        "",
        "### 4.1 text（名言）极值",
        "",
        f"- 最长名言：{longest[0]} 字",
        f"  > {(longest[1].get('text','')[:120] + ('...' if longest[0] > 120 else ''))}",
        f"- 最短名言：{shortest[0]} 字",
        f"  > {shortest[1].get('text','')!r}",
        "",
        "### 4.2 author（作者）出现频次 Top3",
        "",
        "| 排名 | 作者 | 条数 |",
        "|------|------|------|",
    ]
    for i, (name, cnt) in enumerate(author_top3, 1):
        lines.append(f"| {i} | {name} | {cnt} |")

    lines.extend([
        "",
        "### 4.3 tags 最多的一条",
        "",
        f"- 标签数：{tag_count(most_tags_row)} 个",
        f"- 内容：{(most_tags_row.get('text','')[:120] + ('...' if most_tags_row.get('text','') and len(most_tags_row['text']) > 120 else ''))}",
        f"- 标签：{most_tags_row.get('tags','')}",
        "",
        "### 4.4 可疑值清单（text 长度 < 10 字）",
        "",
    ])
    if suspicious:
        lines.append(f"共 {len(suspicious)} 条，建议人工核对：")
        lines.append("")
        for i, r in enumerate(suspicious, 1):
            lines.append(f"{i}. text={r.get('text','')!r}  author={r.get('author','')}  page={r.get('page','')}")
    else:
        lines.append("无，全部 text 长度 ≥ 10 字。")

    lines.extend([
        "",
        "## 五、这份数据适合回答什么问题",
        "",
        "1. **哪位作者在网站上出现频率最高？** —— 可按 `author` 聚合计数，得到 Top N 高频作者排行。",
        "2. **各标签的分布如何？哪些主题最流行？** —— 拆解 `tags` 字段，按标签聚合即可得到主题热度排名。",
        "3. **最长/最短的名言有哪些？各作者的平均名言长度差异？** —— 按 `text` 长度做极值与分组统计。",
        "4. **5 页内的名言在不同页面上的分布是否均匀？** —— 按 `page` 分组看每页条数，判断采集是否均衡。",
        "5. **某一位作者的所有名言列表？** —— 直接按 `author` 过滤即可，适合做作者专题合集。",
        "6. **某一标签下都有哪些作者提到过？** —— 反查 `tags` 包含某个值的行，聚合 `author` 列。",
        "",
    ])

    content = "\n".join(lines)
    with open("report.md", "w", encoding="utf-8") as f:
        f.write(content)
    print(f"📄 数据质量报告已生成 -> report.md")


def fetch(session, url):
    """请求一个页面：失败重试 1 次；403 立即终止；两次均失败返回 None。"""
    global total_requests
    for attempt in (1, 2):
        total_requests += 1
        try:
            resp = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        except requests.RequestException as exc:
            print(f"  [网络异常] {exc}")
        else:
            if resp.status_code == 403:
                print("收到 403 Forbidden，疑似被站点限制访问，按合规要求立即终止。")
                report_stats()
                sys.exit(1)
            if resp.status_code == 200:
                time.sleep(SLEEP_SECONDS)  # 合规：每次请求后限速
                return resp.text
            print(f"  [HTTP {resp.status_code}] 请求失败")
        if attempt == 1:
            time.sleep(SLEEP_SECONDS)  # 重试前同样遵守限速
    return None


def parse_quotes(html, page):
    """解析一页的名言数据，字段与要求严格一致。"""
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for box in soup.select("div.quote"):
        text_el = box.select_one("span.text")
        author_el = box.select_one("small.author")
        about_el = box.select_one("a[href^='/author/']")
        rows.append({
            "text": text_el.get_text(strip=True) if text_el else "",
            "author": author_el.get_text(strip=True) if author_el else "",
            "author_url": urljoin(BASE_URL, about_el["href"]) if about_el else "",
            "tags": "|".join(a.get_text(strip=True) for a in box.select("div.tags a.tag")),
            "page": page,
        })
    return rows


def next_page_url(html):
    """从分页导航中取出下一页地址，没有则返回 None。"""
    soup = BeautifulSoup(html, "lxml")
    nxt = soup.select_one("ul.pager li.next a")
    return urljoin(BASE_URL, nxt["href"]) if nxt else None


def print_table(rows):
    """控制台表格打印，供人工核对（text 过长时截断显示）。"""
    headers = ["#", "text", "author", "author_url", "tags", "page"]
    view = []
    for i, r in enumerate(rows, 1):
        text = r["text"] if len(r["text"]) <= 40 else r["text"][:40] + "..."
        view.append([str(i), text, r["author"], r["author_url"], r["tags"], str(r["page"])])
    widths = [max([len(h)] + [len(v[c]) for v in view]) for c, h in enumerate(headers)]
    line = "+-" + "-+-".join("-" * w for w in widths) + "-+"

    def fmt(cells):
        return "| " + " | ".join(c.ljust(w) for c, w in zip(cells, widths)) + " |"

    print(line)
    print(fmt(headers))
    print(line)
    for v in view:
        print(fmt(v))
    print(line)


def save_csv(rows):
    """以 utf-8-sig 编码保存 CSV，文件名带当天日期。"""
    filename = f"data_quotes_{date.today():%Y%m%d}.csv"
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return filename


def state_path():
    return STATE_FILE


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None


def save_state(completed_pages, row_count, last_text_preview, done=False):
    state = {
        "done": done,
        "completed_pages": sorted(set(completed_pages)),
        "row_count": row_count,
        "last_text_preview": last_text_preview,
    }
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_csv_rows():
    """续爬时读回已有 CSV 数据（避免重采已完成页）。"""
    filename = f"data_quotes_{date.today():%Y%m%d}.csv"
    if not os.path.exists(filename):
        return [], filename
    with open(filename, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, filename


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # 防止 Windows 控制台编码报错

    parser = argparse.ArgumentParser(description="quotes.toscrape.com 合规爬虫")
    parser.add_argument("--full", action="store_true",
                        help="全量模式：翻页采集前 5 页（默认仅第 1 页前 5 条供人工核对）")
    parser.add_argument("--fresh", action="store_true",
                        help="忽略断点从零开始（删除 state.json 和已采 CSV）")
    args = parser.parse_args()

    session = requests.Session()
    rows = []

    if not args.full:
        print("== 抽样模式：第 1 页前 5 条 ==")
        html = fetch(session, BASE_URL + "/")
        if html:
            rows = parse_quotes(html, page=1)[:5]
            print_table(rows)
        else:
            failed_pages.append(1)
            print("第 1 页重试后仍失败，无数据。")
    else:
        # --- 断点续爬入口 ---
        if args.fresh:
            if os.path.exists(STATE_FILE):
                os.remove(STATE_FILE)
            old_csv = f"data_quotes_{date.today():%Y%m%d}.csv"
            if os.path.exists(old_csv):
                os.remove(old_csv)
            print("== 全量模式：--fresh 从零开始 ==")
            completed_pages = []
        else:
            state = load_state()
            if state and state.get("done"):
                history_rows, _ = load_csv_rows()
                if history_rows:
                    generate_report(history_rows)
                print(f"\n✅ state.json 标记已完成（{state['row_count']} 条），无需重跑。加 --fresh 强制重采。")
                report_stats()
                sys.exit(0)
            rows, _ = load_csv_rows()  # 读回已有 CSV，防续爬时重采
            completed_pages = state.get("completed_pages", []) if state else []
            if completed_pages:
                next_page = max(completed_pages) + 1
                print(f"== 全量模式：从第 {next_page} 页续爬（已完成 {completed_pages}，已采 {len(rows)} 条） ==")
            else:
                print("== 全量模式：采集前 5 页 ==")

        # --- 翻页采集（核心逻辑不变，仅外层加状态读写） ---
        start_page = max(completed_pages, default=0) + 1
        page = start_page
        url = BASE_URL + "/" if page == 1 else f"{BASE_URL}/page/{page}/"
        while url and page <= MAX_PAGES:
            print(f"[第 {page}/{MAX_PAGES} 页] {url}")
            html = fetch(session, url)
            if html:
                page_rows = parse_quotes(html, page)
                rows.extend(page_rows)
                completed_pages.append(page)
                preview = page_rows[-1]["text"][:50] if page_rows else ""
                save_state(completed_pages, len(rows), preview, done=False)
                save_csv(rows)  # 中间产物同步落盘，防强杀丢数据
                print(f"  ✓ 当页 +{len(page_rows)} 条，累计 {len(rows)} 条（state 已更新）")
                nxt = next_page_url(html)
            else:
                print(f"  ✗ 第 {page} 页重试后仍失败，记录页码并跳过。")
                failed_pages.append(page)
                nxt = f"{BASE_URL}/page/{page + 1}/"  # 按站点规律跳到下一页
            page += 1
            url = nxt if page <= MAX_PAGES else None

        # --- 全部完成：写 done 标记 ---
        if page > MAX_PAGES:
            preview = rows[-1]["text"][:50] if rows else ""
            save_state(completed_pages, len(rows), preview, done=True)
            print(f"\n✅ 全部 {MAX_PAGES} 页采完，state.json 已标记 done=true")

    if rows:
        filename = save_csv(rows)
        empty_text = sum(1 for r in rows if not r["text"])
        print(f"\n已保存 {len(rows)} 条记录 -> {filename}（utf-8-sig）")
        print("校验通过：无空 text 字段。" if empty_text == 0
              else f"[警告] 存在 {empty_text} 条空 text 字段，请检查解析规则！")
        generate_report(rows)
    else:
        print("\n未采集到数据，未生成 CSV。")

    if failed_pages:
        print(f"失败页码（已跳过）：{failed_pages}")

    report_stats()


if __name__ == "__main__":
    main()
