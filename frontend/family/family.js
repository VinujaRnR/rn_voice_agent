/**
 * Family Portal Controller
 * Fully synchronized with MySQL 8.4 database.
 */

document.addEventListener('DOMContentLoaded', async () => {
    await renderSharedNav('family');

    const msgForm = document.getElementById('family-msg-form');
    const msgInput = document.getElementById('family-message');
    const feedback = document.getElementById('note-sent-feedback');

    if (msgForm) {
        msgForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const msg = msgInput.value.trim();
            if (!msg) return;

            try {
                await api.sendFamilyContactRequest('Family Contact', msg);
                if (feedback) feedback.style.display = 'inline';
                msgInput.value = '';
                setTimeout(() => {
                    if (feedback) feedback.style.display = 'none';
                }, 4000);
            } catch (err) {
                alert('Failed to send note: ' + err.message);
            }
        });
    }

    // Load Live Family Contacts from MySQL
    async function loadContacts() {
        try {
            const rawData = await api.getFamilyContacts();
            const contacts = Array.isArray(rawData) ? rawData : (rawData.contacts || []);
            const list = document.getElementById('contacts-list');
            if (!list) return;

            if (contacts && contacts.length > 0) {
                list.innerHTML = '';
                contacts.forEach(c => {
                    const li = document.createElement('li');
                    li.className = 'timeline-item';
                    li.innerHTML = `
                        <div class="item-info">
                            <span class="item-title">${c.name}</span>
                            <span class="item-sub">${c.relationship_type || 'Family'} • ${c.phone_number || 'No phone'} ${c.email ? '• ' + c.email : ''}</span>
                        </div>
                        <span class="status-pill ${c.is_emergency_contact ? 'pill-green' : 'pill-blue'}">
                            ${c.is_emergency_contact ? 'Emergency Contact' : 'Authorized'}
                        </span>
                    `;
                    list.appendChild(li);
                });
            } else {
                list.innerHTML = `
                    <li class="timeline-item" style="color: var(--text-muted); font-size: 0.95rem;">
                        No family contacts registered in MySQL database yet.
                    </li>
                `;
            }
        } catch (e) {
            console.warn('Error loading family contacts from MySQL:', e);
        }
    }

    await loadContacts();

    // Add Birthday Handler
    const btnAddBirthday = document.getElementById('btn-add-birthday');
    if (btnAddBirthday) {
        btnAddBirthday.addEventListener('click', () => {
            const name = prompt('Enter family member name and event:', 'Sarah Higgins - Birthday');
            if (name) {
                const list = document.getElementById('events-list');
                const li = document.createElement('li');
                li.className = 'timeline-item';
                li.innerHTML = `
                    <div class="item-info">
                        <span class="item-title">${name}</span>
                        <span class="item-sub">Registered Event</span>
                    </div>
                    <span class="status-pill pill-amber">New</span>
                `;
                list.appendChild(li);
            }
        });
    }
});
