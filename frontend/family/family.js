/**
 * Family Portal Controller
 */

document.addEventListener('DOMContentLoaded', async () => {
    renderSharedNav('family');

    const msgForm = document.getElementById('family-msg-form');
    const msgInput = document.getElementById('family-message');
    const feedback = document.getElementById('note-sent-feedback');

    msgForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const msg = msgInput.value.trim();
        if (!msg) return;

        try {
            await api.sendFamilyContactRequest('Emma', msg);
            feedback.style.display = 'inline';
            msgInput.value = '';
            setTimeout(() => {
                feedback.style.display = 'none';
            }, 4000);
        } catch (err) {
            alert('Failed to send note: ' + err.message);
        }
    });

    // Load Live Family Contacts
    try {
        const contactsData = await api.getFamilyContacts();
        if (contactsData && contactsData.contacts && contactsData.contacts.length > 0) {
            const list = document.getElementById('contacts-list');
            list.innerHTML = '';
            contactsData.contacts.forEach(c => {
                const li = document.createElement('li');
                li.className = 'timeline-item';
                li.innerHTML = `
                    <div class="item-info">
                        <span class="item-title">${c.name}</span>
                        <span class="item-sub">${c.relationship_type} • ${c.phone_number || 'No phone'}</span>
                    </div>
                    <span class="status-pill ${c.is_primary ? 'pill-green' : 'pill-blue'}">
                        ${c.is_primary ? 'Primary' : 'Authorized'}
                    </span>
                `;
                list.appendChild(li);
            });
        }
    } catch (e) {
        console.log('Using default contacts view.');
    }

    // Add Birthday Handler
    document.getElementById('btn-add-birthday').addEventListener('click', () => {
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
});
