import com.jmcomic.app.Downloader;
import com.jmcomic.app.JmImage;
import com.jmcomic.app.JmParser;
import com.jmcomic.app.Json;
import com.jmcomic.app.PdfWriter;
import com.jmcomic.app.Settings;

import javax.imageio.ImageIO;
import java.awt.Graphics2D;
import java.awt.image.BufferedImage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.util.Arrays;
import java.util.List;

/** 桌面端验证：解析规则 + 真实下载 + PDF 生成（不含 Android UI）。 */
public class DesktopMain {

    // 仅桌面测试用：JDK 不支持 WebP，借 Pillow 转一次；Android 上由 BitmapFactory 直接解码
    static final String PY = System.getenv().getOrDefault("JM_PY", "python");

    static BufferedImage decodeAny(byte[] raw) throws Exception {
        BufferedImage img = ImageIO.read(new ByteArrayInputStream(raw));
        if (img != null) return img;
        File in = File.createTempFile("jmimg", ".webp");
        File out = File.createTempFile("jmimg", ".png");
        java.nio.file.Files.write(in.toPath(), raw);
        Process p = new ProcessBuilder(PY, "-c",
                "from PIL import Image;import sys;Image.open(sys.argv[1]).convert('RGB').save(sys.argv[2])",
                in.getAbsolutePath(), out.getAbsolutePath()).redirectErrorStream(true).start();
        p.waitFor();
        img = ImageIO.read(out);
        in.delete();
        out.delete();
        return img;
    }

    static class DesktopCodec implements Downloader.ImageCodec {
        @Override
        public byte[] toJpeg(byte[] raw, int num, int quality, int maxWidth) throws Exception {
            BufferedImage src = decodeAny(raw);
            if (src == null) throw new java.io.IOException("图片解码失败");
            int w = src.getWidth();
            int h = src.getHeight();
            BufferedImage out = new BufferedImage(w, h, BufferedImage.TYPE_INT_RGB);
            Graphics2D g = out.createGraphics();
            g.setColor(java.awt.Color.WHITE);
            g.fillRect(0, 0, w, h);
            if (num > 0) {
                for (int[] band : JmImage.plan(h, num)) {
                    g.drawImage(src, 0, band[1], w, band[1] + band[2],
                            0, band[0], w, band[0] + band[2], null);
                }
            } else {
                g.drawImage(src, 0, 0, null);
            }
            g.dispose();

            if (maxWidth > 0 && w > maxWidth) {
                int nh = Math.max(1, Math.round(h * (float) maxWidth / w));
                BufferedImage scaled = new BufferedImage(maxWidth, nh, BufferedImage.TYPE_INT_RGB);
                Graphics2D g2 = scaled.createGraphics();
                g2.setRenderingHint(java.awt.RenderingHints.KEY_INTERPOLATION,
                        java.awt.RenderingHints.VALUE_INTERPOLATION_BILINEAR);
                g2.drawImage(out, 0, 0, maxWidth, nh, null);
                g2.dispose();
                out = scaled;
            }
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            ImageIO.write(out, "jpg", bos);
            return bos.toByteArray();
        }
    }

    static void check(List<String> got, String[] expected, String input) {
        boolean ok = got.size() == expected.length;
        if (ok) {
            for (int i = 0; i < expected.length; i++) {
                if (!expected[i].equals(got.get(i))) ok = false;
            }
        }
        System.out.println((ok ? "[ OK ] " : "[FAIL] ") + input + " -> " + got
                + (ok ? "" : " 期望 " + Arrays.toString(expected)));
        if (!ok) failures++;
    }

    static int failures = 0;

    public static void main(String[] args) throws Exception {
        System.out.println("== 解析测试 ==");
        check(JmParser.parseIds("jm54747电梯（极品）"), new String[]{"54747"}, "jm54747电梯（极品）");
        check(JmParser.parseIds("142176(母子大车)404477(长篇大车，经典作品)404098(狐娘)431896(熟女)"),
                new String[]{"142176", "404477", "404098", "431896"}, "括号连写");
        check(JmParser.parseIds("h540931(瞬)-h499835(幼瞬)✔️"),
                new String[]{"540931", "499835"}, "h 前缀");
        check(JmParser.parseIds("500703(柚子)-h559091(柚子)"),
                new String[]{"500703", "559091"}, "混合前缀");
        check(JmParser.parseIds("【格黑娜】22\n【千年】36"), new String[]{}, "分类标题");
        check(JmParser.parseIds("2024-10-26 10:30 版本2.5.36 (C88)"), new String[]{}, "噪声");
        check(JmParser.parseIds("https://18comic.vip/album/54747/"), new String[]{"54747"}, "URL");
        check(JmParser.parseIds("47228，118983，152470"), new String[]{"47228", "118983", "152470"}, "批量");

        System.out.println("== 分割数测试 ==");
        int n1 = JmImage.decodeNum(220980, 1233916, "00001");
        int n2 = JmImage.decodeNum(220980, 1233916, "00001.webp");
        System.out.println("num(00001)=" + n1 + " (应为 16) " + (n1 == 16 ? "[ OK ]" : "[FAIL]"));
        System.out.println("num(00001.webp)=" + n2 + "（带后缀会算错，仅作对照）");
        if (n1 != 16) failures++;

        System.out.println("== 还原分块测试 ==");
        int[][] plan = JmImage.plan(1000, 10);
        System.out.println("plan(1000,10) = " + Arrays.deepToString(plan));
        int covered = 0;
        for (int[] band : plan) covered += band[2];
        System.out.println("覆盖高度 " + covered + (covered == 1000 ? " [ OK ]" : " [FAIL]"));

        if (args.length > 0 && "single".equals(args[0])) {
            String id = args[1];
            int count = args.length > 2 ? Integer.parseInt(args[2]) : 3;
            com.jmcomic.app.JmApi api = new com.jmcomic.app.JmApi(new Settings());
            java.util.Map<String, Object> album = api.album(id);
            java.util.List<String> pids = api.photoIds(id, album);
            String pid = pids.get(0);
            java.util.Map<String, Object> chapter = api.chapter(pid);
            int scramble = api.scrambleId(pid);
            java.util.List<Object> images = Json.list(chapter.get("images"));
            File outDir = new File("build/testout");
            outDir.mkdirs();
            System.out.println("album=" + id + " pid=" + pid + " scramble=" + scramble);
            for (int i = 0; i < Math.min(count, images.size()); i++) {
                String filename = Json.str(images.get(i), "");
                int dot = filename.lastIndexOf('.');
                String stem = dot > 0 ? filename.substring(0, dot) : filename;
                int num = JmImage.decodeNum(scramble, Integer.parseInt(pid), stem);
                byte[] raw = api.image(pid, filename);
                byte[] jpeg = new DesktopCodec().toJpeg(raw, num, 95, 0);
                java.nio.file.Files.write(new File(outDir, "single_" + (i + 1) + ".jpg").toPath(), jpeg);
                System.out.println(filename + " stem=" + stem + " num=" + num + " raw=" + raw.length);
            }
        }

        if (args.length > 0 && "download".equals(args[0])) {
            String id = args.length > 1 ? args[1] : "54747";
            System.out.println("== 真实下载 JM" + id + " ==");
            Settings settings = new Settings();
            settings.pdfQuality = 85;
            settings.pdfMaxWidth = 800;
            settings.keepZip = true;

            File dir = new File("build/testout");
            Downloader.deleteRecursive(dir);
            dir.mkdirs();
            File pdf = new File(dir, "JM" + id + ".pdf");

            Downloader downloader = new Downloader(settings, new DesktopCodec());
            long started = System.currentTimeMillis();
            Downloader.Result result = downloader.run(id, new File(dir, "work"), pdf,
                    new Downloader.Events() {
                        @Override
                        public void title(String title) {
                            System.out.println("标题: " + title);
                        }

                        @Override
                        public void status(String status, double progress, String detail) {
                            if (progress < 0.02 || detail.endsWith("/" + detail.split("/")[0]) || Math.random() < 0.08) {
                                System.out.printf("  %s %.0f%% %s%n", status, progress * 100, detail);
                            }
                        }

                        @Override
                        public void log(String level, String msg) {
                        }

                        @Override
                        public boolean cancelled() {
                            return false;
                        }
                    });

            long seconds = (System.currentTimeMillis() - started) / 1000;
            System.out.println("页数: " + result.pages);
            System.out.println("PDF : " + pdf.getAbsolutePath() + " " + pdf.length() / 1024 + " KB");
            System.out.println("ZIP : " + (result.zip == null ? "-" : result.zip.length() / 1024 + " KB"));
            System.out.println("耗时: " + seconds + "s");
            int[] size = PdfWriter.jpegSize(readFirstJpeg(dir));
            System.out.println("首图尺寸: " + (size == null ? "?" : size[0] + "x" + size[1]));
        }

        System.out.println(failures == 0 ? "== 全部通过 ==" : "== 失败 " + failures + " 项 ==");
        System.exit(failures == 0 ? 0 : 1);
    }

    static byte[] readFirstJpeg(File dir) throws Exception {
        File images = new File(dir, "work/images");
        File[] files = images.listFiles();
        if (files == null || files.length == 0) return null;
        Arrays.sort(files);
        return java.nio.file.Files.readAllBytes(files[0].toPath());
    }
}
