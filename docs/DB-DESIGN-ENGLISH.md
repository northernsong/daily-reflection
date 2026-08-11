# 英语学习模块 · 数据表字段设计

> 版本：v1.1（草案）
> 最后更新：2026-08-11
> 适用架构：MCP Server（Spring Boot + H2/Postgres），生成类工作（释义、例句、出题、批改）由宿主 LLM 完成，服务端只负责存储与调度

## 修订记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v1.0 | 2026-08-11 | 初稿，7 张表 |
| v1.1 | 2026-08-11 | `word_sense`、`example` 提到一期；`example` 增加 LLM 结果缓存语义（去重、屏蔽、轮换）；`word_relation` 定稿设计并建表，数据渐进积累；移除 `tag / item_tag`；`word.definition_zh`、`word.pos_primary` 下沉到 `word_sense` |

---

## 1. 设计目标

围绕四个可回答的问题：

| 用户问题 | 由谁回答 |
| --- | --- |
| 我学了哪些？ | `study_record` 事件流 + `study_item` 覆盖情况 |
| 该复习哪些？ | `study_item.due_at <= now()` 排序取 N 条 |
| 进度如何？ | `study_item` 对 `word_list` 的覆盖率 + `daily_stat` 趋势 |
| 这个词什么意思、怎么用？ | `word_sense` 义项 + `example` 例句（LLM 生成一次，长期复用） |

## 2. 分层结构

```
内容层（是什么，可共享、可预置）
  word          单词词条（形、音、词频、分级）
  word_sense    义项（词性 + 释义），一词多义
  example       例句，单词 / 义项 / 语法共用，兼作 LLM 生成结果缓存
  grammar_point 语法点
  word_list / word_list_item   目标词表（四级、雅思核心词…）→ 进度的分母
  word_relation 词间关系（同义/反义/派生/形近）→ 知识图谱底座，数据渐进积累

学习层（用户与内容的关系 + 复习状态）
  study_item    可复习项 = 用户 × (单词 | 语法)，承载 SM-2 状态

事件层（唯一事实来源，只追加）
  study_record  每一次学习/复习/答题

汇总层（派生数据，可随时重算）
  daily_stat    每日快照，用于打卡与趋势图
```

一期共 10 张表。两条贯穿全局的原则：

1. **事件流是唯一权威数据**。`study_record` 只追加，`study_item` 与 `daily_stat` 都是派生状态，任何时候都能从事件流重放重建。统计口径变了或算错了，重算即可。
2. **内容层不含 user_id**。词条、义项、例句是共享词典，用户私有的东西只有两类：`study_item` 上的复习状态和笔记，以及 `example` 上的收藏/屏蔽标记。

---

## 3. 内容层

### 3.1 word · 单词词条

只放"这个词本身"的属性，释义和词性归 `word_sense`。

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| id | bigint | N | 自增 | 主键 |
| headword | varchar(64) | N | - | 词条原形（lemma），如 `take` |
| lemma_id | bigint | Y | null | 指向原形词，变形词（took/taken）用；自引用 |
| phonetic_uk | varchar(64) | Y | null | 英式音标 |
| phonetic_us | varchar(64) | Y | null | 美式音标 |
| syllables | varchar(64) | Y | null | 音节划分，如 `beau·ti·ful`，拼写练习用 |
| cefr_level | varchar(4) | Y | null | `A1/A2/B1/B2/C1/C2`，取最常用义项的级别 |
| frequency_rank | int | Y | null | 词频排名，越小越常用，决定学习顺序 |
| sense_count | smallint | N | 0 | 义项数，冗余，列表页避免 count 子查询 |
| source | varchar(32) | Y | null | 来源 `MANUAL/IMPORT/LLM` |
| created_at | timestamp | N | now | |
| updated_at | timestamp | N | now | |

- 唯一约束：`uk_word_headword (headword)`
- 索引：`idx_word_freq (frequency_rank)`、`idx_word_level (cefr_level)`

> v1.0 里的 `definition_zh` 和 `pos_primary` 已移除。有了 `word_sense`，把释义同时放两处必然出现不一致；列表展示走 `is_primary = true` 的那条义项，这个规模下 join 成本可以忽略。真成为热点了再加缓存列，那时也只有一个明确的回填来源。

### 3.2 word_sense · 义项（一词多义）

`take` 的"拿走""花费（时间）""搭乘"是三个独立义项，各自的常用度、难度、例句都不同。

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| id | bigint | N | 自增 | 主键 |
| word_id | bigint | N | - | FK → word |
| sense_order | smallint | N | 1 | 义项序号，1 最常用，决定展示顺序 |
| is_primary | boolean | N | false | 主义项，列表页只显示这一条 |
| pos | varchar(16) | N | - | 词性 `n/v/adj/adv/prep/conj/pron/num/art/int/phr` |
| definition_zh | varchar(512) | N | - | 中文释义 |
| definition_en | varchar(512) | Y | null | 英文释义，进阶阶段用英英解释 |
| register | varchar(32) | Y | null | 语域 `FORMAL/INFORMAL/SLANG/LITERARY/TECHNICAL` |
| cefr_level | varchar(4) | Y | null | 义项级别。`take` 常用义 A1，"忍受"义 B2 |
| collocations | varchar(256) | Y | null | 典型搭配，逗号分隔，如 `take place, take a bus` |
| note | varchar(256) | Y | null | 辨析、易错提示 |
| source | varchar(32) | Y | null | `MANUAL/IMPORT/LLM` |
| created_at | timestamp | N | now | |
| updated_at | timestamp | N | now | |

- 唯一约束：`uk_sense_word_order (word_id, sense_order)`
- 索引：`idx_sense_word (word_id)`
- 一个词最多一条主义项：Postgres 用条件唯一索引 `(word_id) WHERE is_primary`；H2 不支持条件唯一索引，需在应用层保证（写入主义项时先清掉旧的，同一事务内）。

### 3.3 example · 例句（兼 LLM 生成结果缓存）

这张表有双重身份：内容上是例句库，工程上是宿主 LLM 的产出缓存。同一个词第二次复习时直接返回已存的句子，不再让 LLM 重新生成，省 token 也省等待。

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| id | bigint | N | 自增 | 主键 |
| ref_type | varchar(16) | N | - | `WORD` / `WORD_SENSE` / `GRAMMAR` |
| ref_id | bigint | N | - | 指向 word.id / word_sense.id / grammar_point.id |
| text_en | varchar(512) | N | - | 英文例句 |
| text_zh | varchar(512) | Y | null | 中文翻译 |
| target_form | varchar(64) | Y | null | 目标词在句中的实际形态（如 `took`），用于高亮和挖空出题 |
| text_hash | char(32) | N | - | `md5(lower(trim(text_en)))`，去重键 |
| cefr_level | varchar(4) | Y | null | 例句难度，按学习者水平挑句子 |
| source | varchar(32) | N | `LLM` | `LLM/IMPORT/MANUAL` |
| source_model | varchar(64) | Y | null | 生成模型标识，便于日后按模型清理低质量批次 |
| is_pinned | boolean | N | false | 用户收藏，优先展示 |
| is_hidden | boolean | N | false | 质量差，屏蔽 |
| use_count | int | N | 0 | 被展示/出题次数，用于轮换 |
| last_used_at | timestamp | Y | null | 最近使用时间 |
| created_at | timestamp | N | now | |

- 唯一约束：`uk_example_ref_hash (ref_type, ref_id, text_hash)` —— 缓存去重的关键。LLM 反复生成同一句是常态，靠这个约束挡掉，写入时用 upsert（`ON CONFLICT DO NOTHING`）而不是先查再插。
- 索引：`idx_example_ref (ref_type, ref_id, is_hidden, use_count)` —— 取"这个词还没怎么用过的例句"。

**缓存怎么用**：MCP 工具返回某词的学习卡片时，先查该词已有几条可用例句（`is_hidden = false`）。够数（建议 3 条）就只返回缓存；不够才在响应里提示宿主 LLM 补齐，再由写入工具落库。`use_count` 让每次复习尽量换一句，避免用户把句子而不是词背下来。

**屏蔽而不是删除**：LLM 生成的句子有时有语法错误或搭配别扭，`is_hidden = true` 保留 `text_hash`，下次生成到同一句会被唯一约束挡回去，不会再冒出来。物理删掉就失去这个记忆了。

### 3.4 grammar_point · 语法点

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| id | bigint | N | 自增 | 主键 |
| title | varchar(128) | N | - | 如「现在完成时」 |
| category | varchar(32) | N | - | `TENSE/VOICE/CLAUSE/NON_FINITE/PREPOSITION/ARTICLE/WORD_ORDER/OTHER` |
| parent_id | bigint | Y | null | 层级，如「从句」→「定语从句」 |
| formula | varchar(256) | Y | null | 结构公式，如 `have/has + done` |
| summary | varchar(512) | Y | null | 一句话说明，列表展示用 |
| explanation | text | Y | null | 详细讲解（Markdown） |
| common_mistakes | text | Y | null | 常见错误，出改错题的素材 |
| cefr_level | varchar(4) | Y | null | 同上 |
| difficulty | smallint | N | 3 | 1~5，出题与排序参考 |
| source | varchar(32) | Y | null | `MANUAL/IMPORT/LLM` |
| created_at | timestamp | N | now | |
| updated_at | timestamp | N | now | |

- 唯一约束：`uk_grammar_title (title)`
- 索引：`idx_grammar_category (category)`、`idx_grammar_parent (parent_id)`

语法点的例句同样进 `example` 表（`ref_type = 'GRAMMAR'`），机制完全复用。

### 3.5 word_list / word_list_item · 目标词表

进度的分母。没有它，"学了 800 个词"只是个绝对数，说不出完成度。

**word_list**

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| id | bigint | N | 自增 | |
| name | varchar(64) | N | - | 如「CET-4 核心词」 |
| kind | varchar(16) | N | `EXAM` | `EXAM/THEME/CUSTOM` |
| total_count | int | N | 0 | 词条总数，冗余便于算百分比 |
| description | varchar(256) | Y | null | |
| created_at | timestamp | N | now | |

**word_list_item**

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| list_id | bigint | N | - | FK → word_list |
| word_id | bigint | N | - | FK → word |
| sort_order | int | N | 0 | 建议学习顺序 |

- 主键：`(list_id, word_id)`
- 索引：`idx_wli_word (word_id)`

### 3.6 word_relation · 词间关系（知识图谱底座）

表结构一期就建好，数据不集中生产、慢慢长。

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| word_id | bigint | N | - | 起点词 |
| related_word_id | bigint | N | - | 关联词 |
| relation_type | varchar(24) | N | - | 见下表 |
| strength | smallint | Y | null | 1~5 关联紧密度，排序/筛选用 |
| note | varchar(256) | Y | null | **辨析说明**，这张表最值钱的字段 |
| source | varchar(32) | Y | null | `MANUAL/IMPORT/LLM` |
| created_at | timestamp | N | now | |

- 主键：`(word_id, related_word_id, relation_type)`
- 索引：`idx_rel_reverse (related_word_id, relation_type)`
- CHECK：`word_id <> related_word_id`

| relation_type | 含义 | 方向 |
| --- | --- | --- |
| SYNONYM | 同义/近义 | 对称，双向各写一行 |
| ANTONYM | 反义 | 对称，双向各写一行 |
| CONFUSABLE | 形近/易混（affect / effect） | 对称，双向各写一行 |
| SAME_ROOT | 同词根词族（port → import / export） | 对称，双向各写一行 |
| DERIVED_FROM | 派生：`word_id` 派生自 `related_word_id`（happiness → happy） | 单向 |

对称关系写两行而不是一行加 `OR` 查询，是为了让"查某词的所有关联"永远是一次单向索引扫描。代价是应用层要保证成对写入和成对删除，放在同一事务里。

**它能换来什么**（说明为什么值得建，而不只是"图谱听起来不错"）：

- `CONFUSABLE` 直接给选择题提供干扰项，比让 LLM 临时编干扰项更稳定、更有针对性。
- `SYNONYM` + `note` 是辨析题的素材（"这里该用 affect 还是 effect"）。
- `SAME_ROOT` 支持"学一个带出一族"的扩展学习。
- 所有关系反过来还能做复习调度的降权：刚复习过 `happy`，同族的 `happiness` 可以稍微延后，避免同一天扎堆。

**数据怎么积累**：和 `example` 同一套路。宿主 LLM 讲解某个词时顺手产出关联词，调写入工具落库，一次学习补几条。不搞一次性批量灌数据，也不阻塞一期上线。

---

## 4. 学习层

### 4.1 study_item · 可复习项（核心表）

用户 × 一个单词或语法点。把单词和语法收口成同一种"可复习项"，调度和记录因此只需要一套逻辑。

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| id | bigint | N | 自增 | 主键 |
| user_id | bigint | N | - | 一期固定为 1，多用户时才启用 `app_user` |
| item_type | varchar(16) | N | - | `WORD` / `GRAMMAR` |
| ref_id | bigint | N | - | 指向 word.id 或 grammar_point.id |
| state | varchar(16) | N | `NEW` | `NEW/LEARNING/REVIEW/RELEARNING/SUSPENDED/MASTERED` |
| mastery | smallint | N | 0 | 0~100 掌握度，展示用 |
| ease_factor | decimal(4,2) | N | 2.50 | SM-2 难度因子，下限 1.30 |
| interval_days | int | N | 0 | 当前间隔天数 |
| repetitions | int | N | 0 | 连续答对次数 |
| lapses | int | N | 0 | 累计遗忘（答错）次数 |
| due_at | timestamp | Y | null | **下次复习时间**，"该复习哪些"就查这个 |
| first_learned_at | timestamp | Y | null | 首次学习时间 |
| last_reviewed_at | timestamp | Y | null | 最近一次复习时间 |
| review_count | int | N | 0 | 总复习次数 |
| correct_count | int | N | 0 | 累计答对次数 |
| note | varchar(512) | Y | null | 用户私有笔记 / 助记 |
| created_at | timestamp | N | now | |
| updated_at | timestamp | N | now | |

- 唯一约束：`uk_item_user_ref (user_id, item_type, ref_id)` —— 防止同一个词被重复建项
- 索引：`idx_item_due (user_id, state, due_at)` —— 取待复习队列的主索引
- 索引：`idx_item_mastery (user_id, mastery)`
- CHECK：`ease_factor >= 1.30`、`mastery between 0 and 100`

> 用 `(item_type, ref_id)` 而非两个可空外键，是为了让调度、记录、统计都只面对一张表。代价是数据库层无法强制外键完整性，需在应用层保证。

**复习粒度：一期按词，不按义项。** 有了 `word_sense` 之后就出现一个选择：`take` 是一张卡还是三张卡？一期按整词一张卡——初学阶段把一个词的常用义一起过效率更高，卡片数量也不会因为多义词爆炸。等你需要区分"`take` 拿走我会，`take` 花费时间我不会"时，加一个 `item_type = 'WORD_SENSE'`、`ref_id` 指向 `word_sense.id` 就行，其他表一律不动。这也是当初选多态引用的主要收益，同理可扩展 `PHRASE`、`LISTENING` 等类型。

### 4.2 study_record · 学习记录（事件流，只追加）

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| id | bigint | N | 自增 | 主键 |
| user_id | bigint | N | - | 冗余，便于按用户直接聚合 |
| item_id | bigint | N | - | FK → study_item |
| session_id | varchar(36) | Y | null | 同一次学习会话的多条记录共用 |
| action | varchar(16) | N | - | `LEARN` 首学 / `REVIEW` 复习 / `QUIZ` 答题 / `SKIP` 跳过 |
| occurred_at | timestamp | N | now | 事件发生时间 |
| quality | smallint | Y | null | 0~5 自评回忆质量（SM-2 输入） |
| is_correct | boolean | Y | null | 客观题对错；主观项可空 |
| duration_ms | int | Y | null | 本条耗时 |
| example_id | bigint | Y | null | 本次用了哪条例句，便于下次换一句 |
| question_snapshot | text | Y | null | 宿主 LLM 生成的题目原文（可追溯） |
| answer_text | text | Y | null | 用户作答 |
| feedback | text | Y | null | 宿主 LLM 的点评 |
| ease_after | decimal(4,2) | Y | null | 本次调度后的因子（可重放校验） |
| interval_after | int | Y | null | 本次调度后的间隔 |
| due_at_after | timestamp | Y | null | 本次调度后的下次复习时间 |
| created_at | timestamp | N | now | |

- 索引：`idx_rec_user_time (user_id, occurred_at)` —— "今天/本周学了什么"
- 索引：`idx_rec_item_time (item_id, occurred_at)` —— 单个词的学习轨迹
- CHECK：`quality between 0 and 5`

> 写入 `study_record` 与更新 `study_item` 必须在同一事务内。三个 `*_after` 字段让调度过程可复盘，排查"为什么这个词又出现了"时很有用。

---

## 5. 汇总层

### 5.1 daily_stat · 每日快照

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| user_id | bigint | N | - | |
| stat_date | date | N | - | 按用户本地时区归日 |
| new_word_count | int | N | 0 | 当日新学单词数 |
| new_grammar_count | int | N | 0 | 当日新学语法数 |
| review_count | int | N | 0 | 当日复习条数 |
| correct_count | int | N | 0 | 当日答对数 |
| study_seconds | int | N | 0 | 当日学习时长 |
| streak_days | int | N | 0 | 截至当日的连续打卡天数 |
| updated_at | timestamp | N | now | |

- 主键：`(user_id, stat_date)`

**为什么是快照而不是"统计表"**：连续打卡、每日趋势这类查询按需扫全量记录会越来越慢，所以物化一份。但它的每个字段都能由 `study_record` 重算，遇到口径变更直接重跑即可，不作为权威数据。

即时性强的指标（待复习数、掌握度分布、覆盖率）**不要存**，直接查：

```sql
-- 该复习哪些
SELECT * FROM study_item
WHERE user_id = ? AND state <> 'SUSPENDED' AND due_at <= now()
ORDER BY due_at LIMIT 20;

-- 某词表的进度
SELECT count(*) FILTER (WHERE si.mastery >= 80) AS mastered,
       count(si.id)                             AS learned,
       wl.total_count                           AS total
FROM word_list wl
JOIN word_list_item wli ON wli.list_id = wl.id
LEFT JOIN study_item si
       ON si.item_type = 'WORD' AND si.ref_id = wli.word_id AND si.user_id = ?
WHERE wl.id = ?
GROUP BY wl.total_count;

-- 取一条最少用过的例句（缓存轮换）
SELECT * FROM example
WHERE ref_type = 'WORD' AND ref_id = ? AND is_hidden = false
ORDER BY is_pinned DESC, use_count, id LIMIT 1;
```

---

## 6. 二期扩展

| 表 / 字段 | 作用 | 何时再加 |
| --- | --- | --- |
| study_session | 一次复习活动的容器行：开始/结束时间、计划题数、实际完成数、正确率。和 `study_record` 是订单与订单明细的关系 | 需要"续做上次没做完的那组题"时。会话级统计能用 `study_record.session_id` 分组算出来，唯一算不出来的是"计划了 20 题"这种还没发生的意图——没有对应的 record 行 |
| app_user | 多用户、登录 | 一期单用户，`user_id` 全表已预留并固定为 1，加表时不需要改结构 |
| word.audio_url / example.audio_url | 发音与例句音频（TTS 缓存，思路同 example） | 做听力或跟读时 |
| item_type = 'WORD_SENSE' | 义项级复习粒度 | 想区分同一个词的不同义项掌握情况时。只是新增枚举值，不动表结构 |
| word_relation 批量导入 | 一次性灌入现成的同义词/词族数据 | 边用边攒觉得太慢时 |

---

## 附录：DDL（Postgres 方言）

```sql
CREATE TABLE word (
    id              BIGSERIAL PRIMARY KEY,
    headword        VARCHAR(64)  NOT NULL,
    lemma_id        BIGINT       REFERENCES word (id),
    phonetic_uk     VARCHAR(64),
    phonetic_us     VARCHAR(64),
    syllables       VARCHAR(64),
    cefr_level      VARCHAR(4),
    frequency_rank  INT,
    sense_count     SMALLINT     NOT NULL DEFAULT 0,
    source          VARCHAR(32),
    created_at      TIMESTAMP    NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT uk_word_headword UNIQUE (headword)
);
CREATE INDEX idx_word_freq  ON word (frequency_rank);
CREATE INDEX idx_word_level ON word (cefr_level);

CREATE TABLE word_sense (
    id              BIGSERIAL PRIMARY KEY,
    word_id         BIGINT       NOT NULL REFERENCES word (id) ON DELETE CASCADE,
    sense_order     SMALLINT     NOT NULL DEFAULT 1,
    is_primary      BOOLEAN      NOT NULL DEFAULT false,
    pos             VARCHAR(16)  NOT NULL,
    definition_zh   VARCHAR(512) NOT NULL,
    definition_en   VARCHAR(512),
    register        VARCHAR(32),
    cefr_level      VARCHAR(4),
    collocations    VARCHAR(256),
    note            VARCHAR(256),
    source          VARCHAR(32),
    created_at      TIMESTAMP    NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT uk_sense_word_order UNIQUE (word_id, sense_order)
);
CREATE INDEX idx_sense_word ON word_sense (word_id);
-- 一个词最多一条主义项
CREATE UNIQUE INDEX uk_sense_primary ON word_sense (word_id) WHERE is_primary;

CREATE TABLE example (
    id            BIGSERIAL PRIMARY KEY,
    ref_type      VARCHAR(16)  NOT NULL,
    ref_id        BIGINT       NOT NULL,
    text_en       VARCHAR(512) NOT NULL,
    text_zh       VARCHAR(512),
    target_form   VARCHAR(64),
    text_hash     CHAR(32)     NOT NULL,
    cefr_level    VARCHAR(4),
    source        VARCHAR(32)  NOT NULL DEFAULT 'LLM',
    source_model  VARCHAR(64),
    is_pinned     BOOLEAN      NOT NULL DEFAULT false,
    is_hidden     BOOLEAN      NOT NULL DEFAULT false,
    use_count     INT          NOT NULL DEFAULT 0,
    last_used_at  TIMESTAMP,
    created_at    TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT uk_example_ref_hash UNIQUE (ref_type, ref_id, text_hash),
    CONSTRAINT ck_example_ref_type CHECK (ref_type IN ('WORD', 'WORD_SENSE', 'GRAMMAR'))
);
CREATE INDEX idx_example_ref ON example (ref_type, ref_id, is_hidden, use_count);

CREATE TABLE grammar_point (
    id               BIGSERIAL PRIMARY KEY,
    title            VARCHAR(128) NOT NULL,
    category         VARCHAR(32)  NOT NULL,
    parent_id        BIGINT       REFERENCES grammar_point (id),
    formula          VARCHAR(256),
    summary          VARCHAR(512),
    explanation      TEXT,
    common_mistakes  TEXT,
    cefr_level       VARCHAR(4),
    difficulty       SMALLINT     NOT NULL DEFAULT 3,
    source           VARCHAR(32),
    created_at       TIMESTAMP    NOT NULL DEFAULT now(),
    updated_at       TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT uk_grammar_title UNIQUE (title)
);
CREATE INDEX idx_grammar_category ON grammar_point (category);
CREATE INDEX idx_grammar_parent   ON grammar_point (parent_id);

CREATE TABLE word_list (
    id           BIGSERIAL PRIMARY KEY,
    name         VARCHAR(64)  NOT NULL,
    kind         VARCHAR(16)  NOT NULL DEFAULT 'EXAM',
    total_count  INT          NOT NULL DEFAULT 0,
    description  VARCHAR(256),
    created_at   TIMESTAMP    NOT NULL DEFAULT now()
);

CREATE TABLE word_list_item (
    list_id     BIGINT NOT NULL REFERENCES word_list (id) ON DELETE CASCADE,
    word_id     BIGINT NOT NULL REFERENCES word (id),
    sort_order  INT    NOT NULL DEFAULT 0,
    PRIMARY KEY (list_id, word_id)
);
CREATE INDEX idx_wli_word ON word_list_item (word_id);

CREATE TABLE word_relation (
    word_id          BIGINT      NOT NULL REFERENCES word (id) ON DELETE CASCADE,
    related_word_id  BIGINT      NOT NULL REFERENCES word (id) ON DELETE CASCADE,
    relation_type    VARCHAR(24) NOT NULL,
    strength         SMALLINT,
    note             VARCHAR(256),
    source           VARCHAR(32),
    created_at       TIMESTAMP   NOT NULL DEFAULT now(),
    PRIMARY KEY (word_id, related_word_id, relation_type),
    CONSTRAINT ck_rel_type CHECK (relation_type IN
        ('SYNONYM', 'ANTONYM', 'CONFUSABLE', 'SAME_ROOT', 'DERIVED_FROM')),
    CONSTRAINT ck_rel_self CHECK (word_id <> related_word_id)
);
CREATE INDEX idx_rel_reverse ON word_relation (related_word_id, relation_type);

CREATE TABLE study_item (
    id                BIGSERIAL PRIMARY KEY,
    user_id           BIGINT        NOT NULL,
    item_type         VARCHAR(16)   NOT NULL,
    ref_id            BIGINT        NOT NULL,
    state             VARCHAR(16)   NOT NULL DEFAULT 'NEW',
    mastery           SMALLINT      NOT NULL DEFAULT 0,
    ease_factor       DECIMAL(4, 2) NOT NULL DEFAULT 2.50,
    interval_days     INT           NOT NULL DEFAULT 0,
    repetitions       INT           NOT NULL DEFAULT 0,
    lapses            INT           NOT NULL DEFAULT 0,
    due_at            TIMESTAMP,
    first_learned_at  TIMESTAMP,
    last_reviewed_at  TIMESTAMP,
    review_count      INT           NOT NULL DEFAULT 0,
    correct_count     INT           NOT NULL DEFAULT 0,
    note              VARCHAR(512),
    created_at        TIMESTAMP     NOT NULL DEFAULT now(),
    updated_at        TIMESTAMP     NOT NULL DEFAULT now(),
    CONSTRAINT uk_item_user_ref UNIQUE (user_id, item_type, ref_id),
    CONSTRAINT ck_item_type     CHECK (item_type IN ('WORD', 'GRAMMAR')),
    CONSTRAINT ck_item_ease     CHECK (ease_factor >= 1.30),
    CONSTRAINT ck_item_mastery  CHECK (mastery BETWEEN 0 AND 100)
);
CREATE INDEX idx_item_due     ON study_item (user_id, state, due_at);
CREATE INDEX idx_item_mastery ON study_item (user_id, mastery);

CREATE TABLE study_record (
    id                 BIGSERIAL PRIMARY KEY,
    user_id            BIGINT        NOT NULL,
    item_id            BIGINT        NOT NULL REFERENCES study_item (id) ON DELETE CASCADE,
    session_id         VARCHAR(36),
    action             VARCHAR(16)   NOT NULL,
    occurred_at        TIMESTAMP     NOT NULL DEFAULT now(),
    quality            SMALLINT,
    is_correct         BOOLEAN,
    duration_ms        INT,
    example_id         BIGINT        REFERENCES example (id) ON DELETE SET NULL,
    question_snapshot  TEXT,
    answer_text        TEXT,
    feedback           TEXT,
    ease_after         DECIMAL(4, 2),
    interval_after     INT,
    due_at_after       TIMESTAMP,
    created_at         TIMESTAMP     NOT NULL DEFAULT now(),
    CONSTRAINT ck_rec_action  CHECK (action IN ('LEARN', 'REVIEW', 'QUIZ', 'SKIP')),
    CONSTRAINT ck_rec_quality CHECK (quality BETWEEN 0 AND 5)
);
CREATE INDEX idx_rec_user_time ON study_record (user_id, occurred_at);
CREATE INDEX idx_rec_item_time ON study_record (item_id, occurred_at);

CREATE TABLE daily_stat (
    user_id            BIGINT    NOT NULL,
    stat_date          DATE      NOT NULL,
    new_word_count     INT       NOT NULL DEFAULT 0,
    new_grammar_count  INT       NOT NULL DEFAULT 0,
    review_count       INT       NOT NULL DEFAULT 0,
    correct_count      INT       NOT NULL DEFAULT 0,
    study_seconds      INT       NOT NULL DEFAULT 0,
    streak_days        INT       NOT NULL DEFAULT 0,
    updated_at         TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, stat_date)
);
```

### H2 兼容性

| Postgres | H2 写法 |
| --- | --- |
| `BIGSERIAL` | `BIGINT AUTO_INCREMENT` |
| `now()` | `CURRENT_TIMESTAMP` |
| `CREATE UNIQUE INDEX ... WHERE is_primary` | 不支持条件唯一索引，改为应用层约束 |
| `count(*) FILTER (WHERE x)` | `sum(case when x then 1 else 0 end)` |
| `INSERT ... ON CONFLICT DO NOTHING` | `MERGE INTO ... KEY (...)` |

`text_hash` 由应用层计算（`DigestUtils.md5Hex(textEn.trim().toLowerCase())`），不用数据库生成列，避免两种方言的差异。
