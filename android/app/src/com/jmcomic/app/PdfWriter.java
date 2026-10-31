package com.jmcomic.app;

import java.io.BufferedOutputStream;
import java.io.Closeable;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 轻量 PDF 生成：直接把 JPEG 流嵌入（DCTDecode），内存占用低。
 * 与桌面版 app/pdf.py 结构一致。
 */
public class PdfWriter implements Closeable {

    private final OutputStream out;
    private final Map<Integer, Long> offsets = new HashMap<>();
    private final List<Integer> pageIds = new ArrayList<>();
    private long pos = 0;
    private int pages = 0;
    private boolean closed = false;

    public PdfWriter(File file) throws IOException {
        File parent = file.getParentFile();
        if (parent != null) parent.mkdirs();
        this.out = new BufferedOutputStream(new FileOutputStream(file), 1 << 16);
        write("%PDF-1.4\n".getBytes(StandardCharsets.US_ASCII));
        write(new byte[]{(byte) 0x25, (byte) 0xE2, (byte) 0xE3, (byte) 0xCF, (byte) 0xD3, 0x0A});
        obj(1, "<< /Type /Catalog /Pages 2 0 R >>".getBytes(StandardCharsets.US_ASCII));
    }

    /** 添加一页；jpeg 必须是完整的 JPEG 字节流。 */
    public void addPage(byte[] jpeg, int width, int height, int components) throws IOException {
        int base = 3 + 3 * pages;
        int imageId = base;
        int contentId = base + 1;
        int pageId = base + 2;

        String colorSpace = components == 1 ? "DeviceGray" : "DeviceRGB";
        stream(imageId,
                "/Type /XObject /Subtype /Image /Width " + width + " /Height " + height
                        + " /ColorSpace /" + colorSpace + " /BitsPerComponent 8 /Filter /DCTDecode",
                jpeg);

        byte[] content = ("q\n" + width + " 0 0 " + height + " 0 0 cm\n/Im0 Do\nQ\n")
                .getBytes(StandardCharsets.US_ASCII);
        stream(contentId, "", content);

        String page = "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 " + width + " " + height + "] "
                + "/Resources << /XObject << /Im0 " + imageId + " 0 R >> >> "
                + "/Contents " + contentId + " 0 R >>";
        obj(pageId, page.getBytes(StandardCharsets.US_ASCII));

        pageIds.add(pageId);
        pages++;
    }

    public int pageCount() {
        return pages;
    }

    /** 收尾，返回页数。 */
    public int finish(String title) throws IOException {
        if (closed) return pages;
        StringBuilder kids = new StringBuilder();
        for (int i = 0; i < pageIds.size(); i++) {
            if (i > 0) kids.append(' ');
            kids.append(pageIds.get(i)).append(" 0 R");
        }
        obj(2, ("<< /Type /Pages /Count " + pages + " /Kids [" + kids + "] >>")
                .getBytes(StandardCharsets.US_ASCII));

        int infoId = 3 + 3 * pages;
        byte[] info = concat(
                "<< /Producer (JMComic Android) /Title ".getBytes(StandardCharsets.US_ASCII),
                pdfText(title == null ? "" : title),
                " >>".getBytes(StandardCharsets.US_ASCII));
        obj(infoId, info);

        int maxId = infoId;
        long xref = pos;
        write(("xref\n0 " + (maxId + 1) + "\n").getBytes(StandardCharsets.US_ASCII));
        write("0000000000 65535 f \n".getBytes(StandardCharsets.US_ASCII));
        for (int id = 1; id <= maxId; id++) {
            Long off = offsets.get(id);
            if (off == null) {
                write("0000000000 65535 f \n".getBytes(StandardCharsets.US_ASCII));
            } else {
                write(String.format("%010d 00000 n \n", off).getBytes(StandardCharsets.US_ASCII));
            }
        }
        write(("trailer\n<< /Size " + (maxId + 1) + " /Root 1 0 R /Info " + infoId + " 0 R >>\n"
                + "startxref\n" + xref + "\n%%EOF\n").getBytes(StandardCharsets.US_ASCII));
        out.flush();
        closed = true;
        out.close();
        return pages;
    }

    @Override
    public void close() {
        if (!closed) {
            try {
                finish("");
            } catch (IOException ignored) {
            }
        }
    }

    // ------------------------------------------------------------------ //
    private void obj(int id, byte[] body) throws IOException {
        offsets.put(id, pos);
        write((id + " 0 obj\n").getBytes(StandardCharsets.US_ASCII));
        write(body);
        write("\nendobj\n".getBytes(StandardCharsets.US_ASCII));
    }

    private void stream(int id, String dictBody, byte[] data) throws IOException {
        offsets.put(id, pos);
        write((id + " 0 obj\n").getBytes(StandardCharsets.US_ASCII));
        write(("<< " + dictBody + " /Length " + data.length + " >>\nstream\n")
                .getBytes(StandardCharsets.US_ASCII));
        write(data);
        write("\nendstream\nendobj\n".getBytes(StandardCharsets.US_ASCII));
    }

    private void write(byte[] data) throws IOException {
        out.write(data);
        pos += data.length;
    }

    private static byte[] pdfText(String text) {
        StringBuilder hex = new StringBuilder("<FEFF");
        for (int i = 0; i < text.length(); i++) {
            hex.append(String.format("%04X", (int) text.charAt(i)));
        }
        hex.append('>');
        return hex.toString().getBytes(StandardCharsets.US_ASCII);
    }

    private static byte[] concat(byte[]... parts) {
        int total = 0;
        for (byte[] p : parts) total += p.length;
        byte[] out = new byte[total];
        int at = 0;
        for (byte[] p : parts) {
            System.arraycopy(p, 0, out, at, p.length);
            at += p.length;
        }
        return out;
    }

    // ------------------------------------------------------------------ //
    /** 从 JPEG 头里读尺寸和通道数，返回 {width, height, components}。 */
    public static int[] jpegSize(byte[] data) {
        if (data == null || data.length < 4
                || (data[0] & 0xFF) != 0xFF || (data[1] & 0xFF) != 0xD8) {
            return null;
        }
        int i = 2;
        while (i + 9 < data.length) {
            if ((data[i] & 0xFF) != 0xFF) {
                i++;
                continue;
            }
            int marker = data[i + 1] & 0xFF;
            if (marker == 0xD8 || marker == 0x01 || (marker >= 0xD0 && marker <= 0xD7)) {
                i += 2;
                continue;
            }
            int len = ((data[i + 2] & 0xFF) << 8) | (data[i + 3] & 0xFF);
            boolean isSof = (marker >= 0xC0 && marker <= 0xC3)
                    || (marker >= 0xC5 && marker <= 0xC7)
                    || (marker >= 0xC9 && marker <= 0xCB)
                    || (marker >= 0xCD && marker <= 0xCF);
            if (isSof) {
                int h = ((data[i + 5] & 0xFF) << 8) | (data[i + 6] & 0xFF);
                int w = ((data[i + 7] & 0xFF) << 8) | (data[i + 8] & 0xFF);
                int comps = data[i + 9] & 0xFF;
                return new int[]{w, h, comps};
            }
            i += 2 + len;
        }
        return null;
    }
}
