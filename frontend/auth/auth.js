// Authentication logic for Sarah Multi-User Platform
document.addEventListener('DOMContentLoaded', () => {
  const loginForm = document.getElementById('login-form');
  const registerForm = document.getElementById('register-form');
  const alertBox = document.getElementById('auth-alert');

  function showAlert(message, type = 'error') {
    if (!alertBox) return;
    alertBox.textContent = message;
    alertBox.className = `auth-alert ${type}`;
    alertBox.style.display = 'block';
  }

  function clearAlert() {
    if (!alertBox) return;
    alertBox.textContent = '';
    alertBox.style.display = 'none';
  }

  function handleRedirect(role) {
    const roleRoutes = {
      'resident': '/resident/index.html',
      'caregiver': '/caregiver/index.html',
      'family': '/family/index.html',
      'family_member': '/family/index.html',
      'admin': '/admin/index.html',
      'facility_admin': '/admin/index.html'
    };
    const target = roleRoutes[role] || '/resident/index.html';
    window.location.href = target;
  }

  function saveAuthSession(data, fallbackName = null) {
    if (data.access_token) {
      localStorage.setItem('sarah_access_token', data.access_token);
      localStorage.setItem('sarah_auth_token', data.access_token);
    }
    if (data.refresh_token) {
      localStorage.setItem('sarah_refresh_token', data.refresh_token);
    }
    if (data.user_id) {
      localStorage.setItem('sarah_user_id', data.user_id);
    }
    if (data.role) {
      localStorage.setItem('sarah_role', data.role);
      localStorage.setItem('sarah_user_role', data.role);
    }
    if (data.household_id) {
      localStorage.setItem('sarah_household_id', data.household_id);
    }
    if (fallbackName) {
      localStorage.setItem('sarah_user_name', fallbackName);
    }
  }

  // Handle Login
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      clearAlert();

      const email = document.getElementById('email').value.trim();
      const password = document.getElementById('password').value;
      const submitBtn = document.getElementById('login-btn');
      const btnText = document.getElementById('btn-text');

      if (!email || !password) {
        showAlert('Please enter both email and password.');
        return;
      }

      submitBtn.disabled = true;
      btnText.textContent = 'Authenticating with MySQL...';

      try {
        const response = await fetch('/api/v1/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password })
        });

        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.detail || 'Login failed. Please check your credentials.');
        }

        // Store tokens & credentials
        saveAuthSession(data);

        // Fetch user profile from MySQL to get user's full name & household name
        try {
          const meRes = await fetch('/api/v1/auth/me', {
            headers: { 'Authorization': `Bearer ${data.access_token}` }
          });
          if (meRes.ok) {
            const meData = await meRes.json();
            if (meData.full_name) localStorage.setItem('sarah_user_name', meData.full_name);
            if (meData.household_id) localStorage.setItem('sarah_household_id', meData.household_id);
            if (meData.households && meData.households.length > 0) {
              localStorage.setItem('sarah_household_name', meData.households[0].name);
            }
          }
        } catch (meErr) {
          console.debug('Could not preload me:', meErr);
        }

        showAlert('Login successful! Redirecting to your dashboard...', 'success');
        setTimeout(() => handleRedirect(data.role), 600);
      } catch (err) {
        showAlert(err.message);
      } finally {
        submitBtn.disabled = false;
        btnText.textContent = 'Log In';
      }
    });
  }

  // Handle Registration
  if (registerForm) {
    registerForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      clearAlert();

      const fullName = document.getElementById('reg-fullname').value.trim();
      const email = document.getElementById('reg-email').value.trim();
      const password = document.getElementById('reg-password').value;
      const role = document.getElementById('reg-role').value;
      const householdName = document.getElementById('reg-household')?.value.trim() || undefined;

      const submitBtn = document.getElementById('register-btn');
      const btnText = document.getElementById('btn-text');

      if (!email || !password || !fullName) {
        showAlert('Please fill in all required fields.');
        return;
      }

      if (password.length < 6) {
        showAlert('Password must be at least 6 characters.');
        return;
      }

      submitBtn.disabled = true;
      btnText.textContent = 'Creating account in MySQL...';

      try {
        const response = await fetch('/api/v1/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            full_name: fullName,
            email: email,
            password: password,
            role: role,
            household_name: householdName
          })
        });

        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.detail || 'Registration failed. Please try again.');
        }

        // Store tokens & credentials
        saveAuthSession(data, fullName);
        if (householdName) {
          localStorage.setItem('sarah_household_name', householdName);
        }

        showAlert('Account created successfully in MySQL! Redirecting...', 'success');
        setTimeout(() => handleRedirect(data.role), 600);
      } catch (err) {
        showAlert(err.message);
      } finally {
        submitBtn.disabled = false;
        btnText.textContent = 'Create Account';
      }
    });
  }
});
