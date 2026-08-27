// =========================================
// DASHBOARD PAGE
// =========================================

(function () {

  // Load dashboard stats on page load
  document.addEventListener('DOMContentLoaded', function() {
    loadDashboardStats();
  });

  // Load dashboard statistics from API
  async function loadDashboardStats() {
    try {
      const response = await fetch('/api/dashboard');
      if (!response.ok) {
        throw new Error('Failed to load dashboard stats');
      }

      const data = await response.json();
      if (data.success) {
        updateSummaryCards(data.summary);
        updateOperationalCharts(data.operational);
      }
    } catch (error) {
      console.error('Dashboard load error:', error);
      showToast('Failed to load dashboard data', 'error');
    }
  }

  // Update summary stat cards
  function updateSummaryCards(summary) {
    document.getElementById('saved-records').textContent  = summary.saved_records;
    document.getElementById('ceisa-ready').textContent    = summary.ceisa_ready;
    document.getElementById('needs-review').textContent    = summary.needs_review;
    document.getElementById('ceisa-approved').textContent  = summary.ceisa_approved;
  }

  // Update operational declaration overview charts
  function updateOperationalCharts(operational) {
    // Update count values
    document.getElementById('ci-count').textContent           = operational.ci_count;
    document.getElementById('pl-count').textContent           = operational.pl_count;
    document.getElementById('bl-count').textContent           = operational.bl_count;
    document.getElementById('ceisa-ready-count').textContent  = operational.ceisa_ready_count;

    // Update KPI values
    document.getElementById('avg-confidence').textContent = operational.avg_confidence + '%';
    document.getElementById('activity-volume').textContent = operational.activity_volume;

    // Calculate bar heights (max 100px, scale based on max value)
    const maxValue    = Math.max(operational.ci_count, operational.pl_count, operational.bl_count, operational.ceisa_ready_count, 1);
    const baseHeight  = 30;  // Minimum height percentage
    const scaleFactor = 100 - baseHeight;

    const ciHeight    = baseHeight + (operational.ci_count           / maxValue) * scaleFactor;
    const plHeight    = baseHeight + (operational.pl_count           / maxValue) * scaleFactor;
    const blHeight    = baseHeight + (operational.bl_count           / maxValue) * scaleFactor;
    const ceisaHeight = baseHeight + (operational.ceisa_ready_count  / maxValue) * scaleFactor;

    // Animate bar fills
    setTimeout(function() {
      document.getElementById('ci-bar-fill').style.height    = ciHeight    + '%';
      document.getElementById('pl-bar-fill').style.height    = plHeight    + '%';
      document.getElementById('bl-bar-fill').style.height    = blHeight    + '%';
      document.getElementById('ceisa-bar-fill').style.height = ceisaHeight + '%';
    }, 100);
  }

  // Refresh dashboard data
  function refreshDashboard() {
    // Reset bar heights
    document.getElementById('ci-bar-fill').style.height    = '0%';
    document.getElementById('pl-bar-fill').style.height    = '0%';
    document.getElementById('bl-bar-fill').style.height    = '0%';
    document.getElementById('ceisa-bar-fill').style.height = '0%';

    // Reload data
    loadDashboardStats();
    showToast('Dashboard refreshed', 'success');
  }

  // Show toast notification
  function showToast(message, type) {
    if (type === undefined) type = 'info';
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className   = 'toast ' + type + ' show';
    setTimeout(function() {
      toast.classList.remove('show');
    }, 3000);
  }

  // Expose to global scope (inline onclick)
  window.refreshDashboard = refreshDashboard;

})();
