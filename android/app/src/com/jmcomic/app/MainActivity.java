package com.jmcomic.app;

import android.Manifest;
import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.ConsoleMessage;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

public class MainActivity extends Activity {

    private static final String TAG = "JmMain";
    private static final int REQ_NOTIFICATION = 100;

    private WebView web;
    private Engine engine;

    private final Engine.Listener listener = json -> runOnUiThread(() -> {
        if (web != null) {
            web.evaluateJavascript("window.__nativeEvent(" + Json.quote(json) + ")", null);
        }
    });

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        Window window = getWindow();
        window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
        window.setStatusBarColor(Color.parseColor("#0e1014"));
        window.setNavigationBarColor(Color.parseColor("#0e1014"));

        engine = Engine.get(this);

        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#0e1014"));
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setTextZoom(100);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        web.addJavascriptInterface(new Bridge(this), "JmNative");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                pushState();
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onConsoleMessage(ConsoleMessage message) {
                Log.d(TAG, "console: " + message.message() + " @" + message.lineNumber());
                return true;
            }
        });

        setContentView(web);
        web.loadUrl("file:///android_asset/index.html");

        requestNotificationPermission();
    }

    @Override
    protected void onResume() {
        super.onResume();
        engine.addListener(listener);
        engine.maybeAutoResume(this);
        pushState();
    }

    @Override
    protected void onPause() {
        engine.removeListener(listener);
        super.onPause();
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    public void pushState() {
        if (web == null) return;
        String json = engine.snapshotJson();
        web.evaluateJavascript("window.__nativeState(" + Json.quote(json) + ")", null);
    }

    public void openPdf(String id) {
        String uri = engine.taskUri(id);
        if (uri == null || uri.isEmpty()) {
            toast("找不到这个 PDF");
            return;
        }
        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(Uri.parse(uri), "application/pdf");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            startActivity(intent);
        } catch (ActivityNotFoundException e) {
            toast("没有可打开 PDF 的应用");
        }
    }

    public void toast(String message) {
        runOnUiThread(() -> Toast.makeText(this, message, Toast.LENGTH_SHORT).show());
    }

    private void requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                    != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQ_NOTIFICATION);
            }
        }
    }
}
