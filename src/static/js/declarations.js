// =========================================
// DECLARATIONS PAGE
// =========================================

(function () {

  // State
  var currentFilter   = '';
  var searchQuery     = '';
  var shipments       = [];
  var totalCount     = 0;
  var currentPage     = 1;
  var itemsPerPage    = 10;
  var confirmCallback = null;

  // Initialize
  document.addEventListener('DOMContentLoaded', function() {
    loadShipments();
    setupFilters();
    setupSearch();

    // Confirm button click
    document.getElementById('confirmBtn').addEventListener('click', function() {
      if (confirmCallback) {
        var cb = confirmCallback;
        closeConfirmModal();
        cb();
      }
    });

    // Close modal on outside click
    document.getElementById('detailModal').addEventListener('click', function(e) {
      if (e.target.classList.contains('modal-overlay')) closeModal();
    });

    // Close modal on Escape
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        closeModal();
        closeConfirmModal();
      }
    });
  });

  // =========================================
  // Load Shipments
  // =========================================
  async function loadShipments() {
    try {
      var offset    = (currentPage - 1) * itemsPerPage;
      var params    = new URLSearchParams();
      params.append('limit', itemsPerPage);
      params.append('offset', offset);
      if (currentFilter) params.append('status', currentFilter);
      if (searchQuery) params.append('search', searchQuery);

      var response = await fetch('/api/shipments?' + params);
      var data     = await response.json();

      shipments   = data.items || [];
      totalCount = data.total  || 0;
      renderTable();
      renderPagination();
    } catch (error) {
      console.error('Failed to load shipments:', error);
      showToast('Failed to load shipments', 'error');
    }
  }

  // =========================================
  // Render Table
  // =========================================
  function renderTable() {
    var tbody = document.getElementById('shipmentsTable');

    if (shipments.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8">' +
        '<div class="empty-state">' +
          '<div class="empty-state-icon">!</div>' +
          '<h3>No declarations found</h3>' +
          '<p>Upload documents in Smart Upload to create declarations.</p>' +
          '<a href="/smart-upload" class="btn" style="display:inline-block;margin-top:12px;padding:10px 20px;background:var(--primary);color:white;border-radius:var(--radius);text-decoration:none;font-weight:500;">Go to Smart Upload</a>' +
        '</div>' +
      '</td></tr>';
      return;
    }

    var html = '';
    for (var i = 0; i < shipments.length; i++) {
      var s = shipments[i];
      html += '<tr>' +
        '<td><strong>' + (s.reference_code || '-') + '</strong></td>' +
        '<td>' + (s.aju_number || '-') + '</td>' +
        '<td>' + ((s.documents_processed && s.documents_processed.length) ? escHtml(s.documents_processed.join(', ')) : '-') + '</td>' +
        '<td>' + (s.total_amount || '-') + '</td>' +
        '<td>' +
          '<div class="confidence-cell">' +
            '<span>' + (s.extraction_confidence || 0) + '%</span>' +
            '<div class="confidence-bar">' +
              '<div class="confidence-fill confidence-' + getConfidenceClass(s.extraction_confidence) + '" style="width:' + (s.extraction_confidence || 0) + '%"></div>' +
            '</div>' +
          '</div>' +
        '</td>' +
        '<td>' +
          '<span class="status-badge status-' + escHtml((s.status || '-').toLowerCase().replace(/\s+/g, '-')) + '">' + escHtml(s.status || '-') + '</span>' +
          (s.ceisa_id_header ? '<div class="ceisa-id-tag">CEISA: ' + escHtml(s.ceisa_id_header) + '</div>' : '') +
        '</td>' +
        '<td>' + (s.updated_at ? formatDateTime(s.updated_at) : '-') + '</td>' +
        '<td><div class="action-buttons">' +
          // View
          '<button class="action-btn view" onclick="viewDetail(' + s.id + ')" title="View Details">' +
            '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
              '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" stroke="currentColor" stroke-width="2"/>' +
              '<circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2"/>' +
            '</svg>' +
          '</button>' +
          // Send
          ((s.status === 'Draft Valid' || s.status === 'Draft Invalid')
            ? '<button class="action-btn send" onclick="sendShipment(' + s.id + ')" title="Kirim ke CEISA 4.0">' +
                '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
                  '<line x1="22" y1="2" x2="11" y2="13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' +
                  '<polygon points="22 2 15 22 11 13 2 9 22 2" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' +
                '</svg>' +
              '</button>'
            : ''
          ) +
          // Preview CEISA
          ((s.status === 'Sent' && s.ceisa_id_header)
            ? '<button class="action-btn preview-ceisa" onclick="previewCeisa(' + s.id + ')" title="Preview CEISA JSON">' +
                '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
                  '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" stroke="currentColor" stroke-width="2"/>' +
                  '<circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2"/>' +
                '</svg>' +
              '</button>'
            : ''
          ) +
          // Delete
          '<button class="action-btn delete" onclick="deleteShipment(' + s.id + ')" title="Delete">' +
            '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
              '<polyline points="3 6 5 6 21 6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' +
              '<path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' +
            '</svg>' +
          '</button>' +
        '</div></td>' +
      '</tr>';
    }
    tbody.innerHTML = html;
  }

  // =========================================
  // Pagination
  // =========================================
  function renderPagination() {
    var bar      = document.getElementById('paginationBar');
    var info     = document.getElementById('paginationInfo');
    var controls = document.getElementById('paginationControls');

    if (totalCount === 0) {
      bar.style.display = 'none';
      return;
    }
    bar.style.display = 'flex';

    var start = (currentPage - 1) * itemsPerPage + 1;
    var end   = Math.min(currentPage * itemsPerPage, totalCount);
    info.textContent = 'Showing ' + start + '-' + end + ' of ' + totalCount + ' declarations';

    var totalPages = Math.ceil(totalCount / itemsPerPage);
    var pages      = getPageNumbers(totalPages);

    var prevSvg = '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><polyline points="15 18 9 12 15 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    var nextSvg = '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><polyline points="9 18 15 12 9 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

    var html = '<button class="page-btn" onclick="goToPage(' + (currentPage - 1) + ')" ' + (currentPage === 1 ? 'disabled' : '') + ' title="Previous">' + prevSvg + '</button>';

    for (var p = 0; p < pages.length; p++) {
      if (pages[p] === '...') {
        html += '<span class="page-ellipsis">...</span>';
      } else {
        html += '<button class="page-btn' + (pages[p] === currentPage ? ' active' : '') + '" onclick="goToPage(' + pages[p] + ')">' + pages[p] + '</button>';
      }
    }

    html += '<button class="page-btn" onclick="goToPage(' + (currentPage + 1) + ')" ' + (currentPage === totalPages ? 'disabled' : '') + ' title="Next">' + nextSvg + '</button>';

    controls.innerHTML = html;
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
    var totalPages = Math.ceil(totalCount / itemsPerPage);
    if (page < 1 || page > totalPages) return;
    currentPage = page;
    loadShipments();
  }

  function changePageSize(size) {
    itemsPerPage = parseInt(size);
    currentPage  = 1;
    loadShipments();
  }

  // =========================================
  // Setup Filters & Search
  // =========================================
  function setupFilters() {
    var select = document.getElementById('statusFilter');
    select.addEventListener('change', function() {
      currentFilter = select.value;
      currentPage  = 1;
      loadShipments();
    });
  }

  function setupSearch() {
    var input  = document.getElementById('searchInput');
    var timeout;
    input.addEventListener('input', function() {
      clearTimeout(timeout);
      timeout = setTimeout(function() {
        searchQuery = input.value.trim();
        currentPage = 1;
        loadShipments();
      }, 300);
    });
  }

  // =========================================
  // View Detail
  // =========================================
  async function viewDetail(id) {
    try {
      var response = await fetch('/api/shipments/' + id);
      var s        = await response.json();

      var fieldsHtml = '';
      if (s.header_fields && Object.keys(s.header_fields).length > 0) {
        var fieldsArr = [];
        for (var key in s.header_fields) {
          var val = s.header_fields[key];
          fieldsArr.push('<div class="detail-item">' +
            '<div class="detail-label">' + escHtml(key) + '</div>' +
            '<div class="detail-value">' + escHtml(typeof val === 'object' ? (val.value || val) : val) + '</div>' +
          '</div>');
        }
        fieldsHtml = '<h4 class="detail-section-title">Extracted Fields</h4><div class="detail-grid">' + fieldsArr.join('') + '</div>';
      }

      document.getElementById('modalBody').innerHTML =
        '<div class="detail-grid">' +
          '<div class="detail-item"><div class="detail-label">Reference Code</div><div class="detail-value">' + escHtml(s.reference_code || '-') + '</div></div>' +
          '<div class="detail-item"><div class="detail-label">AJU Number</div><div class="detail-value">' + escHtml(s.aju_number || '-') + '</div></div>' +
          '<div class="detail-item"><div class="detail-label">Status</div><div class="detail-value"><span class="status-badge status-' + escHtml((s.status || '-').toLowerCase().replace(/\s+/g, '-')) + '">' + escHtml(s.status || '-') + '</span></div></div>' +
          '<div class="detail-item"><div class="detail-label">Quality Score</div><div class="detail-value">' + escHtml(s.quality_score || '-') + '</div></div>' +
          '<div class="detail-item"><div class="detail-label">Documents</div><div class="detail-value">' + ((s.documents_processed && s.documents_processed.length) ? escHtml(s.documents_processed.join(', ')) : '-') + '</div></div>' +
          '<div class="detail-item"><div class="detail-label">Total Amount</div><div class="detail-value">' + escHtml(s.total_amount || '-') + '</div></div>' +
          '<div class="detail-item"><div class="detail-label">Confidence</div><div class="detail-value">' + (s.extraction_confidence || 0) + '%</div></div>' +
          '<div class="detail-item"><div class="detail-label">Created</div><div class="detail-value">' + (s.created_at ? formatDateTime(s.created_at) : '-') + '</div></div>' +
        '</div>' + fieldsHtml;

      document.getElementById('detailModal').classList.add('show');
    } catch (error) {
      console.error('Failed to load detail:', error);
      showToast('Failed to load details', 'error');
    }
  }

  // =========================================
  // Modals
  // =========================================
  function closeModal() {
    document.getElementById('detailModal').classList.remove('show');
  }

  function showConfirmModal(title, message, confirmText, buttonClass, callback) {
    document.getElementById('confirmTitle').textContent  = title;
    document.getElementById('confirmMessage').textContent = message;
    var btn = document.getElementById('confirmBtn');
    btn.textContent = confirmText;
    btn.className   = 'confirm-btn ' + buttonClass;
    confirmCallback = callback;
    document.getElementById('confirmModal').classList.add('show');
  }

  function closeConfirmModal() {
    document.getElementById('confirmModal').classList.remove('show');
    confirmCallback = null;
  }

  // =========================================
  // Send Shipment to CEISA 4.0
  // =========================================
  async function sendShipment(id) {
    showConfirmModal(
      'Kirim ke CEISA 4.0',
      'Kirim declaration ini ke sistem CEISA 4.0 via Host-to-Host? Pastikan data sudah benar karena tidak dapat dibatalkan.',
      'Kirim',
      'primary',
      async function() {
        try {
          var response = await fetch('/api/shipments/' + id + '/send', { method: 'POST' });
          var data = await response.json();
          if (response.ok) {
            showToast('Berhasil dikirim ke CEISA! idHeader: ' + (data.ceisa_id_header || 'N/A'), 'success');
            loadShipments();
          } else {
            var msg = (data.detail && data.detail.message) ? data.detail.message : (data.detail || 'Gagal mengirim ke CEISA');
            showToast(msg, 'error');
          }
        } catch (e) {
          showToast('Gagal mengirim shipment ke CEISA', 'error');
        }
      }
    );
  }

  // =========================================
  // Preview CEISA JSON
  // =========================================
  async function previewCeisa(id) {
    try {
      var response = await fetch('/api/ceisa/preview/' + id);
      if (!response.ok) throw new Error('Failed');
      var data = await response.json();
      showCeisaPreviewModal(data);
    } catch (error) {
      showToast('Gagal preview CEISA', 'error');
    }
  }

  function showCeisaPreviewModal(data) {
    var modalBody = document.getElementById('modalBody');
    modalBody.innerHTML =
      '<div class="ceisa-preview">' +
        '<div class="preview-header">' +
          '<h3 style="font-size:16px;font-weight:600;color:var(--navy);margin-bottom:8px;">Preview CEISA 4.0</h3>' +
          '<div class="preview-meta">' +
            '<span><strong>Shipment:</strong> ' + escHtml(data.reference_code) + '</span>' +
            '<span><strong>Nomor Aju:</strong> <code>' + escHtml(data.nomorAju) + '</code></span>' +
            '<span><strong>Items:</strong> ' + data.items_count + '</span>' +
          '</div>' +
        '</div>' +
        '<div class="preview-doc"><pre>' + JSON.stringify(data.document, null, 2) + '</pre></div>' +
        '<div class="preview-note">! Ini hanya preview. Data BELUM dikirim ke CEISA.</div>' +
      '</div>';
    document.getElementById('detailModal').classList.add('show');
  }

  // =========================================
  // Delete Shipment
  // =========================================
  async function deleteShipment(id) {
    showConfirmModal(
      'Delete Declaration',
      'Delete this shipment? This action cannot be undone.',
      'Delete',
      'danger',
      async function() {
        try {
          var response = await fetch('/api/shipments/' + id, { method: 'DELETE' });
          if (response.ok) {
            showToast('Shipment deleted', 'success');
            loadShipments();
          } else {
            throw new Error('Failed to delete');
          }
        } catch (e) {
          showToast('Failed to delete shipment', 'error');
        }
      }
    );
  }

  // =========================================
  // Helpers
  // =========================================
  function getConfidenceClass(confidence) {
    if (confidence >= 80) return 'high';
    if (confidence >= 50) return 'medium';
    return 'low';
  }

  function showToast(message, type) {
    if (!type) type = 'info';
    var toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className   = 'toast ' + type + ' show';
    setTimeout(function() { toast.classList.remove('show'); }, 3000);
  }

  function formatDateTime(isoString) {
    var date    = new Date(isoString);
    var options = {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit', hour12: false,
    };
    return date.toLocaleString('en-GB', options).replace(',', '');
  }

  function escHtml(str) {
    if (str === null || str === undefined) return '';
    var div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }

  // Expose to global scope
  window.viewDetail      = viewDetail;
  window.sendShipment   = sendShipment;
  window.previewCeisa   = previewCeisa;
  window.deleteShipment = deleteShipment;
  window.closeModal      = closeModal;
  window.closeConfirmModal = closeConfirmModal;
  window.goToPage       = goToPage;

})();
