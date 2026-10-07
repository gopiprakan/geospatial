/**
 * Geospatial File Measurement API - Frontend Application Logic
 * Pure Vanilla JS, zero dependencies, responsive and interactive
 */

document.addEventListener('DOMContentLoaded', () => {
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const progressBar = document.getElementById('progressBar');
  const progressFill = document.getElementById('progressFill');
  const progressStatus = document.getElementById('progressStatus');
  const resultsSection = document.getElementById('resultsSection');

  const btnSampleKml = document.getElementById('btnSampleKml');
  const btnSampleShp = document.getElementById('btnSampleShp');

  let currentMeasurements = [];
  let currentFilter = 'ALL';

  // ---------------- Drag & Drop Events ----------------
  ['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.add('dragover');
    });
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove('dragover');
    });
  });

  dropZone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileUpload(files[0]);
    }
  });

  dropZone.addEventListener('click', () => {
    fileInput.click();
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
      handleFileUpload(fileInput.files[0]);
    }
  });

  // ---------------- Sample Data Buttons ----------------
  btnSampleKml.addEventListener('click', (e) => {
    e.stopPropagation();
    const sampleKmlContent = `<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Bengaluru Urban Survey</name>
    <Placemark>
      <name>Cubbon Park Perimeter</name>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              77.5900,12.9700,0
              77.6000,12.9700,0
              77.6000,12.9800,0
              77.5900,12.9800,0
              77.5900,12.9700,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
    <Placemark>
      <name>MG Road Transit Corridor</name>
      <LineString>
        <coordinates>
          77.5900,12.9700,0
          77.6050,12.9750,0
          77.6150,12.9800,0
        </coordinates>
      </LineString>
    </Placemark>
    <Placemark>
      <name>Vidhana Soudha Landmark</name>
      <Point>
        <coordinates>77.5906,12.9797,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>`;
    const blob = new Blob([sampleKmlContent], { type: 'application/vnd.google-earth.kml+xml' });
    const file = new File([blob], 'bengaluru_survey.kml', { type: 'application/vnd.google-earth.kml+xml' });
    handleFileUpload(file);
  });

  // ---------------- Upload & API Pipeline ----------------
  async function handleFileUpload(file) {
    const ext = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (ext !== '.kml' && ext !== '.zip') {
      showToast('Unsupported file format. Please upload .kml or .zip', 'error');
      return;
    }

    // Show Progress
    progressBar.style.display = 'block';
    progressFill.style.width = '30%';
    progressStatus.textContent = 'Uploading file to server...';

    const formData = new FormData();
    formData.append('file', file);

    try {
      progressFill.style.width = '60%';
      progressStatus.textContent = 'Processing geometries & calculating UTM projections...';

      const uploadRes = await fetch('/api/files/', {
        method: 'POST',
        body: formData,
      });

      const uploadData = await uploadRes.json();

      if (!uploadRes.ok) {
        throw new Error(uploadData.detail || 'Upload failed');
      }

      progressFill.style.width = '90%';
      progressStatus.textContent = 'Fetching metric measurements...';

      // Fetch measurements
      const measRes = await fetch(`/api/files/${uploadData.id}/measurements/`);
      const measData = await measRes.json();

      if (!measRes.ok) {
        throw new Error(measData.detail || 'Failed to fetch measurements');
      }

      progressFill.style.width = '100%';
      progressStatus.textContent = 'Completed!';

      setTimeout(() => {
        progressBar.style.display = 'none';
        progressFill.style.width = '0%';
        displayResults(uploadData, measData.measurements);
        showToast('File processed successfully!', 'success');
      }, 400);

    } catch (err) {
      progressBar.style.display = 'none';
      progressFill.style.width = '0%';
      showToast(`Error: ${err.message}`, 'error');
    }
  }

  // ---------------- Render Results ----------------
  function displayResults(fileInfo, measurements) {
    currentMeasurements = measurements;
    resultsSection.style.display = 'block';
    resultsSection.scrollIntoView({ behavior: 'smooth' });

    // File Header
    document.getElementById('resFilename').textContent = fileInfo.filename;
    document.getElementById('resFileId').textContent = fileInfo.id;
    document.getElementById('resCrs').textContent = fileInfo.crs;
    document.getElementById('resCount').textContent = fileInfo.feature_count;
    document.getElementById('resStatus').textContent = fileInfo.status;

    // Aggregate statistics
    let polyCount = 0;
    let totalArea = 0;
    let lineCount = 0;
    let totalLength = 0;
    let pointCount = 0;

    measurements.forEach(m => {
      const type = (m.geometry_type || '').toLowerCase();
      if (type.includes('polygon')) {
        polyCount++;
        totalArea += (m.area || 0);
      } else if (type.includes('linestring') || type.includes('line')) {
        lineCount++;
        totalLength += (m.length || 0);
      } else if (type.includes('point')) {
        pointCount++;
      }
    });

    document.getElementById('metricPolyCount').textContent = polyCount;
    document.getElementById('metricTotalArea').textContent = formatNumber(totalArea) + ' m²';
    document.getElementById('metricAreaSub').textContent = totalArea > 10000 
      ? `≈ ${(totalArea / 10000).toFixed(2)} hectares (${(totalArea / 1000000).toFixed(3)} km²)`
      : 'Metric area';

    document.getElementById('metricLineCount').textContent = lineCount;
    document.getElementById('metricTotalLength').textContent = formatNumber(totalLength) + ' m';
    document.getElementById('metricLengthSub').textContent = totalLength > 1000 
      ? `≈ ${(totalLength / 1000).toFixed(2)} km`
      : 'Metric length';

    document.getElementById('metricPointCount').textContent = pointCount;

    renderTable();
  }

  // ---------------- Measurements Table ----------------
  function renderTable() {
    const tbody = document.getElementById('measurementsTableBody');
    tbody.innerHTML = '';

    const searchTerm = (document.getElementById('searchInput').value || '').toLowerCase();

    const filtered = currentMeasurements.filter(m => {
      const type = (m.geometry_type || '').toUpperCase();
      if (currentFilter !== 'ALL' && !type.includes(currentFilter)) {
        return false;
      }
      if (searchTerm) {
        const idStr = String(m.feature_id);
        const nameStr = (m.properties && m.properties.Name) ? String(m.properties.Name).toLowerCase() : '';
        if (!idStr.includes(searchTerm) && !nameStr.includes(searchTerm)) {
          return false;
        }
      }
      return true;
    });

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">No matching features found.</td></tr>`;
      return;
    }

    filtered.forEach(m => {
      const tr = document.createElement('tr');

      let badgeClass = 'geom-badge';
      let measHtml = '-';
      const type = m.geometry_type || 'Unknown';

      if (type.toLowerCase().includes('polygon')) {
        badgeClass += ' geom-polygon';
        measHtml = `<span class="meas-val">${formatNumber(m.area)}</span><span class="meas-unit">${m.unit || 'm²'}</span>`;
      } else if (type.toLowerCase().includes('linestring') || type.toLowerCase().includes('line')) {
        badgeClass += ' geom-linestring';
        measHtml = `<span class="meas-val">${formatNumber(m.length)}</span><span class="meas-unit">${m.unit || 'm'}</span>`;
      } else if (type.toLowerCase().includes('point')) {
        badgeClass += ' geom-point';
        measHtml = `<span style="color: var(--text-muted); font-size: 0.8rem;">null (Point feature)</span>`;
      } else {
        measHtml = `<span style="color: var(--accent-amber); font-size: 0.8rem;">${m.message || 'Unsupported'}</span>`;
      }

      // Feature name or label
      const name = (m.properties && (m.properties.Name || m.properties.name || m.properties.id)) || '-';

      tr.innerHTML = `
        <td style="font-family: var(--font-mono); font-weight: 600;">#${m.feature_id}</td>
        <td><span class="${badgeClass}">${type}</span></td>
        <td style="font-weight: 500;">${name}</td>
        <td>${measHtml}</td>
        <td>
          <button class="btn btn-secondary" style="padding: 0.25rem 0.6rem; font-size: 0.75rem;" onclick="copyFeatureJson(${m.feature_id})">
            Copy JSON
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });
  }

  // ---------------- Filtering ----------------
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentFilter = btn.dataset.filter;
      renderTable();
    });
  });

  document.getElementById('searchInput').addEventListener('input', () => {
    renderTable();
  });

  // ---------------- Copy Helpers ----------------
  window.copyFileId = function() {
    const id = document.getElementById('resFileId').textContent;
    navigator.clipboard.writeText(id);
    showToast(`Copied File ID: ${id}`, 'info');
  };

  window.copyFeatureJson = function(featureId) {
    const item = currentMeasurements.find(m => m.feature_id === featureId);
    if (item) {
      navigator.clipboard.writeText(JSON.stringify(item, null, 2));
      showToast(`Copied Feature #${featureId} JSON`, 'info');
    }
  };

  window.downloadJson = function() {
    const fileId = document.getElementById('resFileId').textContent;
    const blob = new Blob([JSON.stringify({ file_id: fileId, measurements: currentMeasurements }, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `measurements_${fileId}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  function formatNumber(num) {
    if (num === null || num === undefined) return '-';
    return Number(num).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = 'toast';
    const icon = type === 'error' ? '❌' : type === 'success' ? '✅' : '📋';
    toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = '0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 3500);
  }
});
