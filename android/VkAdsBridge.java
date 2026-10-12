package org.flare.app;

import android.os.SystemClock;
import android.util.Log;

import com.my.target.ads.InterstitialAd;
import com.my.target.common.MyTargetPrivacy;
import com.my.target.common.models.IAdLoadingError;

/**
 * OPTIONAL Android-only VK Реклама (myTarget) adapter.
 *
 * Included only in builds explicitly configured with a real VK ad slot.
 * Requests remain disabled until an actual user-facing privacy/consent flow
 * calls setPrivacyReady(). No SDK object is created by the offline default build.
 *
 * The game never waits for an ad to load. Only a completed game session,
 * after a native save and return to the title, is eligible for interstitials.
 */
final class VkAdsBridge {
    private static final String TAG = "FlareVKAds";
    private static final long MIN_SESSION_AGE_MS = 3L * 60 * 1000;
    private static final long MIN_BETWEEN_ADS_MS = 4L * 60 * 1000;

    private final FLARE activity;
    private final int slotId;
    private final long sessionStartedAt = SystemClock.elapsedRealtime();
    private long lastShownAt = 0;
    private boolean privacyReady = false;
    private boolean loaded = false;
    private InterstitialAd pendingAd;

    VkAdsBridge(FLARE activity, int slotId) {
        this.activity = activity;
        this.slotId = slotId;
    }

    /**
     * Call only after implementing consent/privacy disclosure in the UI.
     * No production code currently calls this, intentionally.
     */
    void setPrivacyReady(boolean consentGranted) {
        privacyReady = consentGranted;
        MyTargetPrivacy.setUserConsent(consentGranted);
        if (privacyReady) {
            loadNext();
        } else {
            loaded = false;
            pendingAd = null;
        }
    }

    void onGameSessionEnded() {
        if (!privacyReady || slotId <= 0 || !loaded || pendingAd == null)
            return;

        long now = SystemClock.elapsedRealtime();
        if (now - sessionStartedAt < MIN_SESSION_AGE_MS ||
                (lastShownAt > 0 && now - lastShownAt < MIN_BETWEEN_ADS_MS))
            return;

        InterstitialAd ad = pendingAd;
        pendingAd = null;
        loaded = false;
        lastShownAt = now;

        try {
            ad.show();
        } catch (RuntimeException error) {
            Log.w(TAG, "Unable to show VK interstitial; continuing the game", error);
            loadNext();
        }
    }

    private void loadNext() {
        if (!privacyReady || slotId <= 0 || pendingAd != null)
            return;
        try {
            InterstitialAd next = new InterstitialAd(slotId, activity);
            pendingAd = next;
            next.setListener2(new InterstitialAd.InterstitialAdListener2() {
                @Override
                public void onLoad(InterstitialAd ad) {
                    loaded = (ad == pendingAd) && privacyReady;
                }

                @Override
                public void onNoAd(IAdLoadingError error, InterstitialAd ad) {
                    Log.i(TAG, "VK interstitial unavailable; game continues");
                    if (ad == pendingAd) {
                        pendingAd = null;
                        loaded = false;
                    }
                }

                @Override
                public void onFailedToShow(InterstitialAd ad) {
                    Log.i(TAG, "VK interstitial failed to display");
                    pendingAd = null;
                    loaded = false;
                }

                @Override
                public void onDisplay(InterstitialAd ad) {
                    Log.i(TAG, "Interstitial displayed at completed-game break");
                }

                @Override
                public void onClose(InterstitialAd ad) {
                    pendingAd = null;
                    loaded = false;
                    loadNext();
                }
            });
            next.load();
        } catch (RuntimeException error) {
            pendingAd = null;
            loaded = false;
            Log.w(TAG, "Unable to load VK interstitial; game remains playable", error);
        }
    }
}
