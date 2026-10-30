/**
 * AquaSense Application Controller
 * Handles SPA navigation, real-time polling, safety confirmation modals,
 * form validations, alert handling, and test simulation controls.
 */

const App = {
  currentView: 'overview',
  pollInterval: null,
  pollFrequencyMs: 3000,
  isPollingPaused: false,
  pendingPumpDuration: 15,

  // Cached system state
  status: null,
  latestReading: null,
  settings: null,
  alerts: [],

  init() {
    this.setupTheme();
    this.bindNavigation();
    this.bindControls();
    this.bindSettingsForm();
    this.bindSimulatorControls();
    
    // Start initial load and background polling
    this.refreshAll();
    this.startPolling();
  },

  // -------------------------------------------------------------
  // 1. Theme Management (Light / Dark Forest Green)
  // -------------------------------------------------------------
  setupTheme() {
    const savedTheme = localStorage.getItem('aquasense_theme');
    if (savedTheme === 'dark' || (!savedTheme && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
      document.body.classList.add('dark-mode');
    }

    const themeToggleBtn = document.getElementById('theme-toggle-btn');
    if (themeToggleBtn) {
      themeToggleBtn.addEventListener('click', () => {
        document.body.classList.toggle('dark-mode');
        const isDark = document.body.classList.contains('dark-mode');
        localStorage.setItem('aquasense_theme', isDark ? 'dark' : 'light');
        if (window.ChartsManager) {
          ChartsManager.updateAllThemes();
        }
      });
    }
  },

  // -------------------------------------------------------------
  // 2. Navigation Routing (9 Views)
  // -------------------------------------------------------------
  bindNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
      item.addEventListener('click', (e) => {
        e.preventDefault();
        const targetView = item.getAttribute('data-view');
        this.navigateTo(targetView);
      });
    });

    // Mobile Drawer Toggle
    const mobileBtn = document.getElementById('mobile-menu-btn');
    const sidebar = document.getElementById('app-sidebar');
    if (mobileBtn && sidebar) {
      mobileBtn.addEventListener('click', () => {
        sidebar.classList.toggle('open');
      });
      // Close sidebar when clicking outside on mobile
      document.addEventListener('click', (e) => {
        if (!sidebar.contains(e.target) && !mobileBtn.contains(e.target) && sidebar.classList.contains('open')) {
          sidebar.classList.remove('open');
        }
      });
    }

    // Topbar shortcuts
    const settingsShortcut = document.getElementById('topbar-settings-btn');
    if (settingsShortcut) {
      settingsShortcut.addEventListener('click', () => this.navigateTo('settings'));
    }
    const alertsShortcut = document.getElementById('topbar-alerts-btn');
    if (alertsShortcut) {
      alertsShortcut.addEventListener('click', () => this.navigateTo('alerts'));
    }
  },

  navigateTo(viewId) {
    this.currentView = viewId;

    // Update active nav button
    document.querySelectorAll('.nav-item').forEach(item => {
      item.classList.toggle('active', item.getAttribute('data-view') === viewId);
    });

    // Switch view section visibility
    document.querySelectorAll('.view-section').forEach(sec => {
      sec.classList.remove('active');
    });
    const targetSection = document.getElementById(`view-${viewId}`);
    if (targetSection) {
      targetSection.classList.add('active');
    }

    // Update topbar title
    const titleMap = {
      overview: 'System Overview',
      monitoring: 'Live Monitoring',
      control: 'Irrigation Control',
      analytics: 'Sensor Analytics',
      history: 'Irrigation History',
      alerts: 'Alerts & Notifications',
      health: 'Device Health',
      settings: 'Settings & Calibration',
      about: 'About AquaSense'
    };
    const titleEl = document.getElementById('current-page-title');
    if (titleEl) {
      titleEl.textContent = titleMap[viewId] || 'Dashboard';
    }

    // Close mobile drawer if open
    const sidebar = document.getElementById('app-sidebar');
    if (sidebar) sidebar.classList.remove('open');

    // View-specific initializers
    if (viewId === 'analytics') {
      this.loadAnalyticsCharts();
    } else if (viewId === 'history') {
      this.loadHistoryTable();
    } else if (viewId === 'alerts') {
      this.renderAlertsView();
    } else if (viewId === 'health') {
      this.renderHealthView();
    }
  },

  // -------------------------------------------------------------
  // 3. Polling Engine & Real-Time Data Sync
  // -------------------------------------------------------------
  startPolling() {
    this.stopPolling();
    this.pollInterval = setInterval(() => {
      if (!this.isPollingPaused) {
        this.refreshAll();
      }
    }, this.pollFrequencyMs);
  },

  stopPolling() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
  },

  async refreshAll() {
    try {
      const [status, latest, alerts] = await Promise.all([
        API.getStatus(),
        API.getLatestReading(),
        API.getAlerts()
      ]);

      // If Firebase cloud stream has live telemetry, preserve online state
      if (window.FirebaseService && window.FirebaseService.isOnline) {
        status.online = true;
        if (this.status && this.status.device_id) {
          status.device_id = this.status.device_id;
        }
        status.seconds_since_last_seen = 0;
      }

      this.status = status;
      this.latestReading = latest || this.latestReading;
      this.alerts = alerts;

      this.renderTopbarStatus();
      this.renderOverviewKPIs();
      this.renderMonitoringView();
      this.renderControlState();
      this.updateAlertBadges();

      // Check if simulation is active
      const simBanner = document.getElementById('sim-banner');
      if (simBanner) {
        simBanner.style.display = (status && status.is_simulated) ? 'flex' : 'none';
      }
    } catch (err) {
      console.warn('[Refresh error]:', err.message);
      this.renderOfflineFallback();
    }
  },

  // -------------------------------------------------------------
  // 4. Rendering Views & KPIs
  // -------------------------------------------------------------
  renderTopbarStatus() {
    const pill = document.getElementById('device-status-pill');
    const text = document.getElementById('device-status-text');
    const updateTimeEl = document.getElementById('last-update-time');
    const offlineBanner = document.getElementById('esp-offline-banner');
    const lastSeenBadge = document.getElementById('esp-last-seen-badge');

    if (!pill || !text) return;

    const isOnline = Boolean(this.status && this.status.online);

    if (isOnline) {
      pill.className = 'device-status-pill ' + (this.status.is_simulated ? 'simulated' : 'online');
      text.textContent = this.status.is_simulated ? 'ESP Online (Sim)' : 'ESP Online';
      if (offlineBanner) offlineBanner.style.display = 'none';
    } else {
      pill.className = 'device-status-pill offline';
      text.textContent = 'ESP Offline';
      if (offlineBanner) {
        offlineBanner.style.display = 'flex';
        const lastSeen = this.status && this.status.seconds_since_last_seen;
        if (lastSeenBadge) {
          if (lastSeen !== undefined && lastSeen !== null && lastSeen > 0) {
            const mins = Math.floor(lastSeen / 60);
            const secs = Math.floor(lastSeen % 60);
            lastSeenBadge.textContent = mins > 0 ? `Last seen ${mins}m ${secs}s ago` : `Last seen ${secs}s ago`;
          } else {
            lastSeenBadge.textContent = 'Hardware Disconnected';
          }
        }
      }
    }

    if (updateTimeEl) {
      if (isOnline && this.latestReading && this.latestReading.timestamp) {
        const d = new Date(this.latestReading.timestamp);
        updateTimeEl.textContent = d.toLocaleTimeString();
      } else {
        updateTimeEl.textContent = '--:--:--';
      }
    }
  },

  renderOverviewKPIs() {
    const r = this.latestReading;
    const isOnline = this.status && this.status.online;

    // Soil Moisture
    const soilVal = document.getElementById('kpi-soil-value');
    const soilBadge = document.getElementById('kpi-soil-badge');
    const soilFooter = document.getElementById('kpi-soil-footer');
    if (soilVal) {
      soilVal.textContent = isOnline && r ? `${r.soil_moisture}` : '--';
    }
    if (soilBadge) {
      if (isOnline && r) {
        if (r.soil_moisture < 15.0) {
          soilBadge.className = 'kpi-status-badge critical';
          soilBadge.textContent = 'Critical Dry';
        } else if (r.soil_moisture < 25.0) {
          soilBadge.className = 'kpi-status-badge healthy';
          soilBadge.textContent = 'Optimal Root Zone';
        } else {
          soilBadge.className = 'kpi-status-badge info';
          soilBadge.textContent = 'Sufficiently Moist';
        }
      } else {
        soilBadge.className = 'kpi-status-badge warning';
        soilBadge.textContent = isOnline ? 'Awaiting Data' : 'Device Offline';
      }
    }
    if (soilFooter && this.settings) {
      soilFooter.textContent = `Auto Trigger: < ${this.settings.dry_threshold}%`;
    }

    // Temperature
    const tempVal = document.getElementById('kpi-temp-value');
    const tempBadge = document.getElementById('kpi-temp-badge');
    if (tempVal) tempVal.textContent = isOnline && r ? `${r.temperature}` : '--';
    if (tempBadge) {
      tempBadge.className = 'kpi-status-badge healthy';
      tempBadge.textContent = isOnline ? 'DHT11 Sensor OK' : 'Sensor Offline';
    }

    // Humidity
    const humVal = document.getElementById('kpi-humidity-value');
    if (humVal) humVal.textContent = isOnline && r ? `${r.humidity}` : '--';

    // Light
    const lightVal = document.getElementById('kpi-light-value');
    const lightBadge = document.getElementById('kpi-light-badge');
    if (lightVal) lightVal.textContent = isOnline && r ? `${r.light_raw}` : '--';
    if (lightBadge && isOnline && r) {
      lightBadge.textContent = `State: ${r.light_state}`;
    }

    // Rain Status
    const rainVal = document.getElementById('kpi-rain-value');
    const rainBadge = document.getElementById('kpi-rain-badge');
    if (rainVal) {
      if (isOnline && r) {
        rainVal.textContent = r.rain_detected ? 'Rain Active' : 'No Rain';
      } else {
        rainVal.textContent = '--';
      }
    }
    if (rainBadge) {
      if (isOnline && r && r.rain_detected) {
        rainBadge.className = 'kpi-status-badge warning';
        rainBadge.textContent = 'Lockout Active';
      } else {
        rainBadge.className = 'kpi-status-badge healthy';
        rainBadge.textContent = 'Lockout Idle';
      }
    }

    // Pump Status
    const pumpVal = document.getElementById('kpi-pump-value');
    const pumpBadge = document.getElementById('kpi-pump-badge');
    if (pumpVal) {
      pumpVal.textContent = isOnline && r ? r.pump_state : '--';
    }
    if (pumpBadge) {
      if (isOnline && r && r.pump_state === 'ON') {
        pumpBadge.className = 'kpi-status-badge info';
        pumpBadge.textContent = 'Watering Active';
      } else {
        pumpBadge.className = 'kpi-status-badge healthy';
        pumpBadge.textContent = isOnline ? 'Pump Idle (OFF)' : 'Offline';
      }
    }

    // Recommendation Banner
    const recText = document.getElementById('recommendation-text');
    if (recText && this.status) {
      recText.textContent = this.status.recommendation;
    }

    // Load mini trend chart on overview
    this.loadOverviewChart();
  },

  async loadOverviewChart() {
    try {
      const history = await API.getHistory('1h', 25);
      if (window.ChartsManager) {
        ChartsManager.initOverviewTrend('overview-trend-canvas', history);
      }
    } catch {
      // Ignored if canvas not present
    }
  },

  renderMonitoringView() {
    const r = this.latestReading;
    const isOnline = this.status && this.status.online;

    const freshnessEl = document.getElementById('mon-freshness-badge');
    if (freshnessEl) {
      if (isOnline && r && r.freshness_seconds !== null) {
        if (r.freshness_seconds < 10) {
          freshnessEl.className = 'kpi-status-badge healthy';
          freshnessEl.textContent = `Fresh (${Math.round(r.freshness_seconds)}s ago)`;
        } else {
          freshnessEl.className = 'kpi-status-badge warning';
          freshnessEl.textContent = `Stale (${Math.round(r.freshness_seconds)}s ago)`;
        }
      } else {
        freshnessEl.className = 'kpi-status-badge critical';
        freshnessEl.textContent = 'Offline';
      }
    }

    // Update raw values
    const rawSoil = document.getElementById('mon-raw-soil');
    if (rawSoil) rawSoil.textContent = isOnline && r ? r.soil_raw_adc : '--';

    const rawRain = document.getElementById('mon-raw-rain');
    if (rawRain) rawRain.textContent = isOnline && r ? r.rain_raw_adc : '--';

    const rawLight = document.getElementById('mon-raw-light');
    if (rawLight) rawLight.textContent = isOnline && r ? r.light_raw : '--';
  },

  renderControlState() {
    const r = this.latestReading;
    const isOnline = this.status && this.status.online;

    const pumpIndicator = document.getElementById('pump-status-indicator');
    const pumpHeadline = document.getElementById('pump-state-headline');
    const pumpDesc = document.getElementById('pump-state-description');
    const startBtn = document.getElementById('btn-start-pump');
    const stopBtn = document.getElementById('btn-stop-pump');

    const isPumpOn = isOnline && r && r.pump_state === 'ON';

    if (pumpIndicator) {
      pumpIndicator.className = 'pump-status-indicator ' + (isPumpOn ? 'on' : 'off');
    }
    if (pumpHeadline) {
      pumpHeadline.textContent = isPumpOn ? 'PUMP IS RUNNING' : 'PUMP IS OFF';
    }
    if (pumpDesc) {
      if (!isOnline) {
        pumpDesc.textContent = 'ESP32 device is offline. Remote pump activation is disabled for electrical safety.';
      } else if (isPumpOn) {
        pumpDesc.textContent = 'Irrigation cycle in progress. Safety watchdog will stop pump if max run-time is reached.';
      } else {
        pumpDesc.textContent = 'Relay contact is open. Pump is safely idle.';
      }
    }

    // Enable/disable buttons based on state
    if (startBtn) {
      startBtn.disabled = !isOnline || isPumpOn;
    }
    if (stopBtn) {
      stopBtn.disabled = !isOnline || !isPumpOn;
    }

    // Mode tabs
    const currentMode = (r && r.operating_mode) || (this.status && this.status.current_mode) || 'AUTO';
    document.querySelectorAll('.mode-tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-mode') === currentMode);
    });
  },

  updateAlertBadges() {
    const unackCount = this.alerts.filter(a => !a.is_acknowledged).length;
    
    // Topbar badge
    const topDot = document.getElementById('alerts-badge-dot');
    if (topDot) topDot.style.display = unackCount > 0 ? 'block' : 'none';

    // Sidebar badge
    const sideBadge = document.getElementById('sidebar-alerts-badge');
    if (sideBadge) {
      sideBadge.style.display = unackCount > 0 ? 'inline-block' : 'none';
      sideBadge.textContent = unackCount;
    }
  },

  renderOfflineFallback() {
    const pill = document.getElementById('device-status-pill');
    const text = document.getElementById('device-status-text');
    if (pill && text) {
      pill.className = 'device-status-pill offline';
      text.textContent = 'Backend Offline';
    }
  },

  // -------------------------------------------------------------
  // 5. Irrigation Control & Confirmation Modal
  // -------------------------------------------------------------
  bindControls() {
    const startBtn = document.getElementById('btn-start-pump');
    const stopBtn = document.getElementById('btn-stop-pump');
    const modal = document.getElementById('pump-confirm-modal');
    const modalConfirm = document.getElementById('modal-btn-confirm');
    const modalCancel = document.getElementById('modal-btn-cancel');

    // Open confirmation dialog before starting pump
    if (startBtn) {
      startBtn.addEventListener('click', () => {
        if (!this.status || !this.status.online) {
          this.showToast('ESP32 device is reporting offline. Command will be queued for delivery.', 'warning');
        }
        if (modal) modal.classList.add('active');
      });
    }

    if (modalCancel && modal) {
      modalCancel.addEventListener('click', () => modal.classList.remove('active'));
    }

    if (modalConfirm && modal) {
      modalConfirm.addEventListener('click', async () => {
        modal.classList.remove('active');
        await this.executePumpStart();
      });
    }

    if (stopBtn) {
      stopBtn.addEventListener('click', async () => {
        await this.executePumpStop();
      });
    }

    // Mode tab click handler
    document.querySelectorAll('.mode-tab-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const newMode = btn.getAttribute('data-mode');
        try {
          await API.sendCommand({
            command_type: 'SET_MODE',
            mode: newMode,
            source: 'MANUAL_DASHBOARD',
            reason: `User switched mode to ${newMode}`
          });
          if (window.FirebaseService && FirebaseService.db) {
            FirebaseService.db.ref('aquasense/commands/latest').set({
              id: Date.now().toString(),
              command_type: 'SET_MODE',
              mode: newMode,
              created_at: new Date().toISOString(),
              status: 'PENDING'
            });
            FirebaseService.db.ref('aquasense/status/current_mode').set(newMode);
            FirebaseService.logEvent('mode_change', { mode: newMode });
          }
          this.showToast(`Switched operating mode to ${newMode}`, 'success');
          this.refreshAll();
        } catch (err) {
          this.showToast(`Failed to switch mode: ${err.message}`, 'error');
        }
      });
    });
  },

  async executePumpStart() {
    try {
      const durationSelect = document.getElementById('manual-duration-select');
      const duration = durationSelect ? parseInt(durationSelect.value, 10) : 15;

      const res = await API.sendCommand({
        command_type: 'PUMP_START',
        target_state: 'ON',
        duration_sec: duration,
        source: 'MANUAL_DASHBOARD',
        reason: `Manual pump activation for ${duration} seconds`
      });

      if (window.FirebaseService && FirebaseService.db) {
        FirebaseService.db.ref('aquasense/commands/latest').set({
          id: (res && res.command) ? res.command.id : Date.now().toString(),
          command_type: 'PUMP_START',
          target_state: 'ON',
          duration_sec: duration,
          created_at: new Date().toISOString(),
          status: 'PENDING'
        });
        FirebaseService.db.ref('aquasense/status/current_pump_state').set('ON');
        FirebaseService.logEvent('pump_start', { duration_sec: duration });
      }

      this.showToast(`Pump START command queued for ${duration}s.`, 'success');
      this.refreshAll();
    } catch (err) {
      this.showToast(`Start Command Failed: ${err.message}`, 'error');
    }
  },

  async executePumpStop() {
    try {
      const res = await API.sendCommand({
        command_type: 'PUMP_STOP',
        target_state: 'OFF',
        source: 'MANUAL_DASHBOARD',
        reason: 'Immediate manual pump stop request'
      });

      if (window.FirebaseService && FirebaseService.db) {
        FirebaseService.db.ref('aquasense/commands/latest').set({
          id: (res && res.command) ? res.command.id : Date.now().toString(),
          command_type: 'PUMP_STOP',
          target_state: 'OFF',
          duration_sec: 0,
          created_at: new Date().toISOString(),
          status: 'PENDING'
        });
        FirebaseService.db.ref('aquasense/status/current_pump_state').set('OFF');
        FirebaseService.logEvent('pump_stop', { reason: 'user_manual' });
      }

      this.showToast('Emergency STOP command sent to relay.', 'warning');
      this.refreshAll();
    } catch (err) {
      this.showToast(`Stop Command Failed: ${err.message}`, 'error');
    }
  },

  // -------------------------------------------------------------
  // 6. Settings & Sensor Calibration Form
  // -------------------------------------------------------------
  async bindSettingsForm() {
    const form = document.getElementById('settings-form');
    if (!form) return;

    // Load initial settings
    try {
      this.settings = await API.getSettings();
      this.populateSettingsForm(this.settings);
    } catch (err) {
      console.warn('Failed to load settings:', err);
    }

    form.addEventListener('submit', async (e) => {
      e.preventDefault();

      const dry = parseFloat(document.getElementById('setting-dry').value);
      const wet = parseFloat(document.getElementById('setting-wet').value);
      const maxRuntime = parseInt(document.getElementById('setting-max-runtime').value, 10);
      const cooldown = parseInt(document.getElementById('setting-cooldown').value, 10);
      const rainLockout = document.getElementById('setting-rain-lockout').checked;
      const defaultMode = document.getElementById('setting-default-mode').value;
      const dryRaw = parseInt(document.getElementById('setting-soil-dry-raw').value, 10);
      const wetRaw = parseInt(document.getElementById('setting-soil-wet-raw').value, 10);
      const timeout = parseInt(document.getElementById('setting-timeout').value, 10);

      // Client validation
      if (wet <= dry + 2.0) {
        this.showToast('Wet threshold must be at least 2% higher than dry threshold for safe hysteresis.', 'error');
        return;
      }
      if (dryRaw <= wetRaw + 200) {
        this.showToast('Soil dry calibration raw ADC must be greater than wet raw ADC.', 'error');
        return;
      }

      try {
        const updated = await API.updateSettings({
          dry_threshold: dry,
          wet_threshold: wet,
          max_pump_runtime_sec: maxRuntime,
          cooldown_duration_sec: cooldown,
          rain_lockout_enabled: rainLockout,
          default_mode: defaultMode,
          soil_dry_raw: dryRaw,
          soil_wet_raw: wetRaw,
          device_timeout_sec: timeout
        });
        this.settings = updated;
        this.showToast('Settings and calibration successfully updated!', 'success');
        this.refreshAll();
      } catch (err) {
        this.showToast(`Failed to update settings: ${err.message}`, 'error');
      }
    });
  },

  populateSettingsForm(s) {
    if (!s) return;
    if (document.getElementById('setting-dry')) document.getElementById('setting-dry').value = s.dry_threshold;
    if (document.getElementById('setting-wet')) document.getElementById('setting-wet').value = s.wet_threshold;
    if (document.getElementById('setting-max-runtime')) document.getElementById('setting-max-runtime').value = s.max_pump_runtime_sec;
    if (document.getElementById('setting-cooldown')) document.getElementById('setting-cooldown').value = s.cooldown_duration_sec;
    if (document.getElementById('setting-rain-lockout')) document.getElementById('setting-rain-lockout').checked = s.rain_lockout_enabled;
    if (document.getElementById('setting-default-mode')) document.getElementById('setting-default-mode').value = s.default_mode;
    if (document.getElementById('setting-soil-dry-raw')) document.getElementById('setting-soil-dry-raw').value = s.soil_dry_raw;
    if (document.getElementById('setting-soil-wet-raw')) document.getElementById('setting-soil-wet-raw').value = s.soil_wet_raw;
    if (document.getElementById('setting-timeout')) document.getElementById('setting-timeout').value = s.device_timeout_sec;
  },

  // -------------------------------------------------------------
  // 7. Sensor Analytics View
  // -------------------------------------------------------------
  async loadAnalyticsCharts(timeframe = '24h') {
    try {
      const readings = await API.getHistory(timeframe, 100);
      if (window.ChartsManager) {
        const dry = this.settings ? this.settings.dry_threshold : 15.0;
        const wet = this.settings ? this.settings.wet_threshold : 25.0;
        ChartsManager.initSoilMoistureChart('analytics-soil-canvas', readings, dry, wet);
        ChartsManager.initEnvChart('analytics-env-canvas', readings);
        ChartsManager.initLightChart('analytics-light-canvas', readings);
        ChartsManager.initPumpTimelineChart('analytics-pump-canvas', readings);
      }
    } catch (err) {
      console.warn('Analytics loading error:', err);
    }
  },

  // -------------------------------------------------------------
  // 8. Irrigation History Table & CSV Export
  // -------------------------------------------------------------
  async loadHistoryTable() {
    const tbody = document.getElementById('history-table-body');
    if (!tbody) return;

    try {
      const events = await API.getEvents({ limit: 50 });
      if (events.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding: 2rem; color: var(--color-text-dim);">No irrigation events recorded yet.</td></tr>';
        return;
      }

      tbody.innerHTML = events.map(e => {
        const d = new Date(e.timestamp);
        return `
          <tr>
            <td style="font-family: var(--font-mono); font-size: 0.75rem;">${d.toLocaleString()}</td>
            <td><strong>${e.event_type}</strong></td>
            <td>${e.soil_moisture !== null ? e.soil_moisture + '%' : '--'}</td>
            <td><span class="kpi-status-badge ${e.pump_state === 'ON' ? 'info' : 'healthy'}">${e.pump_state}</span></td>
            <td>${e.operating_mode}</td>
            <td>${e.reason}</td>
            <td>${e.duration_sec > 0 ? e.duration_sec + 's' : '--'}</td>
            <td><span style="font-size: 0.75rem; color: var(--color-text-muted);">${e.source}</span></td>
          </tr>
        `;
      }).join('');
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color: var(--color-error); padding: 1.5rem;">Failed to load events: ${err.message}</td></tr>`;
    }
  },

  // -------------------------------------------------------------
  // 9. Alerts View
  // -------------------------------------------------------------
  renderAlertsView() {
    const container = document.getElementById('alerts-list-container');
    if (!container) return;

    if (!this.alerts || this.alerts.length === 0) {
      container.innerHTML = `
        <div class="card" style="text-align: center; padding: 3rem; color: var(--color-text-dim);">
          <div style="font-size: 1.25rem; font-weight: 700; color: var(--color-text-main); margin-bottom: 0.5rem;">No Active Alerts</div>
          <div>All sensors, irrigation rules, and communication watchdogs are operating normally.</div>
        </div>
      `;
      return;
    }

    container.innerHTML = this.alerts.map(a => {
      const d = new Date(a.timestamp);
      const sevClass = a.severity === 'CRITICAL' ? 'critical' : (a.severity === 'WARNING' ? 'warning' : 'info');
      return `
        <div class="card" style="margin-bottom: 1rem; border-left: 4px solid var(--color-${sevClass === 'critical' ? 'error' : (sevClass === 'warning' ? 'warning' : 'info')});">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
            <div>
              <span class="kpi-status-badge ${sevClass}">${a.severity}</span>
              <strong style="margin-left: 0.5rem; font-size: 1rem;">${a.title}</strong>
            </div>
            <span style="font-size: 0.75rem; color: var(--color-text-dim);">${d.toLocaleTimeString()}</span>
          </div>
          <p style="font-size: 0.875rem; color: var(--color-text-main); margin-bottom: 0.5rem;">${a.explanation}</p>
          <div style="font-size: 0.8125rem; color: var(--color-text-muted); background: var(--color-bg-card-subtle); padding: 0.5rem 0.75rem; border-radius: var(--radius-sm); margin-bottom: 0.75rem;">
            <strong>Recommended Action:</strong> ${a.recommended_action}
          </div>
          ${!a.is_acknowledged ? `
            <button class="btn btn-outline" style="padding: 0.375rem 0.75rem; font-size: 0.75rem;" onclick="App.ackAlert(${a.id})">
              Acknowledge Alert
            </button>
          ` : '<span style="font-size: 0.75rem; color: var(--color-text-dim);">Acknowledged</span>'}
        </div>
      `;
    }).join('');
  },

  async ackAlert(alertId) {
    try {
      await API.acknowledgeAlert(alertId);
      this.showToast('Alert acknowledged.', 'success');
      this.refreshAll();
    } catch (err) {
      this.showToast(`Failed to acknowledge alert: ${err.message}`, 'error');
    }
  },

  // -------------------------------------------------------------
  // 10. Device Health View
  // -------------------------------------------------------------
  renderHealthView() {
    const s = this.status;
    const r = this.latestReading;

    const onlineEl = document.getElementById('health-online-status');
    const hbEl = document.getElementById('health-last-heartbeat');
    const fwEl = document.getElementById('health-firmware');
    const rssiEl = document.getElementById('health-rssi');
    const batteryEl = document.getElementById('health-battery');

    if (onlineEl) {
      if (s && s.online) {
        onlineEl.innerHTML = `<span class="badge-status-pill online"><span class="dot online"></span> ${s.is_simulated ? 'ESP Online (Sim)' : 'ESP Online'}</span>`;
      } else {
        onlineEl.innerHTML = `<span class="badge-status-pill offline"><span class="dot offline"></span> ESP Offline</span>`;
      }
    }

    if (hbEl) hbEl.textContent = s && s.last_heartbeat ? new Date(s.last_heartbeat).toLocaleString() : '--';
    if (fwEl) fwEl.textContent = s && s.firmware_version ? s.firmware_version : 'v1.0.0-esp32';
    if (rssiEl) rssiEl.textContent = s && s.wifi_rssi !== null ? `${s.wifi_rssi} dBm (Good)` : '--';
    if (batteryEl) {
      if (r && r.battery_voltage) {
        batteryEl.textContent = `${r.battery_voltage.toFixed(2)} V`;
      } else {
        batteryEl.textContent = 'Not Measured (Direct Power)';
      }
    }
  },

  // -------------------------------------------------------------
  // 11. Testing Simulator Controls
  // -------------------------------------------------------------
  bindSimulatorControls() {
    const toggleBtn = document.getElementById('btn-toggle-simulator');
    const dryBtn = document.getElementById('btn-sim-dry');
    const rainBtn = document.getElementById('btn-sim-rain');

    if (toggleBtn) {
      toggleBtn.addEventListener('click', async () => {
        const currentlySim = this.status && this.status.is_simulated;
        try {
          await API.toggleSimulator(!currentlySim);
          this.showToast(currentlySim ? 'Simulator Deactivated' : 'Software Test Simulator Activated', 'info');
          this.refreshAll();
        } catch (err) {
          this.showToast(`Simulator error: ${err.message}`, 'error');
        }
      });
    }

    if (dryBtn) {
      dryBtn.addEventListener('click', async () => {
        try {
          await API.stepSimulator(false, true); // force dry soil (<15%)
          this.showToast('Simulated drought (<15% soil moisture). Check automated pump start!', 'warning');
          this.refreshAll();
        } catch (err) {
          this.showToast(err.message, 'error');
        }
      });
    }

    if (rainBtn) {
      rainBtn.addEventListener('click', async () => {
        try {
          await API.stepSimulator(true, false); // force rain
          this.showToast('Simulated rain precipitation. Check rain lockout!', 'info');
          this.refreshAll();
        } catch (err) {
          this.showToast(err.message, 'error');
        }
      });
    }
  },

  // -------------------------------------------------------------
  // 12. Toast Feedback Manager
  // -------------------------------------------------------------
  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 4000);
  }
};

document.addEventListener('DOMContentLoaded', () => {
  App.init();
});

window.App = App;
