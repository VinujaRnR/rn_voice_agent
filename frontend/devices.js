/**
 * Devices & Hardware Nodes Table Dashboard Logic
 * Provides real-time data table rendering, live search/filtering, power toggling,
 * and complete CRUD management (Add, Edit, Delete).
 */

document.addEventListener('DOMContentLoaded', () => {
  let allDevices = [];
  let currentFilter = 'all';
  let searchQuery = '';

  const tbody = document.getElementById('devices-tbody');
  const searchInput = document.getElementById('search-input');
  const filterPills = document.getElementById('filter-pills');
  const refreshBtn = document.getElementById('refresh-btn');
  const openAddBtn = document.getElementById('open-add-btn');
  const connectionBadge = document.getElementById('connection-badge');
  const connectionText = document.getElementById('connection-text');
  const tableResultsCount = document.getElementById('table-results-count');

  // Stats elements
  const statTotal = document.getElementById('stat-total-devices');
  const statNodes = document.getElementById('stat-total-nodes');
  const statConnected = document.getElementById('stat-connected-sub');
  const statOnline = document.getElementById('stat-online-devices');
  const navBadge = document.getElementById('nav-badge-count');

  // Modal elements
  const modal = document.getElementById('device-modal');
  const modalTitle = document.getElementById('modal-title');
  const modalCloseBtn = document.getElementById('modal-close-btn');
  const modalCancelBtn = document.getElementById('modal-cancel-btn');
  const deviceForm = document.getElementById('device-form');
  const formIsEdit = document.getElementById('form-is-edit');
  const formDevId = document.getElementById('form-dev-id');
  const formDevName = document.getElementById('form-dev-name');
  const formNodeId = document.getElementById('form-node-id');
  const formDevType = document.getElementById('form-dev-type');
  const formLocation = document.getElementById('form-location');
  const formActions = document.getElementById('form-actions');
  const formParams = document.getElementById('form-params');
  const formAliases = document.getElementById('form-aliases');
  const formSubDevices = document.getElementById('form-sub-devices');
  const toast = document.getElementById('toast-notice');

  // Device type to icon mapping
  function getDeviceIcon(type) {
    const t = (type || '').toLowerCase();
    if (t.includes('hub')) return '🖧';
    if (t.includes('relay')) return '🔌';
    if (t.includes('light')) return '💡';
    if (t.includes('robot')) return '🤖';
    if (t.includes('arm')) return '🦾';
    if (t.includes('climate')) return '🌡️';
    if (t.includes('sensor')) return '📡';
    if (t.includes('plug')) return '🔌';
    return '📟';
  }

  // Toast feedback notice
  function showToast(message, type = 'success') {
    if (!toast) return;
    toast.textContent = message;
    toast.className = `toast-notice show ${type}`;
    setTimeout(() => {
      toast.className = 'toast-notice';
    }, 3500);
  }

  // Fetch devices from backend
  async function fetchDevices() {
    try {
      const res = await fetch('/api/devices');
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();
      allDevices = data.devices || [];

      // Update Stats
      if (statTotal) statTotal.textContent = data.total_devices || allDevices.length;
      if (statNodes) statNodes.textContent = data.total_nodes || 0;
      if (statConnected) statConnected.textContent = data.total_connected_sub_devices || 0;
      if (statOnline) statOnline.textContent = data.online_devices || 0;
      if (navBadge) navBadge.textContent = `${allDevices.length} Devices`;

      updateFilterCounts();
      updateConnectionStatus(true);
      renderTable();
    } catch (err) {
      console.error('Failed to load devices:', err);
      updateConnectionStatus(false);
      if (tbody) {
        tbody.innerHTML = `
          <tr>
            <td colspan="8" style="text-align: center; color: var(--accent-rose); padding: 30px;">
              ⚠️ Unable to connect to RN Hub device registry. Check server status.
            </td>
          </tr>
        `;
      }
    }
  }

  // Update dynamic count badges on category filter buttons
  function updateFilterCounts() {
    if (!filterPills) return;
    const btns = filterPills.querySelectorAll('.filter-btn');
    btns.forEach(btn => {
      const cat = btn.getAttribute('data-category');
      let count = 0;
      if (cat === 'all') count = allDevices.length;
      else if (cat === 'hub') count = allDevices.filter(d => (d.type || '').toLowerCase().includes('hub')).length;
      else if (cat === 'relay') count = allDevices.filter(d => (d.type || '').toLowerCase().includes('relay')).length;
      else if (cat === 'lighting') count = allDevices.filter(d => (d.type || '').toLowerCase().includes('light')).length;
      else if (cat === 'robot') count = allDevices.filter(d => (d.type || '').toLowerCase().includes('robot') || (d.type || '').toLowerCase().includes('arm')).length;
      else if (cat === 'climate') count = allDevices.filter(d => (d.type || '').toLowerCase().includes('climate')).length;

      const label = cat === 'all' ? 'All' :
                    cat === 'hub' ? 'Hubs' :
                    cat === 'relay' ? 'Relays' :
                    cat === 'lighting' ? 'Lighting' :
                    cat === 'robot' ? 'Robots' :
                    cat === 'climate' ? 'Climate' : cat;

      btn.innerHTML = `<span>${label}</span> <span class="filter-count-badge">${count}</span>`;
    });
  }

  // Render Table Rows
  function renderTable() {
    if (!tbody) return;

    const filtered = allDevices.filter(dev => {
      // Category filter
      if (currentFilter !== 'all') {
        const devType = (dev.type || '').toLowerCase();
        if (currentFilter === 'hub' && !devType.includes('hub')) return false;
        if (currentFilter === 'relay' && !devType.includes('relay')) return false;
        if (currentFilter === 'lighting' && !devType.includes('light')) return false;
        if (currentFilter === 'robot' && !devType.includes('robot') && !devType.includes('arm')) return false;
        if (currentFilter === 'climate' && !devType.includes('climate')) return false;
      }

      // Search query filter
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const name = (dev.name || '').toLowerCase();
        const devId = (dev.device_id || '').toLowerCase();
        const nodeId = (dev.node_id || '').toLowerCase();
        const location = (dev.location || '').toLowerCase();
        const subDevs = (dev.connected_devices || []).map(s => (s.name || '').toLowerCase()).join(' ');

        const match = name.includes(q) ||
          devId.includes(q) ||
          nodeId.includes(q) ||
          location.includes(q) ||
          subDevs.includes(q);

        if (!match) return false;
      }

      return true;
    });

    if (tableResultsCount) {
      tableResultsCount.textContent = `${filtered.length} of ${allDevices.length} Records`;
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="8" style="text-align: center; color: var(--text-muted); padding: 40px;">
            No matching devices or hardware nodes found.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = filtered.map(dev => {
      const icon = getDeviceIcon(dev.type);
      const isOnline = (dev.status || '').toLowerCase() === 'online';
      const powerState = (dev.power_state || 'off').toLowerCase();
      const isPowerOn = powerState === 'on';
      const connectedCount = dev.connected_devices_count || (dev.connected_devices || []).length;
      const connectedList = dev.connected_devices || [];

      // Check if power action is supported
      const allowed = dev.allowed_actions || [];
      const hasPowerAction = allowed.includes('set_power') || allowed.includes('turn_on') || allowed.includes('turn_off');

      return `
        <tr id="row-${escapeHtml(dev.device_id)}">
          <!-- Device Name & ID -->
          <td>
            <div class="device-cell">
              <div class="dev-icon">${icon}</div>
              <div>
                <span class="dev-name">${escapeHtml(dev.name)}</span>
                <span class="dev-id">${escapeHtml(dev.device_id)}</span>
              </div>
            </div>
          </td>

          <!-- Node ID -->
          <td>
            <div class="node-chip" title="Hardware Node ID">
              <span>🖧</span>
              <strong>${escapeHtml(dev.node_id || 'STANDALONE')}</strong>
            </div>
          </td>

          <!-- Device Type -->
          <td>
            <span class="device-type-tag type-${escapeHtml((dev.type || 'generic').toLowerCase())}">
              ${escapeHtml(dev.type || 'generic')}
            </span>
          </td>

          <!-- Location -->
          <td>
            <div class="location-chip">
              <span>📍 ${escapeHtml(dev.location || 'General')}</span>
            </div>
          </td>

          <!-- Predefined Actions & Params -->
          <td>
            <div style="display: flex; flex-direction: column; gap: 4px; font-size: 0.75rem;">
              <div style="display: flex; flex-wrap: wrap; gap: 4px; align-items: center;">
                <span style="font-weight: 600; color: var(--accent-cyan);">⚡ Actions:</span>
                ${(dev.actions || dev.allowed_actions || ['set_power']).map(act => `
                  <span style="background: rgba(0,242,254,0.12); color: #00f2fe; padding: 1px 6px; border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;">${escapeHtml(act)}</span>
                `).join('')}
              </div>
              <div style="display: flex; gap: 4px; align-items: center; color: #94a3b8; font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;">
                <span style="font-weight: 600; color: #a855f7;">⚙️ Params:</span>
                <span style="background: rgba(168,85,247,0.12); color: #c084fc; padding: 1px 6px; border-radius: 4px;">${escapeHtml(JSON.stringify(dev.params || dev.parameters || { state: 'on' }))}</span>
              </div>
            </div>
          </td>

          <!-- Connected Devices -->
          <td>
            ${connectedList.length > 0 ? `
              <div class="sub-devices-pill-list">
                <span class="sub-count-badge">
                  ⚡ ${connectedCount} Connected
                </span>
                <div class="sub-pill-tags">
                  ${connectedList.slice(0, 2).map(sub => `
                    <span class="sub-pill" title="${escapeHtml(sub.name || sub.device_id)}">
                      ${sub.channel ? `<span class="sub-pill-ch">${escapeHtml(sub.channel)}</span>` : ''}
                      <span class="sub-pill-title">${escapeHtml(sub.name || sub.device_id)}</span>
                    </span>
                  `).join('')}
                  ${connectedList.length > 2 ? `
                    <span class="sub-pill-more">
                      +${connectedList.length - 2} more
                    </span>
                  ` : ''}
                </div>
              </div>
            ` : `
              <span class="sub-empty-tag">
                None (Standalone)
              </span>
            `}
          </td>

          <!-- Power State Toggle -->
          <td style="text-align: center;">
            ${hasPowerAction ? `
              <button 
                type="button" 
                class="power-btn ${isPowerOn ? 'on' : 'off'}" 
                data-devid="${escapeHtml(dev.device_id)}"
                title="Toggle power state"
              >
                <span class="power-indicator-dot"></span>
                <span class="power-label">${isPowerOn ? 'ON' : 'OFF'}</span>
              </button>
            ` : `
              <span class="power-always-on">
                <span class="power-dot-fixed"></span> Always On
              </span>
            `}
          </td>

          <!-- Online Status -->
          <td style="text-align: center;">
            <div class="device-status-badge ${isOnline ? 'online' : 'offline'}" style="justify-content: center;">
              <span class="status-beacon ${isOnline ? 'beacon-pulse' : ''}"></span>
              <span>${isOnline ? 'Online' : 'Offline'}</span>
            </div>
          </td>

          <!-- Action Buttons (Edit / Delete) -->
          <td style="text-align: right;">
            <div class="action-buttons-group" style="justify-content: flex-end;">
              <button 
                type="button" 
                class="action-btn edit-btn" 
                data-devid="${escapeHtml(dev.device_id)}"
                title="Edit device details"
              >
                <span>✏️</span>
                <span>Edit</span>
              </button>
              <button 
                type="button" 
                class="action-btn delete-btn" 
                data-devid="${escapeHtml(dev.device_id)}"
                data-devname="${escapeHtml(dev.name)}"
                title="Delete device"
              >
                <span>🗑️</span>
                <span>Delete</span>
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join('');

    _bindTableEvents();
  }

  // Bind dynamic table actions (Power Toggle, Edit, Delete)
  function _bindTableEvents() {
    // 1. Power Toggle
    document.querySelectorAll('.power-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const devId = btn.getAttribute('data-devid');
        if (!devId) return;

        btn.disabled = true;
        const origHTML = btn.innerHTML;
        btn.innerHTML = `<span>⏳</span>`;

        try {
          const res = await fetch(`/api/devices/${encodeURIComponent(devId)}/toggle`, {
            method: 'POST'
          });
          if (res.ok) {
            const result = await res.json();
            showToast(`Device '${result.device_name}' power set to ${result.new_state.toUpperCase()}.`);
            await fetchDevices();
          } else {
            showToast('Failed to toggle power state.', 'error');
            btn.innerHTML = origHTML;
            btn.disabled = false;
          }
        } catch (err) {
          console.error('Error toggling power:', err);
          showToast('Connection error toggling power.', 'error');
          btn.innerHTML = origHTML;
          btn.disabled = false;
        }
      });
    });

    // 2. Edit Device
    document.querySelectorAll('.edit-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const devId = btn.getAttribute('data-devid');
        const dev = allDevices.find(d => d.device_id === devId);
        if (dev) {
          openEditModal(dev);
        }
      });
    });

    // 3. Delete Device
    document.querySelectorAll('.delete-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const devId = btn.getAttribute('data-devid');
        const devName = btn.getAttribute('data-devname') || devId;
        if (!devId) return;

        const confirmed = confirm(`Are you sure you want to delete '${devName}' (ID: ${devId}) from the device registry?`);
        if (!confirmed) return;

        try {
          const res = await fetch(`/api/devices/${encodeURIComponent(devId)}`, {
            method: 'DELETE'
          });
          if (res.ok) {
            showToast(`Device '${devName}' deleted successfully.`);
            await fetchDevices();
          } else {
            const err = await res.json();
            showToast(err.detail || 'Failed to delete device.', 'error');
          }
        } catch (err) {
          console.error('Error deleting device:', err);
          showToast('Network error while deleting device.', 'error');
        }
      });
    });
  }

  // Open Modal: Add Mode
  function openAddModal() {
    if (!modal) return;
    modalTitle.innerHTML = '➕ Add New Device';
    formIsEdit.value = 'false';
    formDevId.value = '';
    formDevId.disabled = false;
    formDevName.value = '';
    formNodeId.value = 'NODE-ESP8266-02';
    formDevType.value = 'Relay';
    formLocation.value = 'Living Room';
    if (formActions) formActions.value = 'set_power, turn_on, turn_off, get_status';
    if (formParams) formParams.value = '{\n  "state": "on"\n}';
    formAliases.value = '';
    formSubDevices.value = '';

    modal.style.display = 'flex';
    requestAnimationFrame(() => modal.classList.add('active'));
    formDevId.focus();
  }

  // Open Modal: Edit Mode
  function openEditModal(dev) {
    if (!modal) return;
    modalTitle.innerHTML = `✏️ Edit Device Details — ${escapeHtml(dev.name)}`;
    formIsEdit.value = 'true';
    formDevId.value = dev.device_id;
    formDevId.disabled = true; // Cannot alter primary key ID in edit mode
    formDevName.value = dev.name || '';
    formNodeId.value = dev.node_id || '';
    formDevType.value = dev.type || 'Relay';
    formLocation.value = dev.location || '';
    if (formActions) formActions.value = (dev.actions || dev.allowed_actions || ['set_power', 'turn_on', 'turn_off']).join(', ');
    if (formParams) formParams.value = JSON.stringify(dev.params || dev.parameters || { state: 'on' }, null, 2);
    formAliases.value = (dev.aliases || []).join(', ');

    if (dev.connected_devices && dev.connected_devices.length > 0) {
      formSubDevices.value = JSON.stringify(dev.connected_devices, null, 2);
    } else {
      formSubDevices.value = '';
    }

    modal.style.display = 'flex';
    requestAnimationFrame(() => modal.classList.add('active'));
    formDevName.focus();
  }

  function closeModal() {
    if (modal) {
      modal.classList.remove('active');
      setTimeout(() => {
        if (!modal.classList.contains('active')) {
          modal.style.display = 'none';
        }
      }, 200);
    }
  }

  // Form Submission (Add or Update)
  if (deviceForm) {
    deviceForm.addEventListener('submit', async (e) => {
      e.preventDefault();

      const isEdit = formIsEdit.value === 'true';
      const devId = formDevId.value.trim();
      const devName = formDevName.value.trim();
      const nodeId = formNodeId.value.trim();
      const devType = formDevType.value;
      const location = formLocation.value.trim();
      const aliases = formAliases.value.split(',').map(s => s.trim()).filter(Boolean);
      const actions = formActions && formActions.value
        ? formActions.value.split(',').map(s => s.trim()).filter(Boolean)
        : ['set_power', 'turn_on', 'turn_off'];
      let params = { state: 'on' };
      if (formParams && formParams.value.trim()) {
        try {
          params = JSON.parse(formParams.value.trim());
        } catch (e) {
          params = { state: formParams.value.trim() };
        }
      }

      // Parse sub-devices
      let connectedList = [];
      const subDevsRaw = formSubDevices.value.trim();
      if (subDevsRaw) {
        try {
          if (subDevsRaw.startsWith('[') || subDevsRaw.startsWith('{')) {
            const parsed = JSON.parse(subDevsRaw);
            connectedList = Array.isArray(parsed) ? parsed : [parsed];
          } else {
            // Line-by-line format
            connectedList = subDevsRaw.split('\n').filter(Boolean).map((line, idx) => ({
              device_id: `sub_${idx + 1}`,
              name: line.trim(),
              status: 'online'
            }));
          }
        } catch (err) {
          alert('Invalid format for connected sub-devices. Please use valid JSON or line-separated text.');
          return;
        }
      }

      const submitBtn = document.getElementById('modal-submit-btn');
      submitBtn.disabled = true;
      submitBtn.textContent = 'Saving...';

      try {
        let res;
        if (isEdit) {
          // PUT update
          res = await fetch(`/api/devices/${encodeURIComponent(devId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name: devName,
              node_id: nodeId,
              type: devType,
              location: location,
              actions: actions,
              allowed_actions: actions,
              params: params,
              aliases: aliases,
              connected_devices: connectedList
            })
          });
        } else {
          // POST create
          res = await fetch('/api/devices', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              device_id: devId,
              name: devName,
              node_id: nodeId,
              type: devType,
              location: location,
              actions: actions,
              allowed_actions: actions,
              params: params,
              aliases: aliases,
              connected_devices: connectedList
            })
          });
        }

        if (res.ok) {
          const result = await res.json();
          closeModal();
          showToast(result.message || 'Device saved successfully.');
          await fetchDevices();
        } else {
          const err = await res.json();
          alert(err.detail || 'Failed to save device.');
        }
      } catch (err) {
        console.error('Error saving device:', err);
        alert('Network error while saving device.');
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Save Device';
      }
    });
  }

  // Modal Event Listeners
  if (openAddBtn) openAddBtn.addEventListener('click', openAddModal);
  if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeModal);
  if (modalCancelBtn) modalCancelBtn.addEventListener('click', closeModal);
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });
  }

  // Filter pills click
  if (filterPills) {
    filterPills.addEventListener('click', (e) => {
      const btn = e.target.closest('.filter-btn');
      if (!btn) return;

      filterPills.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentFilter = btn.getAttribute('data-category') || 'all';
      renderTable();
    });
  }

  // Search input typing
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      searchQuery = e.target.value.trim();
      renderTable();
    });
  }

  // Refresh button
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      refreshBtn.disabled = true;
      fetchDevices().finally(() => {
        refreshBtn.disabled = false;
        showToast('Device table refreshed.');
      });
    });
  }

  // Health and connection check
  function updateConnectionStatus(connected) {
    if (!connectionBadge || !connectionText) return;
    if (connected) {
      connectionBadge.className = 'connection-badge connected';
      connectionText.textContent = 'Hub Connected';
    } else {
      connectionBadge.className = 'connection-badge disconnected';
      connectionText.textContent = 'Hub Offline';
    }
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // Initial load
  fetchDevices();
});
