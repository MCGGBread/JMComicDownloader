"""从任意粘贴文本中提取 JM 番号。

支持的形式（可混排、可紧贴无分隔）：
    jm54747电梯（极品）
    JM28650 体育用具储藏室
    JM-54747 / JM 54747 / jm#54747 / [JM54747]
    h540931(瞬)-h499835(幼瞬)      （h 前缀，常见于合集/对照表）
    500703(柚子)-h559091(柚子)     （h 前缀与纯数字混用）
    47228，118983，152470 ...
    142176(母子大车)404477(长篇大车，经典作品)404098(狐娘)431896(熟女)
    142176（母子大车）404477
    推荐142176(母子大车)
    54747 电梯          （数字 + 标题）
    https://18comic.vip/album/54747/
    ?aid=54747
同一番号重复出现会自动去重，并保持输入顺序。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_ID = 9_999_999
MIN_ID = 1


@dataclass(frozen=True)
class ParsedId:
    jm_id: str
    source: str


_TRANS: dict[int, int] = {i: i - 0xFEE0 for i in range(0xFF01, 0xFF5F)}  # 全角 ASCII
_TRANS.update({0x3000: 0x20, 0xFF0C: 0x2C, 0x3001: 0x2C, 0x3002: 0x2E, 0xFF1B: 0x3B})

_JM_PREFIX = re.compile(r"(?<![0-9a-z])jm[\s\-_#:]*([0-9]{2,8})(?![0-9])", re.I)
# h 前缀（h540931）。单字母前缀容易误伤（h264 编码、H100 显卡），
# 所以要求至少 4 位数字，且前后不能连着字母/下划线。
_H_PREFIX = re.compile(r"(?<![0-9a-z_])h([0-9]{4,8})(?![0-9a-z_])", re.I)
_URL_ALBUM = re.compile(r"/(?:album|photo|video)/([0-9]{2,8})(?![0-9])", re.I)
_URL_QUERY = re.compile(r"[?&](?:aid|id|album_id|photo_id)=([0-9]{2,8})(?![0-9])", re.I)

# 任意位置上的连续数字（前后不能再接数字，避免从长数字里截一段）
_DIGIT_RUN = re.compile(r"(?<!\d)([0-9]{2,8})(?!\d)")

# 数字后面紧跟这些括号，说明是「番号(备注)」的写法
_OPEN_BRACKETS = "([{【〔［｛《〈"

# 数字后面跟着这些量词/单位，说明是普通数字而不是车号
_BAD_TAIL = re.compile(
    r"^\s*(?:年|月|日|号|號|时|時|分|秒|页|頁|话|話|集|卷|期|章|节|節|楼|樓|版|个|個|人|次|元|块|塊|张|張|幅|篇|本|岁|歲|%|％|℃|kg|cm|mm|km|px|dpi|k|w|万|萬)",
    re.I,
)


def _normalize(text: str) -> str:
    return str(text or "").translate(_TRANS)


def _valid(raw: str) -> bool:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return False
    return MIN_ID <= value <= MAX_ID


def _is_cjk(char: str) -> bool:
    """是否是正文用字（汉字/假名）。中文标点【】《》不算，否则会挡住后面的番号。"""
    if not char:
        return False
    code = ord(char)
    return (
        0x3400 <= code <= 0x4DBF      # 扩展 A
        or 0x4E00 <= code <= 0x9FFF   # 基本汉字
        or 0xF900 <= code <= 0xFAFF   # 兼容汉字
        or 0x3040 <= code <= 0x30FF   # 日文假名
    )


def _scan_digit_runs(text: str) -> list[tuple[int, str, str]]:
    """扫描裸数字，根据前后文判断是否像番号。

    关键点：不依赖分隔符，所以 `142176(母子大车)404477(...)` 这种紧贴写法也能逐个切出来。
    """
    hits: list[tuple[int, str, str]] = []
    length = len(text)

    for match in _DIGIT_RUN.finditer(text):
        raw = match.group(1)
        if len(raw) < 3:  # 裸番号至少 3 位，避免把「第2话」「C88」当成车号
            continue

        start, end = match.start(), match.end()
        prev = text[start - 1] if start > 0 else ""
        nxt = text[end] if end < length else ""

        # 前后还连着字母/数字 → 属于单词或更长的数字
        if prev and prev.isascii() and (prev.isalnum() or prev == "_"):
            continue
        if nxt and nxt.isascii() and (nxt.isalpha() or nxt == "_"):
            continue

        # 日期 / 版本 / 小数 / 时间：2024-10-26、2.5.36、10:30
        if nxt and nxt in "-./:" and end + 1 < length and text[end + 1].isdigit():
            continue
        if prev and prev in "-./:" and start >= 2 and text[start - 2].isdigit():
            continue

        # 查询参数里的数字：aid=142176 / id=142176（裸片段也要认），其余 a=1 之类不认
        if prev == "=":
            head = text[:start - 1]
            if not re.search(r"(?:^|[?&\s])(?:aid|id|album_id|photo_id)$", head, re.I):
                continue
        elif prev and prev in "=+":
            continue

        # 普通量词：2024年、35页、50%
        if _BAD_TAIL.match(text[end:end + 4]):
            continue

        # 数字后面紧跟括号注释，是最强的「番号」信号，允许前面是中文（推荐142176(...)）
        annotation = bool(nxt) and nxt in _OPEN_BRACKETS

        # 前面是中文且后面不是括号注释 → 更像正文里的数字（第404477话、共12345字）
        if _is_cjk(prev) and not annotation:
            continue

        hits.append((start, raw, raw))

    return hits


def parse(text: str) -> list[ParsedId]:
    """返回去重后的番号列表（保持出现顺序）。"""
    normalized = _normalize(text)
    hits: list[tuple[int, str, str]] = []

    for m in _JM_PREFIX.finditer(normalized):
        hits.append((m.start(), m.group(1), m.group(0).strip()))

    for m in _H_PREFIX.finditer(normalized):
        hits.append((m.start(), m.group(1), m.group(0).strip()))

    for m in _URL_ALBUM.finditer(normalized):
        hits.append((m.start(), m.group(1), m.group(0)))

    for m in _URL_QUERY.finditer(normalized):
        hits.append((m.start(), m.group(1), m.group(0)))

    hits.extend(_scan_digit_runs(normalized))

    hits.sort(key=lambda item: item[0])

    result: list[ParsedId] = []
    seen: set[str] = set()
    for _pos, raw, source in hits:
        if not _valid(raw):
            continue
        jm_id = str(int(raw))
        if jm_id in seen:
            continue
        seen.add(jm_id)
        result.append(ParsedId(jm_id=jm_id, source=source))
    return result


def parse_ids(text: str) -> list[str]:
    return [item.jm_id for item in parse(text)]


def join_ids(ids) -> str:
    return "，".join(str(i) for i in ids)
