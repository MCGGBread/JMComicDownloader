package com.jmcomic.app;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** 极简 JSON 解析/序列化（不依赖 org.json，桌面测试也能用）。 */
public final class Json {

    private Json() {}

    // ------------------------------------------------------------------ //
    // 解析
    // ------------------------------------------------------------------ //
    public static Object parse(String text) {
        Parser p = new Parser(text);
        Object value = p.value();
        p.skipWs();
        if (p.pos < text.length()) {
            throw new IllegalArgumentException("多余字符 @" + p.pos);
        }
        return value;
    }

    @SuppressWarnings("unchecked")
    public static Map<String, Object> parseObject(String text) {
        Object v = parse(text);
        if (v instanceof Map) return (Map<String, Object>) v;
        throw new IllegalArgumentException("不是 JSON 对象");
    }

    @SuppressWarnings("unchecked")
    public static List<Object> parseArray(String text) {
        Object v = parse(text);
        if (v instanceof List) return (List<Object>) v;
        throw new IllegalArgumentException("不是 JSON 数组");
    }

    private static final class Parser {
        final String s;
        int pos;

        Parser(String s) {
            this.s = s;
        }

        void skipWs() {
            while (pos < s.length()) {
                char c = s.charAt(pos);
                if (c == ' ' || c == '\n' || c == '\r' || c == '\t') pos++;
                else break;
            }
        }

        Object value() {
            skipWs();
            if (pos >= s.length()) throw new IllegalArgumentException("意外结束");
            char c = s.charAt(pos);
            switch (c) {
                case '{': return object();
                case '[': return array();
                case '"': return string();
                case 't': expect("true"); return Boolean.TRUE;
                case 'f': expect("false"); return Boolean.FALSE;
                case 'n': expect("null"); return null;
                default: return number();
            }
        }

        void expect(String word) {
            if (!s.startsWith(word, pos)) throw new IllegalArgumentException("非法字面量 @" + pos);
            pos += word.length();
        }

        Map<String, Object> object() {
            Map<String, Object> map = new LinkedHashMap<>();
            pos++; // {
            skipWs();
            if (pos < s.length() && s.charAt(pos) == '}') { pos++; return map; }
            while (true) {
                skipWs();
                String key = string();
                skipWs();
                if (pos >= s.length() || s.charAt(pos) != ':') throw new IllegalArgumentException("缺少冒号");
                pos++;
                map.put(key, value());
                skipWs();
                if (pos >= s.length()) throw new IllegalArgumentException("对象未闭合");
                char c = s.charAt(pos++);
                if (c == '}') return map;
                if (c != ',') throw new IllegalArgumentException("缺少逗号");
            }
        }

        List<Object> array() {
            List<Object> list = new ArrayList<>();
            pos++; // [
            skipWs();
            if (pos < s.length() && s.charAt(pos) == ']') { pos++; return list; }
            while (true) {
                list.add(value());
                skipWs();
                if (pos >= s.length()) throw new IllegalArgumentException("数组未闭合");
                char c = s.charAt(pos++);
                if (c == ']') return list;
                if (c != ',') throw new IllegalArgumentException("缺少逗号");
            }
        }

        String string() {
            if (s.charAt(pos) != '"') throw new IllegalArgumentException("不是字符串 @" + pos);
            pos++;
            StringBuilder sb = new StringBuilder();
            while (pos < s.length()) {
                char c = s.charAt(pos++);
                if (c == '"') return sb.toString();
                if (c != '\\') { sb.append(c); continue; }
                if (pos >= s.length()) break;
                char e = s.charAt(pos++);
                switch (e) {
                    case '"': sb.append('"'); break;
                    case '\\': sb.append('\\'); break;
                    case '/': sb.append('/'); break;
                    case 'b': sb.append('\b'); break;
                    case 'f': sb.append('\f'); break;
                    case 'n': sb.append('\n'); break;
                    case 'r': sb.append('\r'); break;
                    case 't': sb.append('\t'); break;
                    case 'u':
                        if (pos + 4 <= s.length()) {
                            sb.append((char) Integer.parseInt(s.substring(pos, pos + 4), 16));
                            pos += 4;
                        }
                        break;
                    default: sb.append(e);
                }
            }
            throw new IllegalArgumentException("字符串未闭合");
        }

        Object number() {
            int start = pos;
            while (pos < s.length()) {
                char c = s.charAt(pos);
                if ((c >= '0' && c <= '9') || c == '-' || c == '+' || c == '.' || c == 'e' || c == 'E') pos++;
                else break;
            }
            String raw = s.substring(start, pos);
            if (raw.isEmpty()) throw new IllegalArgumentException("非法字符 @" + start);
            double d = Double.parseDouble(raw);
            if (d == Math.rint(d) && Math.abs(d) < 9e15) return (long) d;
            return d;
        }
    }

    // ------------------------------------------------------------------ //
    // 序列化
    // ------------------------------------------------------------------ //
    public static String stringify(Object value) {
        StringBuilder sb = new StringBuilder();
        write(sb, value);
        return sb.toString();
    }

    @SuppressWarnings("unchecked")
    private static void write(StringBuilder sb, Object v) {
        if (v == null) {
            sb.append("null");
        } else if (v instanceof String) {
            sb.append(quote((String) v));
        } else if (v instanceof Boolean) {
            sb.append(v.toString());
        } else if (v instanceof Number) {
            double d = ((Number) v).doubleValue();
            if (d == Math.rint(d) && Math.abs(d) < 9e15) sb.append(((Number) v).longValue());
            else sb.append(v.toString());
        } else if (v instanceof Map) {
            sb.append('{');
            boolean first = true;
            for (Map.Entry<String, Object> e : ((Map<String, Object>) v).entrySet()) {
                if (!first) sb.append(',');
                first = false;
                sb.append(quote(e.getKey())).append(':').append(stringify(e.getValue()));
            }
            sb.append('}');
        } else if (v instanceof Iterable) {
            sb.append('[');
            boolean first = true;
            for (Object item : (Iterable<Object>) v) {
                if (!first) sb.append(',');
                first = false;
                sb.append(stringify(item));
            }
            sb.append(']');
        } else {
            sb.append(quote(v.toString()));
        }
    }

    /** 生成可安全嵌入 JS/JSON 的字符串字面量。 */
    public static String quote(String text) {
        StringBuilder sb = new StringBuilder(text.length() + 8);
        sb.append('"');
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                case '\b': sb.append("\\b"); break;
                case '\f': sb.append("\\f"); break;
                default:
                    if (c < 0x20 || c == 0x2028 || c == 0x2029) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
            }
        }
        sb.append('"');
        return sb.toString();
    }

    // ------------------------------------------------------------------ //
    // 取值辅助
    // ------------------------------------------------------------------ //
    @SuppressWarnings("unchecked")
    public static Map<String, Object> obj(Object v) {
        if (v instanceof Map) return (Map<String, Object>) v;
        return new LinkedHashMap<>();
    }

    @SuppressWarnings("unchecked")
    public static List<Object> list(Object v) {
        if (v instanceof List) return (List<Object>) v;
        return new ArrayList<>();
    }

    public static String str(Object v, String def) {
        if (v == null) return def;
        if (v instanceof String) return (String) v;
        if (v instanceof Number) {
            double d = ((Number) v).doubleValue();
            if (d == Math.rint(d)) return String.valueOf(((Number) v).longValue());
        }
        return String.valueOf(v);
    }

    public static int i(Object v, int def) {
        if (v instanceof Number) return ((Number) v).intValue();
        try {
            return Integer.parseInt(str(v, String.valueOf(def)));
        } catch (Exception e) {
            return def;
        }
    }

    public static boolean b(Object v, boolean def) {
        if (v instanceof Boolean) return (Boolean) v;
        if (v instanceof String) return "true".equalsIgnoreCase((String) v);
        if (v instanceof Number) return ((Number) v).intValue() != 0;
        return def;
    }
}
