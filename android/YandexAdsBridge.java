package org.flare.app;

import android.util.Log;


import com.yandex.mobile.ads.common.AdError;
import com.yandex.mobile.ads.common.AdRequest;
import com.yandex.mobile.ads.common.AdRequestError;
import com.yandex.mobile.ads.common.ImpressionData;
import com.yandex.mobile.ads.common.YandexAds;
import com.yandex.mobile.ads.interstitial.InterstitialAd;
import com.yandex.mobile.ads.interstitial.InterstitialAdEventListener;
import com.yandex.mobile.ads.interstitial.InterstitialAdLoadListener;
import com.yandex.mobile.ads.interstitial.InterstitialAdLoader;

/**
 * Optional Yandex Advertising Network SDK 8 bridge for Android/RuStore.
 *
 * A real ad-unit ID and explicit user choice are required. The SDK must have
 * AUTOMATIC_SDK_INITIALIZATION=false in the manifest: do not start requests
 * (or manual SDK initialization) before the consent screen.
 *
 * The Activity enforces consent, first-play delay and one shared 150-second
 * cooldown across all safe-break events and advertising networks.
 */
final class YandexAdsBridge {
    private static final String TAG = "FlareYandexAds";

    private final FLARE activity;
    private final String adUnitId;
    private InterstitialAdLoader loader;
    private InterstitialAd pendingAd;
    private boolean privacyReady = false;

    YandexAdsBridge(FLARE activity, String adUnitId) {
        this.activity = activity;
        this.adUnitId = adUnitId;
    }

    void setPrivacyReady(boolean allowed) {
        privacyReady = allowed;
        if (!allowed) {
            discardAd();
            loader = null;
            return;
        }
        // The SDK must initialize after consent, not during Android startup.
        try {
            YandexAds.setUserConsent(true);
            YandexAds.initialize(activity, () -> {
                if (privacyReady && !adUnitId.isEmpty()) {
                    loader = new InterstitialAdLoader(activity);
                    loadNext();
                }
            });
        } catch (RuntimeException error) {
            Log.w(TAG, "Yandex Mobile Ads initialization failed; gameplay continues", error);
        }
    }

    /** Show only when preloaded; never block loading, game progress or saves. */
    boolean showIfReady() {
        if (!privacyReady || pendingAd == null) return false;

        final InterstitialAd ad = pendingAd;
        pendingAd = null;
        ad.setAdEventListener(new InterstitialAdEventListener() {
            @Override public void onAdShown() {
                Log.i(TAG, "Interstitial displayed at a safe game break");
            }
            @Override public void onAdFailedToShow(AdError error) {
                cleanup(ad);
                loadNext();
            }
            @Override public void onAdDismissed() {
                cleanup(ad);
                loadNext();
            }
            @Override public void onAdClicked() {}
            @Override public void onAdImpression(ImpressionData data) {}
        });
        try {
            ad.show(activity);
            return true;
        } catch (RuntimeException error) {
            Log.w(TAG, "Interstitial could not open; gameplay continues", error);
            cleanup(ad);
            loadNext();
            return false;
        }
    }

    private void loadNext() {
        if (!privacyReady || loader == null || pendingAd != null || adUnitId.isEmpty()) return;
        try {
            loader.loadAd(new AdRequest.Builder(adUnitId).build(), new InterstitialAdLoadListener() {
                @Override public void onAdLoaded(InterstitialAd ad) {
                    if (!privacyReady) {
                        ad.setAdEventListener(null);
                        return;
                    }
                    discardAd();
                    pendingAd = ad;
                }
                @Override public void onAdFailedToLoad(AdRequestError error) {
                    // No automatic retries. Another session or launch may retry.
                    Log.i(TAG, "No Yandex interstitial available; game continues");
                }
            });
        } catch (RuntimeException error) {
            Log.w(TAG, "Yandex interstitial request failed; game continues", error);
        }
    }

    private void cleanup(InterstitialAd ad) {
        ad.setAdEventListener(null);
        if (pendingAd == ad) pendingAd = null;
    }

    private void discardAd() {
        if (pendingAd != null) {
            pendingAd.setAdEventListener(null);
            pendingAd = null;
        }
    }
}
