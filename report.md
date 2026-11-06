# 数据质量报告

生成时间：2026-11-06  
数据源：data_quotes_20261106.csv  
生成方式：`python crawler.py --full` 自动产出

## 一、采集概况

| 指标 | 数值 |
|------|------|
| 采集总条数 | 50 |
| 去重后条数 | 50（删除 0 条） |
| 爬虫总请求数 | 5 |
| 爬虫总耗时 | 11.3 秒 |
| 采集页码范围 | 第 1 ~ 5 页 |

## 二、字段完整率

| 字段 | 非空数/总数 | 完整率 |
|------|------------|--------|
| text         | 50/50 | 100.0% |
| author       | 50/50 | 100.0% |
| author_url   | 50/50 | 100.0% |
| tags         | 48/50 | 96.0% |
| page         | 50/50 | 100.0% |

## 三、去重统计

- 去重规则：按 `text`（名言全文）唯一键，保留首条
- 原始条数：**50** 条 → 去重后：**50** 条（删除 0 条）

## 四、字段极值与可疑值

### 4.1 text（名言）极值

- 最长名言：1084 字
  > “This life is what you make it. No matter what, you're going to mess up sometimes, it's a universal truth. But the good ...
- 最短名言：34 字
  > "“We read to know we're not alone.”"

### 4.2 author（作者）出现频次 Top3

| 排名 | 作者 | 条数 |
|------|------|------|
| 1 | Albert Einstein | 8 |
| 2 | J.K. Rowling | 6 |
| 3 | Marilyn Monroe | 6 |

### 4.3 tags 最多的一条

- 标签数：8 个
- 内容：“The opposite of love is not hate, it's indifference. The opposite of art is not ugliness, it's indifference. The opposi...
- 标签：activism|apathy|hate|indifference|inspirational|love|opposite|philosophy

### 4.4 可疑值清单（text 长度 < 10 字）

无，全部 text 长度 ≥ 10 字。

## 五、这份数据适合回答什么问题

1. **哪位作者在网站上出现频率最高？** —— 可按 `author` 聚合计数，得到 Top N 高频作者排行。
2. **各标签的分布如何？哪些主题最流行？** —— 拆解 `tags` 字段，按标签聚合即可得到主题热度排名。
3. **最长/最短的名言有哪些？各作者的平均名言长度差异？** —— 按 `text` 长度做极值与分组统计。
4. **5 页内的名言在不同页面上的分布是否均匀？** —— 按 `page` 分组看每页条数，判断采集是否均衡。
5. **某一位作者的所有名言列表？** —— 直接按 `author` 过滤即可，适合做作者专题合集。
6. **某一标签下都有哪些作者提到过？** —— 反查 `tags` 包含某个值的行，聚合 `author` 列。
