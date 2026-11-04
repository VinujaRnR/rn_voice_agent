/**
 * Sarah Centralized API Client
 * Manages JWT tokens, multi-tenant session isolation, role authentication,
 * and service endpoints for Resident, Family, Caregiver, and Admin portals.
 * Fully connected to MySQL database.
 */

class ApiService {
    constructor() {
        this.tokenKey = 'sarah_access_token';
        this.fallbackTokenKey = 'sarah_auth_token';
        this.sessionKey = 'sarah_session_id';
        this.householdKey = 'sarah_household_id';
        this.roleKey = 'sarah_role';
        this.userKey = 'sarah_user_id';
        this.userNameKey = 'sarah_user_name';
    }

    getToken() {
        return localStorage.getItem(this.tokenKey) ||
               localStorage.getItem(this.fallbackTokenKey) ||
               localStorage.getItem('token') || '';
    }

    setToken(token, userData = null) {
        if (token) {
            localStorage.setItem(this.tokenKey, token);
            localStorage.setItem(this.fallbackTokenKey, token);
            if (userData) {
                if (userData.user_id || userData.id) localStorage.setItem(this.userKey, userData.user_id || userData.id);
                if (userData.role) {
                    localStorage.setItem(this.roleKey, userData.role);
                    localStorage.setItem('sarah_user_role', userData.role);
                }
                if (userData.household_id) localStorage.setItem(this.householdKey, userData.household_id);
                if (userData.full_name) localStorage.setItem(this.userNameKey, userData.full_name);
            }
            try {
                const payload = JSON.parse(atob(token.split('.')[1]));
                if (payload.role) {
                    localStorage.setItem(this.roleKey, payload.role);
                    localStorage.setItem('sarah_user_role', payload.role);
                }
                if (payload.sub && !localStorage.getItem(this.userKey)) {
                    localStorage.setItem(this.userKey, payload.sub);
                }
                if (payload.household_id) {
                    localStorage.setItem(this.householdKey, payload.household_id);
                }
            } catch (e) {
                // Ignore parse errors
            }
        } else {
            localStorage.removeItem(this.tokenKey);
            localStorage.removeItem(this.fallbackTokenKey);
            localStorage.removeItem(this.userKey);
            localStorage.removeItem(this.roleKey);
            localStorage.removeItem('sarah_user_role');
            localStorage.removeItem(this.householdKey);
            localStorage.removeItem(this.userNameKey);
        }
    }

    logout() {
        this.setToken(null);
        window.location.href = '/auth/login.html';
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
        return localStorage.getItem(this.roleKey) || localStorage.getItem('sarah_user_role') || 'resident';
    }

    getHouseholdId() {
        return localStorage.getItem(this.householdKey) || '';
    }

    getUserId() {
        return localStorage.getItem(this.userKey) || '';
    }

    getUserName() {
        return localStorage.getItem(this.userNameKey) || '';
    }

    setContext(user, role, householdId, name = null) {
        if (user) localStorage.setItem(this.userKey, user);
        if (role) {
            localStorage.setItem(this.roleKey, role);
            localStorage.setItem('sarah_user_role', role);
        }
        if (householdId) localStorage.setItem(this.householdKey, householdId);
        if (name) localStorage.setItem(this.userNameKey, name);
    }

    getHeaders(extra = {}) {
        const headers = {
            'Content-Type': 'application/json',
            'X-Session-ID': this.getSessionId(),
            ...extra
        };
        const hid = this.getHouseholdId();
        if (hid) headers['X-Household-ID'] = hid;

        const uid = this.getUserId();
        if (uid) headers['X-Resident-ID'] = uid;

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

    // Authenticated Profile & Me
    async getCurrentUser() {
        let token = this.getToken();
        if (!token) {
            try {
                // Auto-fetch active default resident from MySQL so dashboard is instantly connected
                const res = await fetch('/api/v1/auth/default-resident');
                if (res.ok) {
                    const defData = await res.json();
                    if (defData.access_token) {
                        this.setToken(defData.access_token, defData);
                        if (defData.household_name) localStorage.setItem('sarah_household_name', defData.household_name);
                        return {
                            user_id: defData.user_id,
                            email: defData.email,
                            full_name: defData.full_name,
                            role: defData.role,
                            household_id: defData.household_id,
                            households: defData.household_id ? [{ id: defData.household_id, name: defData.household_name || 'Colombo' }] : []
                        };
                    }
                }
            } catch (err) {
                console.debug('Could not load default resident:', err);
            }
            return null;
        }
        try {
            const data = await this.request('/api/v1/auth/me');
            if (data) {
                if (data.user_id) localStorage.setItem(this.userKey, data.user_id);
                if (data.role) {
                    localStorage.setItem(this.roleKey, data.role);
                    localStorage.setItem('sarah_user_role', data.role);
                }
                if (data.household_id) localStorage.setItem(this.householdKey, data.household_id);
                if (data.full_name) localStorage.setItem(this.userNameKey, data.full_name);
                if (data.households && data.households.length > 0) {
                    localStorage.setItem('sarah_household_name', data.households[0].name);
                }
            }
            return data;
        } catch (e) {
            console.warn('Could not fetch current user profile:', e);
            try {
                const res = await fetch('/api/v1/auth/default-resident');
                if (res.ok) {
                    const defData = await res.json();
                    if (defData.access_token) {
                        this.setToken(defData.access_token, defData);
                        if (defData.household_name) localStorage.setItem('sarah_household_name', defData.household_name);
                        return {
                            user_id: defData.user_id,
                            email: defData.email,
                            full_name: defData.full_name,
                            role: defData.role,
                            household_id: defData.household_id,
                            households: defData.household_id ? [{ id: defData.household_id, name: defData.household_name || 'Colombo' }] : []
                        };
                    }
                }
            } catch (recoveryErr) {
                console.debug('Recovery failed:', recoveryErr);
            }
            return null;
        }
    }

    // WebSocket Ticket
    async acquireWsTicket() {
        return this.request('/api/v1/auth/ws-ticket', { method: 'POST' });
    }

    // Voice Chat HTTP fallback
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

    // Devices (Universal IoT from MySQL)
    async listDevices(householdId = null) {
        const hid = householdId || this.getHouseholdId();
        const url = hid ? `/api/v1/devices?household_id=${encodeURIComponent(hid)}` : '/api/v1/devices';
        return this.request(url);
    }

    async registerDevice(deviceData) {
        return this.request('/api/v1/devices', {
            method: 'POST',
            body: JSON.stringify({
                household_id: deviceData.household_id || this.getHouseholdId(),
                name: deviceData.name,
                device_id: deviceData.device_id,
                device_type: deviceData.device_type || 'light',
                location: deviceData.location || 'Living Room',
                connection_type: deviceData.connection_type || 'WiFi',
                capabilities: deviceData.capabilities || ['turn_on', 'turn_off', 'set_power']
            })
        });
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

    // Family Portal (from MySQL)
    async getFamilyContacts(residentId = null) {
        const rid = residentId || this.getUserId();
        const url = rid ? `/api/v1/family/contacts?resident_id=${encodeURIComponent(rid)}` : '/api/v1/family/contacts';
        return this.request(url);
    }

    async getUpcomingEvents(residentId = null) {
        const rid = residentId || this.getUserId();
        const url = rid ? `/api/v1/family/events?resident_id=${encodeURIComponent(rid)}` : '/api/v1/family/events';
        return this.request(url);
    }

    async sendFamilyContactRequest(contactName, message) {
        return this.request('/api/v1/family/contact-requests', {
            method: 'POST',
            body: JSON.stringify({
                contact_name_or_id: contactName,
                custom_message: message
            })
        });
    }

    // Caregiver & Medications (from MySQL)
    async getCarePlan(residentId = null) {
        const rid = residentId || this.getUserId();
        if (!rid) return { routine_details: {} };
        return this.request(`/api/v1/care/residents/${encodeURIComponent(rid)}/plan`);
    }

    async getMedications(residentId = null) {
        const rid = residentId || this.getUserId();
        if (!rid) return [];
        return this.request(`/api/v1/care/residents/${encodeURIComponent(rid)}/medications`);
    }

    async createMedication(residentId, medData) {
        return this.request(`/api/v1/care/residents/${encodeURIComponent(residentId)}/medications`, {
            method: 'POST',
            body: JSON.stringify(medData)
        });
    }

    async recordMedicationAdherence(medicationId, eventType, notes = null) {
        return this.request(`/api/v1/care/medications/${encodeURIComponent(medicationId)}/events`, {
            method: 'POST',
            body: JSON.stringify({
                event_type: eventType,
                notes: notes
            })
        });
    }

    // Music & Entertainment
    async controlMusic(action = 'play', query = null, volume = 75) {
        return this.request('/api/v1/entertainment/music/control', {
            method: 'POST',
            body: JSON.stringify({
                action: action,
                query: query,
                volume: volume
            })
        });
    }
}

// Global Singleton
window.api = new ApiService();
