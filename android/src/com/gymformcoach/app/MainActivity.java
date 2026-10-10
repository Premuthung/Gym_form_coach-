package com.gymformcoach.app;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.ContentValues;
import android.content.Intent;
import android.content.SharedPreferences;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.text.InputType;
import android.view.Gravity;
import android.view.ViewGroup;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.InputStream;

/**
 * The whole Android app: one screen that shows the Gym Form Coach web app from a server.
 *
 * The models (pose, machine recogniser) run on that server, not on the phone, so the app needs the
 * server's address. It comes from assets/server.txt (written by build-apk.bat) or, when that is empty
 * or the server cannot be reached, from a box the user types it into.
 *
 * Besides showing the page, the app does three things a bare WebView does not:
 * the "Scan" and "Record" buttons open the camera, "Upload" opens the file picker, and
 * "Save this video" downloads into the phone's Downloads folder.
 */
public class MainActivity extends Activity {
    private static final int PICK_FILE = 1;

    private SharedPreferences prefs;
    private WebView web;                       // null while the address screen is showing
    private String serverHost = "";
    private ValueCallback<Uri[]> fileCallback; // the page is waiting for a photo or video
    private Uri captureUri;                    // where the camera was told to save a photo

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        prefs = getSharedPreferences("server", MODE_PRIVATE);
        String builtIn = builtInServer();
        if (!builtIn.isEmpty() && !builtIn.equals(prefs.getString("built_in", ""))) {
            // A newer APK carries a newer address: it replaces whatever was typed into the old one.
            prefs.edit().putString("built_in", builtIn).putString("url", builtIn).apply();
        }
        String url = prefs.getString("url", builtIn);
        if (url.isEmpty()) showAddressScreen(null);
        else openServer(url);
    }

    /** The address chosen when the APK was built, or "" if none was given. */
    private String builtInServer() {
        try (InputStream in = getAssets().open("server.txt")) {
            byte[] data = new byte[2048];
            int n = Math.max(0, in.read(data));
            return new String(data, 0, n, "UTF-8").trim();
        } catch (Exception e) {
            return "";
        }
    }

    // ---- the address screen ------------------------------------------------------------------

    private void showAddressScreen(String problem) {
        if (web != null) {
            web.stopLoading();
            web = null;
        }
        int pad = dp(24);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(pad, dp(48), pad, pad);

        TextView title = new TextView(this);
        title.setText("Gym Form Coach");
        title.setTextSize(26);
        title.setTextColor(0xff0f172a);
        box.addView(title);

        TextView message = new TextView(this);
        message.setText((problem == null ? "" : problem + "\n\n")
                + "Enter the link you were given for the test, for example\nhttps://some-words.trycloudflare.com");
        message.setTextSize(16);
        message.setTextColor(0xff5b6577);
        message.setPadding(0, dp(12), 0, dp(16));
        box.addView(message);

        final EditText input = new EditText(this);
        input.setHint("https://");
        input.setSingleLine(true);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        input.setText(prefs.getString("url", builtInServer()));
        box.addView(input, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        Button open = new Button(this);
        open.setText("Open");
        open.setOnClickListener(v -> {
            String url = input.getText().toString().trim();
            if (!url.isEmpty() && !url.contains("://")) url = "https://" + url;
            if (Uri.parse(url).getHost() == null) {
                Toast.makeText(this, "That does not look like a link.", Toast.LENGTH_LONG).show();
                return;
            }
            prefs.edit().putString("url", url).apply();
            openServer(url);
        });
        LinearLayout.LayoutParams wide = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(56));
        wide.topMargin = dp(12);
        box.addView(open, wide);

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        box.setGravity(Gravity.TOP);
        scroll.addView(box);
        setContentView(scroll);
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    // ---- the web app -------------------------------------------------------------------------

    private void openServer(String url) {
        String host = Uri.parse(url).getHost();
        serverHost = host == null ? "" : host;
        final WebView view = new WebView(this);
        web = view;
        WebSettings settings = view.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);          // "Your last checks" is kept in localStorage
        settings.setAllowFileAccess(false);

        view.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest request) {
                if (serverHost.equals(request.getUrl().getHost())) return false;
                try {                                  // any other site opens in the phone's browser
                    startActivity(new Intent(Intent.ACTION_VIEW, request.getUrl()));
                } catch (ActivityNotFoundException ignored) { }
                return true;
            }

            @Override
            public void onReceivedError(WebView v, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) serverFailed(view);
            }

            @Override
            public void onReceivedHttpError(WebView v, WebResourceRequest request, WebResourceResponse response) {
                // A tunnel link whose computer is switched off answers with a 5xx error page.
                if (request.isForMainFrame() && response.getStatusCode() >= 500) serverFailed(view);
            }
        });

        view.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView v, ValueCallback<Uri[]> callback, FileChooserParams params) {
                return chooseFile(callback, params);
            }
        });

        view.setDownloadListener((downloadUrl, userAgent, contentDisposition, mimeType, length) -> {
            try {
                String name = URLUtil.guessFileName(downloadUrl, contentDisposition, mimeType);
                DownloadManager.Request request = new DownloadManager.Request(Uri.parse(downloadUrl));
                request.setMimeType(mimeType);
                request.setTitle(name);
                request.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
                request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
                ((DownloadManager) getSystemService(DOWNLOAD_SERVICE)).enqueue(request);
                Toast.makeText(this, "Saving to Downloads: " + name, Toast.LENGTH_LONG).show();
            } catch (Exception e) {                    // no download app or no permission: use the browser
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(downloadUrl)));
                } catch (ActivityNotFoundException ignored) { }
            }
        });

        setContentView(view);
        view.loadUrl(url);
    }

    private void serverFailed(final WebView view) {
        // Not from inside the WebView's own callback: swap the screen on the next turn of the UI loop.
        view.post(() -> {
            if (web == view) {
                showAddressScreen("Could not reach the server. It may be switched off, or the link has changed.");
            }
        });
    }

    /** The hardware Back button does what the page's own back arrow does; on the home screen it leaves. */
    @Override
    public void onBackPressed() {
        if (web == null) {
            finish();
            return;
        }
        web.evaluateJavascript(
                "(function(){var b=document.getElementById('back');if(b&&!b.hidden){b.click();return true}return false})()",
                went -> { if (!"true".equals(went)) finish(); });
    }

    // ---- photo and video buttons -------------------------------------------------------------

    private boolean chooseFile(ValueCallback<Uri[]> callback, WebChromeClient.FileChooserParams params) {
        if (fileCallback != null) fileCallback.onReceiveValue(null);
        fileCallback = callback;
        captureUri = null;

        String[] types = params.getAcceptTypes();
        boolean video = types != null && types.length > 0 && types[0] != null && types[0].startsWith("video");
        Intent pick = new Intent(Intent.ACTION_GET_CONTENT)
                .addCategory(Intent.CATEGORY_OPENABLE)
                .setType(video ? "video/*" : "image/*");

        Intent camera = null;
        if (params.isCaptureEnabled()) {               // the button asked for the camera, not the gallery
            if (video) {
                camera = new Intent(MediaStore.ACTION_VIDEO_CAPTURE);
            } else if (Build.VERSION.SDK_INT >= 29) {
                // A full-size photo needs a place to be saved. The phone's own picture store gives one
                // without asking for any permission (Android 10 and newer).
                ContentValues values = new ContentValues();
                values.put(MediaStore.Images.Media.DISPLAY_NAME, "gym-machine-" + System.currentTimeMillis() + ".jpg");
                values.put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg");
                try {
                    captureUri = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values);
                } catch (Exception ignored) { }
                if (captureUri != null) {
                    camera = new Intent(MediaStore.ACTION_IMAGE_CAPTURE)
                            .putExtra(MediaStore.EXTRA_OUTPUT, captureUri)
                            .addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
                }
            }
        }

        if (camera != null) {
            try {
                startActivityForResult(camera, PICK_FILE);
                return true;
            } catch (Exception noCameraApp) {
                discardEmptyPhoto();
            }
        }
        try {
            startActivityForResult(pick, PICK_FILE);
        } catch (ActivityNotFoundException e) {
            fileCallback = null;
            callback.onReceiveValue(null);
            Toast.makeText(this, "No app on this phone can choose a file.", Toast.LENGTH_LONG).show();
        }
        return true;
    }

    private void discardEmptyPhoto() {
        if (captureUri != null) {
            try {
                getContentResolver().delete(captureUri, null, null);
            } catch (Exception ignored) { }
            captureUri = null;
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_FILE || fileCallback == null) return;
        Uri[] chosen = null;
        if (resultCode == RESULT_OK) {
            Uri uri = data != null && data.getData() != null ? data.getData() : captureUri;
            if (uri != null) chosen = new Uri[]{uri};
            if (uri != captureUri) discardEmptyPhoto();
        } else {
            discardEmptyPhoto();
        }
        captureUri = null;
        fileCallback.onReceiveValue(chosen);
        fileCallback = null;
    }
}
