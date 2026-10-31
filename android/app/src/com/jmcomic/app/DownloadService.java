package com.jmcomic.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.IBinder;

/** 前台服务：保证切到后台/息屏后仍能继续下载。 */
public class DownloadService extends Service {

    private static final String CHANNEL_ID = "jm_download";
    private static final int NOTIFICATION_ID = 1001;

    private Engine engine;
    private final Engine.ServiceBridge bridge = new Engine.ServiceBridge() {
        @Override
        public void update(String text, int percent) {
            try {
                NotificationManager manager = getSystemService(NotificationManager.class);
                if (manager != null) {
                    manager.notify(NOTIFICATION_ID, buildNotification(text, percent));
                }
            } catch (Exception ignored) {
            }
        }

        @Override
        public void finish() {
            stopForeground(true);
            stopSelf();
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
        engine = Engine.get(this);
        engine.setBridge(bridge);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startForeground(NOTIFICATION_ID, buildNotification("准备下载…", 0));
        engine.startWorker();
        if (!engine.isRunning()) {
            stopForeground(true);
            stopSelf();
        }
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        if (engine != null) engine.setBridge(null);
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void createChannel() {
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (manager == null) return;
        NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID, "下载进度", NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("显示 JMComic 下载进度");
        channel.setShowBadge(false);
        manager.createNotificationChannel(channel);
    }

    private Notification buildNotification(String text, int percent) {
        Intent open = new Intent(this, MainActivity.class);
        open.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pending = PendingIntent.getActivity(
                this, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);

        Notification.Builder builder = new Notification.Builder(this, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.stat_sys_download)
                .setContentTitle("JMComic 下载中")
                .setContentText(text)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setContentIntent(pending)
                .setProgress(100, Math.max(0, Math.min(100, percent)), percent <= 0);
        return builder.build();
    }
}
