#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
epub_tool.py - 专业级 EPUB 电子书解构、智能批次切片、滑动窗口、质检与标准打包引擎
采用 Python 3 标准库原生实现，零第三方依赖。
具备：
1. 尾注与注解（<sup ...><a href="...">N</a></sup>）占位符保护与 100% 靶向无损还原
2. 目录页（TOC）与章节标题反向超链接（<a href="...">）100% 结构保全
3. 段落与标题标签原生属性（id, class）0 丢失
"""

import sys
import os
import re
import json
import zipfile
import shutil
import argparse
import xml.etree.ElementTree as ET
from html import escape

# 默认优雅双语 CSS 样式（支持日间/夜间模式自动适配与舒适行距）
DEFAULT_BILINGUAL_CSS = """
/* === EPUB 智能双语出版级对照样式 === */
.epub-trans-block {
    margin-top: 0.35em !important;
    margin-bottom: 1.15em !important;
    color: #4a5568 !important;
    font-size: 0.95em !important;
    line-height: 1.72 !important;
    font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Source Han Serif SC", "Noto Serif CJK SC", serif, -apple-system, sans-serif !important;
    text-align: justify !important;
}

/* 译文正文自然段落首行缩进 2 字符（中国出版标准） */
p.epub-trans-block {
    text-indent: 2em !important;
}

/* 标题、引文、居中块严格豁免首行缩进 */
h1.epub-trans-block, h2.epub-trans-block, h3.epub-trans-block, 
h4.epub-trans-block, h5.epub-trans-block, h6.epub-trans-block {
    color: #2b6cb0 !important;
    font-weight: 500 !important;
    margin-top: 0.25em !important;
    margin-bottom: 0.85em !important;
    text-indent: 0 !important;
}

blockquote.epub-trans-block {
    color: #718096 !important;
    border-left: 3px solid #cbd5e0 !important;
    padding-left: 0.8em !important;
    margin-left: 0.5em !important;
    text-indent: 0 !important;
}

.center.epub-trans-block, p.center.epub-trans-block, p[class*="center"].epub-trans-block {
    text-indent: 0 !important;
    text-align: center !important;
}

@media (prefers-color-scheme: dark) {
    .epub-trans-block {
        color: #a0aec0 !important;
    }
    h1.epub-trans-block, h2.epub-trans-block, h3.epub-trans-block {
        color: #63b3ed !important;
    }
    blockquote.epub-trans-block {
        border-left-color: #4a5568 !important;
        color: #cbd5e0 !important;
    }
}
"""

# 出版级中文单语排版 CSS（强制首行缩进 2 字符，排版对齐，严格豁免标题/引用/居中/图片）
DEFAULT_MONO_CSS = """
/* === EPUB 中文出版级单语正文排版样式 === */
body {
    font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Source Han Serif SC", "Noto Serif CJK SC", serif, -apple-system, sans-serif !important;
}

/* 中文正文自然段落首行缩进 2 字符（中国出版标准），两端对齐，舒适行高 */
p {
    text-indent: 2em !important;
    text-align: justify !important;
    line-height: 1.75 !important;
    margin-top: 0.25em !important;
    margin-bottom: 0.25em !important;
}

/* 严格豁免清单：标题、引言引用、列表、表格、居中行、图文说明绝对不缩进 */
h1, h2, h3, h4, h5, h6,
h1 p, h2 p, h3 p, h4 p, h5 p, h6 p,
blockquote, blockquote p, li, li p, dt, dd, td, th,
.title, .subtitle, .chapter-title, .heading, .center,
p.title, p.subtitle, p.chapter-title, p.heading, p.center,
p[class*="title"], p[class*="heading"], p[class*="center"],
p:has(img), p:has(svg), p:has(picture) {
    text-indent: 0 !important;
}

p.center, p[class*="center"], div.center {
    text-align: center !important;
    text-indent: 0 !important;
}

blockquote {
    margin-left: 1.5em !important;
    margin-right: 1.5em !important;
    padding-left: 0.8em !important;
    border-left: 3px solid #cbd5e0 !important;
}

blockquote p {
    text-indent: 0 !important;
    line-height: 1.65 !important;
}
"""


def unpack_epub(epub_path, work_dir):
    """解包 EPUB 并解析元数据与阅读顺序 (Spine)"""
    epub_path = os.path.abspath(epub_path)
    work_dir = os.path.abspath(work_dir)
    raw_dir = os.path.join(work_dir, "raw")

    if not os.path.exists(epub_path):
        print(f"[-] 错误: 找不到文件 {epub_path}", file=sys.stderr)
        return False

    if os.path.exists(raw_dir):
        shutil.rmtree(raw_dir)
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(os.path.join(work_dir, "cache"), exist_ok=True)

    with zipfile.ZipFile(epub_path, 'r') as z:
        z.extractall(raw_dir)

    container_xml = os.path.join(raw_dir, "META-INF", "container.xml")
    if not os.path.exists(container_xml):
        print("[-] 错误: 缺少 META-INF/container.xml，非有效 EPUB 文件", file=sys.stderr)
        return False

    try:
        tree = ET.parse(container_xml)
        root = tree.getroot()
        rootfile = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
        if rootfile is None:
            rootfile = root.find(".//rootfile")
        opf_rel_path = rootfile.attrib.get("full-path")
    except Exception as e:
        print(f"[-] 解析 container.xml 失败: {e}", file=sys.stderr)
        return False

    opf_full_path = os.path.join(raw_dir, opf_rel_path)
    opf_dir = os.path.dirname(opf_full_path)

    opf_tree = ET.parse(opf_full_path)
    opf_root = opf_tree.getroot()

    ns = {
        'opf': 'http://www.idpf.org/2007/opf',
        'dc': 'http://purl.org/dc/elements/1.1/'
    }

    title_elem = opf_root.find(".//{http://purl.org/dc/elements/1.1/}title")
    if title_elem is None:
        title_elem = opf_root.find(".//dc:title", ns)

    creator_elem = opf_root.find(".//{http://purl.org/dc/elements/1.1/}creator")
    if creator_elem is None:
        creator_elem = opf_root.find(".//dc:creator", ns)

    lang_elem = opf_root.find(".//{http://purl.org/dc/elements/1.1/}language")
    if lang_elem is None:
        lang_elem = opf_root.find(".//dc:language", ns)

    book_title = title_elem.text if title_elem is not None else "未知书名"
    book_author = creator_elem.text if creator_elem is not None else "未知作者"
    book_lang = lang_elem.text if lang_elem is not None else "en"

    manifest_items = {}
    manifest_elem = opf_root.find("{http://www.idpf.org/2007/opf}manifest")
    if manifest_elem is None:
        manifest_elem = opf_root.find("manifest")
    if manifest_elem is not None:
        for item in manifest_elem.findall("{http://www.idpf.org/2007/opf}item") or manifest_elem.findall("item"):
            item_id = item.attrib.get("id")
            href = item.attrib.get("href")
            media_type = item.attrib.get("media-type")
            manifest_items[item_id] = {
                "href": href,
                "media_type": media_type,
                "full_path": os.path.normpath(os.path.join(opf_dir, href))
            }

    spine_elem = opf_root.find("{http://www.idpf.org/2007/opf}spine")
    if spine_elem is None:
        spine_elem = opf_root.find("spine")
    spine_files = []
    if spine_elem is not None:
        for itemref in spine_elem.findall("{http://www.idpf.org/2007/opf}itemref") or spine_elem.findall("itemref"):
            idref = itemref.attrib.get("idref")
            if idref in manifest_items:
                item_info = manifest_items[idref]
                if "xhtml" in item_info["media_type"] or "html" in item_info["media_type"]:
                    spine_files.append({
                        "id": idref,
                        "href": item_info["href"],
                        "path": item_info["full_path"],
                        "rel_path": os.path.relpath(item_info["full_path"], work_dir)
                    })

    meta_info = {
        "title": book_title,
        "author": book_author,
        "language": book_lang,
        "opf_file": opf_full_path,
        "opf_rel": opf_rel_path,
        "raw_dir": raw_dir,
        "spine": spine_files,
        "total_chapters": len(spine_files)
    }

    meta_json_path = os.path.join(work_dir, "book_info.json")
    with open(meta_json_path, 'w', encoding='utf-8') as f:
        json.dump(meta_info, f, ensure_ascii=False, indent=2)

    progress_info = {
        "title": book_title,
        "total_chapters": len(spine_files),
        "completed_chapters": 0,
        "chapters_status": {item["id"]: "PENDING" for item in spine_files}
    }
    progress_path = os.path.join(work_dir, "progress.json")
    with open(progress_path, 'w', encoding='utf-8') as f:
        json.dump(progress_info, f, ensure_ascii=False, indent=2)

    print(f"[+] 成功解包 EPUB: 《{book_title}》 (作者: {book_author})")
    print(f"[+] 共提取 {len(spine_files)} 个核心章节/阅读文件")
    print(f"[+] 索引与进度跟踪已保存: {progress_path}")
    return True


def extract_blocks_from_file(xhtml_path, output_json=None):
    """
    从单个 XHTML 文件精确提取文本块，
    自动识别并以 ⟦NOTE_N⟧ 占位符保护 <sup>...</sup> 尾注/注解，
    确保在翻译过程中注解标记 0 丢失、0 错位。
    """
    with open(xhtml_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    pattern = re.compile(r'<(p|h[1-6]|li|blockquote|dt|dd)(\s+[^>]*)?>(.*?)</\1>', re.DOTALL | re.IGNORECASE)
    blocks = []
    for m in pattern.finditer(content):
        tag = m.group(1).lower()
        attrs = m.group(2) or ""
        inner = m.group(3)

        # 抽取并保护尾注 <sup>...</sup> 标签
        sup_tags = []
        def mask_sup(match):
            idx = len(sup_tags)
            sup_tags.append(match.group(0))
            return f"⟦NOTE_{idx}⟧"

        masked_inner = re.sub(r'<sup\b[^>]*>.*?</sup>', mask_sup, inner, flags=re.DOTALL | re.IGNORECASE)
        clean_text = re.sub(r'<[^>]+>', '', masked_inner).strip()

        if clean_text:
            blocks.append({
                "index": len(blocks),
                "tag": tag,
                "attrs": attrs,
                "inner_html": inner,
                "sup_tags": sup_tags,
                "text": clean_text,
                "word_count": len(clean_text.split())
            })

    if output_json:
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(blocks, f, ensure_ascii=False, indent=2)

    return blocks


def slice_batches(blocks_json_path, output_dir, max_words=1800, max_blocks=25):
    """
    智能批次切片引擎：
    按 1,500 ~ 2,000 英文词划分批次，并封装三层滑动窗口上下文。
    """
    with open(blocks_json_path, 'r', encoding='utf-8') as f:
        blocks = json.load(f)

    if not blocks:
        return []

    os.makedirs(output_dir, exist_ok=True)
    batches = []
    current_batch = []
    current_words = 0

    for b in blocks:
        w = b.get("word_count") or len(b["text"].split())
        if (current_words + w > max_words or len(current_batch) >= max_blocks) and current_batch:
            batches.append(current_batch)
            current_batch = [b]
            current_words = w
        else:
            current_batch.append(b)
            current_words += w

    if current_batch:
        batches.append(current_batch)

    batch_manifest = []
    for idx, batch in enumerate(batches):
        prev_blocks = []
        if idx > 0:
            prev_blocks = [{"index": b["index"], "text": b["text"]} for b in batches[idx - 1][-2:]]

        next_block = None
        if idx + 1 < len(batches):
            next_b = batches[idx + 1][0]
            next_block = {"index": next_b["index"], "text": next_b["text"][:150]}

        batch_data = {
            "batch_index": idx,
            "total_batches": len(batches),
            "block_range": [batch[0]["index"], batch[-1]["index"]],
            "total_blocks": len(batch),
            "word_count": sum(b.get("word_count") or len(b["text"].split()) for b in batch),
            "context_prev": prev_blocks,
            "context_next": next_block,
            "blocks": [{"index": b["index"], "text": b["text"]} for b in batch]
        }

        batch_file = os.path.join(output_dir, f"batch_{idx:03d}.json")
        with open(batch_file, 'w', encoding='utf-8') as f:
            json.dump(batch_data, f, ensure_ascii=False, indent=2)

        batch_manifest.append({
            "batch_index": idx,
            "file": batch_file,
            "blocks_count": len(batch),
            "word_count": batch_data["word_count"]
        })

    manifest_path = os.path.join(output_dir, "batches_manifest.json")
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(batch_manifest, f, ensure_ascii=False, indent=2)

    total_words = sum(b['word_count'] for b in batch_manifest)
    avg_words = total_words // len(batches) if batches else 0
    print(f"[+] 智能切片完成：共 {len(blocks)} 个段落 -> 切分为 {len(batches)} 个批次 (平均每批约 {avg_words} 词)")
    return batch_manifest


def qa_check(src_json_path, trans_json_path):
    """
    自动化质量守护与单段自愈检测
    """
    with open(src_json_path, 'r', encoding='utf-8') as f:
        src_blocks = json.load(f)
    with open(trans_json_path, 'r', encoding='utf-8') as f:
        trans_data = json.load(f)

    trans_map = {}
    if isinstance(trans_data, list):
        for item in trans_data:
            if isinstance(item, dict) and "index" in item:
                trans_map[item["index"]] = item.get("translation", "")
            elif isinstance(item, str):
                trans_map[len(trans_map)] = item
    elif isinstance(trans_data, dict):
        trans_map = {int(k) if str(k).isdigit() else k: v for k, v in trans_data.items()}

    report = {
        "passed": True,
        "src_count": len(src_blocks),
        "trans_count": len(trans_map),
        "missing_indices": [],
        "length_outliers": [],
        "number_mismatches": [],
        "healing_items": []
    }

    for b in src_blocks:
        idx = b["index"]
        if idx not in trans_map or not trans_map[idx].strip():
            report["missing_indices"].append(idx)
            report["healing_items"].append({
                "index": idx,
                "reason": "Missing translation",
                "text": b["text"]
            })

    for b in src_blocks:
        idx = b["index"]
        if idx not in trans_map:
            continue
        src_text = b["text"]
        tr_text = trans_map[idx].strip()

        src_len = len(src_text)
        tr_len = len(tr_text)
        if src_len > 120 and tr_len < 15:
            report["length_outliers"].append({
                "index": idx,
                "src_len": src_len,
                "tr_len": tr_len,
                "detail": "译文异常短小，疑似严重漏句"
            })
            report["healing_items"].append({
                "index": idx,
                "reason": "Severe truncation",
                "text": src_text
            })
        elif src_len < 30 and tr_len > 300:
            report["length_outliers"].append({
                "index": idx,
                "src_len": src_len,
                "tr_len": tr_len,
                "detail": "译文异常过长，疑似模型复读幻觉"
            })
            report["healing_items"].append({
                "index": idx,
                "reason": "Hallucination/Loop",
                "text": src_text
            })

    if report["missing_indices"] or report["length_outliers"]:
        report["passed"] = False

    return report


def inject_blocks(xhtml_path, trans_json_path, output_xhtml_path, mode="mono", indent="2em"):
    """
    高保真 DOM 注入引擎：
    1. 还原 ⟦NOTE_N⟧ 占位符为原始 <sup ...><a href="...">N</a></sup> 尾注超链接；
    2. 对目录页、章节标题包含的 <a href="..."> 超链接做 100% 结构保留，仅替换文本；
    3. 严禁改动任何标签的 id 与 class 属性，确保所有锚点跳转万无一失。
    """
    with open(xhtml_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    with open(trans_json_path, 'r', encoding='utf-8') as f:
        trans_data = json.load(f)

    trans_map = {}
    if isinstance(trans_data, list):
        for item in trans_data:
            if isinstance(item, dict) and "index" in item:
                trans_map[item["index"]] = item.get("translation", "")
            elif isinstance(item, str):
                trans_map[len(trans_map)] = item
    elif isinstance(trans_data, dict):
        trans_map = {int(k) if str(k).isdigit() else k: v for k, v in trans_data.items()}

    pattern = re.compile(r'<(p|h[1-6]|li|blockquote|dt|dd)(\s+[^>]*)?>(.*?)</\1>', re.DOTALL | re.IGNORECASE)
    valid_matches = []
    for m in pattern.finditer(content):
        clean_text = re.sub(r'<[^>]+>', '', m.group(3)).strip()
        if clean_text:
            valid_matches.append(m)

    modified_content = content
    # 从后向前精确替换，确保字符偏移位置 m.start() 和 m.end() 不发生位移
    for idx in reversed(range(len(valid_matches))):
        if idx not in trans_map or not trans_map[idx].strip():
            continue

        m = valid_matches[idx]
        tag = m.group(1)
        attrs = m.group(2) or ""
        inner_html = m.group(3)
        target_trans = escape(trans_map[idx].strip())

        # 1. 抽取原标签中的所有 <sup ...> 尾注
        sup_tags = re.findall(r'<sup\b[^>]*>.*?</sup>', inner_html, re.DOTALL | re.IGNORECASE)

        # 2. 还原译文中的 ⟦NOTE_N⟧ 占位符
        restored_trans = target_trans
        for s_idx, s_tag in enumerate(sup_tags):
            placeholder = f"⟦NOTE_{s_idx}⟧"
            if placeholder in restored_trans:
                restored_trans = restored_trans.replace(placeholder, s_tag)
            else:
                restored_trans = restored_trans + s_tag

        # 3. 检查原标签内部的非尾注 <a> 超链接（目录项、章节标题）
        inner_no_sup = re.sub(r'<sup\b[^>]*>.*?</sup>', '', inner_html, flags=re.DOTALL | re.IGNORECASE)
        a_links = list(re.finditer(r'(<a\s+[^>]*href=[\"\'][^\"\']+[\"\'][^>]*>)(.*?)(</a>)', inner_no_sup, re.DOTALL | re.IGNORECASE))

        if len(a_links) == 1:
            # 单一链接块（目录项如 <a href="...">Title</a>）
            m_a = a_links[0]
            clean_a_text = re.sub(r'<[^>]+>', '', m_a.group(2)).strip()
            if clean_a_text and clean_a_text in m_a.group(2):
                new_inner_a = m_a.group(2).replace(clean_a_text, restored_trans, 1)
            elif 'class="calibre2"' in m_a.group(2) or 'class="calibre_13"' in m_a.group(2):
                new_inner_a = f'<span class="calibre2"><span class="italic"><span class="calibre_13">{restored_trans}</span></span></span>'
            else:
                new_inner_a = restored_trans
            new_a = m_a.group(1) + new_inner_a + m_a.group(3)
            # 在 inner_html 中替换
            new_inner = inner_html[:m_a.start()] + new_a + inner_html[m_a.end():]
            replacement = f"<{tag}{attrs}>{new_inner}</{tag}>"

        elif len(a_links) == 2 and ("Chapter" in inner_html or "序言" in restored_trans or "章" in restored_trans or "Introduction" in inner_html):
            # 双链接章节标题（如 <a ...>Chapter 1</a><br/><a ...>Title</a>）
            m1 = a_links[0]
            m2 = a_links[1]
            
            part1 = restored_trans
            part2 = ""
            if " / " in restored_trans:
                parts = restored_trans.split(" / ", 1)
                part1, part2 = parts[0], parts[1]
            elif " " in restored_trans:
                parts = restored_trans.split(" ", 1)
                part1, part2 = parts[0], parts[1]

            clean1 = re.sub(r'<[^>]+>', '', m1.group(2)).strip()
            clean2 = re.sub(r'<[^>]+>', '', m2.group(2)).strip()

            new_a1 = m1.group(0).replace(clean1, part1) if clean1 else m1.group(1) + part1 + m1.group(3)
            new_a2 = m2.group(0).replace(clean2, part2 or clean2) if clean2 else m2.group(1) + (part2 or "") + m2.group(3)

            new_inner = inner_html[:m1.start()] + new_a1 + inner_html[m1.end():m2.start()] + new_a2 + inner_html[m2.end():]
            replacement = f"<{tag}{attrs}>{new_inner}</{tag}>"

        elif len(a_links) == 0 and (" / " in restored_trans or "\n" in restored_trans) and re.search(r'(?:<br\b[^>]*>\s*)+', inner_html):
            # 双行主副标题（如 <span ...>INTRODUCTION</span><br/><br/><span ...>Ends and Means</span>）
            br_match = re.search(r'(?:<br\b[^>]*>\s*)+', inner_html)
            sep = " / " if " / " in restored_trans else "\n"
            parts = restored_trans.split(sep, 1)
            t1, t2 = parts[0].strip(), parts[1].strip()
            p1, p2 = inner_html[:br_match.start()], inner_html[br_match.end():]
            clean1 = re.sub(r'<[^>]+>', '', p1).strip()
            clean2 = re.sub(r'<[^>]+>', '', p2).strip()

            def _safe_rep(html_part, old_t, new_t):
                if not old_t:
                    return html_part
                pat = r'(>|^)([^<]*?)' + re.escape(old_t) + r'([^<]*?)(<|$)'
                if re.search(pat, html_part):
                    rep = new_t.replace('\\', '\\\\')
                    return re.sub(pat, r'\g<1>\g<2>' + rep + r'\g<3>\g<4>', html_part, count=1)
                return html_part.replace(old_t, new_t, 1)

            new_p1 = _safe_rep(p1, clean1, t1)
            new_p2 = _safe_rep(p2, clean2, t2)
            new_inner = new_p1 + br_match.group(0) + new_p2
            replacement = f"<{tag}{attrs}>{new_inner}</{tag}>"

        else:
            # 检查是否有整体包裹的样式标签（如各级标题的 <span class="bold">、<span class="italic"> 等）
            prefix_match = re.match(r'^(\s*(?:<span\b[^>]*>)+)', inner_no_sup)
            suffix_match = re.search(r'((?:</span>\s*)+)$', inner_no_sup)
            if prefix_match and suffix_match:
                p_str = prefix_match.group(1)
                s_str = suffix_match.group(1)
                middle = inner_no_sup[len(p_str):len(inner_no_sup)-len(s_str)]
                if not re.search(r'<[^>]+>', middle) and middle.strip():
                    # 原文整体被层级样式标签包裹（标题或强调块），严格保留其内嵌视觉层级结构
                    restored_trans = f"{p_str}{restored_trans}{s_str}"

            if mode == "bilingual":
                # 双语对照模式：保留原英文段落，在下方追加出版级高雅译文段落
                trans_attrs = attrs
                if 'class="' in trans_attrs:
                    trans_attrs = re.sub(r'class="([^"]*)"', r'class="\1 epub-trans-block"', trans_attrs)
                elif "class='" in trans_attrs:
                    trans_attrs = re.sub(r"class='([^']*)'", r"class='\1 epub-trans-block'", trans_attrs)
                else:
                    trans_attrs = f' class="epub-trans-block"{trans_attrs}'
                replacement = f"<{tag}{attrs}>{inner_html}</{tag}>\n<{tag}{trans_attrs}>{restored_trans}</{tag}>"
            else:
                # 纯中文模式：直接高保真替换
                replacement = f"<{tag}{attrs}>{restored_trans}</{tag}>"

        modified_content = modified_content[:m.start()] + replacement + modified_content[m.end():]

    mono_css = DEFAULT_MONO_CSS
    bilingual_css = DEFAULT_BILINGUAL_CSS
    if indent != "2em":
        mono_css = mono_css.replace("text-indent: 2em !important;", f"text-indent: {indent} !important;")
        bilingual_css = bilingual_css.replace("text-indent: 2em !important;", f"text-indent: {indent} !important;")

    if mode == "bilingual" and "</head>" in modified_content and "epub-bilingual-style" not in modified_content and "epub-trans-block" not in modified_content:
        style_block = f"<style type=\"text/css\" id=\"epub-bilingual-style\">\n{bilingual_css}\n</style>\n</head>"
        modified_content = modified_content.replace("</head>", style_block, 1)
    elif mode == "mono" and "</head>" in modified_content and "epub-mono-style" not in modified_content:
        style_block = f"<style type=\"text/css\" id=\"epub-mono-style\">\n{mono_css}\n</style>\n</head>"
        modified_content = modified_content.replace("</head>", style_block, 1)

    with open(output_xhtml_path, 'w', encoding='utf-8') as f:
        f.write(modified_content)

    print(f"[+] 注入翻译成功 -> {output_xhtml_path} (模式: {mode}, 缩进: {indent})")
    return True


def fix_style(work_dir, mode="mono", indent="2em"):
    """
    出版级排版修复引擎：
    在 EPUB 的所有全局 CSS 文件（如 stylesheet.css、page_styles.css）中注入
    出版级中文首行缩进（默认 2em 即空 2 个汉字字符）、两端对齐与舒适行距规则，
    自动豁免标题、引用、列表、表格、图片与居中段落，确保各类阅读器强制生效。
    """
    raw_dir = os.path.join(work_dir, "raw")
    if not os.path.exists(raw_dir):
        print(f"[-] 找不到源目录: {raw_dir}", file=sys.stderr)
        return False

    css_files = []
    for root, dirs, files in os.walk(raw_dir):
        for f in files:
            if f.lower().endswith(".css"):
                css_files.append(os.path.join(root, f))

    css_to_inject = DEFAULT_MONO_CSS if mode == "mono" else DEFAULT_BILINGUAL_CSS
    if indent != "2em":
        css_to_inject = css_to_inject.replace("text-indent: 2em !important;", f"text-indent: {indent} !important;")

    marker = "/* === EPUB 中文出版级" if mode == "mono" else "/* === EPUB 智能双语出版级"

    if not css_files:
        print("[!] 未找到外部 CSS 样式表文件，样式已通过 inject-blocks 内嵌注入。")
        return True

    for css_path in css_files:
        with open(css_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if marker in content:
            print(f"[*] 已存在出版级中文样式，跳过: {os.path.basename(css_path)}")
            continue
        with open(css_path, "a", encoding="utf-8") as f:
            f.write("\n\n" + css_to_inject + "\n")
        print(f"[+] 成功将出版级中文排版样式注入（首行缩进: {indent}）: {os.path.basename(css_path)}")

    return True


def scan_glossary(work_dir, max_chapters=5):
    """扫描提取前序章节中的核心高频专有名词"""
    meta_path = os.path.join(work_dir, "book_info.json")
    if not os.path.exists(meta_path):
        print("[-] 找不到 book_info.json，请先执行 unpack", file=sys.stderr)
        return {}

    with open(meta_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    phrase_counts = {}
    pattern = re.compile(r'\b([A-Z][a-z]+(?:\s+(?:of\s+|the\s+|de\s+)?[A-Z][a-z]+)+)\b')

    chapters_to_scan = meta["spine"][:max_chapters]
    for ch in chapters_to_scan:
        ch_path = ch["path"]
        if os.path.exists(ch_path):
            with open(ch_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            text = re.sub(r'<[^>]+>', ' ', content)
            matches = pattern.findall(text)
            for m in matches:
                clean_m = m.strip()
                if len(clean_m) > 3:
                    phrase_counts[clean_m] = phrase_counts.get(clean_m, 0) + 1

    filtered = {k: "" for k, v in sorted(phrase_counts.items(), key=lambda x: x[1], reverse=True) if v >= 2}
    glossary_path = os.path.join(work_dir, "glossary.json")
    with open(glossary_path, 'w', encoding='utf-8') as f:
        json.dump(filtered, f, ensure_ascii=False, indent=2)

    print(f"[+] 扫描完成，生成核心术语库 ({len(filtered)} 个待补齐项) -> {glossary_path}")
    return filtered


def pack_epub(work_dir, output_epub_path):
    """严格按照 EPUB 国际标准重打包（mimetype 首文件无压缩存储）"""
    raw_dir = os.path.join(work_dir, "raw")
    if not os.path.exists(raw_dir):
        print(f"[-] 找不到源目录: {raw_dir}", file=sys.stderr)
        return False

    output_epub_path = os.path.abspath(output_epub_path)
    output_parent = os.path.dirname(output_epub_path)
    if output_parent:
        os.makedirs(output_parent, exist_ok=True)

    if os.path.exists(output_epub_path):
        os.remove(output_epub_path)

    mimetype_file = os.path.join(raw_dir, "mimetype")
    if not os.path.exists(mimetype_file):
        with open(mimetype_file, 'w', encoding='ascii') as f:
            f.write("application/epub+zip")

    with zipfile.ZipFile(output_epub_path, 'w') as zout:
        zout.write(mimetype_file, "mimetype", compress_type=zipfile.ZIP_STORED)

        for root, dirs, files in os.walk(raw_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, raw_dir)
                if rel_path == "mimetype":
                    continue
                zout.write(full_path, rel_path, compress_type=zipfile.ZIP_DEFLATED)

    file_size_mb = os.path.getsize(output_epub_path) / (1024 * 1024)
    print(f"[+] EPUB 规范打包完成: {output_epub_path} ({file_size_mb:.2f} MB)")
    return True


def sync_ncx(work_dir, toc_trans_json, book_title=None):
    raw_dir = os.path.join(work_dir, "raw")
    ncx_files = [os.path.join(raw_dir, f) for f in os.listdir(raw_dir) if f.endswith(".ncx")]
    if not ncx_files:
        print("[!] 未找到 .ncx 导航文件")
        return False
    ncx_path = ncx_files[0]
    with open(ncx_path, "r", encoding="utf-8") as f:
        ncx_content = f.read()

    with open(toc_trans_json, "r", encoding="utf-8") as f:
        toc_items = json.load(f)

    cache_dir = os.path.join(work_dir, "cache")
    toc_blocks_path = os.path.join(cache_dir, "toc_blocks.json")
    if os.path.exists(toc_blocks_path):
        with open(toc_blocks_path, "r", encoding="utf-8") as f:
            src_blocks = json.load(f)
        src_map = {b["index"]: b["text"].strip() for b in src_blocks}
        for item in toc_items:
            idx = item.get("index")
            zh = item.get("translation", "").strip()
            en = src_map.get(idx, "")
            if en and zh:
                ncx_content = ncx_content.replace(f"<text>{en}</text>", f"<text>{zh}</text>")

    if book_title:
        ncx_content = re.sub(r'<docTitle>\s*<text>.*?</text>\s*</docTitle>', f'<docTitle><text>{book_title}</text></docTitle>', ncx_content)

    with open(ncx_path, "w", encoding="utf-8") as f:
        f.write(ncx_content)
    print(f"[+] 导航目录（NCX）已成功同步中文标签 -> {ncx_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description="EPUB 电子书专业翻译、批次切片与质检引擎")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # unpack
    p_unpack = subparsers.add_parser("unpack", help="解包 EPUB 并提取元数据与阅读顺序")
    p_unpack.add_argument("epub", help="输入的 epub 文件路径")
    p_unpack.add_argument("work_dir", help="工作区目录")

    # extract-blocks
    p_extract = subparsers.add_parser("extract-blocks", help="从单个 xhtml 提取文本块（含尾注保护）")
    p_extract.add_argument("xhtml", help="XHTML 文件路径")
    p_extract.add_argument("--output", "-o", help="输出 blocks.json 路径")

    # slice-batches
    p_slice = subparsers.add_parser("slice-batches", help="智能批次切片引擎（生成带上下文滑动窗口的批次任务）")
    p_slice.add_argument("blocks_json", help="章节提取出的 blocks.json")
    p_slice.add_argument("output_dir", help="输出批次文件的目录")
    p_slice.add_argument("--max-words", type=int, default=1800, help="单批最大词数（默认 1800 词）")
    p_slice.add_argument("--max-blocks", type=int, default=25, help="单批最大段落数（默认 25 段）")

    # inject-blocks
    p_inject = subparsers.add_parser("inject-blocks", help="将翻译文本注入回 XHTML（高保真保留引用与尾注链接）")
    p_inject.add_argument("xhtml", help="原 XHTML 文件路径")
    p_inject.add_argument("trans_json", help="译文 JSON 路径")
    p_inject.add_argument("output", help="输出 XHTML 路径")
    p_inject.add_argument("--mode", choices=["bilingual", "mono"], default="bilingual", help="模式: bilingual 或 mono")
    p_inject.add_argument("--indent", default="2em", help="首行缩进大小（默认 2em 即空 2 个汉字字符，可选 1em）")

    # qa-check
    p_qa = subparsers.add_parser("qa-check", help="自动化质量守护与单段纠错检测")
    p_qa.add_argument("src_json", help="原文 blocks.json")
    p_qa.add_argument("trans_json", help="译文 trans.json")

    # glossary-scan
    p_glossary = subparsers.add_parser("glossary-scan", help="扫描前序章节提取候选人名与专有名词表")
    p_glossary.add_argument("work_dir", help="工作区目录")
    p_glossary.add_argument("--chapters", "-c", type=int, default=5, help="扫描章节数量")

    # pack
    p_pack = subparsers.add_parser("pack", help="规范化重打包为 EPUB")
    p_pack.add_argument("work_dir", help="工作区目录")
    p_pack.add_argument("output_epub", help="输出的 epub 文件路径")

    # sync-ncx
    p_ncx = subparsers.add_parser("sync-ncx", help="同步更新 EPUB 阅读器侧边栏导航目录（toc.ncx）的中文标签")
    p_ncx.add_argument("work_dir", help="工作区目录")
    p_ncx.add_argument("toc_trans_json", help="目录翻译 JSON 文件路径")
    p_ncx.add_argument("--title", default=None, help="可选：全书中英文标题")

    # fix-style
    p_fix = subparsers.add_parser("fix-style", help="修复全书 CSS 样式表，注入出版级中文首行缩进与行距")
    p_fix.add_argument("work_dir", help="工作区目录")
    p_fix.add_argument("--mode", choices=["bilingual", "mono"], default="mono", help="模式: mono（默认）或 bilingual")
    p_fix.add_argument("--indent", default="2em", help="首行缩进大小（默认 2em 即空 2 个汉字字符，可选 1em）")

    args = parser.parse_args()

    if args.command == "unpack":
        unpack_epub(args.epub, args.work_dir)
    elif args.command == "extract-blocks":
        extract_blocks_from_file(args.xhtml, args.output)
    elif args.command == "slice-batches":
        slice_batches(args.blocks_json, args.output_dir, args.max_words, args.max_blocks)
    elif args.command == "inject-blocks":
        inject_blocks(args.xhtml, args.trans_json, args.output, args.mode, args.indent)
    elif args.command == "qa-check":
        res = qa_check(args.src_json, args.trans_json)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.command == "glossary-scan":
        scan_glossary(args.work_dir, args.chapters)
    elif args.command == "sync-ncx":
        sync_ncx(args.work_dir, args.toc_trans_json, args.title)
    elif args.command == "fix-style":
        fix_style(args.work_dir, args.mode, args.indent)
    elif args.command == "pack":
        pack_epub(args.work_dir, args.output_epub)


if __name__ == "__main__":
    main()
