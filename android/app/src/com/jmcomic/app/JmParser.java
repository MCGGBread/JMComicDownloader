package com.jmcomic.app;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 番号解析：与桌面版规则保持一致。
 *
 * jm54747电梯（极品） / h540931(瞬) / 142176(母子大车)404477(...) / 47228，118983
 * / JM-54747 / [JM100] / 18comic 链接 / aid=54747
 */
public final class JmParser {

    private JmParser() {}

    private static final Pattern JM_PREFIX = Pattern.compile(
            "(?<![0-9a-z])jm[\\s\\-_#:]*([0-9]{2,8})(?![0-9])", Pattern.CASE_INSENSITIVE);
    private static final Pattern H_PREFIX = Pattern.compile(
            "(?<![0-9a-z_])h([0-9]{4,8})(?![0-9a-z_])", Pattern.CASE_INSENSITIVE);
    private static final Pattern URL_ALBUM = Pattern.compile(
            "/(?:album|photo|video)/([0-9]{2,8})(?![0-9])", Pattern.CASE_INSENSITIVE);
    private static final Pattern URL_QUERY = Pattern.compile(
            "[?&](?:aid|id|album_id|photo_id)=([0-9]{2,8})(?![0-9])", Pattern.CASE_INSENSITIVE);
    private static final Pattern DIGIT_RUN = Pattern.compile("(?<!\\d)([0-9]{2,8})(?!\\d)");
    private static final Pattern BAD_TAIL = Pattern.compile(
            "^\\s*(?:年|月|日|号|號|时|時|分|秒|页|頁|话|話|集|卷|期|章|节|節|楼|樓|版|个|個|人|次|元|块|塊|张|張|幅|篇|本|岁|歲|%|％|℃|kg|cm|mm|km|px|dpi|k|w|万|萬)",
            Pattern.CASE_INSENSITIVE);
    private static final String OPEN_BRACKETS = "([{【〔［｛《〈";

    private static final class Hit implements Comparable<Hit> {
        final int pos;
        final String id;

        Hit(int pos, String id) {
            this.pos = pos;
            this.id = id;
        }

        @Override
        public int compareTo(Hit o) {
            return Integer.compare(pos, o.pos);
        }
    }

    public static List<String> parseIds(String text) {
        List<String> result = new ArrayList<>();
        if (text == null || text.isEmpty()) return result;
        String s = normalize(text);
        List<Hit> hits = new ArrayList<>();

        collect(hits, JM_PREFIX, s, 1);
        collect(hits, H_PREFIX, s, 1);
        collect(hits, URL_ALBUM, s, 1);
        collect(hits, URL_QUERY, s, 1);
        scanDigitRuns(hits, s);

        hits.sort(null);
        Set<String> seen = new LinkedHashSet<>();
        for (Hit hit : hits) {
            String id = trimZeros(hit.id);
            if (id.isEmpty() || seen.contains(id)) continue;
            int value;
            try {
                value = Integer.parseInt(id);
            } catch (NumberFormatException e) {
                continue;
            }
            if (value < 1 || value > 9_999_999) continue;
            seen.add(id);
            result.add(id);
        }
        return result;
    }

    private static void collect(List<Hit> hits, Pattern pattern, String text, int group) {
        Matcher m = pattern.matcher(text);
        while (m.find()) {
            hits.add(new Hit(m.start(), m.group(group)));
        }
    }

    private static String trimZeros(String raw) {
        int i = 0;
        while (i < raw.length() - 1 && raw.charAt(i) == '0') i++;
        return raw.substring(i);
    }

    private static void scanDigitRuns(List<Hit> hits, String text) {
        Matcher m = DIGIT_RUN.matcher(text);
        int length = text.length();
        while (m.find()) {
            String raw = m.group(1);
            if (raw.length() < 3) continue; // 裸番号至少 3 位

            int start = m.start();
            int end = m.end();
            char prev = start > 0 ? text.charAt(start - 1) : 0;
            char next = end < length ? text.charAt(end) : 0;

            // 前后连着字母/数字 → 属于单词或更长数字
            if (prev != 0 && prev < 128 && (Character.isLetterOrDigit(prev) || prev == '_')) continue;
            if (next != 0 && next < 128 && (Character.isLetter(next) || next == '_')) continue;

            // 日期/版本/时间：2024-10-26、2.5.36、10:30
            if (next != 0 && "-./:".indexOf(next) >= 0 && end + 1 < length
                    && Character.isDigit(text.charAt(end + 1))) {
                continue;
            }
            if (prev != 0 && "-./:".indexOf(prev) >= 0 && start >= 2
                    && Character.isDigit(text.charAt(start - 2))) {
                continue;
            }

            // 查询参数里的数字：aid=142176 / id=142176
            if (prev == '=') {
                String head = text.substring(0, start - 1).toLowerCase();
                if (!(head.endsWith("aid") || head.endsWith("id")
                        || head.endsWith("album_id") || head.endsWith("photo_id"))) {
                    continue;
                }
            } else if (prev == '+' || prev == '=') {
                continue;
            }

            // 普通量词：2024年、35页、50%
            if (BAD_TAIL.matcher(text.substring(end, Math.min(length, end + 4))).find()) continue;

            boolean annotation = next != 0 && OPEN_BRACKETS.indexOf(next) >= 0;
            if (isCjk(prev) && !annotation) continue;

            hits.add(new Hit(start, raw));
        }
    }

    private static boolean isCjk(char c) {
        if (c == 0) return false;
        return (c >= 0x3400 && c <= 0x4DBF)
                || (c >= 0x4E00 && c <= 0x9FFF)
                || (c >= 0xF900 && c <= 0xFAFF)
                || (c >= 0x3040 && c <= 0x30FF);
    }

    /** 全角转半角 + 常见中文标点归一。 */
    public static String normalize(String text) {
        StringBuilder sb = new StringBuilder(text.length());
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (c >= 0xFF01 && c <= 0xFF5E) {
                sb.append((char) (c - 0xFEE0));
            } else if (c == 0x3000) {
                sb.append(' ');
            } else if (c == 0xFF0C || c == 0x3001) {
                sb.append(',');
            } else if (c == 0x3002) {
                sb.append('.');
            } else if (c == 0xFF1B) {
                sb.append(';');
            } else {
                sb.append(c);
            }
        }
        return sb.toString();
    }
}
