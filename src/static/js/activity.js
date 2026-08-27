// =========================================
// ACTIVITY PAGE
// =========================================

(function () {

  // State
  var currentPage    = 1;
  var currentAction  = '';
  var currentStatus  = '';
  var currentSearch  = '';
  var totalItems     = 0;
  var perPage        = 20;
  var totalPages     = 1;

  // Initialize
  document.addEventListener('DOMContentLoaded', function() {
    loadStats();
    loadActivities();
    setupFilters();
    setupSearch();
  });

  // Load stats
  async function loadStats() {
    try {
      var response = await fetch('/api/activities/stats');
      var stats   = await response.json();

      document.getElementById('stat-total').textContent = stats.total_events       || 0;
      document.getElementById('stat-ocr').textContent   = stats.ocr_runs           || 0;
      document.getElementById('stat-ceisa').textContent = stats.ceisa_submissions  || 0;
      document.getElementById('stat-last').textContent  = stats.last_activity
        ? formatDateTime(stats.last_activity)
        : 'No activity yet';
    } catch (error) {
      console.error('Failed to load stats:', error);
      document.getElementById('stat-total').textContent = '0';
      document.getElementById('stat-ocr').textContent   = '0';
      document.getElementById('stat-ceisa').textContent = '0';
      document.getElementById('stat-last').textContent  = 'Error loading';
    }
  }

  // Load activities
  async function loadActivities() {
    var tbody = document.getElementById('activitiesTable');
    tbody.innerHTML = '<tr><td colspan="5"><div class="loading"><div class="spinner"></div></div></td></tr>';

    try {
      var params = new URLSearchParams();
      params.append('page', currentPage);
      params.append('per_page', perPage);
      if (currentAction) params.append('action', currentAction);
      if (currentStatus) params.append('status', currentStatus);
      if (currentSearch) params.append('search', currentSearch);

      var response = await fetch('/api/activities?' + params);
      var data     = await response.json();

      totalItems  = data.total;
      totalPages  = data.pages;
      renderTable(data.items);
      renderPagination();
    } catch (error) {
      console.error('Failed to load activities:', error);
      tbody.innerHTML = '<tr><td colspan="5"><div class="empty-state"><div class="empty-state-icon">!</div><h3>Failed to load activities</h3><p>Could not connect to the server. Please try again.</p></div></td></tr>';
    }
  }

  // Render table
  function renderTable(items) {
    var tbody = document.getElementById('activitiesTable');

    if (items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5"><div class="empty-state"><div class="empty-state-icon">*</div><h3>No activities found</h3><p>No activity records match your current filters.</p></div></td></tr>';
      return;
    }

    var html = '';
    for (var i = 0; i < items.length; i++) {
      var act = items[i];
      var meta = act.metadata || {};
      var metaTitle = getMetaTitle(act.action, meta);
      var metaRows  = getMetaRows(act.action, meta);

      html += '<tr>' +
        '<td>' +
          '<div class="action-title">' + escHtml(act.action) + '</div>' +
          '<span class="status-badge ' + escHtml(act.status || 'draft') + '">' + escHtml(act.status || 'unknown') + '</span>' +
        '</td>' +
        '<td class="desc-text">' + escHtml(act.description) + '</td>' +
        '<td>' +
          (act.reference_code
            ? '<div class="ref-code">' + escHtml(act.reference_code) + '</div>'
            : '<div class="ref-sub">-</div>'
          ) +
          '<div class="ref-sub">ID: ' + (act.entity_id || '-') + '</div>' +
        '</td>' +
        '<td>' +
          (Object.keys(meta).length > 0
            ? '<div class="metadata-box"><div class="meta-title">' + metaTitle + '</div>' + metaRows + '</div>'
            : '<div class="ref-sub">-</div>'
          ) +
        '</td>' +
        '<td class="date-text">' + (act.created_at ? formatDateTime(act.created_at) : '-') + '</td>' +
      '</tr>';
    }
    tbody.innerHTML = html;
  }

  function getMetaTitle(action, meta) {
    if (action === 'OCR Process') return 'OCR METADATA';
    if (action === 'Declaration Approve') return 'CEISA FEEDBACK';
    if (action === 'Declaration Reject') return 'CEISA FEEDBACK';
    if (action === 'Declaration Send') return 'SUBMISSION DETAIL';
    if (action === 'Declaration Delete') return 'DELETION DETAIL';
    return 'WORKFLOW NOTE';
  }

  function getMetaRows(action, meta) {
    if (action === 'OCR Process') {
      var tags = '';
      if (meta.documents && meta.documents.length) {
        for (var t = 0; t < meta.documents.length; t++) {
          tags += '<span class="tag">' + escHtml(meta.documents[t]) + '</span>';
        }
      }
      return '<div class="meta-row">Engine: ' + escHtml(meta.engine || 'HybridExtractor') + '</div>' +
        (meta.confidence !== undefined ? '<div class="meta-row">Confidence: ' + meta.confidence + '%</div>' : '') +
        (meta.items_extracted !== undefined ? '<div class="meta-row">Items: ' + meta.items_extracted + '</div>' : '') +
        (tags ? '<div class="meta-tags">' + tags + '</div>' : '');
    }

    if (action === 'Declaration Approve' || action === 'Declaration Reject') {
      return '<div class="meta-row">Status: ' + escHtml(meta.cesa_status || meta.status || (action === 'Declaration Approve' ? 'Approved' : 'Rejected')) + '</div>' +
        (meta.cesa_ref ? '<div class="meta-row">CESA Ref: ' + escHtml(meta.cesa_ref) + '</div>' : '') +
        '<div class="meta-row meta-muted">' + escHtml(meta.message || 'Declaration processed by CEISA simulation.') + '</div>';
    }

    if (action === 'Declaration Send') {
      return '<div class="meta-row">AJU: ' + escHtml(meta.aju_number || '-') + '</div>' +
        '<div class="meta-row">Confidence: ' + (meta.confidence != null ? meta.confidence : '-') + '%</div>';
    }

    if (action === 'Declaration Delete') {
      return '<div class="meta-row meta-muted">' + escHtml(meta.description || 'Declaration removed from the system.') + '</div>';
    }

    if (action === 'Declaration Create') {
      return '<div class="meta-row">AJU: ' + escHtml(meta.aju_number || '-') + '</div>' +
        (meta.confidence !== undefined ? '<div class="meta-row">Confidence: ' + meta.confidence + '%</div>' : '') +
        (meta.quality_score ? '<div class="meta-row">Quality: ' + escHtml(meta.quality_score) + '</div>' : '') +
        ((meta.documents && meta.documents.length) ? '<div class="meta-row">Documents: ' + escHtml(meta.documents.join(', ')) + '</div>' : '');
    }

    // Generic fallback
    var rows = '';
    var keys = Object.keys(meta).filter(function(k) { return k !== 'error'; }).slice(0, 3);
    for (var k = 0; k < keys.length; k++) {
      rows += '<div class="meta-row">' + escHtml(keys[k]) + ': ' + escHtml(String(meta[keys[k]])) + '</div>';
    }
    return rows;
  }

  // Render pagination
  function renderPagination() {
    var bar      = document.getElementById('paginationBar');
    var infoEl   = document.getElementById('paginationInfo');
    var controlsEl = document.getElementById('paginationControls');

    if (totalItems === 0) {
      bar.style.display = 'none';
      return;
    }
    bar.style.display = 'flex';

    var start = (currentPage - 1) * perPage + 1;
    var end   = Math.min(currentPage * perPage, totalItems);
    infoEl.textContent = 'Showing ' + start + '-' + end + ' of ' + totalItems + ' activities';

    var pages = getPageNumbers(totalPages);

    var prevSvg = '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><polyline points="15 18 9 12 15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    var nextSvg = '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><polyline points="9 18 15 12 9 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

    var html = '<button class="page-btn" onclick="goToPage(' + (currentPage - 1) + ')" ' + (currentPage === 1 ? 'disabled' : '') + ' title="Previous">' + prevSvg + '</button>';

    for (var p = 0; p < pages.length; p++) {
      if (pages[p] === '...') {
        html += '<span class="page-ellipsis" style="min-width:34px;height:34px;display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:13px;">...</span>';
      } else {
        html += '<button class="page-btn' + (pages[p] === currentPage ? ' active' : '') + '" onclick="goToPage(' + pages[p] + ')">' + pages[p] + '</button>';
      }
    }

    html += '<button class="page-btn" onclick="goToPage(' + (currentPage + 1) + ')" ' + (currentPage === totalPages ? 'disabled' : '') + ' title="Next">' + nextSvg + '</button>';

    controlsEl.innerHTML = html;
  }

  function getPageNumbers(totalPages) {
    if (totalPages <= 7) {
      var nums = [];
      for (var i = 1; i <= totalPages; i++) nums.push(i);
      return nums;
    }
    var pages = [];
    if (currentPage <= 4) {
      for (var i = 1; i <= 5; i++) pages.push(i);
      pages.push('...');
      pages.push(totalPages);
    } else if (currentPage >= totalPages - 3) {
      pages.push(1);
      pages.push('...');
      for (var i = totalPages - 4; i <= totalPages; i++) pages.push(i);
    } else {
      pages.push(1);
      pages.push('...');
      for (var i = currentPage - 1; i <= currentPage + 1; i++) pages.push(i);
      pages.push('...');
      pages.push(totalPages);
    }
    return pages;
  }

  function goToPage(page) {
    if (page < 1 || page > totalPages) return;
    currentPage = page;
    loadActivities();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  // Setup filters
  function setupFilters() {
    document.getElementById('actionFilter').addEventListener('change', function(e) {
      currentAction = e.target.value;
      currentPage   = 1;
      loadActivities();
      loadStats();
    });

    document.getElementById('statusFilter').addEventListener('change', function(e) {
      currentStatus = e.target.value;
      currentPage   = 1;
      loadActivities();
    });
  }

  // Setup search with debounce
  function setupSearch() {
    var input  = document.getElementById('searchInput');
    var timeout;
    input.addEventListener('input', function() {
      clearTimeout(timeout);
      timeout = setTimeout(function() {
        currentSearch = input.value.trim();
        currentPage   = 1;
        loadActivities();
      }, 400);
    });
  }

  // Format datetime
  function formatDateTime(isoString) {
    if (!isoString) return '-';
    var date    = new Date(isoString);
    var options = {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit', hour12: false,
      timeZone: 'Asia/Jakarta',
    };
    return date.toLocaleString('en-GB', options).replace(',', '') + ' WIB';
  }

  // Escape HTML
  function escHtml(str) {
    if (str === null || str === undefined) return '';
    var div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }

  // Expose to global scope
  window.goToPage = goToPage;

})();
