/**
 * AquaSense Firebase Realtime Database & Analytics Service
 * Connects directly to Firebase RTDB for real-time live telemetry streaming,
 * device status updates, and Google Analytics event tracking.
 */

(function () {
  'use strict';

  // 1. Firebase Configuration (AquaSense Project)
  const firebaseConfig = {
    apiKey: "AIzaSyCfSBPlTeE9MJaXMmwngwHNQuthbRCFFrs",
    authDomain: "aquasense-62dda.firebaseapp.com",
    databaseURL: "https://aquasense-62dda-default-rtdb.asia-southeast1.firebasedatabase.app",
    projectId: "aquasense-62dda",
    storageBucket: "aquasense-62dda.firebasestorage.app",
    messagingSenderId: "811550760426",
    appId: "1:811550760426:web:be7cf64f30fd21f5c16693",
    measurementId: "G-ZKXDJ7KLWS"
  };

  const FirebaseService = {
    app: null,
    db: null,
    analytics: null,
    isConnected: false,
    lastSyncTime: null,
    lastTelemetryTimestamp: 0,
    isOnline: false,
    watchdogInterval: null,
    subscribers: [],

    init() {
      if (typeof firebase === 'undefined') {
        console.warn('[Firebase] Firebase SDK scripts not loaded. Running in local FastAPI mode.');
        this.updateBadge('offline', 'Firebase SDK Offline');
        return;
      }

      try {
        // Initialize App if not already initialized
        if (!firebase.apps.length) {
          this.app = firebase.initializeApp(firebaseConfig);
        } else {
          this.app = firebase.app();
        }

        // Initialize Analytics if supported
        try {
          if (typeof firebase.analytics === 'function') {
            this.analytics = firebase.analytics();
            this.analytics.logEvent('app_open', { platform: 'web_dashboard' });
          }
        } catch (e) {
          console.debug('[Firebase] Analytics not available in current environment:', e.message);
        }

        // Initialize Realtime Database
        this.db = firebase.database();
        this.bindConnectionListener();
        this.bindRealtimeListeners();
        this.startHeartbeatWatcher();
        this.updateBadge('connected', 'Firebase Cloud Live');
        console.log('[Firebase] Connected to RTDB (asia-southeast1):', firebaseConfig.projectId);
      } catch (err) {
        console.error('[Firebase Init Error]', err);
        this.updateBadge('error', 'Firebase Error');
      }
    },

    // 2. Monitor connection status with Firebase server (.info/connected)
    bindConnectionListener() {
      if (!this.db) return;
      const connectedRef = this.db.ref('.info/connected');
      connectedRef.on('value', (snap) => {
        if (snap.val() === true) {
          this.isConnected = true;
          this.updateBadge('connected', 'Firebase Live');
        } else {
          this.isConnected = false;
          this.updateBadge('offline', 'Firebase Offline');
        }
      });
    },

    // 3. Bind Realtime Listeners for Telemetry, Status, and Alerts
    bindRealtimeListeners() {
      if (!this.db) return;

      // Telemetry latest node
      const telemetryRef = this.db.ref('aquasense/telemetry/latest');
      telemetryRef.on('value', (snapshot) => {
        const val = snapshot.val();
        if (val && window.App) {
          this.lastSyncTime = new Date();
          this.lastTelemetryTimestamp = Date.now();
          this.isOnline = true;
          this.flashSyncIndicator();

          // Immediately update state as solidly Online
          if (!window.App.status) window.App.status = {};
          window.App.status.online = true;
          window.App.status.device_id = val.device_id || 'esp32-aquasense-01';
          window.App.status.is_simulated = Boolean(val.is_simulated);
          window.App.status.seconds_since_last_seen = 0;
          if (val.pump_state) window.App.status.current_pump_state = val.pump_state;
          if (val.operating_mode) window.App.status.current_mode = val.operating_mode;

          window.App.latestReading = val;
          window.App.renderOverviewKPIs();
          window.App.renderMonitoringView();
          window.App.renderTopbarStatus();
        }
      }, (error) => {
        console.warn('[Firebase Telemetry Listener Error]', error.message);
      });

      // System Status node
      const statusRef = this.db.ref('aquasense/status');
      statusRef.on('value', (snapshot) => {
        const val = snapshot.val();
        if (val && window.App) {
          // If telemetry arrived recently, don't let stale status force offline
          const recentTelemetry = (Date.now() - this.lastTelemetryTimestamp) < 45000;
          const resolvedOnline = recentTelemetry || Boolean(val.online);

          window.App.status = {
            ...window.App.status,
            ...val,
            online: resolvedOnline
          };
          window.App.renderTopbarStatus();
          window.App.renderControlState();
        }
      }, (error) => {
        console.warn('[Firebase Status Listener Error]', error.message);
      });

      // Settings node
      const settingsRef = this.db.ref('aquasense/settings');
      settingsRef.on('value', (snapshot) => {
        const val = snapshot.val();
        if (val && window.App) {
          window.App.settings = {
            ...window.App.settings,
            ...val
          };
        }
      });
    },

    // 4. Stable Heartbeat Watcher (prevents rapid online/offline flapping)
    startHeartbeatWatcher() {
      if (this.watchdogInterval) clearInterval(this.watchdogInterval);
      this.watchdogInterval = setInterval(() => {
        if (this.lastTelemetryTimestamp > 0) {
          const elapsed = Date.now() - this.lastTelemetryTimestamp;
          // Mark offline ONLY after a full 45s of silence
          if (elapsed > 45000 && this.isOnline) {
            this.isOnline = false;
            if (window.App && window.App.status) {
              window.App.status.online = false;
              window.App.status.seconds_since_last_seen = Math.round(elapsed / 1000);
              window.App.renderTopbarStatus();
              window.App.renderOverviewKPIs();
            }
          }
        }
      }, 3000);
    },

    // 4. Analytics Logging Helper
    logEvent(eventName, params = {}) {
      if (this.analytics) {
        try {
          this.analytics.logEvent(eventName, params);
        } catch (e) {
          console.debug('[Firebase Analytics] Event failed:', e.message);
        }
      }
    },

    // 5. Send Command to Firebase RTDB
    async sendCommand(cmdPayload) {
      if (!this.db) return null;
      const commandsRef = this.db.ref('aquasense/commands/latest');
      const payload = {
        ...cmdPayload,
        timestamp: new Date().toISOString()
      };
      await commandsRef.set(payload);
      this.logEvent('irrigation_command', { type: cmdPayload.command_type });
      return payload;
    },

    // 6. Force snapshot sync via backend
    async forceSync() {
      try {
        const resp = await fetch('/api/firebase/sync', { method: 'POST' });
        const data = await resp.json();
        this.flashSyncIndicator();
        if (window.App && window.App.showToast) {
          window.App.showToast('Firebase Realtime Database synced successfully!', 'success');
        }
        return data;
      } catch (err) {
        console.warn('[Firebase Force Sync Error]', err);
        if (window.App && window.App.showToast) {
          window.App.showToast('Sync error: ' + err.message, 'error');
        }
      }
    },

    // 7. Update Status Badge in Topbar
    updateBadge(status, text) {
      const badge = document.getElementById('firebase-status-pill');
      const textEl = document.getElementById('firebase-status-text');
      if (badge && textEl) {
        badge.className = `firebase-status-pill ${status}`;
        textEl.textContent = text;
      }
    },

    flashSyncIndicator() {
      const badge = document.getElementById('firebase-status-pill');
      if (badge) {
        badge.classList.add('flash-sync');
        setTimeout(() => badge.classList.remove('flash-sync'), 600);
      }
    }
  };

  // Expose to window
  window.FirebaseService = FirebaseService;

  // Auto-init on DOMContentLoaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => FirebaseService.init());
  } else {
    FirebaseService.init();
  }
})();
