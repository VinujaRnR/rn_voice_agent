/**
 * Sarah Centralized API Client
 * Manages JWT tokens, multi-tenant session isolation, role authentication,
 * and service endpoints for Resident, Family, Caregiver, and Admin portals.
 */

class ApiService {
    constructor() {
        this.tokenKey = 'sarah_auth_token';
        this.sessionKey = 'sarah_session_id';
        this.householdKey = 'sarah_household_id';
        this.roleKey = 'sarah_role';
        this.userKey = 'sarah_user_id';
    }

    getToken() {
        return localStorage.getItem(this.tokenKey) || '';
    }

    setToken(token) {
        if (token) {
            localStorage.setItem(this.tokenKey, token);
            try {
                const payload = JSON.parse(atob(token.split('.')[1]));
                if (payload.role) localStorage.setItem(this.roleKey, payload.role);
                if (payload.sub) localStorage.setItem(this.userKey, payload.sub);
                if (payload.household_id) localStorage.setItem(this.householdKey, payload.household_id);
            } catch (e) {
                // Ignore parse errors
            }
        } else {
            localStorage.removeItem(this.tokenKey);
        }
    }

    getSessionId() {
        let sid = localStorage.getItem(this.sessionKey);
        if (!sid) {
            sid = 'sess_' + Math.random().toString(36).substring(2, 10);
            localStorage.setItem(this.sessionKey, sid);
        }
        return sid;
    }

    getRole() {
        return localStorage.getItem(this.roleKey) || 'resident';
    }

    getHouseholdId() {
        return localStorage.getItem(this.householdKey) || 'household_margaret';
    }

    getUserId() {
        return localStorage.getItem(this.userKey) || 'user_margaret';
    }

    setContext(user, role, householdId) {
        if (user) localStorage.setItem(this.userKey, user);
        if (role) localStorage.setItem(this.roleKey, role);
        if (householdId) localStorage.setItem(this.householdKey, householdId);
    }

    getHeaders(extra = {}) {
        const headers = {
            'Content-Type': 'application/json',
            'X-Session-ID': this.getSessionId(),
            'X-Household-ID': this.getHouseholdId(),
            'X-Resident-ID': this.getUserId(),
            ...extra
        };
        const token = this.getToken();
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }
        return headers;
    }

    async request(url, options = {}) {
        options.headers = this.getHeaders(options.headers || {});
        try {
            const res = await fetch(url, options);
            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                const msg = errData.detail || errData.message || `Request failed (${res.status})`;
                throw new Error(msg);
            }
            return await res.json();
        } catch (err) {
            console.error(`API Error on ${url}:`, err);
            throw err;
        }
    }

    // Voice Chat
    async sendChat(text) {
        return this.request('/api/chat', {
            method: 'POST',
            body: JSON.stringify({
                text: text,
                session_id: this.getSessionId(),
                user_id: this.getUserId(),
                household_id: this.getHouseholdId()
            })
        });
    }

    // Devices (Universal IoT)
    async listDevices() {
        return this.request('/api/v1/devices');
    }

    async sendDeviceCommand(deviceId, action, parameters = {}) {
        return this.request(`/api/v1/devices/${deviceId}/command`, {
            method: 'POST',
            body: JSON.stringify({
                action: action,
                parameters: parameters
            })
        });
    }

    // Reminders
    async listReminders() {
        return this.request(`/api/reminders/?session_id=${encodeURIComponent(this.getSessionId())}`);
    }

    async cancelReminder(reminderId) {
        return this.request(`/api/reminders/${reminderId}?session_id=${encodeURIComponent(this.getSessionId())}`, {
            method: 'DELETE'
        });
    }

    // Family Portal (Step 11)
    async getFamilyContacts() {
        return this.request('/api/v1/family/contacts');
    }

    async getUpcomingEvents() {
        return this.request('/api/v1/family/events');
    }

    async sendFamilyContactRequest(contactName, message) {
        return this.request('/api/v1/family/contact-requests', {
            method: 'POST',
            body: JSON.stringify({
                contact_name: contactName,
                message: message
            })
        });
    }

    // Caregiver Portal (Step 12)
    async getCarePlan() {
        return this.request('/api/v1/care/care-plan');
    }

    async getMedicationSchedule() {
        return this.request('/api/v1/care/medications/schedule');
    }

    async updateMedicationStage(scheduleId, stage) {
        return this.request(`/api/v1/care/medications/${scheduleId}/stage`, {
            method: 'POST',
            body: JSON.stringify({ stage: stage })
        });
    }

    // Safety Radar & Alerts (Step 13)
    async getSafetyIncidents() {
        return this.request('/api/v1/safety/incidents');
    }

    async getExternalAlerts(postcode = '3000') {
        return this.request(`/api/v1/safety/alerts?postcode=${postcode}`);
    }

    // Music & Entertainment (Step 15)
    async getPlaylists() {
        return this.request('/api/v1/entertainment/playlists');
    }

    async controlMusic(action, query = '', volume = 75) {
        return this.request('/api/v1/entertainment/control', {
            method: 'POST',
            body: JSON.stringify({
                action: action,
                query: query,
                volume_level: volume
            })
        });
    }
}

// Global instance
const api = new ApiService();
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { api, ApiService };
} else {
    window.api = api;
}
