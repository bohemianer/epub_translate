# 📚 EPUB 电子书专业全书翻译与出版排版专家 (EPUB Translator)

[![GitHub license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-green.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/EPUB-3.0%2F2.0%20Standard-orange.svg)]()

专为整本大部头长篇外文著作（严肃文学、人物传记、社科历史、科技商业）设计的大模型全自动翻译与出版级排版工具包。

彻底攻克长篇外文电子书翻译中的核心痛点：
1. **破折号长句破碎翻译腔**：自动解构英语多破折号长句，重塑为优雅地道的中文意合母语叙事。
2. **中文首行缩紧与缺失缩进**：内置出版级中文排版引擎，正文智能强制缩进 1 个汉字（`1em`，移动端黄金标准），标题/引文/图片/居中段落精准豁免。
3. **上下文割裂与代词混淆**：智能切片引擎自动携带三层滑动窗口上下文（前序末尾 + 后续起始）。
4. **DOM 结构与跳转破坏**：100% 结构保留，尾注、正文锚点、目录超链接与原生系统阅读器目录（NCX/NAV）全链路打通。
5. **漏段吞字与复读幻觉**：硬性质检守门（QA Guardrails）与单段纠错重试（Healing）。

---

## 🌟 核心突破与特性

### 1. 破折号长句解构与重组准则（Dash Decomposition & Restructuring Rules）
英语非虚构长篇（如罗伯特·卡洛《林登·约翰逊传》、丘吉尔传记）作者极爱在单句中塞入多个破折号（`—`）。若机械硬译为“——”，会彻底撕裂中文主谓宾骨架。本工具库内置四大解构法则：
- **流水短句化**：化插入语为前后相承的动词短句，恢复中文意合流动感。
- **前置吸附融入**：将人物身份与背景同位语转化为中心词之前的前置修饰语。
- **显性逻辑连接**：将破折号暗含的弱逻辑显化为“正因如此”、“即”、“归根结底”等关联词。
- **单句限单破折号守则**：全句至多在文末保留一个破折号用于戏剧性转折或余韵收束，单句严禁出现多对破折号。

### 2. 出版级中文排版引擎（Chinese Publication Typography）
- **正文标准缩进**：默认采用**移动端与现代电子阅读器主流黄金标准——首行缩进 1 个汉字（`text-indent: 1em !important;`）**，视觉紧凑精致，消除手机窄屏过度留白；亦可通过 `--indent 2em` 切换为传统纸书大部头 2 个汉字缩进。行高 `1.75`，两端对齐。
- **智能排版白名单（豁免防偏心）**：自动识别并豁免各级标题（`h1-h6`、`.title`、`.chapter-title`）、引文块（`blockquote`）、列表项（`li`）、表格（`td/th`）、居中行（`.center`）与图文插图（`p:has(img)`、`.illustration`）。
- **全局与内嵌双重防御**：支持 `inject-blocks` 页面级内嵌样式注入与 `fix-style` 全局外部样式表（`stylesheet.css`）一键穿透修复。

---

## 🏗 工具链（scripts/epub_tool.py）

纯 Python 3 原生标准库实现，零第三方外部依赖：

| 子命令 | 功能描述 |
|---|---|
| `unpack <epub> <work_dir>` | 解包 EPUB，解析元数据与阅读顺序（Spine），生成进度断点追踪。 |
| `extract-blocks <xhtml> -o <out.json>` | 精准抽取段落与标题，以 `⟦NOTE_N⟧` 占位符隔离保护尾注。 |
| `slice-batches <blocks.json> <out_dir>` | 智能切片引擎，划分 1,500 ~ 2,000 词批次并封装三层滑动窗口上下文。 |
| `inject-blocks <xhtml> <trans.json> <out.xhtml> [--mode mono\|bilingual] [--indent 1em\|2em]` | 高保真回填译文，注入出版级首行缩进与样式，保留标题内嵌层级标签。 |
| `fix-style <work_dir> [--mode mono\|bilingual] [--indent 1em\|2em]` | 全局样式修复引擎，在全局 CSS 样式表中强制注入 1em（或 2em）首行缩进规则。 |
| `sync-ncx <work_dir> <toc_trans.json> [--title "..."]` | 同步阅读器侧边栏导航目录（`toc.ncx` / `nav.xhtml`）为纯中文标签。 |
| `qa-check <src.json> <trans.json>` | 检验索引 1:1 对齐、字符长度离群值（防漏译/复读），输出纠错清单。 |
| `glossary-scan <work_dir> -c 5` | 扫描前序章节，自动提取高频专有名词与术语表。 |
| `pack <work_dir> <out.epub>` | 严格按照 EPUB 国际标准规范打包（`mimetype` 首位无压缩存储）。 |

---

## 🚀 推荐 5 阶段工作流（SOP）

### 阶段一：解构与断点初始化
```bash
python3 scripts/epub_tool.py unpack "book.epub" "./work_dir"
```

### 阶段二：提取术语表与确认版式风格
```bash
python3 scripts/epub_tool.py glossary-scan "./work_dir" -c 5
```
确认版式需求：**双语对照（bilingual）** 还是 **纯中文替换（mono，推荐严肃阅读）**。

### 阶段三：智能切片与滑动窗口批次翻译
按章节循环执行：
```bash
# 1. 提取原子块
python3 scripts/epub_tool.py extract-blocks "./work_dir/raw/.../ch1.xhtml" -o "./work_dir/cache/ch1_blocks.json"

# 2. 生成滑动窗口切片任务
python3 scripts/epub_tool.py slice-batches "./work_dir/cache/ch1_blocks.json" "./work_dir/cache/ch1_batches"

# 3. 传入模型（参考 references/prompts.md 中的破折号解构准则与 Prompt 模板）进行批次翻译
```

### 阶段四：自动化质检与单段纠错（QA & Healing）
```bash
python3 scripts/epub_tool.py qa-check "./work_dir/cache/ch1_blocks.json" "./work_dir/cache/ch1_trans.json"
```
若发现漏译或复读，仅对报错的段落重跑单段修复，无需全章重译。

### 阶段五：DOM 重构、排版修复与国际标准打包
```bash
# 1. 注入译文
python3 scripts/epub_tool.py inject-blocks "./work_dir/raw/.../ch1.xhtml" "./work_dir/cache/ch1_trans.json" "./work_dir/raw/.../ch1.xhtml" --mode mono

# 2. 全局样式注入 2em 首行缩进
python3 scripts/epub_tool.py fix-style "./work_dir" --mode mono

# 3. 同步系统原生目录为纯中文
python3 scripts/epub_tool.py sync-ncx "./work_dir" "./work_dir/cache/toc_trans.json" --title "中文书名"

# 4. 国际规范重打包
python3 scripts/epub_tool.py pack "./work_dir" "./output_translated.epub"
```

---

## 📖 参考资料与样式规范
- `references/prompts.md`：包含文学小说、社科科技、严肃传记的专属 Prompt 模板与**破折号解构案例对比**。
- `references/mono.css`：中文出版级纯中文排版样式表。
- `references/bilingual.css`：深色/浅色自适应双语出版级对照样式表。

---

## 📄 License
MIT License
