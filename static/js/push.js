/* =========================================================================
   push.js — Web Push notification setup (Phase 2).

   Honest platform reality (also in the README):
     * Android Chrome: push works once the PWA is installed.
     * iOS/iPadOS:     push works ONLY for a PWA added to the Home Screen,
                       on iOS 16.4 or later. In a normal Safari tab it won't.
     * Desktop Chrome/Edge/Firefox: works for testing.

   If push isn't available we degrade gracefully: the toggle still saves your
   preference, and we clearly explain why notifications can't be delivered yet.
   Exposed as window.Push.
   ========================================================================= */

(function () {
  const { api, toast, saveSetting } = window.PT;

  const toggle = document.getElementById("notif-toggle");
  const details = document.getElementById("notif-details");
  const statusEl = document.getElementById("notif-status");
  const platformNote = document.getElementById("platform-note");
  const testBtn = document.getElementById("notif-test");

  /* Is this browser even capable of Web Push? */
  function browserSupportsPush() {
    return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  }

  /* Detect a Home-Screen (standalone) install — required for push on iOS. */
  function isStandalone() {
    return (
      window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true
    );
  }

  function isIOS() {
    return /iphone|ipad|ipod/i.test(navigator.userAgent);
  }

  /* Show the honest platform message under the settings. */
  function describePlatform(serverHasKeys) {
    let msg;
    if (!serverHasKeys) {
      msg =
        "⚠️ Push isn't configured on the server yet. Generate VAPID keys " +
        "(see the README) and add them to your environment to enable delivery.";
    } else if (!browserSupportsPush()) {
      msg = "This browser doesn't support web push notifications.";
    } else if (isIOS() && !isStandalone()) {
      msg =
        "On iPhone/iPad, notifications work only after you use Share → " +
        "“Add to Home Screen” and open PaperPilot from that icon (iOS 16.4+).";
    } else {
      msg = "You can enable gentle reading nudges below.";
    }
    if (platformNote) platformNote.textContent = msg;
  }

  /* Convert a base64 VAPID key to the Uint8Array the browser API needs. */
  function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = atob(base64);
    const output = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) output[i] = raw.charCodeAt(i);
    return output;
  }

  /* Subscribe this browser to push and register it with our server. */
  async function subscribe() {
    if (!browserSupportsPush()) {
      toast("This browser can't receive push notifications.");
      return false;
    }

    // Ask the user for permission.
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      toast("Notification permission was declined.");
      return false;
    }

    // Fetch the server's public VAPID key.
    const { public_key, available } = await api.get("/api/push/vapid-public-key");
    if (!available || !public_key) {
      toast("Server push keys aren't set up yet (see README).");
      return false;
    }

    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(public_key),
    });

    // Send the subscription to our backend to store.
    await api.post("/api/push/subscribe", sub.toJSON());
    return true;
  }

  /* ---- Wire up the settings toggle -------------------------------------- */
  toggle.addEventListener("change", async () => {
    const on = toggle.checked;
    details.classList.toggle("hidden", !on);

    if (on) {
      const ok = await subscribe();
      if (!ok) {
        // Roll the toggle back if we couldn't actually subscribe.
        toggle.checked = false;
        details.classList.add("hidden");
        await saveSetting({ notifications_enabled: false });
        return;
      }
      await saveSetting({ notifications_enabled: true });
      statusEl.textContent = "Nudges are on.";
      toast("Notifications enabled!");
    } else {
      await saveSetting({ notifications_enabled: false });
      statusEl.textContent = "Gentle nudges to read a paper.";
    }
  });

  /* Send a test notification right now. */
  testBtn.addEventListener("click", async () => {
    try {
      const res = await api.post("/api/push/test", {});
      toast(res.delivered ? "Test sent! Check your notifications." : "No devices subscribed yet.");
    } catch (err) {
      toast("Couldn't send a test — is push configured on the server?");
      console.error(err);
    }
  });

  window.Push = { describePlatform, subscribe };
})();
