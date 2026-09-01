let currentStatus = 'idle';
let progressInterval = null;

// Initialize page
document.addEventListener('DOMContentLoaded', () => {
  loadDatasetStats();
  loadDatasets();
  checkTrainingStatus();
  setupEventListeners();
});

function setupEventListeners() {
  // Add dataset button
  const addDatasetBtn = document.getElementById('add-dataset-btn');
  if (addDatasetBtn) {
    addDatasetBtn.addEventListener('click', openAddDatasetModal);
  }

  // Retrain button
  const retrainBtn = document.getElementById('retrain-btn');
  if (retrainBtn) {
    retrainBtn.addEventListener('click', startTraining);
  }
}

// Open add dataset modal
function openAddDatasetModal() {
  const modal = document.getElementById('add-dataset-modal');
  if (modal) {
    modal.classList.add('show');
  }
}

// Close add dataset modal
function closeAddDatasetModal() {
  const modal = document.getElementById('add-dataset-modal');
  if (modal) {
    modal.classList.remove('show');
  }
  const ajuInput = document.getElementById('upload-aju-input');
  if (ajuInput) ajuInput.value = '';
  const progressDiv = document.getElementById('upload-progress');
  if (progressDiv) {
    progressDiv.style.display = 'none';
    progressDiv.textContent = '';
  }
  ['file-ci', 'file-pl', 'file-bl', 'file-xlsx'].forEach(id => {
    const input = document.getElementById(id);
    if (input) input.value = '';
  });
  const uploadBtn = document.getElementById('upload-btn');
  if (uploadBtn) {
    uploadBtn.disabled = false;
    uploadBtn.textContent = 'Upload Dataset';
  }
}

// Submit dataset upload
async function submitDatasetUpload() {
  const ajuInput = document.getElementById('upload-aju-input');
  const aju = ajuInput?.value.trim();

  if (!aju) {
    showToast('Masukkan nama AJU terlebih dahulu', 'error');
    return;
  }

  if (!/^[a-zA-Z0-9_-]+$/.test(aju)) {
    showToast('Nama AJU hanya boleh huruf, angka, strip, dan underscore', 'error');
    return;
  }

  const fileCi = document.getElementById('file-ci').files[0];
  const filePl = document.getElementById('file-pl').files[0];
  const fileBl = document.getElementById('file-bl').files[0];
  const fileXlsx = document.getElementById('file-xlsx').files[0];

  if (!fileCi && !filePl && !fileBl && !fileXlsx) {
    showToast('Pilih minimal satu file untuk diupload', 'error');
    return;
  }

  const progressDiv = document.getElementById('upload-progress');
  const uploadBtn = document.getElementById('upload-btn');

  progressDiv.style.display = 'block';
  progressDiv.textContent = 'Mengupload...';
  uploadBtn.disabled = true;
  uploadBtn.textContent = 'Mengupload...';

  const formData = new FormData();
  formData.append('aju', aju);

  if (fileCi) formData.append('files', fileCi);
  if (filePl) formData.append('files', filePl);
  if (fileBl) formData.append('files', fileBl);
  if (fileXlsx) formData.append('files', fileXlsx);

  try {
    const response = await fetch('/api/training/datasets/upload', {
      method: 'POST',
      body: formData
    });

    const result = await response.json();

    if (response.ok && result.success) {
      showToast(`Dataset "${aju}" berhasil ditambahkan`, 'success');
      closeAddDatasetModal();
      loadDatasetStats();
      loadDatasets();
    } else {
      showToast(result.error || 'Gagal upload dataset', 'error');
      progressDiv.style.display = 'none';
      uploadBtn.disabled = false;
      uploadBtn.textContent = 'Upload Dataset';
    }
  } catch (error) {
    console.error('Upload error:', error);
    showToast('Gagal upload dataset', 'error');
    progressDiv.style.display = 'none';
    uploadBtn.disabled = false;
    uploadBtn.textContent = 'Upload Dataset';
  }
}
async function loadDatasetStats() {
  try {
    const response = await fetch('/api/training/stats');
    if (!response.ok) throw new Error('Failed to load stats');

    const stats = await response.json();

    document.getElementById('total-datasets').textContent = stats.total || 0;
    document.getElementById('complete-datasets').textContent = stats.complete || 0;
    document.getElementById('partial-datasets').textContent = stats.partial || 0;
    document.getElementById('missing-datasets').textContent = stats.missing || 0;
  } catch (error) {
    console.error('Error loading stats:', error);
    document.getElementById('total-datasets').textContent = '-';
    document.getElementById('complete-datasets').textContent = '-';
    document.getElementById('partial-datasets').textContent = '-';
    document.getElementById('missing-datasets').textContent = '-';
  }
}

// Load dataset list
async function loadDatasets() {
  try {
    const response = await fetch('/api/training/datasets');
    if (!response.ok) throw new Error('Failed to load datasets');

    const data = await response.json();
    renderDatasetTable(data.datasets || []);
  } catch (error) {
    console.error('Error loading datasets:', error);
    showToast('Gagal memuat daftar dataset', 'error');
  }
}

// Render dataset table
function renderDatasetTable(datasets) {
  const tbody = document.getElementById('dataset-tbody');
  if (!tbody) return;

  if (!datasets || datasets.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="7" class="empty-state">
          <div class="empty-state-icon">📁</div>
          <h3>Belum ada dataset</h3>
          <p>Tambahkan dataset baru untuk memulai training</p>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = datasets.map(ds => `
    <tr>
      <td><span class="dataset-name">${escapeHtml(ds.name)}</span></td>
      <td><span class="file-check ${ds.files?.ci ? 'yes' : 'no'}">${ds.files?.ci ? '✓' : '✗'}</span></td>
      <td><span class="file-check ${ds.files?.pl ? 'yes' : 'no'}">${ds.files?.pl ? '✓' : '✗'}</span></td>
      <td><span class="file-check ${ds.files?.bl ? 'yes' : 'no'}">${ds.files?.bl ? '✓' : '✗'}</span></td>
      <td><span class="file-check ${ds.files?.xlsx ? 'yes' : 'no'}">${ds.files?.xlsx ? '✓' : '✗'}</span></td>
      <td>${getStatusBadge(ds.status)}</td>
      <td>
        <button class="delete-btn" onclick="deleteDataset('${escapeHtml(ds.name)}')" title="Hapus dataset">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          </svg>
        </button>
      </td>
    </tr>
  `).join('');
}

function getStatusBadge(status) {
  switch (status) {
    case 'complete':
      return '<span class="status-badge status-complete">Lengkap</span>';
    case 'partial':
      return '<span class="status-badge status-partial">Sebagian</span>';
    case 'missing':
      return '<span class="status-badge status-missing">Tidak Lengkap</span>';
    default:
      return '<span class="status-badge">-</span>';
  }
}

// Delete dataset
async function deleteDataset(aju) {
  if (!confirm(`Hapus dataset "${aju}"?`)) return;

  try {
    const response = await fetch(`/api/training/datasets/${encodeURIComponent(aju)}`, {
      method: 'DELETE'
    });

    if (response.ok) {
      showToast(`Dataset "${aju}" berhasil dihapus`, 'success');
      loadDatasetStats();
      loadDatasets();
    } else {
      const result = await response.json();
      showToast(result.detail || 'Gagal menghapus dataset', 'error');
    }
  } catch (error) {
    console.error('Delete error:', error);
    showToast('Gagal menghapus dataset', 'error');
  }
}

// Start training
async function startTraining() {
  const btn = document.getElementById('retrain-btn');
  btn.disabled = true;
  btn.innerHTML = `
    <svg class="btn-icon" viewBox="0 0 24 24" fill="none">
      <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    Memulai...
  `;

  try {
    const response = await fetch('/api/training/start', {
      method: 'POST'
    });

    const result = await response.json();

    if (response.ok) {
      showToast('Training dimulai', 'success');
      startProgressPolling();
      updateProgressUI('preparing');
    } else {
      showToast(result.detail || result.error || 'Gagal memulai training', 'error');
      btn.disabled = false;
      btn.innerHTML = `
        <svg class="btn-icon" viewBox="0 0 24 24" fill="none">
          <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        Retrain Model
      `;
    }
  } catch (error) {
    console.error('Start training error:', error);
    showToast('Gagal memulai training', 'error');
    btn.disabled = false;
    btn.innerHTML = `
      <svg class="btn-icon" viewBox="0 0 24 24" fill="none">
        <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      Retrain Model
    `;
  }
}

// Check training status
async function checkTrainingStatus() {
  try {
    const response = await fetch('/api/training/status');
    if (!response.ok) return;

    const status = await response.json();
    currentStatus = status.status;

    if (status.status === 'preparing' || status.status === 'training' || status.status === 'evaluating' || status.status === 'deploying') {
      updateProgressUI(status.status);
      startProgressPolling();
    } else if (status.status === 'completed') {
      updateProgressUI('completed');
      resetRetrainButton();
      if (status.metrics) {
        showTrainingMetrics(status.metrics);
      }
    } else if (status.status === 'failed') {
      updateProgressUI('failed');
      resetRetrainButton();
      showToast('Training gagal: ' + (status.error || 'Unknown error'), 'error');
    }
  } catch (error) {
    console.error('Status check error:', error);
  }
}

// Start progress polling
function startProgressPolling() {
  if (progressInterval) clearInterval(progressInterval);
  progressInterval = setInterval(pollProgress, 2000);
}

// Poll progress
async function pollProgress() {
  try {
    const response = await fetch('/api/training/progress');
    if (!response.ok) return;

    const progress = await response.json();
    updateProgressLog(progress.logs);

    if (progress.step) {
      updateStepUI(progress.step);
    }

    const percent = progress.percent || 0;
    document.getElementById('progress-percent').textContent = Math.round(percent) + '%';
    document.getElementById('progress-fill').style.width = percent + '%';

    if (progress.status === 'completed') {
      clearInterval(progressInterval);
      progressInterval = null;
      updateProgressUI('completed');
      if (progress.metrics) {
        showTrainingMetrics(progress.metrics);
      }
      showToast('Training berhasil! Model sudah di-deploy.', 'success');
      resetRetrainButton();
    } else if (progress.status === 'failed') {
      clearInterval(progressInterval);
      progressInterval = null;
      updateProgressUI('failed');
      showToast('Training gagal', 'error');
      resetRetrainButton();
    }
  } catch (error) {
    console.error('Progress poll error:', error);
  }
}

// Update progress UI
function updateProgressUI(step) {
  const steps = ['idle', 'preparing', 'training', 'evaluating', 'deploying', 'completed'];
  const stepIndex = steps.indexOf(step);

  document.querySelectorAll('.progress-step').forEach((el, i) => {
    el.classList.remove('active', 'completed');
    if (i < stepIndex) {
      el.classList.add('completed');
    } else if (i === stepIndex) {
      el.classList.add('active');
    }
  });

  // Update progress bar
  const percentMap = {
    'idle': 0,
    'preparing': 15,
    'training': 60,
    'evaluating': 90,
    'deploying': 95,
    'completed': 100,
    'failed': 0
  };
  const percent = percentMap[step] || 0;
  document.getElementById('progress-percent').textContent = percent + '%';
  document.getElementById('progress-fill').style.width = percent + '%';
}

function updateStepUI(step) {
  updateProgressUI(step);
}

// Update progress log
function updateProgressLog(logs) {
  const logContainer = document.getElementById('progress-log');
  if (!logContainer || !logs) return;

  const logHtml = logs.slice(-50).map(log => {
    let cssClass = 'log-info';
    if (log.includes('✓') || log.includes('[OK]') || log.includes('saved') || log.includes('best')) {
      cssClass = 'log-success';
    } else if (log.includes('[WARN]') || log.includes('Warning')) {
      cssClass = 'log-warning';
    } else if (log.includes('[ERR]') || log.includes('Error') || log.includes('failed')) {
      cssClass = 'log-error';
    }

    const now = new Date();
    const time = now.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    return `<p><span class="log-time">[${time}]</span> <span class="${cssClass}">${escapeHtml(log)}</span></p>`;
  }).join('');

  logContainer.innerHTML = logHtml;
  logContainer.scrollTop = logContainer.scrollHeight;
}

// Show training metrics
function showTrainingMetrics(metrics) {
  const metricsDiv = document.getElementById('training-metrics');
  if (!metricsDiv || !metrics) return;

  metricsDiv.style.display = 'block';
  metricsDiv.innerHTML = `
    <h4>Hasil Training</h4>
    <div class="metrics-grid">
      <div class="metric-item">
        <div class="metric-value f1">${metrics.f1 || 'N/A'}%</div>
        <div class="metric-label">Entity F1</div>
      </div>
      <div class="metric-item">
        <div class="metric-value">${metrics.precision || 'N/A'}%</div>
        <div class="metric-label">Precision</div>
      </div>
      <div class="metric-item">
        <div class="metric-value recall">${metrics.recall || 'N/A'}%</div>
        <div class="metric-label">Recall</div>
      </div>
    </div>
  `;
}

// Reset retrain button
function resetRetrainButton() {
  const btn = document.getElementById('retrain-btn');
  if (btn) {
    btn.disabled = false;
    btn.innerHTML = `
      <svg class="btn-icon" viewBox="0 0 24 24" fill="none">
        <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      Retrain Model
    `;
  }
}

// Cancel training
async function cancelTraining() {
  if (!confirm('Batalkan training yang sedang berjalan?')) return;

  try {
    const response = await fetch('/api/training/cancel', {
      method: 'POST'
    });

    if (response.ok) {
      showToast('Training dibatalkan', 'warning');
      clearInterval(progressInterval);
      progressInterval = null;
      updateProgressUI('idle');
      resetRetrainButton();
    }
  } catch (error) {
    console.error('Cancel error:', error);
    showToast('Gagal membatalkan training', 'error');
  }
}

// Toast notification
function showToast(message, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);

  setTimeout(() => toast.classList.add('show'), 10);

  // Remove after 4 seconds
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Escape HTML
function escapeHtml(text) {
  if (!text) return '';
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Expose functions globally for HTML onclick/onchange handlers
window.openAddDatasetModal = openAddDatasetModal;
window.closeAddDatasetModal = closeAddDatasetModal;
window.submitDatasetUpload = submitDatasetUpload;
window.deleteDataset = deleteDataset;
window.cancelTraining = cancelTraining;
window.startTraining = startTraining;
