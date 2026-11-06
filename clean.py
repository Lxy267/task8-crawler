# -*- coding: utf-8 -*-
"""数据清洗脚本：对 data_quotes_日期.csv 做四步清洗。

用法：python clean.py [文件名]
  - 不传参数时，自动选取目录下最新的 data_quotes_*.csv
  - 输出：clean_log.txt（清洗日志）、data_quotes_clean_日期.csv（utf-8-sig）

清洗步骤：
  ① 去重：按 text 全文去重，保留首条
  ② 补空： author 空 -> "未知"；tags 空 -> "无标签"
  ③ 统一格式：text 去首尾空白、内部多空格压一个；author_url 补绝对地址
  ④ 极值校验：打印非空率、text 长度 min/max、长度 <5 的行列出人工确认
每一步都打印并记录处理前后的行数。
"""

import csv
import glob
import os
import re
import sys
from datetime import date
from urllib.parse import urljoin

BASE_URL = "https://quotes.toscrape.com"
FIELDS = ["text", "author", "author_url", "tags", "page"]

# 清洗日志：终端同步输出 + clean_log.txt 落盘
LOG_FILE = "clean_log.txt"


class Logger:
    """同时写终端和日志文件，避免 Windows 控制台编码报错。"""

    def __init__(self, path):
        self.f = open(path, "w", encoding="utf-8")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="replace")

    def log(self, line=""):
        print(line)
        self.f.write(line + "\n")
        self.f.flush()

    def close(self):
        self.f.close()


def pick_input():
    """自动选取目录下最新的 data_quotes_*.csv。"""
    files = glob.glob("data_quotes_*.csv")
    files = [f for f in files if "clean" not in f]  # 排除 clean 结果
    if not files:
        print("未找到 data_quotes_*.csv，请先运行 crawler.py --full")
        sys.exit(1)
    files.sort(key=os.path.getmtime, reverse=True)
    return files[0]


def read_csv(path):
    """读取 CSV，utf-8-sig（带 BOM）→ 列名 strip 去 BOM。"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    # 规范化列名（去 BOM / 首尾空格）
    norm = {}
    for k in rows[0].keys() if rows else []:
        norm[k] = k.strip().lstrip("\ufeff")
    return [{norm[k]: v for k, v in r.items()} for r in rows]


def step1_dedup(rows, log):
    """按 text 去重，保留首条。"""
    before = len(rows)
    seen = set()
    kept = []
    for r in rows:
        key = r.get("text", "")
        if key and key not in seen:
            seen.add(key)
            kept.append(r)
    deleted = before - len(kept)
    log.log(f"[Step1 去重] 处理前 {before} 行 -> 处理后 {len(kept)} 行，删除 {deleted} 行")
    return kept, deleted


def step2_fill_nulls(rows, log):
    """author 空填 '未知'；tags 空填 '无标签'。"""
    before = len(rows)
    fill_author = 0
    fill_tags = 0
    for r in rows:
        if not (r.get("author") or "").strip():
            r["author"] = "未知"
            fill_author += 1
        if not (r.get("tags") or "").strip():
            r["tags"] = "无标签"
            fill_tags += 1
    log.log(f"[Step2 补空] 处理前 {before} 行 -> 处理后 {len(rows)} 行")
    log.log(f"             author 补空 {fill_author} 条，tags 补空 {fill_tags} 条")
    return rows, fill_author, fill_tags


def step3_normalize(rows, log):
    """text：去首尾空白 + 内部连续空格压成一个；author_url：补全绝对地址。"""
    before = len(rows)
    text_changed = 0
    url_changed = 0
    for r in rows:
        orig_text = r.get("text", "")
        new_text = re.sub(r"\s+", " ", orig_text).strip()
        if new_text != orig_text:
            r["text"] = new_text
            text_changed += 1

        orig_url = r.get("author_url", "")
        if orig_url and not orig_url.startswith(("http://", "https://")):
            r["author_url"] = urljoin(BASE_URL, orig_url)
            url_changed += 1
        elif not orig_url:
            r["author_url"] = ""  # 保持一致，空值交给 Step2 不会处理它（author_url 不在补空规则内）
    log.log(f"[Step3 统一格式] 处理前 {before} 行 -> 处理后 {len(rows)} 行")
    log.log(f"                 text 规范化 {text_changed} 条，author_url 补绝对地址 {url_changed} 条")
    return rows, text_changed, url_changed


def step4_profile(rows, log):
    """极值校验：非空率、text 长度 min/max、text 长度 <5 的行列出。"""
    log.log(f"[Step4 极值校验] 样本数 {len(rows)}")
    log.log("--- 各列非空率 ---")
    for col in FIELDS:
        total = len(rows)
        non_empty = sum(1 for r in rows if (r.get(col) or "").strip() != "")
        pct = (non_empty / total * 100) if total else 0
        log.log(f"  {col:12s}: {non_empty}/{total}  ({pct:.1f}%)")

    text_lens = [(len((r.get("text") or "").strip()), i + 1) for i, r in enumerate(rows)]
    if text_lens:
        lengths = [t for t, _ in text_lens]
        log.log(f"\n--- text 长度统计 ---")
        log.log(f"  min = {min(lengths)}  max = {max(lengths)}  avg = {sum(lengths) / len(lengths):.1f}")

        short = [(t, idx) for t, idx in text_lens if t < 5]
        if short:
            log.log(f"\n--- 人工确认：text 长度 <5 行（共 {len(short)} 条） ---")
            for t, idx in short:
                sample = rows[idx - 1].get("text", "")
                log.log(f"  行 #{idx}  长度 {t}  text={sample!r}")
        else:
            log.log("\n--- 人工确认：无 text 长度 <5 的行，全部正常 ---")
    return rows


def write_csv(rows, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else pick_input()
    if not os.path.exists(src):
        print(f"输入文件不存在：{src}")
        sys.exit(1)

    clean_date = date.today().strftime("%Y%m%d")
    dst = f"data_quotes_clean_{clean_date}.csv"

    log = Logger(LOG_FILE)
    log.log(f"=== 数据清洗开始 ===\n输入：{src}\n输出：{dst}\n")

    rows = read_csv(src)
    log.log(f"[读取] {len(rows)} 行，字段：{FIELDS}\n")

    rows, _ = step1_dedup(rows, log)
    log.log("")
    rows, _, _ = step2_fill_nulls(rows, log)
    log.log("")
    rows, _, _ = step3_normalize(rows, log)
    log.log("")
    step4_profile(rows, log)

    write_csv(rows, dst)
    log.log(f"\n[完成] 已保存清洗结果 -> {dst}（utf-8-sig）")
    log.log(f"       清洗日志 -> {LOG_FILE}")
    log.close()


if __name__ == "__main__":
    main()
