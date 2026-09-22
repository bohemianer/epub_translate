---
name: epub-translator
description: >-
  专业级 EPUB 电子书全书翻译与出版排版专家。支持中英双语对照与纯中文两种排版模式；
  保持原书 DOM 结构、目录跳转、内嵌样式与插图；内置前置专有名词术语库（Glossary）抽取、
  优先忠于原文原则（忠实还原作者修辞与标点张力）、
  自动化中文出版级首行缩进（默认 1em 即 1 个汉字）与行距自适应渲染、
  三步级联审校流（Agentic 3-Pass Refinement）、自动化漏译错对齐质检（QA Guardrails）
  及符合国际 EPUB 3.0/2.0 标准规范的重打包（mimetype 首位无压缩存储）。
  Triggers: "翻译epub", "翻译电子书", "epub双语", "电子书翻译", "epub翻译", "translate epub", "epub对照", "制作双语电子书"
---

# EPUB 电子书专业翻译技能规范 (epub-translator)

本 Skill 专为整本大部头长篇著作设计，彻底解决**长文翻译中的上下文割裂、中文首行缩紧/缺缩进排版混乱、漏段吞字、术语漂移、代词混淆、排版损坏与阅读器兼容性**等难题。

---

## 🏗 工具链说明

本 Skill 内置纯 Python 3 原生标准库实现的 CLI 辅助工具，零第三方外部依赖：
- 脚本位置：`scripts/epub_tool.py`
- 支持子命令：
  - `unpack <epub> <work_dir>`：解包 EPUB，解析 `container.xml`、`content.opf`，输出 `book_info.json` 与断点追踪 `progress.json`。
  - `extract-blocks <xhtml> -o <blocks.json>`：安全抽取章节内段落与标题标签（`p`, `h1-h6`, `li`, `blockquote` 等），建立原子索引。
  - `slice-batches <blocks.json> <out_dir> [--max-words 1800]`：**智能批次切片引擎**。按 1,500 ~ 2,000 词自动划分批次，并封装**三层滑动窗口上下文**（前序末尾 2 段 + 后续起始 1 段）。
  - `inject-blocks <xhtml> <trans.json> <out_xhtml> [--mode bilingual|mono] [--indent 2em|1em]`：回填译文，注入深色/浅色自适应高雅排版样式。自动注入**中文出版级首行缩进（默认 2em 即空 2 个汉字字符，中国图书出版标准）**，智能豁免各级标题、引言块、居中段落、插图及表格。自动保留原书各级标题的内嵌层级样式包裹标签（`<span class="bold">`、`<span class="italic">` 等），确保排版视觉阶梯感与原书完全一致。
  - `fix-style <work_dir> [--mode mono|bilingual] [--indent 2em|1em]`：**全局排版样式修复引擎**。在 EPUB 的所有全局 CSS 样式表（`stylesheet.css` 等）中追加出版级中文段落排版规则，确保各类阅读器（Apple Books、微信读书、Kindle 等）强制生效标准 2 字符（2em）缩进与舒适行距。
  - `qa-check <src.json> <trans.json>`：**程序化硬性质检**。检验索引数量 1:1 对齐、字符长度离群值（防漏译/复读）、关键数字与年代遗失检测，自动输出单段纠错清单。
  - `glossary-scan <work_dir> -c 5`：扫描全书前序章节，提取高频大写专有名词与核心金融/科技概念。
  - `sync-ncx <work_dir> <toc_trans.json> [--title "..."]`：**底层导航目录同步**。将翻译后的章节名称同步刷入 `toc.ncx` / `nav.xhtml`，确保阅读器自带的侧边栏/弹出式原生系统目录 100% 显示纯中文。
  - `pack <work_dir> <out.epub>`：严格按国际标准打包（`mimetype` 首位无压缩存储），确保各类阅读器完美兼容。

---

## ✒️ 核心翻译与文学重塑准则

### 1. 优先忠于原文与修辞还原（Faithful to the Original）
- **尊重原作风貌**：严谨尊重原作者的句子结构、逻辑脉络与行文节奏。
- **还原标点修辞**：对原文中的破折号、插入语与语调停顿，优先忠于原文修辞进行准确传译，不擅自拆解、随意删减或过度重写作者的句式，完整保留原书的情感张力与思想深度。
- **去翻译腔**：在忠于原文的基础上摆脱生硬的欧化语病，保持中文母语表达的通畅自然。

### 2. 出版级中文排版规范（Chinese Typography）
- **正文首行缩进**：默认采用**中国图书出版国家标准（GB/T 15834）经典规范——首行缩进 2 个汉字字符（`text-indent: 2em !important;`）**，段落边界清晰分明；亦可通过 `--indent 1em` 灵活切换为小屏幕紧凑版。
- **豁免白名单**：标题（`h1-h6`、`.title`、`.chapter-title`）、引文块（`blockquote`）、列表项（`li`）、表格（`td/th`）、居中行（`.center`）与图文插图（`p:has(img)`、`.illustration`）严格禁止首行缩进（`text-indent: 0 !important;`）。

---

## 🚀 工业级防错翻译工作流 (5 阶段 SOP)

### 阶段一：解构、建立索引与全书断点初始化
```bash
python3 scripts/epub_tool.py unpack "<input.epub>" "<work_dir>"
```
- 查看 `<work_dir>/book_info.json` 与 `<work_dir>/progress.json`。
- 明确章节总数、各章节排版文件路径及总字数。

### 阶段二：前置术语库扫描与试译风格确认
1. 运行 `python3 scripts/epub_tool.py glossary-scan "<work_dir>" -c 5` 抽取核心词表。
2. 提取开篇 15~20 个段落，展示**【风格 A：专业严谨版】**与**【风格 B：通俗流畅版】**供用户选定。
3. 确认版式需求：**双语对照（bilingual，默认）** 还是 **纯中文替换（mono）**。

### 阶段三：智能切片与滑动窗口批次翻译
按 Spine 章节顺序循环执行：
1. 提取章节块：
   ```bash
   python3 scripts/epub_tool.py extract-blocks "<xhtml_path>" -o "<work_dir>/cache/<ch_id>_blocks.json"
   ```
2. 智能切片生成滑动窗口任务：
   ```bash
   python3 scripts/epub_tool.py slice-batches "<work_dir>/cache/<ch_id>_blocks.json" "<work_dir>/cache/<ch_id>_batches"
   ```
3. **调用翻译模型**：
   - 载入批次任务文件中的 `context_prev` 与 `context_next`，保障语境自然过渡；
   - 注入静态锁死的术语映射表（Glossary）；
   - 执行严苛负向约束：坚持**优先忠于原文**，忠实传达作者修辞，严禁合并段落，严禁汉化链接或专有标记，输出严格 JSON 数组格式。

### 阶段四：硬性质检守门与单段自动纠错 (QA & Healing)
合并当前章节所有批次译文后，执行：
```bash
python3 scripts/epub_tool.py qa-check "<work_dir>/cache/<ch_id>_blocks.json" "<work_dir>/cache/<ch_id>_trans.json"
```
- 若 `passed: false`：读取报告中的 `healing_items`，**仅对出错的几个段落进行单段纠错重跑**，修正后合并回主文件，避免无谓重译全批次。

### 阶段五：DOM 重构注入、样式全局修复与标准打包
1. 注入译文并添加出版级排版样式：
   ```bash
   python3 scripts/epub_tool.py inject-blocks "<raw_xhtml>" "<trans.json>" "<raw_xhtml>" --mode mono
   ```
2. 全局样式表注入 2em 首行缩进与行距（防止原书 CSS 覆盖）：
   ```bash
   python3 scripts/epub_tool.py fix-style "<work_dir>" --mode mono
   ```
3. 同步底层系统阅读器目录（NCX/NAV）：
   ```bash
   python3 scripts/epub_tool.py sync-ncx "<work_dir>" "<toc_trans.json>" --title "书名"
   ```
4. 更新 `<work_dir>/progress.json` 章节完成状态。
5. 全部章节完成后，规范化打包生成目标 EPUB：
   ```bash
   python3 scripts/epub_tool.py pack "<work_dir>" "<output_translated.epub>"
   ```

---

## ⚡ 性能与成本分级路由最佳实践
- **海量常规章节（90% 正文）**：使用 **Flash 级别模型**。速度极快，在严格 JSON Schema + 上下文窗口约束下准确率极高，全书仅需约 80 万 Tokens（成本约 1~2 元）。
- **皇冠重点章节（重大传记序言、核心转折篇章）**：使用 **Pro 级别模型** 或开启 **Agentic 3-Pass 审校流**，追求文学典籍级的高端质感。
