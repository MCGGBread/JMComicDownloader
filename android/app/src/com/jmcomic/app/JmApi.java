package com.jmcomic.app;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.zip.GZIPInputStream;

import javax.crypto.Cipher;
import javax.crypto.spec.SecretKeySpec;

/**
 * 禁漫移动端 API 客户端（Java 移植版）。
 *
 * 与 jmcomic 的 api 实现保持一致：
 *   token = md5(ts + secret)，tokenparam = "ts,2.1.12"
 *   响应 data = base64(AES-ECB(json))，key = md5(ts + secret)
 */
public class JmApi {

    private static final String UA = "Mozilla/5.0 (Linux; Android 9; V1938CT Build/PQ3A.190705.11211812; wv) "
            + "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/91.0.4472.114 Safari/537.36";
    private static final String SECRET = "185Hcomic3PAPP7R";
    private static final String APP_VER = "2.1.12";
    private static final String[] API_DOMAINS = {
            "www.cdnhjk.net", "www.cdnutc.cc", "www.cdngwc.net", "www.cdngwc.club"
    };
    private static final String[] IMG_DOMAINS = {
            "cdn-msp.jmapiproxy1.cc", "cdn-msp.jmapiproxy2.cc", "cdn-msp2.jmapiproxy2.cc",
            "cdn-msp3.jmapiproxy2.cc", "cdn-msp.jmapinodeudzn.net", "cdn-msp3.jmapinodeudzn.net"
    };
    private static final int SCRAMBLE_220980 = 220980;
    private static final int TIMEOUT_CONNECT = 15000;
    private static final int TIMEOUT_READ = 40000;

    private final Proxy proxy;
    private final String cookie;
    private final int retries;
    private final Random random = new Random();

    public JmApi(Settings settings) {
        Proxy p = Proxy.NO_PROXY;
        String raw = settings.proxy == null ? "" : settings.proxy.trim();
        if (!raw.isEmpty()) {
            try {
                String host = raw;
                int port = 7890;
                int idx = raw.lastIndexOf(':');
                if (idx > 0) {
                    host = raw.substring(0, idx);
                    port = Integer.parseInt(raw.substring(idx + 1));
                }
                p = new Proxy(Proxy.Type.HTTP, new InetSocketAddress(host, port));
            } catch (Exception ignored) {
                p = Proxy.NO_PROXY;
            }
        }
        this.proxy = p;
        this.cookie = settings.cookie == null ? "" : settings.cookie.trim();
        this.retries = Math.max(1, settings.retries);
    }

    // ------------------------------------------------------------------ //
    // 业务接口
    // ------------------------------------------------------------------ //
    public Map<String, Object> album(String albumId) throws IOException {
        Map<String, Object> data = apiGet("/album", params("id", albumId));
        String seriesId = Json.str(data.get("series_id"), "0");
        String id = Json.str(data.get("id"), albumId);
        if (!seriesId.isEmpty() && !"0".equals(seriesId) && !seriesId.equals(id)) {
            // 传入的是章节号，重定向到所属本子
            return apiGet("/album", params("id", seriesId));
        }
        return data;
    }

    public Map<String, Object> chapter(String photoId) throws IOException {
        return apiGet("/chapter", params("id", photoId));
    }

    /** 章节列表：多章节本子取 series，否则本子自己就是一个章节。 */
    public List<String> photoIds(String albumId, Map<String, Object> album) {
        List<String> ids = new ArrayList<>();
        List<Object> series = Json.list(album.get("series"));
        if (!series.isEmpty()) {
            for (Object item : series) {
                String id = Json.str(Json.obj(item).get("id"), "");
                if (!id.isEmpty()) ids.add(id);
            }
        }
        if (ids.isEmpty()) ids.add(albumId);
        return ids;
    }

    /** 图片分割数所需的 scramble_id（从 chapter_view_template 页面里抓）。 */
    public int scrambleId(String photoId) {
        long ts = now();
        Map<String, String> headers = baseHeaders(ts);
        Map<String, String> query = new LinkedHashMap<>();
        query.put("id", photoId);
        query.put("mode", "vertical");
        query.put("page", "0");
        query.put("app_img_shunt", "1");
        query.put("express", "off");
        query.put("v", String.valueOf(ts));

        for (int attempt = 0; attempt < 2; attempt++) {
            for (String domain : API_DOMAINS) {
                try {
                    byte[] raw = httpGet("https://" + domain + "/chapter_view_template?" + encode(query),
                            headers, TIMEOUT_CONNECT, TIMEOUT_READ);
                    String html = new String(raw, StandardCharsets.UTF_8);
                    java.util.regex.Matcher m = java.util.regex.Pattern
                            .compile("var scramble_id = (\\d+);").matcher(html);
                    if (m.find()) return Integer.parseInt(m.group(1));
                } catch (Exception ignored) {
                    // 换下一个域名
                }
            }
        }
        return SCRAMBLE_220980;
    }

    public byte[] image(String photoId, String filename) throws IOException {
        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("user-agent", UA);
        headers.put("Accept", "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8");
        headers.put("X-Requested-With", "com.JMComic3.app");
        headers.put("Referer", "https://" + API_DOMAINS[0]);
        headers.put("Accept-Language", "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7");

        List<String> domains = new ArrayList<>();
        for (String d : IMG_DOMAINS) domains.add(d);
        java.util.Collections.shuffle(domains, random);

        IOException last = null;
        for (int attempt = 0; attempt < 2; attempt++) {
            for (String domain : domains) {
                String url = "https://" + domain + "/media/photos/" + photoId + "/" + filename;
                try {
                    return httpGet(url, headers, TIMEOUT_CONNECT, TIMEOUT_READ);
                } catch (IOException e) {
                    last = e;
                }
            }
        }
        throw last != null ? last : new IOException("图片下载失败");
    }

    // ------------------------------------------------------------------ //
    // HTTP
    // ------------------------------------------------------------------ //
    private Map<String, Object> apiGet(String path, Map<String, String> query) throws IOException {
        IOException last = null;
        for (int attempt = 0; attempt < Math.min(3, retries); attempt++) {
            long ts = now();
            Map<String, String> headers = baseHeaders(ts);
            for (String domain : API_DOMAINS) {
                String url = "https://" + domain + path + "?" + encode(query);
                try {
                    byte[] raw = httpGet(url, headers, TIMEOUT_CONNECT, TIMEOUT_READ);
                    Map<String, Object> body = Json.parseObject(new String(raw, StandardCharsets.UTF_8));
                    int code = Json.i(body.get("code"), -1);
                    if (code != 200) {
                        throw new IOException("接口返回 code=" + code);
                    }
                    String encrypted = Json.str(body.get("data"), "");
                    if (encrypted.isEmpty()) throw new IOException("响应 data 为空");
                    String json = decrypt(encrypted, ts);
                    return Json.parseObject(json);
                } catch (Exception e) {
                    last = e instanceof IOException ? (IOException) e : new IOException(e);
                }
            }
            try {
                Thread.sleep(600);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            }
        }
        throw last != null ? last : new IOException("请求失败");
    }

    private Map<String, String> baseHeaders(long ts) {
        Map<String, String> headers = new LinkedHashMap<>();
        headers.put("user-agent", UA);
        headers.put("token", md5(ts + SECRET));
        headers.put("tokenparam", ts + "," + APP_VER);
        if (!cookie.isEmpty()) headers.put("Cookie", "AVS=" + cookie);
        return headers;
    }

    private byte[] httpGet(String url, Map<String, String> headers, int connectTimeout, int readTimeout)
            throws IOException {
        HttpURLConnection conn = null;
        try {
            conn = (HttpURLConnection) new URL(url).openConnection(proxy);
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(connectTimeout);
            conn.setReadTimeout(readTimeout);
            conn.setInstanceFollowRedirects(true);
            for (Map.Entry<String, String> e : headers.entrySet()) {
                conn.setRequestProperty(e.getKey(), e.getValue());
            }
            int code = conn.getResponseCode();
            InputStream in = code >= 400 ? conn.getErrorStream() : conn.getInputStream();
            if (in == null) throw new IOException("HTTP " + code);
            String encoding = conn.getContentEncoding();
            if (encoding != null && encoding.toLowerCase().contains("gzip")) {
                in = new GZIPInputStream(in);
            }
            byte[] data = readAll(in);
            in.close();
            if (code >= 400) throw new IOException("HTTP " + code + " len=" + data.length);
            return data;
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

    private static byte[] readAll(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[16384];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        return out.toByteArray();
    }

    // ------------------------------------------------------------------ //
    // 工具
    // ------------------------------------------------------------------ //
    private static long now() {
        return System.currentTimeMillis() / 1000L;
    }

    private static Map<String, String> params(String key, String value) {
        Map<String, String> m = new LinkedHashMap<>();
        m.put(key, value);
        return m;
    }

    private static String encode(Map<String, String> query) {
        StringBuilder sb = new StringBuilder();
        for (Map.Entry<String, String> e : query.entrySet()) {
            if (sb.length() > 0) sb.append('&');
            try {
                sb.append(URLEncoder.encode(e.getKey(), "UTF-8"))
                        .append('=')
                        .append(URLEncoder.encode(e.getValue(), "UTF-8"));
            } catch (Exception ignored) {
            }
        }
        return sb.toString();
    }

    public static String md5(String text) {
        try {
            MessageDigest md = MessageDigest.getInstance("MD5");
            byte[] digest = md.digest(text.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : digest) sb.append(String.format("%02x", b));
            return sb.toString();
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }

    private static String decrypt(String encrypted, long ts) throws Exception {
        byte[] data = Base64.getDecoder().decode(encrypted);
        byte[] key = md5(ts + SECRET).getBytes(StandardCharsets.UTF_8);
        Cipher cipher = Cipher.getInstance("AES/ECB/NoPadding");
        cipher.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"));
        byte[] plain = cipher.doFinal(data);
        int pad = plain[plain.length - 1] & 0xFF;
        if (pad <= 0 || pad > 16) pad = 0;
        return new String(plain, 0, plain.length - pad, StandardCharsets.UTF_8);
    }
}
