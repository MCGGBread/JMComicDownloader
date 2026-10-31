package com.jmcomic.app;

import java.util.LinkedHashMap;
import java.util.Map;

/** 用户设置（与桌面版字段尽量对齐）。 */
public class Settings {
    public int threadsImage = 8;
    public int threadsPhoto = 4;
    public int retries = 5;
    public String proxy = "";          // host:port，留空为直连
    public String cookie = "";         // AVS
    public boolean keepImages = false;
    public boolean keepZip = false;
    public boolean autoResume = true;
    public boolean skipCrawled = false;
    public int pdfQuality = 90;
    public int pdfMaxWidth = 0;
    public String filenameTemplate = "JM{id} {title}";

    public static Settings fromJson(Map<String, Object> m) {
        Settings s = new Settings();
        if (m == null) return s;
        s.threadsImage = clamp(Json.i(m.get("threadsImage"), 8), 1, 8);
        s.threadsPhoto = clamp(Json.i(m.get("threadsPhoto"), 4), 1, 8);
        s.retries = clamp(Json.i(m.get("retries"), 5), 0, 20);
        s.proxy = Json.str(m.get("proxy"), "").trim();
        s.cookie = Json.str(m.get("cookie"), "").trim();
        s.keepImages = Json.b(m.get("keepImages"), false);
        s.keepZip = Json.b(m.get("keepZip"), false);
        s.autoResume = Json.b(m.get("autoResume"), true);
        s.skipCrawled = Json.b(m.get("skipCrawled"), false);
        s.pdfQuality = clamp(Json.i(m.get("pdfQuality"), 90), 50, 100);
        s.pdfMaxWidth = clamp(Json.i(m.get("pdfMaxWidth"), 0), 0, 4000);
        String tpl = Json.str(m.get("filenameTemplate"), "JM{id} {title}").trim();
        s.filenameTemplate = tpl.isEmpty() ? "JM{id} {title}" : tpl;
        return s;
    }

    public Map<String, Object> toJson() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("threadsImage", threadsImage);
        m.put("threadsPhoto", threadsPhoto);
        m.put("retries", retries);
        m.put("proxy", proxy);
        m.put("cookie", cookie);
        m.put("keepImages", keepImages);
        m.put("keepZip", keepZip);
        m.put("autoResume", autoResume);
        m.put("skipCrawled", skipCrawled);
        m.put("pdfQuality", pdfQuality);
        m.put("pdfMaxWidth", pdfMaxWidth);
        m.put("filenameTemplate", filenameTemplate);
        return m;
    }

    private static int clamp(int v, int lo, int hi) {
        return Math.max(lo, Math.min(hi, v));
    }
}
