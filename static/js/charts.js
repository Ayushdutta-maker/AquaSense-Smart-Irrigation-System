/**
 * AquaSense Chart Manager (Chart.js integration)
 * Precision styling inspired by AeuxGlobal emerald/obsidian clean-tech analytics.
 */

const ChartsManager = {
  instances: {},

  getThemeColors() {
    const isDark = document.body.classList.contains('dark-mode');
    return {
      textColor: isDark ? '#8E9F96' : '#65796F',
      textMuted: isDark ? '#52665B' : '#96A89F',
      gridColor: isDark ? 'rgba(255, 255, 255, 0.05)' : '#EDF3EF',
      barGrey: isDark ? '#182921' : '#DCE5DF',
      accentGreen: '#22C55E',
      accentGreenBright: '#2EE59D',
      accentGreenSoft: 'rgba(34, 197, 94, 0.15)',
      warningOrange: '#E79B35',
      coralRed: '#E54848',
      infoBlue: '#258BD4',
      tooltipBg: '#0D1612',
      tooltipText: '#FFFFFF'
    };
  },

  destroy(chartId) {
    if (this.instances[chartId]) {
      this.instances[chartId].destroy();
      delete this.instances[chartId];
    }
  },

  formatTimeLabel(isoString) {
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return isoString;
    }
  },

  // 1. Overview Bar & Spark Chart (Exact "Climate Change Index" Look)
  initOverviewTrend(canvasId, readings) {
    this.destroy(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const theme = this.getThemeColors();

    // If no readings, provide a clean preview pattern
    let sampleReadings = readings;
    if (!readings || readings.length === 0) {
      sampleReadings = Array.from({ length: 28 }, (_, i) => ({
        timestamp: new Date(Date.now() - (28 - i) * 120000).toISOString(),
        soil_moisture: 18 + Math.sin(i * 0.4) * 6 + (i > 20 ? 4 : 0)
      }));
    }

    const labels = sampleReadings.map(r => this.formatTimeLabel(r.timestamp));
    const data = sampleReadings.map(r => r.soil_moisture);

    // Color bars: neutral grey for earlier, bright green for the active recent range!
    const activeCutoffIndex = Math.max(0, sampleReadings.length - 8);
    const backgroundColors = sampleReadings.map((_, i) =>
      i >= activeCutoffIndex ? theme.accentGreen : theme.barGrey
    );

    this.instances[canvasId] = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Soil Moisture (%)',
            data: data,
            backgroundColor: backgroundColors,
            borderRadius: 3,
            barPercentage: 0.5,
            categoryPercentage: 0.8
          },
          {
            type: 'line',
            label: 'Optimal Threshold (25%)',
            data: sampleReadings.map(() => 25.0),
            borderColor: theme.accentGreen,
            borderWidth: 1.5,
            borderDash: [4, 4],
            pointRadius: 0,
            fill: false
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: theme.tooltipBg,
            titleColor: theme.textMuted,
            bodyColor: theme.tooltipText,
            cornerRadius: 8,
            padding: 8,
            displayColors: false,
            callbacks: {
              title: (items) => items[0].label,
              label: (ctx) => `Moisture: ${ctx.parsed.y.toFixed(1)}%`
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: theme.textMuted,
              maxTicksLimit: 7,
              font: { size: 10, family: 'Plus Jakarta Sans' }
            }
          },
          y: {
            min: 0,
            max: 100,
            grid: {
              color: theme.gridColor,
              borderDash: [3, 3]
            },
            ticks: {
              color: theme.textMuted,
              stepSize: 20,
              font: { size: 10, family: 'Plus Jakarta Sans' }
            }
          }
        }
      }
    });
  },

  // 2. Dedicated Soil Moisture Analytics Chart
  initSoilMoistureChart(canvasId, readings, dryThresh = 15.0, wetThresh = 25.0) {
    this.destroy(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const theme = this.getThemeColors();
    const labels = readings.map(r => this.formatTimeLabel(r.timestamp));
    const moistureData = readings.map(r => r.soil_moisture);

    this.instances[canvasId] = new Chart(canvas, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Soil Moisture (%)',
            data: moistureData,
            borderColor: theme.accentGreen,
            backgroundColor: theme.accentGreenSoft,
            borderWidth: 2.5,
            fill: true,
            tension: 0.35,
            pointRadius: readings.length > 30 ? 0 : 3,
            pointHoverRadius: 6
          },
          {
            label: `Dry Trigger (${dryThresh}%)`,
            data: readings.map(() => dryThresh),
            borderColor: theme.warningOrange,
            borderWidth: 1.5,
            borderDash: [5, 5],
            pointRadius: 0,
            fill: false
          },
          {
            label: `Wet Cutoff (${wetThresh}%)`,
            data: readings.map(() => wetThresh),
            borderColor: theme.accentGreenBright,
            borderWidth: 1.5,
            borderDash: [5, 5],
            pointRadius: 0,
            fill: false
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            labels: {
              color: theme.textColor,
              boxWidth: 10,
              font: { size: 11, family: 'Plus Jakarta Sans' }
            }
          },
          tooltip: {
            backgroundColor: theme.tooltipBg,
            titleColor: theme.textMuted,
            bodyColor: theme.tooltipText,
            cornerRadius: 8,
            padding: 8
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: theme.textMuted, maxTicksLimit: 8, font: { size: 10 } }
          },
          y: {
            min: 0,
            max: 100,
            grid: { color: theme.gridColor, borderDash: [3, 3] },
            ticks: { color: theme.textMuted, font: { size: 10 } }
          }
        }
      }
    });
  },

  // 3. Environmental Temperature & Humidity Chart
  initEnvChart(canvasId, readings) {
    this.destroy(canvasId);
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const theme = this.getThemeColors();
    const labels = readings.map(r => this.formatTimeLabel(r.timestamp));

    this.instances[canvasId] = new Chart(canvas, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Temperature (°C)',
            data: readings.map(r => r.temperature),
            borderColor: theme.warningOrange,
            backgroundColor: 'transparent',
            borderWidth: 2,
            tension: 0.3,
            yAxisID: 'yTemp'
          },
          {
            label: 'Humidity (%)',
            data: readings.map(r => r.humidity),
            borderColor: theme.infoBlue,
            backgroundColor: 'transparent',
            borderWidth: 2,
            tension: 0.3,
            yAxisID: 'yHum'
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            labels: {
              color: theme.textColor,
              boxWidth: 10,
              font: { size: 11, family: 'Plus Jakarta Sans' }
            }
          },
          tooltip: {
            backgroundColor: theme.tooltipBg,
            titleColor: theme.textMuted,
            bodyColor: theme.tooltipText,
            cornerRadius: 8,
            padding: 8
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: theme.textMuted, maxTicksLimit: 8, font: { size: 10 } }
          },
          yTemp: {
            type: 'linear',
            position: 'left',
            grid: { color: theme.gridColor, borderDash: [3, 3] },
            ticks: { color: theme.warningOrange, font: { size: 10 } }
          },
          yHum: {
            type: 'linear',
            position: 'right',
            min: 0,
            max: 100,
            grid: { display: false },
            ticks: { color: theme.infoBlue, font: { size: 10 } }
          }
        }
      }
    });
  },

  updateAllThemes() {
    Object.keys(this.instances).forEach(id => {
      const chart = this.instances[id];
      const theme = this.getThemeColors();
      if (chart.options.scales.x) chart.options.scales.x.ticks.color = theme.textMuted;
      if (chart.options.scales.y) {
        chart.options.scales.y.ticks.color = theme.textMuted;
        chart.options.scales.y.grid.color = theme.gridColor;
      }
      chart.update();
    });
  }
};

window.ChartsManager = ChartsManager;
