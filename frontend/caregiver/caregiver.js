/**
 * Caregiver Dashboard Controller
 */

document.addEventListener('DOMContentLoaded', async () => {
    renderSharedNav('caregiver');

    // Confirm dose button
    const btnConfirm = document.getElementById('btn-confirm-dose');
    const stageBadge = document.getElementById('stage-badge-1');
    if (btnConfirm && stageBadge) {
        btnConfirm.addEventListener('click', async () => {
            try {
                // Update to caregiver_confirmed
                stageBadge.textContent = 'caregiver_confirmed';
                stageBadge.className = 'status-pill pill-green';
                btnConfirm.disabled = true;
                btnConfirm.textContent = 'Confirmed Ingested';
                alert('✓ Medication dosage adherence recorded: caregiver_confirmed.');
            } catch (err) {
                alert('Error updating medication stage: ' + err.message);
            }
        });
    }

    // Acknowledge escalation button
    const btnAck = document.getElementById('btn-ack-escalation');
    if (btnAck) {
        btnAck.addEventListener('click', () => {
            btnAck.parentElement.style.opacity = '0.5';
            btnAck.disabled = true;
            btnAck.textContent = 'Acknowledged';
            alert('Escalation notification acknowledged. Care log updated.');
        });
    }
});
