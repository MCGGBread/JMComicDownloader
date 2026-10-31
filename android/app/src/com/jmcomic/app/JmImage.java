package com.jmcomic.app;

/** 图片分块还原：算法与 jmcomic 的 JmImageTool 完全一致。 */
public final class JmImage {

    private JmImage() {}

    private static final int SCRAMBLE_268850 = 268850;
    private static final int SCRAMBLE_421926 = 421926;

    /** 每张图需要切成几块（0 表示原图未打乱）。 */
    public static int decodeNum(int scrambleId, int aid, String filename) {
        if (aid < scrambleId) return 0;
        if (aid < SCRAMBLE_268850) return 10;
        int x = aid < SCRAMBLE_421926 ? 10 : 8;
        String digest = JmApi.md5(aid + filename);
        int num = (digest.charAt(digest.length() - 1)) % x;
        return num * 2 + 2;
    }

    /**
     * 计算每一块的搬运计划：{源 Y, 目标 Y, 高度}。
     * 原图从上到下切成 num 块后倒序拼接。
     */
    public static int[][] plan(int height, int num) {
        if (num <= 0 || height < num) return new int[0][];
        int[][] result = new int[num][];
        int over = height % num;
        int move = height / num;
        for (int i = 0; i < num; i++) {
            int srcY = height - move * (i + 1) - over;
            int dstY = move * i;
            int h = move;
            if (i == 0) {
                h += over;
            } else {
                dstY += over;
            }
            result[i] = new int[]{srcY, dstY, h};
        }
        return result;
    }
}
