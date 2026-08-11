# 英语学习模块 · 数据表字段设计

> 版本：v1.2（草案）
> 最后更新：2026-08-11
> 适用架构：MCP Server（Spring Boot + H2/Postgres），生成类工作（释义、例句、出题、批改）由宿主 LLM 完成，服务端只负责存储与调度

## 修订记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v1.0 | 2026-08-11 | 初稿，7 张表 |
| v1.1 | 2026-08-11 | `word_sense`、`example` 提到一期；`example` 增加 LLM 结果缓存语义（去重、屏蔽、轮换）；`word_relation` 定稿设计并建表，数据渐进积累；移除 `tag / item_tag`；`word.definition_zh`、`word.pos_primary` 下沉到 `word_sense` |
| v1.2 | 2026-08-11 | 评审修订：`study_record` 改为 RESTRICT 并引入软删；一期收口 `example.ref_type` 只允许 `WORD`；`idx_item_due` 改为 `(user_id, due_at)`；时间类型统一 `TIMESTAMPTZ`；`headword` 唯一约束改 `lower()`；`study_item` 增加 `version` 乐观锁；新增 `user_setting` 表；补充「冗余列维护」「已知取舍」章节 |

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

配置层
  user_setting  学习目标与时区，一期单行
```

一期共 11 张表。三条贯穿全局的原则：

1. **事件流是唯一权威数据**。`study_record` 只追加、不级联删除，`study_item` 与 `daily_stat` 都是派生状态，任何时候都能从事件流重放重建。统计口径变了或算错了，重算即可。
2. **内容层不含 user_id**。词条、义项、例句是共享词典。唯一的例外是 `example` 上的收藏/屏蔽/轮换四个字段，一期单用户先内联，二期拆表（见 §7 已知取舍）。
3. **内容层不做物理删除**。`study_item.ref_id`、`example.ref_id` 是多态引用，数据库无法保证完整性，因此内容层一律软删（`is_active = false`），避免出现指向不存在 id 的复习项。

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
| is_active | boolean | N | true | 软删标记，见原则 3 |
| source | varchar(32) | Y | null | 来源 `MANUAL/IMPORT/LLM` |
| created_at | timestamptz | N | now | |
| updated_at | timestamptz | N | now | |

- 唯一约束：`uk_word_headword` 建在 `lower(headword)` 上。Postgres 默认大小写敏感，否则 `march` / `March`、`us` / `US` 会各存一行。应用层写入前也统一转小写（专有名词的展示形态交给 `word_sense.note`）。
- 索引：`idx_word_freq (frequency_rank)`、`idx_word_level (cefr_level)`

> **同形异义词的已知限制**：`lead` 有 /liːd/ 和 /led/ 两个读音、`bow` 同理，单列唯一约束下它们只能是一条记录，音标字段只放主读音，另一个读音写进对应义项的 `note`。一期规模下可接受；真要拆，唯一键扩成 `(lower(headword), homograph_no)`，其余表不动。

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
| note | varchar(256) | Y | null | 辨析、易错提示；同形异义词的另一读音也写这里 |
| is_active | boolean | N | true | 软删标记 |
| source | varchar(32) | Y | null | `MANUAL/IMPORT/LLM` |
| created_at | timestamptz | N | now | |
| updated_at | timestamptz | N | now | |

- 唯一约束：`uk_sense_word_order (word_id, sense_order)`
- 索引：`idx_sense_word (word_id)`
- 一个词最多一条主义项：Postgres 用条件唯一索引 `(word_id) WHERE is_primary`；H2 不支持条件唯一索引，需在应用层保证（写入主义项时先清掉旧的，同一事务内）。

### 3.3 example · 例句（兼 LLM 生成结果缓存）

这张表有双重身份：内容上是例句库，工程上是宿主 LLM 的产出缓存。同一个词第二次复习时直接返回已存的句子，不再让 LLM 重新生成，省 token 也省等待。

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| id | bigint | N | 自增 | 主键 |
| ref_type | varchar(16) | N | - | 一期只允许 `WORD` / `GRAMMAR`，`WORD_SENSE` 二期开放（见下） |
| ref_id | bigint | N | - | 指向 word.id / grammar_point.id |
| text_en | varchar(512) | N | - | 英文例句 |
| text_zh | varchar(512) | Y | null | 中文翻译 |
| target_form | varchar(64) | Y | null | 目标词在句中的实际形态（如 `took`），用于高亮和挖空出题 |
| text_hash | char(32) | N | - | `md5(lower(trim(text_en)))`，去重键 |
| cefr_level | varchar(4) | Y | null | 例句难度，按学习者水平挑句子 |
| source | varchar(32) | N | `LLM` | `LLM/IMPORT/MANUAL` |
| source_model | varchar(64) | Y | null | 生成模型标识，便于日后按模型清理低质量批次 |
| is_pinned | boolean | N | false | 用户收藏，优先展示（★ 用户私有） |
| is_hidden | boolean | N | false | 质量差，屏蔽（★ 用户私有） |
| use_count | int | N | 0 | 被展示/出题次数，用于轮换（★ 用户私有） |
| last_used_at | timestamptz | Y | null | 最近使用时间（★ 用户私有） |
| created_at | timestamptz | N | now | |

- 唯一约束：`uk_example_ref_hash (ref_type, ref_id, text_hash)` —— 缓存去重的关键。LLM 反复生成同一句是常态，靠这个约束挡掉，写入时用 upsert（`ON CONFLICT DO NOTHING`）而不是先查再插。
- 索引：`idx_example_ref (ref_type, ref_id, is_hidden, use_count)` —— 取"这个词还没怎么用过的例句"。
- CHECK：`ref_type IN ('WORD', 'GRAMMAR')`

**一期只挂整词，不挂义项。** 唯一键含 `ref_type`，同一句挂 `WORD` 又挂 `WORD_SENSE` 会存成两行，跨层去重失效；而一期复习粒度是整词，取句子只查 `ref_type = 'WORD'`，挂在义项上的句子永远取不到。所以一期用 CHECK 把 `WORD_SENSE` 挡在门外。二期放开义项粒度时，取句子改为「按 word_id + 其名下所有 sense_id 一起查」，去重键同时保留两层。

★ 标记的四个字段是"某个用户对这句话"的状态，严格说不属于共享内容层。一期单用户先内联，二期随 `app_user` 一起拆到 `user_example (user_id, example_id, ...)`。这是本设计已知的一处取舍，见 §7。

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
| is_active | boolean | N | true | 软删标记 |
| source | varchar(32) | Y | null | `MANUAL/IMPORT/LLM` |
| created_at | timestamptz | N | now | |
| updated_at | timestamptz | N | now | |

- 唯一约束：`uk_grammar_title (parent_id, title)` —— 全局唯一会让「一般现在时 → 否定式」和「一般过去时 → 否定式」撞车，改为同层内唯一。注意 Postgres 唯一约束里 `null` 互不相等，顶层节点（`parent_id is null`）的重名挡不住，需应用层补一道校验。
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
| total_count | int | N | 0 | 词条总数，冗余便于算百分比（见 §6 冗余列维护） |
| description | varchar(256) | Y | null | |
| created_at | timestamptz | N | now | |

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
| created_at | timestamptz | N | now | |

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
| state | varchar(16) | N | `NEW` | `NEW/LEARNING/REVIEW/RELEARNING/SUSPENDED/MASTERED`，由 mastery 与调度结果单向推导，不独立赋值 |
| mastery | smallint | N | 0 | 0~100 掌握度，展示用；`state` 的唯一输入 |
| ease_factor | decimal(4,2) | N | 2.50 | SM-2 难度因子，下限 1.30 |
| interval_days | int | N | 0 | 当前间隔天数 |
| repetitions | int | N | 0 | 连续答对次数 |
| lapses | int | N | 0 | 累计遗忘（答错）次数 |
| due_at | timestamptz | Y | null | **下次复习时间**，"该复习哪些"就查这个 |
| first_learned_at | timestamptz | Y | null | 首次学习时间 |
| last_reviewed_at | timestamptz | Y | null | 最近一次复习时间 |
| review_count | int | N | 0 | 总复习次数 |
| correct_count | int | N | 0 | 累计答对次数 |
| note | varchar(512) | Y | null | 用户私有笔记 / 助记 |
| archived_at | timestamptz | Y | null | 用户移出学习列表的时间。软删，不物理删除（否则事件流一起消失） |
| version | bigint | N | 0 | 乐观锁（JPA `@Version`）。这是全库最热的行 |
| created_at | timestamptz | N | now | |
| updated_at | timestamptz | N | now | |

- 唯一约束：`uk_item_user_ref (user_id, item_type, ref_id)` —— 防止同一个词被重复建项
- 索引：`idx_item_due (user_id, due_at)` —— 取待复习队列的主索引。**不要把 `state` 放进来**：查询里 `state <> 'SUSPENDED'` 是不等值条件，索引扫到它就停，`due_at` 既不能过滤也不能免排序。Postgres 可进一步用部分索引 `(user_id, due_at) WHERE state <> 'SUSPENDED' AND archived_at IS NULL`。
- 索引：`idx_item_mastery (user_id, mastery)`
- CHECK：`ease_factor >= 1.30`、`mastery between 0 and 100`

> 用 `(item_type, ref_id)` 而非两个可空外键，是为了让调度、记录、统计都只面对一张表。代价是数据库层无法强制外键完整性，需在应用层保证（配合原则 3 的内容层软删）。

**为什么加乐观锁**：一次会话里，调度更新（`ease_factor`/`due_at`/计数）和用户改 `note` 可能落在同一行上，后写的整行覆盖会把前一个的结果吞掉。`version` 一列的成本几乎为零，换掉一类很难复现的丢更新。

**复习粒度：一期按词，不按义项。** 有了 `word_sense` 之后就出现一个选择：`take` 是一张卡还是三张卡？一期按整词一张卡——初学阶段把一个词的常用义一起过效率更高，卡片数量也不会因为多义词爆炸。等你需要区分"`take` 拿走我会，`take` 花费时间我不会"时，加一个 `item_type = 'WORD_SENSE'`、`ref_id` 指向 `word_sense.id` 就行，其他表一律不动。这也是当初选多态引用的主要收益，同理可扩展 `PHRASE`、`LISTENING` 等类型。

### 4.2 study_record · 学习记录（事件流，只追加）

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| id | bigint | N | 自增 | 主键 |
| user_id | bigint | N | - | 冗余，便于按用户直接聚合 |
| item_id | bigint | N | - | FK → study_item，`ON DELETE RESTRICT` |
| session_id | varchar(36) | Y | null | 同一次学习会话的多条记录共用 |
| action | varchar(16) | N | - | `LEARN` 首学 / `REVIEW` 复习 / `QUIZ` 答题 / `SKIP` 跳过 |
| occurred_at | timestamptz | N | now | 事件发生时间 |
| quality | smallint | Y | null | 0~5 自评回忆质量（SM-2 输入） |
| is_correct | boolean | Y | null | 客观题对错；主观项可空 |
| duration_ms | int | Y | null | 本条耗时 |
| example_id | bigint | Y | null | 本次用了哪条例句，便于下次换一句；`ON DELETE RESTRICT` |
| question_snapshot | text | Y | null | 宿主 LLM 生成的题目原文（可追溯） |
| answer_text | text | Y | null | 用户作答 |
| feedback | text | Y | null | 宿主 LLM 的点评 |
| ease_after | decimal(4,2) | Y | null | 本次调度后的因子（可重放校验） |
| interval_after | int | Y | null | 本次调度后的间隔 |
| due_at_after | timestamptz | Y | null | 本次调度后的下次复习时间 |
| created_at | timestamptz | N | now | |

- 索引：`idx_rec_user_time (user_id, occurred_at)` —— "今天/本周学了什么"
- 索引：`idx_rec_item_time (item_id, occurred_at)` —— 单个词的学习轨迹
- CHECK：`quality between 0 and 5`

> 写入 `study_record` 与更新 `study_item` 必须在同一事务内。三个 `*_after` 字段让调度过程可复盘，排查"为什么这个词又出现了"时很有用。

**不级联删除。** `item_id` 和 `example_id` 都是 `RESTRICT`，不是 `CASCADE`/`SET NULL`。这是原则 1 的直接结果：如果用户把一个词移出学习列表就连带删掉它的全部历史事件，`daily_stat` 也就再也重算不出来，事件流的权威性名存实亡。移出学习列表的正确做法是 `study_item.state = 'SUSPENDED'` 或置 `archived_at`，行本身保留。同理例句只软删（`is_hidden`），不物理删，`example_id` 因此永远指向真实存在的行。

---

## 5. 汇总层

### 5.1 daily_stat · 每日快照

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| user_id | bigint | N | - | |
| stat_date | date | N | - | 归日用 `user_setting.timezone`，不用服务器时区 |
| new_word_count | int | N | 0 | 当日新学单词数 |
| new_grammar_count | int | N | 0 | 当日新学语法数 |
| review_count | int | N | 0 | 当日复习条数 |
| correct_count | int | N | 0 | 当日答对数 |
| study_seconds | int | N | 0 | 当日学习时长 |
| streak_days | int | N | 0 | 截至当日的连续打卡天数 |
| updated_at | timestamptz | N | now | |

- 主键：`(user_id, stat_date)`

**归日靠时区，时区存在 `user_setting.timezone`。** `stat_date` 是 date、`occurred_at` 是 timestamptz，两者之间必须显式转换：

```sql
-- 把事件归到用户本地日
(sr.occurred_at AT TIME ZONE us.timezone)::date AS stat_date
```

漏掉这一步就等于按服务器时区归日，跨时区使用或夏令时切换当天，连续打卡天数会算错（凌晨学的那次落到前一天，streak 断在一个用户没做错任何事的日子上）。这也是全库统一用 `TIMESTAMPTZ` 而不是 `TIMESTAMP` 的原因：`TIMESTAMP` 不带偏移量，存进去就再也无法可靠还原到某个本地日。

**为什么是快照而不是"统计表"**：连续打卡、每日趋势这类查询按需扫全量记录会越来越慢，所以物化一份。但它的每个字段都能由 `study_record` 重算，遇到口径变更直接重跑即可，不作为权威数据。

即时性强的指标（待复习数、掌握度分布、覆盖率）**不要存**，直接查：

```sql
-- 该复习哪些（走 idx_item_due (user_id, due_at)）
SELECT * FROM study_item
WHERE user_id = ?
  AND due_at <= now()
  AND state <> 'SUSPENDED'
  AND archived_at IS NULL
ORDER BY due_at LIMIT 20;

-- 某词表的进度
SELECT count(*) FILTER (WHERE si.mastery >= 80) AS mastered,
       count(si.id)                             AS learned,
       wl.total_count                           AS total
FROM word_list wl
JOIN word_list_item wli ON wli.list_id = wl.id
LEFT JOIN study_item si
       ON si.item_type = 'WORD' AND si.ref_id = wli.word_id
      AND si.user_id = ? AND si.archived_at IS NULL
WHERE wl.id = ?
GROUP BY wl.total_count;

-- 取一条最少用过的例句（缓存轮换）
SELECT * FROM example
WHERE ref_type = 'WORD' AND ref_id = ? AND is_hidden = false
ORDER BY is_pinned DESC, use_count, id LIMIT 1;
```

---

## 6. 配置层

### 6.1 user_setting · 学习目标与时区

原设计能回答"学了多少""该复习哪些"，但答不了"我进度算快还是慢"——因为没有目标值，也没有"当前在学哪个词表"。这张表补上分母之外的另一半：期望值。一期单行（`user_id = 1`）。

| 字段 | 类型 | 空 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| user_id | bigint | N | - | 主键，一期固定为 1 |
| timezone | varchar(64) | N | `Asia/Shanghai` | IANA 时区名。`daily_stat` 归日、"今天学了什么"都以此为准 |
| active_list_id | bigint | Y | null | 当前主攻词表 → word_list。进度默认报这一个，不用每次都问 |
| daily_new_target | int | N | 10 | 每日新学目标数 |
| daily_review_target | int | N | 50 | 每日复习目标数 |
| target_date | date | Y | null | 期望学完 `active_list_id` 的日期，用于算"每天得学几个才来得及" |
| mastery_threshold | smallint | N | 80 | 判定"已掌握"的 mastery 阈值。原先硬编码在统计 SQL 里，抽出来可调 |
| updated_at | timestamptz | N | now | |

- 主键：`(user_id)`
- CHECK：`mastery_threshold BETWEEN 0 AND 100`

有了它，"进度如何"才能给出有判断的回答：按当前速度能否在 `target_date` 前学完，今天还差多少条。否则只能报绝对数，让用户自己算。

---

## 7. 冗余列的维护责任

三个冗余列（`word.sense_count`、`word_list.total_count`、`daily_stat.*`）都可能和真相漂移。规则统一为：**写入时同事务维护，同时提供重算入口**。

| 冗余列 | 谁维护 | 重算方式 |
| --- | --- | --- |
| `word.sense_count` | 增删 `word_sense` 的同一事务内 `UPDATE word SET sense_count = ...` | `UPDATE word w SET sense_count = (SELECT count(*) FROM word_sense s WHERE s.word_id = w.id AND s.is_active)` |
| `word_list.total_count` | 增删 `word_list_item` 的同一事务内 | 同上，按 list 分组 count |
| `daily_stat` 全部字段 | 每次写 `study_record` 后 upsert 当日行 | 按日期区间从 `study_record` 全量重跑（见 §5.1） |

没有触发器，全部在应用层。理由是这三处的写入路径都很窄（各一两个 service 方法），触发器带来的隐式行为和 H2/Postgres 的方言差异不值得。代价是必须记住：任何绕过 service 直接改库的操作（含数据导入脚本）之后要跑一次重算。

---

## 8. 已知取舍

不是遗漏，是明确接受的成本，避免后来者当成 bug 修。

| 取舍 | 现状 | 代价 / 触发条件 |
| --- | --- | --- |
| `example` 的 4 个用户私有字段内联在共享表上 | 一期单用户，`is_pinned/is_hidden/use_count/last_used_at` 直接放 `example` | 二期加 `app_user` 时必须拆 `user_example`，例句轮换的查询和写入路径要改。这是 `app_user` 唯一一处"不是纯加表"的迁移 |
| 多态引用无外键 | `study_item.ref_id`、`example.ref_id` 靠应用层保证 | 内容层只能软删（原则 3）。直接 SQL 删词会留下孤儿复习项 |
| 同形异义词共用一行 | `lead` /liːd/ 与 /led/ 是一条 `word` | 音标只存主读音，另一读音写进义项 `note`。要拆就把唯一键扩成 `(lower(headword), homograph_no)` |
| `grammar_point.title` 全局唯一 | 不区分父节点 | 不同父节点下不能重名（如两处都想叫「基本用法」）。语法点数量小，手工避开 |
| `study_record.user_id` 与 `study_item.user_id` 无一致性约束 | 冗余列，写入时由应用层填 | 单用户期无风险；多用户后需在写入处校验，或加复合外键 |
| 三个 TEXT 列与事件同行 | `question_snapshot/answer_text/feedback` 直接放 `study_record` | 行宽较大，事件表增长快。到百万行级再考虑拆冷表；Postgres 的 TOAST 在此之前不会成为问题 |

---

## 9. 二期扩展

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
    is_active       BOOLEAN      NOT NULL DEFAULT true,
    source          VARCHAR(32),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
-- 大小写不敏感的词条唯一性
CREATE UNIQUE INDEX uk_word_headword ON word (lower(headword));
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
    is_active       BOOLEAN      NOT NULL DEFAULT true,
    source          VARCHAR(32),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
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
    last_used_at  TIMESTAMPTZ,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uk_example_ref_hash UNIQUE (ref_type, ref_id, text_hash),
    -- 一期不开放 WORD_SENSE：见 §3.3
    CONSTRAINT ck_example_ref_type CHECK (ref_type IN ('WORD', 'GRAMMAR'))
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
    is_active        BOOLEAN      NOT NULL DEFAULT true,
    source           VARCHAR(32),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
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
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
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
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
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
    due_at            TIMESTAMPTZ,
    first_learned_at  TIMESTAMPTZ,
    last_reviewed_at  TIMESTAMPTZ,
    review_count      INT           NOT NULL DEFAULT 0,
    correct_count     INT           NOT NULL DEFAULT 0,
    note              VARCHAR(512),
    archived_at       TIMESTAMPTZ,
    version           BIGINT        NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT uk_item_user_ref UNIQUE (user_id, item_type, ref_id),
    CONSTRAINT ck_item_type     CHECK (item_type IN ('WORD', 'GRAMMAR')),
    CONSTRAINT ck_item_ease     CHECK (ease_factor >= 1.30),
    CONSTRAINT ck_item_mastery  CHECK (mastery BETWEEN 0 AND 100)
);
-- state 是不等值条件，不能进索引；due_at 必须紧跟 user_id 才能免排序
CREATE INDEX idx_item_due ON study_item (user_id, due_at)
    WHERE state <> 'SUSPENDED' AND archived_at IS NULL;
CREATE INDEX idx_item_mastery ON study_item (user_id, mastery);

CREATE TABLE study_record (
    id                 BIGSERIAL PRIMARY KEY,
    user_id            BIGINT        NOT NULL,
    -- RESTRICT，不是 CASCADE：事件流不能被派生表的生命周期删掉
    item_id            BIGINT        NOT NULL REFERENCES study_item (id) ON DELETE RESTRICT,
    session_id         VARCHAR(36),
    action             VARCHAR(16)   NOT NULL,
    occurred_at        TIMESTAMPTZ   NOT NULL DEFAULT now(),
    quality            SMALLINT,
    is_correct         BOOLEAN,
    duration_ms        INT,
    example_id         BIGINT        REFERENCES example (id) ON DELETE RESTRICT,
    question_snapshot  TEXT,
    answer_text        TEXT,
    feedback           TEXT,
    ease_after         DECIMAL(4, 2),
    interval_after     INT,
    due_at_after       TIMESTAMPTZ,
    created_at         TIMESTAMPTZ   NOT NULL DEFAULT now(),
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
    streak_days        INT         NOT NULL DEFAULT 0,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, stat_date)
);

CREATE TABLE user_setting (
    user_id              BIGINT      PRIMARY KEY,
    timezone             VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai',
    active_list_id       BIGINT      REFERENCES word_list (id) ON DELETE SET NULL,
    daily_new_target     INT         NOT NULL DEFAULT 10,
    daily_review_target  INT         NOT NULL DEFAULT 50,
    target_date          DATE,
    mastery_threshold    SMALLINT    NOT NULL DEFAULT 80,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_setting_threshold CHECK (mastery_threshold BETWEEN 0 AND 100)
);
INSERT INTO user_setting (user_id) VALUES (1);
```

### H2 兼容性

| Postgres | H2 写法 |
| --- | --- |
| `BIGSERIAL` | `BIGINT AUTO_INCREMENT` |
| `TIMESTAMPTZ` | `TIMESTAMP WITH TIME ZONE`（H2 2.x 支持） |
| `now()` | `CURRENT_TIMESTAMP` |
| `CREATE UNIQUE INDEX ... WHERE is_primary` | 不支持条件唯一索引，改为应用层约束 |
| `CREATE INDEX ... WHERE state <> ...`（部分索引） | 不支持，退化为普通索引 `(user_id, due_at)`。过滤条件仍写在 SQL 里，只是不进索引 |
| `CREATE UNIQUE INDEX ON word (lower(headword))` | 支持函数索引；或用 `headword` 列直接存小写形态 |
| `count(*) FILTER (WHERE x)` | `sum(case when x then 1 else 0 end)` |
| `INSERT ... ON CONFLICT DO NOTHING` | `MERGE INTO ... KEY (...)` |
| `occurred_at AT TIME ZONE us.timezone` | 语法相同，但 H2 对 IANA 时区名的支持较弱，归日建议在 Java 侧算（`ZonedDateTime`）|

`text_hash` 由应用层计算（`DigestUtils.md5Hex(textEn.trim().toLowerCase())`），不用数据库生成列，避免两种方言的差异。
