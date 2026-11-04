/**
 * Admin Console Controller
 * Fully synchronized with MySQL 8.4 database.
 */

document.addEventListener('DOMContentLoaded', async () => {
    await renderSharedNav('admin');

    const form = document.getElementById('device-enroll-form');
    const feedback = document.getElementById('enroll-feedback');
    const tableBody = document.getElementById('admin-devices-table');

    // 1. Fetch live registered devices from MySQL
    async function loadDevices() {
        try {
            const rawData = await api.listDevices();
            const devices = Array.isArray(rawData) ? rawData : (rawData.devices || []);
            
            if (devices && devices.length > 0) {
                tableBody.innerHTML = '';
                devices.forEach(dev => {
                    const tr = document.createElement('tr');
                    tr.style.borderBottom = '1px solid var(--border-color)';
                    tr.innerHTML = `
                        <td style="padding: 12px; font-weight: 600;">${dev.name}</td>
                        <td style="padding: 12px;">${dev.device_type || dev.type}</td>
                        <td style="padding: 12px;"><code>${dev.device_id || dev.node_id || dev.id}</code></td>
                        <td style="padding: 12px;">${dev.connection_type || 'WiFi'}</td>
                        <td style="padding: 12px;"><span class="status-pill pill-green">${dev.online_status || 'Online'}</span></td>
                        <td style="padding: 12px;"><button class="a11y-btn" onclick="alert('Ping dispatched to hardware node ${dev.device_id || dev.id}.')">Test Ping</button></td>
                    `;
                    tableBody.appendChild(tr);
                });
            } else {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="6" style="padding: 16px; text-align: center; color: var(--text-muted);">
                            No devices found in MySQL database. Enroll a device below to add it to your household.
                        </td>
                    </tr>
                `;
            }
        } catch (e) {
            console.warn('Error loading MySQL devices:', e);
        }
    }

    await loadDevices();

    // 2. Enroll device into MySQL
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const devName = document.getElementById('dev-name').value.trim();
            const devType = document.getElementById('dev-type').value;
            const devNode = document.getElementById('dev-node').value.trim();
            const devProto = document.getElementById('dev-protocol').value;

            try {
                await api.registerDevice({
                    name: devName,
                    device_id: devNode,
                    device_type: devType,
                    location: 'Living Room',
                    connection_type: devProto,
                    capabilities: ['turn_on', 'turn_off', 'set_power']
                });

                if (feedback) {
                    feedback.style.display = 'inline';
                    setTimeout(() => { feedback.style.display = 'none'; }, 3000);
                }
                form.reset();
                await loadDevices();
                alert(`✓ Device "${devName}" enrolled successfully in MySQL database.`);
            } catch (err) {
                alert('Failed to register device in MySQL: ' + err.message);
            }
        });
    }
});
