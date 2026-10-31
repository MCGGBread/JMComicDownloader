package com.jmcomic.app;

import android.webkit.JavascriptInterface;

/** 暴露给网页的接口。注意：这些方法运行在 WebView 的 JS 线程，不能直接碰 UI。 */
public class Bridge {

    private final MainActivity activity;

    public Bridge(MainActivity activity) {
        this.activity = activity;
    }

    @JavascriptInterface
    public String snapshot() {
        return Engine.get(activity).snapshotJson();
    }

    @JavascriptInterface
    public String preview(String text) {
        return Json.stringify(Engine.get(activity).parsePreview(text));
    }

    @JavascriptInterface
    public String submit(String text) {
        return Engine.get(activity).submit(text);
    }

    @JavascriptInterface
    public void stop() {
        Engine.get(activity).stop();
    }

    @JavascriptInterface
    public void clearTasks() {
        Engine.get(activity).clearTasks();
    }

    @JavascriptInterface
    public String saveSettings(String json) {
        return Engine.get(activity).saveSettings(json);
    }

    @JavascriptInterface
    public String history() {
        return Engine.get(activity).historyJson();
    }

    @JavascriptInterface
    public void removeHistory(String id) {
        Engine.get(activity).removeHistory(id);
    }

    @JavascriptInterface
    public void clearHistory() {
        Engine.get(activity).clearHistory();
    }

    @JavascriptInterface
    public void openPdf(String id) {
        activity.openPdf(id);
    }

    @JavascriptInterface
    public String storagePath() {
        return Engine.get(activity).storagePath();
    }

    @JavascriptInterface
    public void toast(String message) {
        activity.toast(message);
    }
}
