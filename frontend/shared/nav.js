/**
 * Shared Role Navigation & Header for Sarah Platform
 * Contains exactly 5 pages:
 * 🏡 Resident Dashboard
 * 👨‍👩‍👧 Family Portal
 * 🩺 Caregiver View
 * ⚙️ Admin Console
 * 🔐 Log In (or 🚪 Log Out when authenticated)
 * Fully connected to MySQL database.
 */

async function renderSharedNav(activePage) {
    const navPlaceholder = document.getElementById('shared-nav');
    if (!navPlaceholder) return;

    // Check authenticated user
    const token = window.api ? window.api.getToken() : localStorage.getItem('sarah_access_token');
    let currentUser = null;
    if (token && window.api) {
        currentUser = await window.api.getCurrentUser();
    }

    const userName = currentUser ? (currentUser.full_name || currentUser.preferred_name || currentUser.email) : (localStorage.getItem('sarah_user_name') || 'Guest User');
    const userRole = currentUser ? currentUser.role : (localStorage.getItem('sarah_role') || 'visitor');
    const householdName = currentUser && currentUser.households && currentUser.households.length > 0 ? currentUser.households[0].name : (localStorage.getItem('sarah_household_name') || 'Home');

    const roleFormatted = userRole.charAt(0).toUpperCase() + userRole.slice(1).replace('_', ' ');

    navPlaceholder.innerHTML = `
        <header class="platform-header" style="display: flex; justify-content: space-between; align-items: center; padding: 16px 24px; background: var(--bg-card); border-radius: var(--radius-lg); box-shadow: var(--shadow-soft); margin-top: 16px; margin-bottom: 14px;">
            <div class="brand-group" style="display: flex; align-items: center; gap: 14px;">
                <img src="/avatar/sarah_photo.jpg?v=20261105_photo_v5" alt="Sarah Voice AI" style="width: 44px; height: 44px; border-radius: 50%; object-fit: cover; border: 2px solid var(--primary); box-shadow: 0 2px 8px rgba(0,0,0,0.12);" />
                <div>
                    <h1 class="brand-title" style="font-size: 1.45rem; font-weight: 700; color: var(--primary-dark); margin: 0;">Sarah</h1>
                    <span class="brand-subtitle" style="font-size: 0.85rem; color: var(--text-muted);">RN Robots AI Platform • MySQL Connected</span>
                </div>
            </div>

            <!-- User Status & Logout -->
            <div style="display: flex; align-items: center; gap: 12px;">
                <div class="user-pill" style="display: flex; align-items: center; gap: 8px; background: var(--primary-light); padding: 6px 14px; border-radius: 20px; font-size: 0.88rem;">
                    <span>👤</span>
                    <strong style="color: var(--primary-dark);">${userName}</strong>
                    <span style="background: white; border: 1px solid var(--border-color); padding: 2px 8px; border-radius: 10px; font-size: 0.75rem; color: var(--text-muted); font-weight: 600;">
                        ${roleFormatted}
                    </span>
                </div>
                ${token ? `
                    <button id="btn-logout" class="a11y-btn" style="padding: 6px 14px; border-radius: 8px; background: #fff1f2; color: #e11d48; border: 1px solid #fecdd3; cursor: pointer; font-weight: 600; font-size: 0.85rem;">
                        🚪 Log Out
                    </button>
                ` : `
                    <a href="/auth/login.html" class="a11y-btn" style="padding: 6px 14px; border-radius: 8px; background: var(--primary); color: white; text-decoration: none; font-weight: 600; font-size: 0.85rem;">
                        🔐 Log In
                    </a>
                `}
            </div>
        </header>

        <!-- Only the 5 required pages in navigation -->
        <nav class="portal-nav" aria-label="Portals Navigation" style="display: flex; gap: 10px; background: var(--bg-card); padding: 8px 12px; border-radius: var(--radius-md); box-shadow: var(--shadow-soft); margin-bottom: 16px; overflow-x: auto;">
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
            <a href="/auth/login.html" class="nav-item ${activePage === 'login' ? 'active' : ''}" id="nav-login-tab">
                <span class="icon">🔐</span>
                <span class="label">${token ? 'Account' : 'Log In'}</span>
            </a>
        </nav>
        <div id="a11y-container"></div>
    `;

    // Logout button handler
    const logoutBtn = document.getElementById('btn-logout');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            if (window.api) {
                window.api.logout();
            } else {
                localStorage.clear();
                window.location.href = '/auth/login.html';
            }
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
