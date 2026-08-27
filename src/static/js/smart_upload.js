// =========================================
// SMART UPLOAD PAGE — dashboard.js
// =========================================

(function () {
  // State
  const state = {
    files: { CI: null, PL: null, BL: null },
    processing: false,
    startTime: null,
    lastExtractionResult: null,
  };

  // =========================================
  // Drag & Drop
  // =========================================
  function onDragOver(event) {
    event.preventDefault();
    event.currentTarget.classList.add('drag-over');
  }

  function onDragLeave(event) {
    event.currentTarget.classList.remove('drag-over');
  }

  function triggerFileInput(id) {
    document.getElementById(id).click();
  }

  // =========================================
  // File Selection
  // =========================================
  function onFileSelected(input, docType) {
    const file = input.files[0];
    if (!file) return;

    // Validate size (20 MB)
    if (file.size > 20 * 1024 * 1024) {
      showStatus('error', 'File Too Large',
        file.name + ' is ' + (file.size / 1024 / 1024).toFixed(1) + ' MB. Maximum: 20 MB.');
      input.value = '';
      return;
    }

    state.files[docType] = file;
    updateUI(docType, file);
  }

  function removeFile(docType) {
    state.files[docType] = null;
    const input = document.getElementById(docType.toLowerCase() + '-input');
    if (input) input.value = '';
    updateUI(docType, null);
  }

  function updateUI(docType, file) {
    const drop    = document.getElementById('drop-'    + docType.toLowerCase());
    const preview = document.getElementById('preview-' + docType.toLowerCase());
    const nameEl  = document.getElementById(docType.toLowerCase() + '-name');
    const sizeEl  = document.getElementById(docType.toLowerCase() + '-size');
    const card    = document.getElementById('card-'   + docType.toLowerCase());

    if (file) {
      drop.style.display    = 'none';
      preview.style.display = 'flex';
      nameEl.textContent   = file.name;
      sizeEl.textContent   = formatBytes(file.size);
      card.classList.add('has-file');
    } else {
      drop.style.display    = 'flex';
      preview.style.display = 'none';
      nameEl.textContent   = '';
      sizeEl.textContent   = '';
      card.classList.remove('has-file');
    }

    updateFileCountBadge();
    updateRunButton();
  }

  function updateFileCountBadge() {
    const count = Object.values(state.files).filter(Boolean).length;
    const badge = document.getElementById('file-count-badge');
    const text  = document.getElementById('file-count-text');

    if (count === 0) {
      text.textContent  = 'No files selected';
      badge.className   = 'file-count-badge';
    } else {
      text.textContent  = count + ' file' + (count > 1 ? 's' : '') + ' selected';
      badge.className   = 'file-count-badge has-files';
    }
  }

  function updateRunButton() {
    const btn      = document.getElementById('run-btn');
    const hasFiles = Object.values(state.files).some(Boolean);
    btn.disabled   = !hasFiles || state.processing;
  }

  function formatBytes(bytes) {
    if (bytes < 1024)                    return bytes + ' B';
    if (bytes < 1024 * 1024)             return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  }

  // =========================================
  // Loading Animation
  // =========================================
  let _loadingTimer = null;
  let _startTime    = 0;

  function _tickTime() {
    const sec = Math.round((Date.now() - _startTime) / 1000);
    const el  = document.getElementById('loading-time');
    if (el) el.textContent = 'Processing... ' + sec + 's';
  }

  function showLoading() {
    document.getElementById('loading-section').style.display = 'flex';
    document.getElementById('results-section').style.display = 'none';
    _startTime = Date.now();
    _tickTime();
    _loadingTimer = setInterval(_tickTime, 1000);
  }

  function hideLoading() {
    if (_loadingTimer) { clearInterval(_loadingTimer); _loadingTimer = null; }
    document.getElementById('loading-section').style.display = 'none';
  }

  function showResults(data, fullData) {
    const resultsSection = document.getElementById('results-section');
    resultsSection.style.display = 'block';

    // Update metrics
    document.getElementById('confidence-value').textContent = data.confidence     || '--';
    document.getElementById('docs-count').textContent        = data.docsCount      || 0;
    document.getElementById('items-count').textContent        = data.itemsCount      || 0;
    document.getElementById('time-value').textContent         = data.processingTime  || '--';

    // Update confidence bar
    const confidenceFill = document.getElementById('confidence-fill');
    const confValue      = parseFloat(data.confidence) || 0;
    confidenceFill.style.width = confValue + '%';

    // Update badge
    const badge = document.getElementById('results-badge');
    if (confValue >= 80) {
      badge.textContent = 'High Confidence';
      badge.className   = 'results-badge high';
    } else if (confValue >= 60) {
      badge.textContent = 'Medium Confidence';
      badge.className   = 'results-badge medium';
    } else {
      badge.textContent = 'Review Required';
      badge.className   = 'results-badge low';
    }

    // Populate header fields
    const fieldList    = document.getElementById('field-list');
    const headerFields = fullData ? fullData.header_fields || {} : {};

    if (Object.keys(headerFields).length > 0) {
      fieldList.innerHTML = Object.entries(headerFields)
        .map(function(entry) {
          const fieldName = entry[0];
          const fieldData = entry[1];
          const conf      = fieldData.confidence || 0;
          const statusClass = conf >= 80 ? 'high' : conf >= 60 ? 'medium' : 'low';
          const statusText  = conf >= 80 ? 'High' : conf >= 60 ? 'Medium' : 'Low';
          return '<div class="field-item">' +
            '<div class="field-info">' +
              '<span class="field-name">' + escHtml(fieldName) + '</span>' +
              '<span class="field-value">' + escHtml(fieldData.value || '--') + '</span>' +
            '</div>' +
            '<span class="field-status ' + statusClass + '">' + statusText + ' (' + conf + '%)</span>' +
          '</div>';
        }).join('');
    } else {
      fieldList.innerHTML = '<div class="field-item">' +
        '<span class="field-name">No header fields extracted</span>' +
        '<span class="field-status medium">--</span>' +
      '</div>';
    }

    // Populate line items table
    const lineItemsSection = document.getElementById('line-items-section');
    const itemsTableBody   = document.getElementById('items-tbody');
    const lineItems        = fullData ? fullData.line_items || [] : [];

    if (lineItems.length > 0) {
      lineItemsSection.style.display = 'block';
      itemsTableBody.innerHTML = lineItems.map(function(item) {
        return '<tr>' +
          '<td>' + escHtml(item.description  || '--') + '</td>' +
          '<td>' + escHtml(item.hs_code      || '--') + '</td>' +
          '<td>' + escHtml(item.quantity     || '--') + '</td>' +
          '<td>' + escHtml(item.unit         || '--') + '</td>' +
          '<td>' + escHtml(item.unit_price   || '--') + '</td>' +
          '<td>' + escHtml(item.amount        || '--') + '</td>' +
        '</tr>';
      }).join('');
    } else {
      lineItemsSection.style.display = 'none';
    }

    // Show quality warnings if low confidence
    const warningsSection = document.getElementById('quality-warnings');
    const warningsList    = document.getElementById('warnings-list');
    const qualityReport   = fullData ? fullData.quality_report || {} : {};

    if (confValue < 60 || (qualityReport.header_fields_missing && qualityReport.header_fields_missing.length > 0)) {
      warningsSection.style.display = 'block';
      var warningHtml = '';

      if (confValue < 60) {
        warningHtml += '<div class="warning-item">' +
          '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
            '<path d="M12 9v4M12 17h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' +
            '<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" stroke="currentColor" stroke-width="2"/>' +
          '</svg>' +
          '<span>Low extraction confidence (' + confValue + '%). Please review extracted data manually before submission.</span>' +
        '</div>';
      }

      if (qualityReport.header_fields_missing && qualityReport.header_fields_missing.length > 0) {
        warningHtml += '<div class="warning-item">' +
          '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
            '<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>' +
            '<path d="M12 8v4M12 16h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' +
          '</svg>' +
          '<span>Missing header fields: ' + qualityReport.header_fields_missing.join(', ') + '</span>' +
        '</div>';
      }

      warningsList.innerHTML = warningHtml;
    } else {
      warningsSection.style.display = 'none';
    }

    // Scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // =========================================
  // Run Pipeline
  // =========================================
  async function runPipeline() {
    if (state.processing) return;

    const uploaded = Object.entries(state.files)
      .filter(function(entry) { return entry[1] !== null; })
      .reduce(function(acc, entry) { acc[entry[0]] = entry[1]; return acc; }, {});

    if (Object.keys(uploaded).length === 0) {
      showStatus('error', 'No Files Selected',
        'Please upload at least one document (CI, PL, or BL).');
      return;
    }

    state.processing = true;
    state.startTime  = Date.now();
    hideStatus();
    showLoading();
    setProcessing(true);

    const formData = new FormData();
    for (const [docType, file] of Object.entries(uploaded)) {
      formData.append(docType, file);
    }
    const ajuNumber = document.getElementById('aju-number').value.trim();
    if (ajuNumber) formData.append('shipment_id', ajuNumber);

    try {
      const response = await fetch('/api/extract', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        let errorMsg = 'Server error: ' + response.status + ' ' + response.statusText;
        try { var d = await response.json(); if (d.detail) errorMsg = d.detail; } catch (_) {}
        throw new Error(errorMsg);
      }

      const jsonData = await response.json();
      state.lastExtractionResult = jsonData;

      // Decode base64 and trigger download
      const byteCharacters  = atob(jsonData.excel_base64);
      const byteNumbers     = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob       = new Blob([byteArray], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      });

      const url = URL.createObjectURL(blob);
      const a   = document.createElement('a');
      a.href     = url;
      a.download = jsonData.filename || 'extraction.xlsx';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      setTimeout(function() {
        hideLoading();
        showResults({
          confidence:    jsonData.confidence,
          docsCount:     jsonData.documents_processed.length,
          itemsCount:    jsonData.items_count,
          processingTime: jsonData.processing_time_seconds + 's',
          qualityScore:   jsonData.quality_score,
          fieldsExtracted: {},
        }, jsonData);
        showStatus('success', 'Extraction Complete',
          'CEISA 4.0 Excel file "' + (jsonData.filename || 'extraction') + '" has been downloaded. ' +
          'Click "Save to Declarations" to save this result.');
      }, 400);

    } catch (err) {
      console.error('Extraction error:', err);
      hideLoading();
      showStatus('error', 'Extraction Failed', err.message || 'An unknown error occurred.');
    } finally {
      state.processing = false;
      setProcessing(false);
    }
  }

  // =========================================
  // Save to Declarations
  // =========================================
  async function saveToDeclarations() {
    const saveBtn = document.getElementById('save-btn');
    if (!state.lastExtractionResult) {
      showStatus('error', 'No Result', 'Please run extraction first.');
      return;
    }

    saveBtn.disabled = true;
    saveBtn.querySelector('span').textContent = 'Saving...';

    try {
      const result = state.lastExtractionResult;

      const response = await fetch('/api/shipments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          aju_number:            result.aju_number          || document.getElementById('aju-number').value.trim(),
          excel_filename:        result.filename,
          documents_processed:   result.documents_processed,
          total_amount:          result.total_amount,
          extraction_confidence:  result.extraction_confidence,
          quality_score:          result.quality_score,
          status:                result.status,
          header_fields:         result.header_fields,
          line_items:            result.line_items,
          quality_report:        result.quality_report,
          excel_base64:          result.excel_base64,
          file_size_kb:          Math.round(atob(result.excel_base64).length / 1024),
        }),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to save');
      }

      const data = await response.json();
      showStatus('success', 'Saved!',
        'Declaration "' + data.reference_code + '" saved successfully.');

      state.lastExtractionResult = null;

    } catch (err) {
      console.error('Save error:', err);
      showStatus('error', 'Save Failed', err.message || 'Could not save to declarations.');
    } finally {
      saveBtn.disabled = false;
      saveBtn.querySelector('span').textContent = 'Save to Declarations';
    }
  }

  function setProcessing(val) {
    const btn     = document.getElementById('run-btn');
    const btnText = document.getElementById('run-btn-text');
    const spinner = document.getElementById('spinner');

    if (val) {
      btn.disabled      = true;
      btnText.textContent = 'Processing…';
      spinner.style.display = 'inline-block';
      btn.classList.add('processing');
    } else {
      btn.disabled        = Object.values(state.files).every(function(f) { return !f; });
      btnText.textContent = 'Run OCR Pipeline';
      spinner.style.display = 'none';
      btn.classList.remove('processing');
      updateRunButton();
    }
  }

  // =========================================
  // Status Panel
  // =========================================
  function showStatus(type, title, message) {
    const section = document.getElementById('status-section');
    const card    = document.getElementById('status-card');
    const icon    = document.getElementById('status-icon');
    const titleEl = document.getElementById('status-title');
    const msgEl   = document.getElementById('status-message');

    section.style.display = 'block';
    card.className        = 'status-card status-' + type;

    if (type === 'success') {
      icon.innerHTML = '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
        '<path d="M22 11.08V12a10 10 0 11-5.93-9.14" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' +
        '<path d="M22 4L12 14.01l-3-3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>' +
      '</svg>';
    } else {
      icon.innerHTML = '<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">' +
        '<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2"/>' +
        '<path d="M12 8v4M12 16h.01" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>' +
      '</svg>';
    }

    titleEl.textContent = title;
    msgEl.textContent   = message;
    section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function hideStatus() {
    document.getElementById('status-section').style.display = 'none';
  }

  // =========================================
  // Utility
  // =========================================
  function escHtml(str) {
    if (str === null || str === undefined) return '';
    var div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
  }

  // =========================================
  // Init
  // =========================================
  updateFileCountBadge();
  updateRunButton();

  // Expose to global scope so inline onclick handlers still work
  window.onDragOver    = onDragOver;
  window.onDragLeave   = onDragLeave;
  window.triggerFileInput = triggerFileInput;
  window.onFileSelected   = onFileSelected;
  window.removeFile       = removeFile;
  window.runPipeline      = runPipeline;
  window.saveToDeclarations = saveToDeclarations;

})();
