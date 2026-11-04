/**
 * Admin Console Controller
 */

document.addEventListener('DOMContentLoaded', async () => {
    renderSharedNav('admin');

    const form = document.getElementById('device-enroll-form');
    const feedback = document.getElementById('enroll-feedback');
    const tableBody = document.getElementById('admin-devices-table');

    // 1. Fetch live registered devices
    async function loadDevices() {
        try {
            const data = await api.listDevices();
            if (data && data.devices && data.devices.length > 0) {
                tableBody.innerHTML = '';
                data.devices.forEach(dev => {
                    const tr = document.createElement('tr');
                    tr.style.borderBottom = '1px solid var(--border-color)';
                    tr.innerHTML = `
                        <td style="padding: 12px; font-weight: 600;">${dev.name}</td>
                        <td style="padding: 12px;">${dev.device_type}</td>
                        <td style="padding: 12px;"><code>${dev.node_id || dev.device_id}</code></td>
                        <td style="padding: 12px;">${dev.protocol || 'RabbitMQ'}</td>
                        <td style="padding: 12px;"><span class="status-pill pill-green">Online</span></td>
                        <td style="padding: 12px;"><button class="a11y-btn" onclick="alert('Ping sent.')">Test Ping</button></td>
                    `;
                    tableBody.appendChild(tr);
                });
            }
        } catch (e) {
            console.log('Using default device rows in admin table.');
        }
    }

    await loadDevices();

    // 2. Enroll device
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const devName = document.getElementById('dev-name').value;
        const devType = document.getElementById('dev-type').value;
        const devNode = document.getElementById('dev-node').value;
        const devProto = document.getElementById('dev-protocol').value;

        try {
            await api.request('/api/v1/devices', {
                method: 'POST',
                body: JSON.stringify({
                    household_id: api.getHouseholdId(),
                    device_type: devType,
                    name: devName,
                    node_id: devNode,
                    protocol: devProto,
                    capabilities: ['power', 'telemetry']
                })
            });

            feedback.style.display = 'inline';
            form.reset();
            setTimeout(() => { feedback.style.display = 'none'; }, 3000);
            await loadDevices();
        } catch (err) {
            alert('Failed to register device: ' + err.message);
        }
    });
});
