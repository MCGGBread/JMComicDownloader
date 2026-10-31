package com.jmcomic.app;

import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import android.util.Log;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

/** 全局任务引擎：队列、持久化、下载线程、历史记录。 */
public class Engine {

    private static final String TAG = "JmEngine";
    private static Engine INSTANCE;

    public interface Listener {
        void onEvent(String json);
    }

    public interface ServiceBridge {
        void update(String text, int percent);

        void finish();
    }

    public static class Task {
        public String id = "";
        public String title = "";
        public String status = "等待";
        public String detail = "";
        public double progress = 0;
        public int pages = 0;
        public String uri = "";
        public String time = "";

        Map<String, Object> toJson() {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", id);
            m.put("title", title);
            m.put("status", status);
            m.put("detail", detail);
            m.put("progress", progress);
            m.put("pages", pages);
            m.put("uri", uri);
            m.put("time", time);
            return m;
        }

        static Task fromJson(Map<String, Object> m) {
            Task t = new Task();
            t.id = Json.str(m.get("id"), "");
            t.title = Json.str(m.get("title"), "");
            t.status = Json.str(m.get("status"), "等待");
            t.detail = Json.str(m.get("detail"), "");
            t.progress = m.get("progress") instanceof Number
                    ? ((Number) m.get("progress")).doubleValue() : 0;
            t.pages = Json.i(m.get("pages"), 0);
            t.uri = Json.str(m.get("uri"), "");
            t.time = Json.str(m.get("time"), "");
            return t;
        }
    }

    private static final Set<String> ACTIVE = new LinkedHashSet<>(java.util.Arrays.asList(
            "等待", "准备", "解析", "下载中", "打包 ZIP", "生成 PDF"));
    private static final Set<String> TERMINAL = new LinkedHashSet<>(java.util.Arrays.asList(
            "完成", "失败", "跳过", "已取消"));

    private final Context app;
    private Settings settings;
    private final LinkedHashMap<String, Task> tasks = new LinkedHashMap<>();
    private final LinkedHashMap<String, Map<String, Object>> history = new LinkedHashMap<>();
    private final LinkedBlockingQueue<String> pending = new LinkedBlockingQueue<>();
    private final Set<String> pendingSet = new HashSet<>();
    private final List<Listener> listeners = new CopyOnWriteArrayList<>();
    private final Handler main = new Handler(Looper.getMainLooper());

    private volatile boolean running = false;
    private volatile boolean stopRequested = false;
    private volatile String runningId = null;
    private volatile ServiceBridge bridge;
    private Thread worker;

    private Engine(Context context) {
        this.app = context.getApplicationContext();
        this.settings = loadSettings();
        loadHistory();
        loadQueue();
    }

    public static synchronized Engine get(Context context) {
        if (INSTANCE == null) INSTANCE = new Engine(context);
        return INSTANCE;
    }

    // ------------------------------------------------------------------ //
    // 对外接口
    // ------------------------------------------------------------------ //
    public void addListener(Listener listener) {
        if (listener != null && !listeners.contains(listener)) listeners.add(listener);
    }

    public void removeListener(Listener listener) {
        listeners.remove(listener);
    }

    public void setBridge(ServiceBridge bridge) {
        this.bridge = bridge;
    }

    public Settings settings() {
        return settings;
    }

    public boolean isRunning() {
        return running;
    }

    public List<String> parsePreview(String text) {
        return JmParser.parseIds(text);
    }

    public synchronized String submit(String text) {
        List<String> ids = JmParser.parseIds(text);
        Map<String, Object> result = new LinkedHashMap<>();
        int added = 0;
        int duplicate = 0;

        if (ids.isEmpty()) {
            result.put("added", 0);
            result.put("duplicate", 0);
            result.put("error", "没有识别到有效番号");
            return Json.stringify(result);
        }
        if (running && stopRequested) {
            result.put("added", 0);
            result.put("duplicate", 0);
            result.put("error", "正在停止，请稍候再添加");
            return Json.stringify(result);
        }

        boolean starting = !running && pending.isEmpty();
        if (starting) {
            tasks.clear();
            pending.clear();
            pendingSet.clear();
        }

        for (String id : ids) {
            Task existing = tasks.get(id);
            if (existing != null) {
                if (!"失败".equals(existing.status) && !"已取消".equals(existing.status)) {
                    duplicate++;
                    continue;
                }
            }
            Task task = new Task();
            task.id = id;
            task.status = "等待";
            tasks.put(id, task);
            pending.offer(id);
            pendingSet.add(id);
            added++;
        }

        saveQueue();
        emitState();
        if (added > 0) {
            startService();
            startWorker();
        }
        result.put("added", added);
        result.put("duplicate", duplicate);
        result.put("error", "");
        return Json.stringify(result);
    }

    public void maybeAutoResume(Context context) {
        if (!settings.autoResume) return;
        if (running || pending.isEmpty()) return;
        startService();
        startWorker();
    }

    public synchronized void stop() {
        stopRequested = true;
        pending.clear();
        pendingSet.clear();
        for (Task task : tasks.values()) {
            if ("等待".equals(task.status)) {
                task.status = "已取消";
                task.detail = "未开始";
                task.progress = 0;
            }
        }
        saveQueue();
        emitState();
    }

    public synchronized void clearTasks() {
        if (running) return;
        tasks.clear();
        pending.clear();
        pendingSet.clear();
        saveQueue();
        emitState();
    }

    public synchronized String saveSettings(String json) {
        try {
            settings = Settings.fromJson(Json.parseObject(json));
            writeFile(new File(app.getFilesDir(), "settings.json"),
                    Json.stringify(settings.toJson()));
            return Json.stringify(settings.toJson());
        } catch (Exception e) {
            return "{}";
        }
    }

    public synchronized String snapshotJson() {
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("running", running);
        root.put("total", tasks.size());
        root.put("done", doneCount());
        root.put("settings", settings.toJson());
        List<Object> list = new ArrayList<>();
        for (Task t : tasks.values()) list.add(t.toJson());
        root.put("tasks", list);
        root.put("historyCount", history.size());
        root.put("storage", storagePath());
        return Json.stringify(root);
    }

    public synchronized String historyJson() {
        List<Object> list = new ArrayList<>();
        List<Map<String, Object>> values = new ArrayList<>(history.values());
        values.sort((a, b) -> Json.str(b.get("time"), "").compareTo(Json.str(a.get("time"), "")));
        for (Map<String, Object> item : values) list.add(item);
        return Json.stringify(list);
    }

    public synchronized void removeHistory(String id) {
        history.remove(id);
        saveHistory();
        emitState();
    }

    public synchronized void clearHistory() {
        history.clear();
        saveHistory();
        emitState();
    }

    public synchronized String taskUri(String id) {
        Task task = tasks.get(id);
        if (task != null && !task.uri.isEmpty()) return task.uri;
        Map<String, Object> record = history.get(id);
        return record == null ? "" : Json.str(record.get("uri"), "");
    }

    public String storagePath() {
        File dir = app.getExternalFilesDir(null);
        return dir == null ? app.getFilesDir().getAbsolutePath() : dir.getAbsolutePath();
    }

    // ------------------------------------------------------------------ //
    // 队列执行
    // ------------------------------------------------------------------ //
    private void startService() {
        try {
            Intent intent = new Intent(app, DownloadService.class);
            app.startForegroundService(intent);
        } catch (Exception e) {
            Log.w(TAG, "启动前台服务失败: " + e);
        }
    }

    public synchronized void startWorker() {
        if (running || pending.isEmpty()) return;
        stopRequested = false;
        running = true;
        emitState();
        worker = new Thread(this::loop, "jm-worker");
        worker.start();
    }

    private void loop() {
        int ok = 0;
        int fail = 0;
        int skip = 0;
        long started = System.currentTimeMillis();
        Downloader.ImageCodec codec = new AndroidCodec();

        while (!stopRequested) {
            String id;
            try {
                id = pending.poll(1200, TimeUnit.MILLISECONDS);
            } catch (InterruptedException e) {
                break;
            }
            if (id == null) break;
            pendingSet.remove(id);

            Task task = tasks.get(id);
            if (task == null) continue;
            runningId = id;

            if (settings.skipCrawled && history.containsKey(id)) {
                task.status = "跳过";
                task.detail = "历史已存在";
                task.progress = 1;
                skip++;
                emitTask(task);
                saveQueue();
                runningId = null;
                continue;
            }

            task.status = "准备";
            task.progress = 0.01;
            task.detail = "";
            emitTask(task);
            saveQueue();

            File workDir = new File(app.getCacheDir(), "JM" + id);
            File pdfFile = new File(app.getCacheDir(), "JM" + id + ".pdf");
            Downloader downloader = new Downloader(settings, codec);
            long taskStarted = System.currentTimeMillis();

            try {
                Downloader.Result result = downloader.run(id, workDir, pdfFile, new Downloader.Events() {
                    @Override
                    public void title(String title) {
                        task.title = title;
                        emitTask(task);
                    }

                    @Override
                    public void status(String status, double progress, String detail) {
                        task.status = status;
                        task.progress = progress;
                        task.detail = detail;
                        emitTask(task);
                        updateBridge();
                    }

                    @Override
                    public void log(String level, String msg) {
                        emitLog(level, msg);
                    }

                    @Override
                    public boolean cancelled() {
                        return stopRequested;
                    }
                });

                String name = Downloader.safeName(
                        settings.filenameTemplate.replace("{id}", id)
                                .replace("{title}", result.title)
                                .replace("{pages}", String.valueOf(result.pages)));
                if (name.isEmpty()) name = "JM" + id;

                String uri = publishPdf(pdfFile, name);
                task.title = result.title;
                task.pages = result.pages;
                task.uri = uri;
                task.status = "完成";
                task.progress = 1;
                task.detail = result.pages + " 页";
                task.time = now();
                ok++;

                Map<String, Object> record = new LinkedHashMap<>();
                record.put("jm_id", id);
                record.put("title", result.title);
                record.put("pages", result.pages);
                record.put("time", task.time);
                record.put("uri", uri);
                record.put("name", name + ".pdf");
                record.put("duration", (System.currentTimeMillis() - taskStarted) / 1000);
                history.put(id, record);
                saveHistory();
                emitLog("ok", "JM" + id + " 完成：" + result.pages + " 页");
            } catch (Downloader.CancelledException e) {
                task.status = "已取消";
                task.detail = "用户停止";
                emitTask(task);
                runningId = null;
                saveQueue();
                break;
            } catch (Exception e) {
                fail++;
                task.status = "失败";
                task.progress = 1;
                task.detail = shortError(e);
                emitLog("error", "JM" + id + " 失败：" + task.detail);
            } finally {
                runningId = null;
                Downloader.deleteRecursive(workDir);
                //noinspection ResultOfMethodCallIgnored
                pdfFile.delete();
                emitTask(task);
                saveQueue();
                emitState();
                updateBridge();
            }
        }

        running = false;
        emitState();
        emitLog("info", String.format(Locale.CHINA,
                "任务结束：成功 %d｜失败 %d｜跳过 %d｜耗时 %ds",
                ok, fail, skip, (System.currentTimeMillis() - started) / 1000));
        saveQueue();
        ServiceBridge b = bridge;
        if (b != null) b.finish();
    }

    private static String shortError(Exception e) {
        String msg = e.getMessage();
        if (msg == null || msg.isEmpty()) msg = e.getClass().getSimpleName();
        return msg.length() > 120 ? msg.substring(0, 120) : msg;
    }

    // ------------------------------------------------------------------ //
    // PDF 发布到「下载/JMComic」
    // ------------------------------------------------------------------ //
    private String publishPdf(File source, String name) throws IOException {
        ContentValues values = new ContentValues();
        values.put(MediaStore.MediaColumns.DISPLAY_NAME, name + ".pdf");
        values.put(MediaStore.MediaColumns.MIME_TYPE, "application/pdf");
        values.put(MediaStore.MediaColumns.RELATIVE_PATH,
                Environment.DIRECTORY_DOWNLOADS + "/JMComic");
        Uri uri = app.getContentResolver()
                .insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
        if (uri == null) throw new IOException("无法写入下载目录");
        try (OutputStream out = app.getContentResolver().openOutputStream(uri)) {
            if (out == null) throw new IOException("无法打开输出流");
            Files.copy(source.toPath(), out);
        }
        //noinspection ResultOfMethodCallIgnored
        source.delete();
        return uri.toString();
    }

    // ------------------------------------------------------------------ //
    // 事件
    // ------------------------------------------------------------------ //
    private void emitTask(Task task) {
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("type", "task");
        event.put("task", task.toJson());
        emit(event);
    }

    private void emitState() {
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("type", "state");
        event.put("running", running);
        event.put("total", tasks.size());
        event.put("done", doneCount());
        emit(event);
    }

    private void emitLog(String level, String msg) {
        Map<String, Object> event = new LinkedHashMap<>();
        event.put("type", "log");
        event.put("level", level);
        event.put("msg", msg);
        emit(event);
    }

    private void emit(Map<String, Object> event) {
        String json = Json.stringify(event);
        main.post(() -> {
            for (Listener listener : listeners) {
                try {
                    listener.onEvent(json);
                } catch (Exception ignored) {
                }
            }
        });
    }

    private void updateBridge() {
        ServiceBridge b = bridge;
        if (b == null) return;
        String id = runningId;
        Task task = id == null ? null : tasks.get(id);
        if (task == null) {
            b.update("准备下载…", 0);
            return;
        }
        int percent = (int) Math.round(task.progress * 100);
        b.update("JM" + task.id + " · " + task.status + " " + task.detail, percent);
    }

    private int doneCount() {
        int done = 0;
        for (Task task : tasks.values()) {
            if (TERMINAL.contains(task.status)) done++;
        }
        return done;
    }

    // ------------------------------------------------------------------ //
    // 持久化
    // ------------------------------------------------------------------ //
    private Settings loadSettings() {
        File file = new File(app.getFilesDir(), "settings.json");
        if (!file.isFile()) return new Settings();
        try {
            return Settings.fromJson(Json.parseObject(readFile(file)));
        } catch (Exception e) {
            return new Settings();
        }
    }

    private void loadQueue() {
        File file = new File(app.getFilesDir(), "queue.json");
        if (!file.isFile()) return;
        try {
            Map<String, Object> root = Json.parseObject(readFile(file));
            for (Object item : Json.list(root.get("tasks"))) {
                Task task = Task.fromJson(Json.obj(item));
                if (task.id.isEmpty()) continue;
                if (ACTIVE.contains(task.status)) {
                    task.status = "等待";
                    task.detail = "";
                    task.progress = 0;
                }
                tasks.put(task.id, task);
                if ("等待".equals(task.status)) {
                    pending.offer(task.id);
                    pendingSet.add(task.id);
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "读取队列失败: " + e);
        }
    }

    private synchronized void saveQueue() {
        List<Object> list = new ArrayList<>();
        for (Task task : tasks.values()) list.add(task.toJson());
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("version", 1);
        root.put("updated", now());
        root.put("tasks", list);
        try {
            writeFile(new File(app.getFilesDir(), "queue.json"), Json.stringify(root));
        } catch (IOException e) {
            Log.w(TAG, "保存队列失败: " + e);
        }
    }

    private void loadHistory() {
        File file = new File(app.getFilesDir(), "history.json");
        if (!file.isFile()) return;
        try {
            Map<String, Object> root = Json.parseObject(readFile(file));
            for (Object item : Json.list(root.get("albums"))) {
                Map<String, Object> record = Json.obj(item);
                String id = Json.str(record.get("jm_id"), "");
                if (!id.isEmpty()) history.put(id, record);
            }
        } catch (Exception e) {
            Log.w(TAG, "读取历史失败: " + e);
        }
    }

    private synchronized void saveHistory() {
        List<Object> list = new ArrayList<>(history.values());
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("version", 1);
        root.put("albums", list);
        try {
            writeFile(new File(app.getFilesDir(), "history.json"), Json.stringify(root));
        } catch (IOException e) {
            Log.w(TAG, "保存历史失败: " + e);
        }
    }

    private static String readFile(File file) throws IOException {
        return new String(Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8);
    }

    private static void writeFile(File file, String text) throws IOException {
        File parent = file.getParentFile();
        if (parent != null) parent.mkdirs();
        try (FileOutputStream out = new FileOutputStream(file)) {
            out.write(text.getBytes(StandardCharsets.UTF_8));
        }
    }

    private static String now() {
        return new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.CHINA).format(new Date());
    }
}
