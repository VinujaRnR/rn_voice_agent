/**
 * Sarah Admin Console & IoT Device Management Controller
 * Dual-synchronized with data/devices.json dataset and MySQL 8.4 database.
 */

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Render shared navigation
    if (typeof renderSharedNav === 'function') {
        await renderSharedNav('admin');
    }

    // Dataset template presets matching data/devices.json
    const DATASET_TEMPLATES = {
        garden_lights: {
            device_id: '98a316e6b658',
            name: 'Garden Pathway Lights',
            node_id: 'NODE-ESP8266-02',
            type: 'Relay',
            location: 'Living Room',
            actions: ['set_power', 'turn_on', 'turn_off', 'get_status'],
            params: { state: 'on' },
            aliases: ['garden lights', 'pathway lights', 'garden lamp', 'pathway light'],
            sub_devices: [
                { name: 'Lamp 1', channel: 'CH1' },
                { name: 'Lamp 2', channel: 'CH2' }
            ]
        },
        farm_lights: {
            device_id: '98a316e6b658',
            name: 'Testing Farm Lights',
            node_id: 'NODE-ESP8266-01',
            type: 'lighting',
            location: 'Farm / Perimeter',
            actions: ['set_power', 'turn_on', 'turn_off', 'get_status'],
            params: { state: 'on' },
            aliases: ['testing farm lights', 'testing farm light', 'farm lights', 'farm relay'],
            sub_devices: [
                { device_id: 'farm_floodlight_1', name: 'Farm Perimeter Floodlight', channel: 'Relay CH1', status: 'online' },
                { device_id: 'farm_barn_light_2', name: 'Barn Worklight', channel: 'Relay CH2', status: 'online' }
            ]
        },
        rn_hub: {
            device_id: 'rn_hub_main',
            name: 'RN Main Control Hub',
            node_id: 'NODE-HUB-MASTER-01',
            type: 'hub',
            location: 'Living Room',
            actions: ['reboot', 'sync_devices', 'get_telemetry', 'broadcast'],
            params: { mode: 'auto' },
            aliases: ['main hub', 'home gateway', 'rn hub', 'central controller'],
            sub_devices: [
                { device_id: 'zigbee_dongle', name: 'Zigbee 3.0 Coordinator', channel: 'USB0' },
                { device_id: 'ble_gateway', name: 'Bluetooth LE Scanner', channel: 'USB1' }
            ]
        },
        smart_plug: {
            device_id: 'smart_plug_living',
            name: 'Smart Plug Living Room',
            node_id: 'NODE-ESP8266-03',
            type: 'smart_plug',
            location: 'Living Room',
            actions: ['turn_on', 'turn_off', 'set_power', 'get_power_consumption'],
            params: { state: 'on' },
            aliases: ['living room plug', 'coffee maker plug', 'lamp plug', 'main switch'],
            sub_devices: [
                { device_id: 'plug_meter', name: 'Current & Energy Sensor', channel: 'ADC' }
            ]
        },
        thermostat: {
            device_id: 'thermostat',
            name: 'Master Climate HVAC',
            node_id: 'NODE-HVAC-05',
            type: 'climate',
            location: 'Living Room',
            actions: ['set_temperature', 'set_mode', 'turn_on', 'turn_off'],
            params: { target_temperature: 22.0, mode: 'cool' },
            aliases: ['thermostat', 'climate', 'ac', 'air conditioning', 'heater'],
            sub_devices: [
                { name: 'DHT22 Temp Sensor', channel: 'GPIO4' },
                { name: 'HVAC Compressor Relay', channel: 'GPIO14' }
            ]
        },
        robot_base: {
            device_id: 'robot_base',
            name: 'Autonomous Mobile Robot Base',
            node_id: 'NODE-ROS2-ROBOT-06',
            type: 'robot',
            location: 'Living Room',
            actions: ['start_cleaning', 'dock', 'stop', 'navigate'],
            params: { mode: 'auto', room: 'all' },
            aliases: ['robot cleaner', 'vacuum', 'mobile base', 'robot vacuum'],
            sub_devices: [
                { name: 'LiDAR 360 Scanner', channel: 'ttyUSB0' },
                { name: 'Differential Drive Base', channel: 'CAN0' }
            ]
        },
        arm_manipulator: {
            device_id: 'arm_manipulator',
            name: 'Robot 6-DOF Arm Manipulator',
            node_id: 'NODE-CAN-ARM-07',
            type: 'arm',
            location: 'Laboratory',
            actions: ['home', 'grip', 'release', 'move_to_pose'],
            params: { pose: 'home', speed: 50 },
            aliases: ['robotic arm', 'arm manipulator', 'gripper', 'robot arm'],
            sub_devices: [
                { name: 'Parallel Gripper', channel: 'CAN_ID_1' },
                { name: 'Joint Steppers 1-6', channel: 'CAN_BUS' }
            ]
        },
        fall_radar: {
            device_id: 'fall_radar_01',
            name: 'Safety Radar Fall Sensor',
            node_id: 'NODE-RADAR-01',
            type: 'radar',
            location: 'Living Room',
            actions: ['get_presence', 'get_fall_status', 'calibrate'],
            params: { sensitivity: 'high' },
            aliases: ['fall sensor', 'radar sensor', 'safety radar', 'presence detector'],
            sub_devices: [
                { name: '60GHz mmWave Radar Transceiver', channel: 'UART' }
            ]
        },
        kitchen_lights: {
            device_id: 'kitchen_lights',
            name: 'Kitchen Pendant Lights',
            node_id: 'NODE-ZIGBEE-KIT-03',
            type: 'lighting',
            location: 'Kitchen',
            actions: ['turn_on', 'turn_off', 'set_brightness'],
            params: { state: 'on', brightness: 80 },
            aliases: ['kitchen lights', 'kitchen lamp', 'pendant lights', 'kitchen ceiling light'],
            sub_devices: [
                { name: 'Pendant 1', channel: 'CH1' },
                { name: 'Pendant 2', channel: 'CH2' }
            ]
        }
    };

    // DOM Elements
    const modal = document.getElementById('device-modal');
    const modalTitle = document.getElementById('modal-title');
    const modalCloseBtn = document.getElementById('modal-close-btn');
    const modalCancelBtn = document.getElementById('modal-cancel-btn');
    const modalSubmitBtn = document.getElementById('modal-submit-btn');
    const btnOpenAddModal = document.getElementById('btn-open-add-modal');
    const btnSyncDataset = document.getElementById('btn-sync-dataset');
    const toolbarTemplateSelect = document.getElementById('toolbar-template-select');
    const modalTemplateSelect = document.getElementById('modal-template-select');
    const searchInput = document.getElementById('search-input');
    const filterPills = document.getElementById('filter-pills');
    const tableBody = document.getElementById('admin-devices-table');
    const matchCountEl = document.getElementById('devices-match-count');
    const syncStatusIndicator = document.getElementById('sync-status-indicator');

    // Modal Form Inputs
    const form = document.getElementById('device-form');
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

    // Counters
    const statTotalDevs = document.getElementById('stat-total-devices');
    const statOnlineDevs = document.getElementById('stat-online-devices');
    const statTotalNodes = document.getElementById('stat-total-nodes');
    const statTotalSubDevs = document.getElementById('stat-total-sub-devices');

    let allDevices = [];
    let currentFilter = 'all';
    let searchQuery = '';

    // Device Icon Helper
    function getDeviceIcon(type) {
        const t = (type || '').toLowerCase();
        if (t.includes('relay')) return '⚡';
        if (t.includes('light')) return '💡';
        if (t.includes('hub')) return '🌐';
        if (t.includes('plug')) return '🔌';
        if (t.includes('climate') || t.includes('hvac')) return '❄️';
        if (t.includes('robot')) return '🤖';
        if (t.includes('arm')) return '🦾';
        if (t.includes('radar') || t.includes('sensor')) return '📡';
        return '📟';
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // Load devices from dataset API
    async function loadDevices() {
        try {
            const res = await fetch('/api/devices');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            allDevices = data.devices || [];

            // Update Statistics
            const total = allDevices.length;
            const online = allDevices.filter(d => (d.status || d.online_status || '').toLowerCase() === 'online').length;
            const nodes = new Set(allDevices.map(d => d.node_id).filter(Boolean)).size;
            let subDevCount = 0;
            allDevices.forEach(d => {
                subDevCount += (d.connected_devices || []).length || d.connected_devices_count || 0;
            });

            if (statTotalDevs) statTotalDevs.textContent = total;
            if (statOnlineDevs) statOnlineDevs.textContent = online;
            if (statTotalNodes) statTotalNodes.textContent = nodes;
            if (statTotalSubDevs) statTotalSubDevs.textContent = subDevCount;

            updateFilterCounts();
            renderTable();
        } catch (e) {
            console.error('Error loading devices from dataset:', e);
            if (tableBody) {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="8" style="padding: 24px; text-align: center; color: var(--danger);">
                            ⚠️ Failed to load devices from dataset API. Please ensure server is running.
                        </td>
                    </tr>
                `;
            }
        }
    }

    // Update filter counts
    function updateFilterCounts() {
        if (!filterPills) return;
        const counts = {
            all: allDevices.length,
            relay: allDevices.filter(d => (d.type || '').toLowerCase().includes('relay')).length,
            lighting: allDevices.filter(d => (d.type || '').toLowerCase().includes('light')).length,
            hub: allDevices.filter(d => (d.type || '').toLowerCase().includes('hub')).length,
            smart_plug: allDevices.filter(d => (d.type || '').toLowerCase().includes('plug')).length,
            climate: allDevices.filter(d => (d.type || '').toLowerCase().includes('climate') || (d.type || '').toLowerCase().includes('hvac')).length,
            robot: allDevices.filter(d => (d.type || '').toLowerCase().includes('robot') || (d.type || '').toLowerCase().includes('arm')).length,
            sensor: allDevices.filter(d => (d.type || '').toLowerCase().includes('sensor') || (d.type || '').toLowerCase().includes('radar')).length
        };

        const setBadge = (id, count) => {
            const el = document.getElementById(id);
            if (el) el.textContent = count;
        };

        setBadge('filter-count-all', counts.all);
        setBadge('filter-count-relay', counts.relay);
        setBadge('filter-count-lighting', counts.lighting);
        setBadge('filter-count-hub', counts.hub);
        setBadge('filter-count-plug', counts.smart_plug);
        setBadge('filter-count-climate', counts.climate);
        setBadge('filter-count-robot', counts.robot);
        setBadge('filter-count-sensor', counts.sensor);
    }

    // Render Table
    function renderTable() {
        if (!tableBody) return;

        const filtered = allDevices.filter(dev => {
            if (currentFilter !== 'all') {
                const t = (dev.type || '').toLowerCase();
                if (currentFilter === 'relay' && !t.includes('relay')) return false;
                if (currentFilter === 'lighting' && !t.includes('light')) return false;
                if (currentFilter === 'hub' && !t.includes('hub')) return false;
                if (currentFilter === 'smart_plug' && !t.includes('plug')) return false;
                if (currentFilter === 'climate' && !t.includes('climate') && !t.includes('hvac')) return false;
                if (currentFilter === 'robot' && !t.includes('robot') && !t.includes('arm')) return false;
                if (currentFilter === 'sensor' && !t.includes('sensor') && !t.includes('radar')) return false;
            }

            if (searchQuery) {
                const q = searchQuery.toLowerCase();
                const name = (dev.name || '').toLowerCase();
                const devId = (dev.device_id || '').toLowerCase();
                const nodeId = (dev.node_id || '').toLowerCase();
                const loc = (dev.location || '').toLowerCase();
                const aliases = (dev.aliases || []).join(' ').toLowerCase();
                const subs = (dev.connected_devices || []).map(s => s.name || '').join(' ').toLowerCase();

                if (!name.includes(q) && !devId.includes(q) && !nodeId.includes(q) && !loc.includes(q) && !aliases.includes(q) && !subs.includes(q)) {
                    return false;
                }
            }
            return true;
        });

        if (matchCountEl) {
            matchCountEl.textContent = `Showing ${filtered.length} of ${allDevices.length} devices`;
        }

        if (filtered.length === 0) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="8" style="padding: 40px; text-align: center; color: var(--text-muted);">
                        No matching devices found in household registry. Click "Add New Device" to enroll one.
                    </td>
                </tr>
            `;
            return;
        }

        tableBody.innerHTML = '';
        filtered.forEach(dev => {
            const tr = document.createElement('tr');
            tr.style.borderBottom = '1px solid var(--border-color)';
            tr.id = `row-${escapeHtml(dev.device_id)}`;

            const icon = getDeviceIcon(dev.type);
            const isOnline = (dev.status || dev.online_status || 'online').toLowerCase() === 'online';
            const powerState = (dev.power_state || 'off').toLowerCase();
            const isPowerOn = powerState === 'on';

            // Aliases badges
            const aliasesHtml = (dev.aliases && dev.aliases.length > 0)
                ? `<div style="margin-top: 4px;">${dev.aliases.slice(0, 3).map(a => `<span class="alias-pill">🗣️ "${escapeHtml(a)}"</span>`).join(' ')}${dev.aliases.length > 3 ? `<span class="alias-pill">+${dev.aliases.length - 3} more</span>` : ''}</div>`
                : '';

            // Actions & Params badges
            const actionsList = dev.allowed_actions || dev.actions || ['set_power'];
            const actionsHtml = actionsList.slice(0, 3).map(a => `<span class="action-pill">${escapeHtml(a)}</span>`).join(' ');
            const paramsSummary = dev.params && Object.keys(dev.params).length > 0
                ? `<div style="font-size: 0.75rem; color: var(--text-muted); font-family: monospace; margin-top: 4px;">${escapeHtml(JSON.stringify(dev.params))}</div>`
                : '';

            // Sub-Devices badges
            const subDevs = dev.connected_devices || [];
            const subDevsHtml = subDevs.length > 0
                ? subDevs.slice(0, 2).map(s => `<span class="sub-dev-pill">🔌 ${escapeHtml(s.name || s.device_name || 'Sub')}${s.channel ? ` (${escapeHtml(s.channel)})` : ''}</span>`).join('<br>') +
                  (subDevs.length > 2 ? `<div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 2px;">+${subDevs.length - 2} more peripherals</div>` : '')
                : '<span style="color: var(--text-muted); font-size: 0.8rem;">Direct Node</span>';

            tr.innerHTML = `
                <td style="padding: 14px 16px;">
                    <div style="display: flex; align-items: flex-start; gap: 10px;">
                        <span style="font-size: 1.4rem;">${icon}</span>
                        <div>
                            <div style="font-weight: 700; color: var(--text-base);">${escapeHtml(dev.name)}</div>
                            ${aliasesHtml}
                        </div>
                    </div>
                </td>
                <td style="padding: 14px 16px;">
                    <span class="node-badge">${escapeHtml(dev.device_id)}</span>
                </td>
                <td style="padding: 14px 16px;">
                    <span class="node-badge" style="color: #4f46e5; border-color: rgba(99, 102, 241, 0.3);">
                        ${escapeHtml(dev.node_id || 'NODE-STANDALONE')}
                    </span>
                </td>
                <td style="padding: 14px 16px;">
                    <span class="type-badge">${escapeHtml(dev.type || 'generic')}</span>
                    <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 4px;">📍 ${escapeHtml(dev.location || 'Living Room')}</div>
                </td>
                <td style="padding: 14px 16px;">
                    ${actionsHtml}
                    ${paramsSummary}
                </td>
                <td style="padding: 14px 16px;">
                    ${subDevsHtml}
                </td>
                <td style="padding: 14px 16px;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <button type="button" class="power-btn ${isPowerOn ? 'on' : 'off'}" data-dev-id="${escapeHtml(dev.device_id)}" title="Click to toggle power">
                            ${isPowerOn ? '⚡ ON' : '⭕ OFF'}
                        </button>
                        <span class="status-pill ${isOnline ? 'pill-green' : 'pill-red'}">
                            ${isOnline ? 'Online' : 'Offline'}
                        </span>
                    </div>
                </td>
                <td style="padding: 14px 16px; text-align: right;">
                    <div class="action-buttons-group" style="justify-content: flex-end;">
                        <button type="button" class="action-btn edit-btn" data-dev-id="${escapeHtml(dev.device_id)}" title="Edit Device Details">
                            ✏️ Edit
                        </button>
                        <button type="button" class="action-btn delete-btn" data-dev-id="${escapeHtml(dev.device_id)}" data-dev-name="${escapeHtml(dev.name)}" title="Delete Device">
                            🗑️ Delete
                        </button>
                    </div>
                </td>
            `;

            tableBody.appendChild(tr);
        });

        attachRowActionListeners();
    }

    // Attach click listeners for Power toggle, Edit, Delete
    function attachRowActionListeners() {
        // Power Toggles
        document.querySelectorAll('.power-btn').forEach(btn => {
            btn.onclick = async (e) => {
                e.stopPropagation();
                const devId = btn.getAttribute('data-dev-id');
                btn.disabled = true;
                btn.style.opacity = '0.5';
                try {
                    const res = await fetch(`/api/devices/${encodeURIComponent(devId)}/toggle`, { method: 'POST' });
                    if (res.ok) {
                        const data = await res.json();
                        // Update device local state
                        const target = allDevices.find(d => d.device_id === devId);
                        if (target) {
                            target.power_state = data.new_state;
                        }
                        renderTable();
                    } else {
                        alert(`Failed to toggle device power.`);
                    }
                } catch (err) {
                    alert(`Network error toggling device: ${err.message}`);
                } finally {
                    btn.disabled = false;
                    btn.style.opacity = '1';
                }
            };
        });

        // Edit Buttons
        document.querySelectorAll('.action-btn.edit-btn').forEach(btn => {
            btn.onclick = (e) => {
                e.stopPropagation();
                const devId = btn.getAttribute('data-dev-id');
                const target = allDevices.find(d => d.device_id === devId);
                if (target) {
                    openEditModal(target);
                }
            };
        });

        // Delete Buttons
        document.querySelectorAll('.action-btn.delete-btn').forEach(btn => {
            btn.onclick = async (e) => {
                e.stopPropagation();
                const devId = btn.getAttribute('data-dev-id');
                const devName = btn.getAttribute('data-dev-name');
                if (!confirm(`Are you sure you want to delete "${devName}" (${devId}) from the dataset and MySQL database?`)) {
                    return;
                }
                btn.disabled = true;
                try {
                    const res = await fetch(`/api/devices/${encodeURIComponent(devId)}`, { method: 'DELETE' });
                    if (res.ok) {
                        alert(`✓ Device "${devName}" deleted successfully.`);
                        await loadDevices();
                    } else {
                        const err = await res.json();
                        alert(`Failed to delete: ${err.detail || 'Server error'}`);
                    }
                } catch (err) {
                    alert(`Error deleting device: ${err.message}`);
                } finally {
                    btn.disabled = false;
                }
            };
        });
    }

    // Populate form with dataset template
    function populateFormWithTemplate(templateKey) {
        const t = DATASET_TEMPLATES[templateKey];
        if (!t) return;

        formDevId.value = t.device_id;
        formDevName.value = t.name;
        formNodeId.value = t.node_id;
        formDevType.value = t.type;
        formLocation.value = t.location;
        formActions.value = t.actions.join(', ');
        formParams.value = JSON.stringify(t.params, null, 2);
        formAliases.value = t.aliases.join(', ');
        formSubDevices.value = JSON.stringify(t.sub_devices, null, 2);
    }

    // Open Modal in Add Mode
    function openAddModal() {
        form.reset();
        formIsEdit.value = 'false';
        formDevId.disabled = false;
        modalTitle.textContent = '➕ Add New Device';
        modalSubmitBtn.textContent = 'Save Device';

        // Set clean defaults matching user specifications
        formDevId.placeholder = 'e.g. 98a316e6b658 or garden_lights';
        formDevName.placeholder = 'e.g. Garden Pathway Lights';
        formNodeId.value = 'NODE-ESP8266-02';
        formDevType.value = 'Relay';
        formLocation.value = 'Living Room';
        formActions.value = 'set_power, turn_on, turn_off, get_status';
        formParams.value = '{"state": "on"}';
        formAliases.value = 'garden lights, pathway lights, garden lamp';
        formSubDevices.value = '[{"name": "Lamp 1", "channel": "CH1"}, {"name": "Lamp 2", "channel": "CH2"}]';

        modal.style.display = 'flex';
        requestAnimationFrame(() => modal.classList.add('active'));
        formDevId.focus();
    }

    // Open Modal in Edit Mode
    function openEditModal(dev) {
        form.reset();
        formIsEdit.value = 'true';
        modalTitle.textContent = `✏️ Edit Device — ${dev.name}`;
        modalSubmitBtn.textContent = 'Update Device';

        formDevId.value = dev.device_id || '';
        formDevId.disabled = true; // Primary ID cannot be changed on update
        formDevName.value = dev.name || '';
        formNodeId.value = dev.node_id || '';
        formDevType.value = dev.type || 'Relay';
        formLocation.value = dev.location || 'Living Room';

        const actions = dev.actions || dev.allowed_actions || ['set_power', 'turn_on', 'turn_off', 'get_status'];
        formActions.value = actions.join(', ');

        const params = dev.params || dev.parameters || { state: 'on' };
        formParams.value = JSON.stringify(params, null, 2);

        formAliases.value = (dev.aliases || []).join(', ');

        const subDevs = dev.connected_devices || [];
        formSubDevices.value = subDevs.length > 0 ? JSON.stringify(subDevs, null, 2) : '';

        modal.style.display = 'flex';
        requestAnimationFrame(() => modal.classList.add('active'));
        formDevName.focus();
    }

    function closeModal() {
        modal.classList.remove('active');
        setTimeout(() => {
            if (!modal.classList.contains('active')) {
                modal.style.display = 'none';
            }
        }, 200);
    }

    // Modal listeners
    if (btnOpenAddModal) btnOpenAddModal.onclick = openAddModal;
    if (modalCloseBtn) modalCloseBtn.onclick = closeModal;
    if (modalCancelBtn) modalCancelBtn.onclick = closeModal;
    if (modal) {
        modal.onclick = (e) => {
            if (e.target === modal) closeModal();
        };
    }
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.classList.contains('active')) {
            closeModal();
        }
    });

    // Quick-Fill Selectors
    if (toolbarTemplateSelect) {
        toolbarTemplateSelect.addEventListener('change', (e) => {
            const key = e.target.value;
            if (!key) return;
            openAddModal();
            populateFormWithTemplate(key);
            e.target.value = '';
        });
    }

    if (modalTemplateSelect) {
        modalTemplateSelect.addEventListener('change', (e) => {
            const key = e.target.value;
            if (!key) return;
            populateFormWithTemplate(key);
            e.target.value = '';
        });
    }

    // Form Submission (Add or Update)
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const isEdit = formIsEdit.value === 'true';
            const devId = formDevId.value.trim();
            const devName = formDevName.value.trim();
            const nodeId = formNodeId.value.trim();
            const devType = formDevType.value;
            const location = formLocation.value.trim() || 'Living Room';

            if (!devId || !devName) {
                alert('Device ID and Device Name are required fields.');
                return;
            }

            // Parse actions
            const actions = formActions.value
                .split(',')
                .map(s => s.trim())
                .filter(Boolean);

            // Parse params JSON
            let params = { state: 'on' };
            const paramsRaw = formParams.value.trim();
            if (paramsRaw) {
                try {
                    params = JSON.parse(paramsRaw);
                } catch (err) {
                    alert('Invalid Predefined Params JSON format. Please provide valid JSON, e.g. {"state": "on"}');
                    formParams.focus();
                    return;
                }
            }

            // Parse aliases
            const aliases = formAliases.value
                .split(',')
                .map(s => s.trim())
                .filter(Boolean);

            // Parse sub-devices
            let subDevices = [];
            const subDevsRaw = formSubDevices.value.trim();
            if (subDevsRaw) {
                try {
                    if (subDevsRaw.startsWith('[') || subDevsRaw.startsWith('{')) {
                        const parsed = JSON.parse(subDevsRaw);
                        subDevices = Array.isArray(parsed) ? parsed : [parsed];
                    } else {
                        // Line-separated format
                        subDevices = subDevsRaw.split('\n').filter(Boolean).map((line, idx) => ({
                            device_id: `sub_${idx + 1}`,
                            name: line.trim(),
                            channel: `CH${idx + 1}`,
                            status: 'online'
                        }));
                    }
                } catch (err) {
                    alert('Invalid format for Connected Sub-Devices. Please use valid JSON array or line-separated text.');
                    formSubDevices.focus();
                    return;
                }
            }

            modalSubmitBtn.disabled = true;
            modalSubmitBtn.textContent = 'Saving...';

            const payload = {
                device_id: devId,
                name: devName,
                node_id: nodeId || 'NODE-ESP8266-02',
                type: devType,
                connection: 'WiFi',
                location: location,
                actions: actions,
                allowed_actions: actions,
                params: params,
                aliases: aliases,
                connected_devices: subDevices
            };

            try {
                let res;
                if (isEdit) {
                    res = await fetch(`/api/devices/${encodeURIComponent(devId)}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                } else {
                    res = await fetch('/api/devices', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                }

                if (res.ok) {
                    const result = await res.json();
                    closeModal();
                    alert(`✓ Device "${devName}" saved successfully in dataset and MySQL database!`);
                    await loadDevices();
                } else {
                    const err = await res.json();
                    alert(`Error: ${err.detail || 'Failed to save device'}`);
                }
            } catch (err) {
                alert(`Network error saving device: ${err.message}`);
            } finally {
                modalSubmitBtn.disabled = false;
                modalSubmitBtn.textContent = isEdit ? 'Update Device' : 'Save Device';
            }
        });
    }

    // Dataset to MySQL Sync Button
    if (btnSyncDataset) {
        btnSyncDataset.addEventListener('click', async () => {
            btnSyncDataset.disabled = true;
            btnSyncDataset.textContent = '⏳ Syncing...';
            try {
                const res = await fetch('/api/devices/sync', { method: 'POST' });
                if (res.ok) {
                    const data = await res.json();
                    if (syncStatusIndicator) {
                        syncStatusIndicator.textContent = `✓ ${data.synced_count} Nodes Synced to MySQL`;
                    }
                    alert(`✓ ${data.message}`);
                    await loadDevices();
                } else {
                    alert('Sync failed. Please check server logs.');
                }
            } catch (err) {
                alert(`Error syncing dataset to MySQL: ${err.message}`);
            } finally {
                btnSyncDataset.disabled = false;
                btnSyncDataset.innerHTML = '<span>📥</span> Sync Dataset to MySQL';
            }
        });
    }

    // Search input
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            searchQuery = e.target.value.trim();
            renderTable();
        });
    }

    // Filter pills
    if (filterPills) {
        filterPills.addEventListener('click', (e) => {
            const btn = e.target.closest('.filter-btn');
            if (!btn) return;

            filterPills.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFilter = btn.getAttribute('data-filter') || 'all';
            renderTable();
        });
    }

    // Initial load
    await loadDevices();
});
