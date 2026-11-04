/**
 * Shared Role Navigation & Header for Sarah Platform
 */

function renderSharedNav(activePage) {
    const navPlaceholder = document.getElementById('shared-nav');
    if (!navPlaceholder) return;

    navPlaceholder.innerHTML = `
        <header class="platform-header">
            <div class="brand-group">
                <div class="brand-avatar-mini">👩</div>
                <div>
                    <h1 class="brand-title">Sarah</h1>
                    <span class="brand-subtitle">RN Robots Multi-User Elderly Care</span>
                </div>
            </div>

            <div class="role-selector-pill">
                <span class="role-icon">👤</span>
                <label for="role-switch" class="sr-only">Switch Active Role:</label>
                <select id="role-switch" class="role-select" aria-label="Switch portal role">
                    <option value="resident" ${activePage === 'resident' ? 'selected' : ''}>Resident (Margaret)</option>
                    <option value="family" ${activePage === 'family' ? 'selected' : ''}>Family (Emma - Daughter)</option>
                    <option value="caregiver" ${activePage === 'caregiver' ? 'selected' : ''}>Caregiver (Nurse Sarah)</option>
                    <option value="admin" ${activePage === 'admin' ? 'selected' : ''}>Admin (RN Hub Console)</option>
                </select>
            </div>
        </header>

        <nav class="portal-nav" aria-label="Portals Navigation">
            <a href="/resident/index.html" class="nav-item ${activePage === 'resident' ? 'active' : ''}">
                <span class="icon">🏡</span>
                <span class="label">Resident Dashboard</span>
            </a>
            <a href="/family/index.html" class="nav-item ${activePage === 'family' ? 'active' : ''}">
                <span class="icon">👨‍👩‍👧</span>
                <span class="label">Family Portal</span>
            </a>
            <a href="/caregiver/index.html" class="nav-item ${activePage === 'caregiver' ? 'active' : ''}">
                <span class="icon">🩺</span>
                <span class="label">Caregiver View</span>
            </a>
            <a href="/admin/index.html" class="nav-item ${activePage === 'admin' ? 'active' : ''}">
                <span class="icon">⚙️</span>
                <span class="label">Admin Console</span>
            </a>
            <a href="/index.html" class="nav-item ${activePage === 'voice' ? 'active' : ''}">
                <span class="icon">🎙️</span>
                <span class="label">Voice Dev Mode</span>
            </a>
            <a href="/zara/index.html" class="nav-item ${activePage === 'zara' ? 'active' : ''}">
                <span class="icon">⚡</span>
                <span class="label">Zara Live BIDI</span>
            </a>
            <a href="/devices.html" class="nav-item ${activePage === 'devices' ? 'active' : ''}">
                <span class="icon">🌐</span>
                <span class="label">Hardware Devices</span>
            </a>
            <a href="/auth/login.html" class="nav-item ${activePage === 'login' ? 'active' : ''}">
                <span class="icon">🔐</span>
                <span class="label">Log In</span>
            </a>
        </nav>
        <div id="a11y-container"></div>
    `;

    // Role switcher event
    const switchEl = document.getElementById('role-switch');
    if (switchEl) {
        switchEl.addEventListener('change', (e) => {
            const chosen = e.target.value;
            if (window.api) {
                if (chosen === 'resident') window.api.setContext('user_margaret', 'resident', 'household_margaret');
                if (chosen === 'family') window.api.setContext('user_emma', 'family', 'household_margaret');
                if (chosen === 'caregiver') window.api.setContext('user_carer_sarah', 'caregiver', 'household_margaret');
                if (chosen === 'admin') window.api.setContext('user_admin', 'admin', 'household_margaret');
            }
            if (chosen === 'resident') window.location.href = '/resident/index.html';
            else if (chosen === 'family') window.location.href = '/family/index.html';
            else if (chosen === 'caregiver') window.location.href = '/caregiver/index.html';
            else if (chosen === 'admin') window.location.href = '/admin/index.html';
        });
    }

    if (window.a11y) {
        window.a11y.renderControls(document.getElementById('a11y-container'));
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { renderSharedNav };
} else {
    window.renderSharedNav = renderSharedNav;
}
