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
# 合规：自报身份的 UA。注意：HTTP 头只允许 ASCII，不能出现中文
HEADERS = {"User-Agent": "VibeCodingCourse/1.0 (student project; contact: 1871134843@qq.com)"}

START = time.time()
total_requests = 0
failed_pages = []


def report_stats():
    """结束时打印总请求数与总耗时。"""
    print(f"\n总请求数：{total_requests}，总耗时：{time.time() - START:.1f} 秒")


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


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # 防止 Windows 控制台编码报错

    parser = argparse.ArgumentParser(description="quotes.toscrape.com 合规爬虫")
    parser.add_argument("--full", action="store_true",
                        help="全量模式：翻页采集前 5 页（默认仅第 1 页前 5 条供人工核对）")
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
        print("== 全量模式：采集前 5 页 ==")
        url, page = BASE_URL + "/", 1
        while url and page <= MAX_PAGES:
            print(f"[第 {page} 页] {url}")
            html = fetch(session, url)
            if html:
                rows.extend(parse_quotes(html, page))
                nxt = next_page_url(html)
            else:
                print(f"  第 {page} 页重试后仍失败，记录页码并跳过。")
                failed_pages.append(page)
                nxt = f"{BASE_URL}/page/{page + 1}/"  # 按站点规律跳到下一页
            page += 1
            url = nxt if page <= MAX_PAGES else None

    if rows:
        filename = save_csv(rows)
        empty_text = sum(1 for r in rows if not r["text"])
        print(f"\n已保存 {len(rows)} 条记录 -> {filename}（utf-8-sig）")
        print("校验通过：无空 text 字段。" if empty_text == 0
              else f"[警告] 存在 {empty_text} 条空 text 字段，请检查解析规则！")
    else:
        print("\n未采集到数据，未生成 CSV。")

    if failed_pages:
        print(f"失败页码（已跳过）：{failed_pages}")

    report_stats()


if __name__ == "__main__":
    main()
