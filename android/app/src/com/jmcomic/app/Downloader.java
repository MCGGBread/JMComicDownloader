package com.jmcomic.app;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

/** 单个番号的完整流程：取详情 → 下载图片 → 还原 → 合成 PDF（可选打包 ZIP）。 */
public class Downloader {

    public interface ImageCodec {
        byte[] toJpeg(byte[] raw, int num, int quality, int maxWidth) throws Exception;
    }

    public interface Events {
        void title(String title);

        void status(String status, double progress, String detail);

        void log(String level, String msg);

        boolean cancelled();
    }

    public static class Result {
        public String title = "";
        public int pages = 0;
        public File pdf;
        public File zip;
        public String error;
    }

    private final JmApi api;
    private final Settings settings;
    private final ImageCodec codec;

    public Downloader(Settings settings, ImageCodec codec) {
        this.settings = settings;
        this.codec = codec;
        this.api = new JmApi(settings);
    }

    public Result run(String jmId, File workDir, File pdfFile, Events events) throws Exception {
        Result result = new Result();

        events.status("解析", 0.01, "获取本子信息");
        Map<String, Object> album = api.album(jmId);
        String title = Json.str(album.get("name"), "JM" + jmId);
        result.title = title;
        events.title(title);

        List<String> photos = api.photoIds(jmId, album);

        List<String[]> images = new ArrayList<>(); // {photoId, filename, num}
        int total = 0;
        for (String pid : photos) {
            if (events.cancelled()) throw new CancelledException();
            events.status("解析", 0.02, "获取章节 " + pid);
            Map<String, Object> chapter = api.chapter(pid);
            int scramble = api.scrambleId(pid);
            List<Object> files = Json.list(chapter.get("images"));
            for (Object item : files) {
                String filename = Json.str(item, "");
                if (filename.isEmpty()) continue;
                // 注意：分割数用「不含扩展名」的文件名计算（与官方库 img_file_name 一致）
                int num = JmImage.decodeNum(scramble, parseInt(pid), stripExtension(filename));
                images.add(new String[]{pid, filename, String.valueOf(num)});
                total++;
            }
        }
        if (total == 0) throw new IOException("没有可下载的图片");

        File imagesDir = new File(workDir, "images");
        deleteRecursive(imagesDir);
        if (!imagesDir.mkdirs() && !imagesDir.isDirectory()) {
            throw new IOException("无法创建临时目录");
        }

        // 1) 并发下载到临时文件（顺序由文件名保证）
        downloadAll(images, imagesDir, total, events);

        // 2) 顺序合成 PDF
        events.status("生成 PDF", 0.94, "写入文件");
        PdfWriter writer = new PdfWriter(pdfFile);
        int done = 0;
        try {
            for (int i = 0; i < images.size(); i++) {
                if (events.cancelled()) throw new CancelledException();
                File file = new File(imagesDir, String.format("%05d.jpg", i + 1));
                byte[] jpeg = java.nio.file.Files.readAllBytes(file.toPath());
                int[] size = PdfWriter.jpegSize(jpeg);
                if (size == null) throw new IOException("图片解码失败：" + file.getName());
                writer.addPage(jpeg, size[0], size[1], size[2]);
                done++;
                if (done % 10 == 0 || done == images.size()) {
                    events.status("生成 PDF", 0.94 + 0.04 * done / images.size(),
                            done + "/" + images.size() + " 页");
                }
            }
            result.pages = writer.finish("JM" + jmId + " " + title);
        } catch (Exception e) {
            writer.close();
            throw e;
        }

        result.pdf = pdfFile;

        if (settings.keepZip) {
            events.status("打包 ZIP", 0.98, "");
            File zipFile = new File(workDir, safeName(filenameFor(jmId, title, result.pages)) + ".zip");
            zip(imagesDir, zipFile, jmId, title, result.pages);
            result.zip = zipFile;
        }

        if (!settings.keepImages) {
            deleteRecursive(imagesDir);
        }
        return result;
    }

    /** 并发下载所有图片，落到 imagesDir/%05d.jpg。 */
    private void downloadAll(List<String[]> images, File imagesDir, int total,
                             Events events) throws Exception {
        int threads = Math.max(1, Math.min(8, settings.threadsImage));
        java.util.concurrent.ExecutorService pool =
                java.util.concurrent.Executors.newFixedThreadPool(threads);
        java.util.concurrent.atomic.AtomicInteger done =
                new java.util.concurrent.atomic.AtomicInteger(0);
        java.util.concurrent.atomic.AtomicReference<Exception> firstError =
                new java.util.concurrent.atomic.AtomicReference<>();
        int step = Math.max(1, total / 40);

        for (int i = 0; i < images.size(); i++) {
            final int index = i;
            final String[] image = images.get(i);
            pool.submit(() -> {
                if (events.cancelled() || firstError.get() != null) return;
                try {
                    byte[] raw = api.image(image[0], image[1]);
                    byte[] jpeg = codec.toJpeg(raw, Integer.parseInt(image[2]),
                            settings.pdfQuality, settings.pdfMaxWidth);
                    if (PdfWriter.jpegSize(jpeg) == null) {
                        throw new IOException("图片解码失败：" + image[1]);
                    }
                    File file = new File(imagesDir, String.format("%05d.jpg", index + 1));
                    try (FileOutputStream fos = new FileOutputStream(file)) {
                        fos.write(jpeg);
                    }
                    int current = done.incrementAndGet();
                    if (current % step == 0 || current == total) {
                        events.status("下载中", 0.05 + 0.85 * current / total,
                                current + "/" + total + " 页");
                    }
                } catch (Exception e) {
                    firstError.compareAndSet(null, e);
                }
            });
        }

        pool.shutdown();
        while (!pool.awaitTermination(300, java.util.concurrent.TimeUnit.MILLISECONDS)) {
            if (events.cancelled()) {
                pool.shutdownNow();
                throw new CancelledException();
            }
        }
        if (firstError.get() != null) throw firstError.get();
        if (events.cancelled()) throw new CancelledException();
        if (done.get() < total) throw new IOException("部分图片下载失败");
    }

    private String filenameFor(String jmId, String title, int pages) {
        String template = settings.filenameTemplate;
        String name = template
                .replace("{id}", jmId)
                .replace("{title}", title == null ? "" : title)
                .replace("{pages}", String.valueOf(pages))
                .replace("{author}", "");
        name = safeName(name);
        return name.isEmpty() ? "JM" + jmId : name;
    }

    public static String safeName(String raw) {
        if (raw == null) return "";
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < raw.length(); i++) {
            char c = raw.charAt(i);
            if ("<>:\"/\\|?*".indexOf(c) >= 0 || c < 0x20) {
                sb.append(' ');
            } else {
                sb.append(c);
            }
        }
        String text = sb.toString().replaceAll("\\s+", " ").trim();
        while (text.endsWith(".")) text = text.substring(0, text.length() - 1).trim();
        if (text.length() > 80) text = text.substring(0, 80).trim();
        return text;
    }

    private void zip(File imagesDir, File zipFile, String jmId, String title, int pages) throws IOException {
        File parent = zipFile.getParentFile();
        if (parent != null) parent.mkdirs();
        try (ZipOutputStream zos = new ZipOutputStream(new FileOutputStream(zipFile))) {
            File[] files = imagesDir.listFiles();
            if (files != null) {
                java.util.Arrays.sort(files);
                for (File f : files) {
                    if (!f.isFile()) continue;
                    zos.putNextEntry(new ZipEntry(f.getName()));
                    java.io.FileInputStream fis = new java.io.FileInputStream(f);
                    byte[] buf = new byte[16384];
                    int n;
                    while ((n = fis.read(buf)) > 0) zos.write(buf, 0, n);
                    fis.close();
                    zos.closeEntry();
                }
            }
            String info = "{\"jm_id\":\"" + jmId + "\",\"title\":" + Json.quote(title)
                    + ",\"pages\":" + pages + "}";
            zos.putNextEntry(new ZipEntry("_info.json"));
            zos.write(info.getBytes(StandardCharsets.UTF_8));
            zos.closeEntry();
        }
    }

    /** 00001.webp -> 00001（官方库用的是不带后缀的文件名） */
    private static String stripExtension(String filename) {
        int dot = filename.lastIndexOf('.');
        return dot > 0 ? filename.substring(0, dot) : filename;
    }

    private static int parseInt(String text) {
        try {
            return Integer.parseInt(text);
        } catch (Exception e) {
            return 0;
        }
    }

    public static void deleteRecursive(File file) {
        if (file == null || !file.exists()) return;
        File[] children = file.listFiles();
        if (children != null) {
            for (File child : children) deleteRecursive(child);
        }
        //noinspection ResultOfMethodCallIgnored
        file.delete();
    }

    public static class CancelledException extends IOException {
        public CancelledException() {
            super("已取消");
        }
    }
}
