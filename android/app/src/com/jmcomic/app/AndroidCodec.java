package com.jmcomic.app;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Rect;

import java.io.ByteArrayOutputStream;
import java.io.IOException;

/** 把下载到的 WebP/JPEG 还原并转成 JPEG 字节。 */
public class AndroidCodec implements Downloader.ImageCodec {

    @Override
    public byte[] toJpeg(byte[] raw, int num, int quality, int maxWidth) throws Exception {
        BitmapFactory.Options options = new BitmapFactory.Options();
        options.inPreferredConfig = Bitmap.Config.ARGB_8888;
        Bitmap source = BitmapFactory.decodeByteArray(raw, 0, raw.length);
        if (source == null) throw new IOException("图片解码失败");

        int width = source.getWidth();
        int height = source.getHeight();
        Bitmap current = source;

        if (num > 0) {
            Bitmap decoded = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
            Canvas canvas = new Canvas(decoded);
            canvas.drawColor(Color.WHITE);
            for (int[] band : JmImage.plan(height, num)) {
                Rect srcRect = new Rect(0, band[0], width, band[0] + band[2]);
                Rect dstRect = new Rect(0, band[1], width, band[1] + band[2]);
                canvas.drawBitmap(source, srcRect, dstRect, null);
            }
            current = decoded;
        }

        if (maxWidth > 0 && width > maxWidth) {
            int targetHeight = Math.max(1, Math.round(height * (float) maxWidth / width));
            Bitmap scaled = Bitmap.createScaledBitmap(current, maxWidth, targetHeight, true);
            if (scaled != current && current != source) current.recycle();
            current = scaled;
        }

        ByteArrayOutputStream out = new ByteArrayOutputStream();
        current.compress(Bitmap.CompressFormat.JPEG, Math.max(50, Math.min(100, quality)), out);
        if (current != source) current.recycle();
        source.recycle();
        return out.toByteArray();
    }
}
