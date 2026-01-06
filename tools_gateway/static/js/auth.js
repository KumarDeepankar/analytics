/**
 * Authentication Module for MCP Portal
 * Handles local and OAuth authentication
 */

// Use IIFE to avoid global variable conflicts
(function() {
    'use strict';

    // Authentication State
    let currentUser = null;
    let accessToken = null;
    let oauthProviders = [];

// Initialize authentication on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('Auth module initializing...');
    checkAuthStatus();
    loadOAuthProviders();

    // Close dropdowns when clicking outside
    document.addEventListener('click', function(event) {
        const dropdown = document.getElementById('userProfileDropdown');
        const profileButton = document.getElementById('userProfileButton');

        if (dropdown && profileButton) {
            if (!dropdown.contains(event.target) && !profileButton.contains(event.target)) {
                dropdown.style.display = 'none';
            }
        }
    });
});

/**
 * Check if user is already authenticated
 */
function checkAuthStatus() {
    // Check for stored token
    accessToken = localStorage.getItem('access_token');

    if (accessToken) {
        // Validate token and get user info
        fetch('/auth/user', {
            headers: {
                'Authorization': `Bearer ${accessToken}`
            }
        })
        .then(response => {
            if (response.ok) {
                return response.json();
            } else {
                // Token invalid or expired
                clearAuth();
                redirectToLogin();
                throw new Error('Authentication failed');
            }
        })
        .then(data => {
            currentUser = data;
            updateUIForAuthenticatedUser();
        })
        .catch(error => {
            console.error('Auth check failed:', error);
            clearAuth();
            redirectToLogin();
        });
    } else {
        // Not authenticated
        redirectToLogin();
    }
}

/**
 * Redirect to login page
 */
function redirectToLogin() {
    // Don't redirect if we're already on the login page
    if (window.location.pathname === '/login.html' || window.location.pathname === '/static/login.html') {
        return;
    }
    window.location.href = '/static/login.html';
}

/**
 * Load available OAuth providers
 */
async function loadOAuthProviders() {
    try {
        const response = await fetch('/auth/providers');
        if (response.ok) {
            const data = await response.json();
            oauthProviders = data.providers || [];
            renderOAuthProviders();
        }
    } catch (error) {
        console.error('Failed to load OAuth providers:', error);
    }
}

/**
 * Render OAuth provider buttons
 */
function renderOAuthProviders() {
    const container = document.getElementById('oauthProviderButtons');
    const noProvidersMsg = document.getElementById('noOAuthProvidersMessage');

    if (!container) return;

    if (oauthProviders.length === 0) {
        if (noProvidersMsg) noProvidersMsg.style.display = 'block';
        return;
    }

    if (noProvidersMsg) noProvidersMsg.style.display = 'none';

    const providerIcons = {
        'google': 'fab fa-google',
        'microsoft': 'fab fa-microsoft',
        'github': 'fab fa-github'
    };

    const providerColors = {
        'google': '#4285F4',
        'microsoft': '#00A4EF',
        'github': '#333'
    };

    container.innerHTML = oauthProviders.map(provider => {
        const icon = providerIcons[provider.provider_id] || 'fas fa-sign-in-alt';
        const color = providerColors[provider.provider_id] || '#667eea';

        return `
            <button class="oauth-provider-btn" onclick="initiateOAuthLogin('${provider.provider_id}')"
                    style="background: ${color};">
                <i class="${icon}"></i>
                Sign in with ${provider.provider_name}
            </button>
        `;
    }).join('');
}

/**
 * Show login modal
 */
function showLoginModal() {
    const modal = document.getElementById('loginModal');
    if (modal) {
        modal.style.display = 'flex';
        // Reset form
        document.getElementById('localEmail').value = '';
        document.getElementById('localPassword').value = '';
        const errorDiv = document.getElementById('localLoginError');
        if (errorDiv) errorDiv.style.display = 'none';
    }
}

/**
 * Hide login modal
 */
function hideLoginModal() {
    const modal = document.getElementById('loginModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

/**
 * Handle local login form submission
 */
async function handleLocalLogin(event) {
    event.preventDefault();

    const email = document.getElementById('localEmail').value;
    const password = document.getElementById('localPassword').value;
    const errorDiv = document.getElementById('localLoginError');

    try {
        const response = await fetch('/auth/login/local', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ email, password })
        });

        if (response.ok) {
            const data = await response.json();
            accessToken = data.access_token;
            currentUser = data.user;

            // Store token
            localStorage.setItem('access_token', accessToken);

            // IMPORTANT: Trigger storage event for other modules (like admin-security.js)
            // Dispatch custom event to notify admin-security.js
            window.dispatchEvent(new StorageEvent('storage', {
                key: 'access_token',
                newValue: accessToken,
                oldValue: null
            }));

            // Update UI
            hideLoginModal();
            updateUIForAuthenticatedUser();

            // Show success message
            showNotification('Success!', 'You are now signed in.', 'success');

            // Force reload of admin tabs if they're visible
            if (typeof loadOAuthProviders === 'function') loadOAuthProviders();
            if (typeof loadUsers === 'function') loadUsers();
            if (typeof loadRoles === 'function') loadRoles();
            if (typeof loadAuditLogs === 'function') loadAuditLogs();

        } else {
            const error = await response.json();
            if (errorDiv) {
                errorDiv.textContent = error.detail || 'Invalid credentials';
                errorDiv.style.display = 'block';
            }
        }
    } catch (error) {
        console.error('Login failed:', error);
        if (errorDiv) {
            errorDiv.textContent = 'Login failed. Please try again.';
            errorDiv.style.display = 'block';
        }
    }

    return false;
}

/**
 * Initiate OAuth login flow
 */
async function initiateOAuthLogin(providerId) {
    try {
        const response = await fetch(`/auth/login?provider_id=${providerId}`, {
            method: 'POST'
        });

        if (response.ok) {
            const data = await response.json();
            // Redirect to OAuth provider
            window.location.href = data.url;
        } else {
            showNotification('Error', 'Failed to initiate OAuth login', 'error');
        }
    } catch (error) {
        console.error('OAuth login failed:', error);
        showNotification('Error', 'Failed to initiate OAuth login', 'error');
    }
}

/**
 * Update UI for authenticated user
 */
function updateUIForAuthenticatedUser() {
    // Hide login button, show user profile
    const loginButton = document.getElementById('loginButton');
    const profileButton = document.getElementById('userProfileButton');

    if (loginButton) loginButton.style.display = 'none';
    if (profileButton) profileButton.style.display = 'block';

    if (currentUser) {
        // Update header
        const initials = getInitials(currentUser.name || currentUser.email);
        document.getElementById('headerUserInitials').textContent = initials;
        document.getElementById('headerUserName').textContent = currentUser.name || currentUser.email;

        const roles = currentUser.roles || [];
        document.getElementById('headerUserRole').textContent = roles[0] || 'User';

        // Update profile dropdown
        document.getElementById('userInitials').textContent = initials;
        document.getElementById('userDisplayName').textContent = currentUser.name || currentUser.email;
        document.getElementById('userDisplayEmail').textContent = currentUser.email;

        // Render roles
        const rolesHTML = roles.map(role =>
            `<span class="tag" style="background: #667eea; color: white; padding: 4px 8px; border-radius: 4px; font-size: 0.85em; margin-right: 5px;">
                <i class="fas fa-user-shield"></i> ${role}
            </span>`
        ).join('');
        document.getElementById('userRolesList').innerHTML = rolesHTML || '<span class="text-muted">No roles assigned</span>';
    }
}

/**
 * Get user initials from name
 */
function getInitials(name) {
    if (!name) return '?';
    const parts = name.split(' ');
    if (parts.length >= 2) {
        return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return name.substring(0, 2).toUpperCase();
}

/**
 * Toggle user profile dropdown
 */
function toggleUserProfile() {
    const dropdown = document.getElementById('userProfileDropdown');
    if (dropdown) {
        dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
    }
}

/**
 * Handle logout
 */
function handleLogout() {
    clearAuth();
    redirectToLogin();
}

/**
 * Clear authentication state
 */
function clearAuth() {
    currentUser = null;
    accessToken = null;
    localStorage.removeItem('access_token');

    // Update UI
    const loginButton = document.getElementById('loginButton');
    const profileButton = document.getElementById('userProfileButton');
    const dropdown = document.getElementById('userProfileDropdown');

    if (loginButton) loginButton.style.display = 'block';
    if (profileButton) profileButton.style.display = 'none';
    if (dropdown) dropdown.style.display = 'none';
}

/**
 * Show change password modal
 */
function changePassword() {
    const modal = document.getElementById('changePasswordModal');
    if (modal) {
        modal.style.display = 'flex';
        document.getElementById('newPassword').value = '';
        document.getElementById('confirmPassword').value = '';
        const errorDiv = document.getElementById('passwordChangeError');
        const successDiv = document.getElementById('passwordChangeSuccess');
        if (errorDiv) errorDiv.style.display = 'none';
        if (successDiv) successDiv.style.display = 'none';
    }

    // Close profile dropdown
    const dropdown = document.getElementById('userProfileDropdown');
    if (dropdown) dropdown.style.display = 'none';
}

/**
 * Submit password change
 */
async function submitPasswordChange(event) {
    if (event) event.preventDefault();

    const newPassword = document.getElementById('newPassword').value;
    const confirmPassword = document.getElementById('confirmPassword').value;
    const errorDiv = document.getElementById('passwordChangeError');
    const successDiv = document.getElementById('passwordChangeSuccess');

    // Hide previous messages
    if (errorDiv) errorDiv.style.display = 'none';
    if (successDiv) successDiv.style.display = 'none';

    // Validate
    if (newPassword !== confirmPassword) {
        if (errorDiv) {
            errorDiv.textContent = 'Passwords do not match';
            errorDiv.style.display = 'block';
        }
        return false;
    }

    if (newPassword.length < 8) {
        if (errorDiv) {
            errorDiv.textContent = 'Password must be at least 8 characters';
            errorDiv.style.display = 'block';
        }
        return false;
    }

    if (!currentUser || !currentUser.user_id) {
        if (errorDiv) {
            errorDiv.textContent = 'User not authenticated';
            errorDiv.style.display = 'block';
        }
        return false;
    }

    try {
        const response = await fetch(`/admin/users/${currentUser.user_id}/password`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${accessToken}`
            },
            body: JSON.stringify({ new_password: newPassword })
        });

        if (response.ok) {
            if (successDiv) {
                successDiv.textContent = 'Password changed successfully!';
                successDiv.style.display = 'block';
            }

            // Clear form
            document.getElementById('newPassword').value = '';
            document.getElementById('confirmPassword').value = '';

            // Close modal after 2 seconds
            setTimeout(() => {
                closeModal('changePasswordModal');
            }, 2000);

            showNotification('Success', 'Password changed successfully!', 'success');
        } else {
            const error = await response.json();
            if (errorDiv) {
                errorDiv.textContent = error.detail || 'Failed to change password';
                errorDiv.style.display = 'block';
            }
        }
    } catch (error) {
        console.error('Password change failed:', error);
        if (errorDiv) {
            errorDiv.textContent = 'Failed to change password. Please try again.';
            errorDiv.style.display = 'block';
        }
    }

    return false;
}

/**
 * Show notification
 */
function showNotification(title, message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        padding: 16px 20px;
        min-width: 300px;
        z-index: 10000;
        animation: slideIn 0.3s ease-out;
    `;

    const colors = {
        'success': '#10b981',
        'error': '#ef4444',
        'warning': '#f59e0b',
        'info': '#3b82f6'
    };

    const icons = {
        'success': 'fa-check-circle',
        'error': 'fa-exclamation-circle',
        'warning': 'fa-exclamation-triangle',
        'info': 'fa-info-circle'
    };

    notification.innerHTML = `
        <div style="display: flex; align-items: center;">
            <i class="fas ${icons[type]}" style="color: ${colors[type]}; font-size: 1.5em; margin-right: 12px;"></i>
            <div style="flex: 1;">
                <div style="font-weight: 600; color: #333; margin-bottom: 4px;">${title}</div>
                <div style="font-size: 0.9em; color: #666;">${message}</div>
            </div>
            <button onclick="this.parentElement.parentElement.remove()" style="background: none; border: none; font-size: 1.2em; color: #999; cursor: pointer; margin-left: 12px;">&times;</button>
        </div>
    `;

    document.body.appendChild(notification);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-out';
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

// Add CSS animation
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }

    .auth-section {
        margin-bottom: 24px;
    }

    .auth-section-title {
        font-size: 1.1em;
        font-weight: 600;
        color: #333;
        margin-bottom: 16px;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .auth-divider {
        text-align: center;
        margin: 24px 0;
        position: relative;
    }

    .auth-divider::before {
        content: '';
        position: absolute;
        top: 50%;
        left: 0;
        right: 0;
        height: 1px;
        background: #ddd;
    }

    .auth-divider span {
        position: relative;
        background: white;
        padding: 0 16px;
        color: #999;
        font-size: 0.9em;
        font-weight: 500;
    }

    .oauth-providers-list {
        display: flex;
        flex-direction: column;
        gap: 12px;
    }

    .oauth-provider-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        padding: 12px 20px;
        border: none;
        border-radius: 8px;
        color: white;
        font-weight: 600;
        font-size: 0.95em;
        cursor: pointer;
        transition: all 0.3s ease;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }

    .oauth-provider-btn:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.15);
    }

    .oauth-provider-btn:active {
        transform: translateY(0);
    }

    .btn-block {
        width: 100%;
    }

    .modal {
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.5);
        justify-content: center;
        align-items: center;
        z-index: 1000;
    }
`;
document.head.appendChild(style);

/**
 * Show JWT Token Modal
 */
function showJWTTokenModal() {
    const modal = document.getElementById('jwtTokenModal');
    if (!modal) {
        console.error('JWT Token modal not found');
        return;
    }

    // Get the JWT token from storage
    const token = localStorage.getItem('access_token');
    if (!token) {
        showNotification('Error', 'No JWT token found. Please log in again.', 'error');
        return;
    }

    // Get ngrok URL from the ngrok log or use default
    const ngrokUrl = 'https://ce666863018f.ngrok-free.app';

    // Populate the token textarea
    document.getElementById('jwtTokenValue').value = token;

    // Generate Claude Desktop configuration
    const claudeConfig = {
        "mcpServers": {
            "toolbox-gateway": {
                "url": `${ngrokUrl}/mcp?token=${token}`
            }
        }
    };

    // Populate the Claude config textarea
    document.getElementById('claudeConfigValue').value = JSON.stringify(claudeConfig, null, 2);

    // Show the modal
    modal.style.display = 'flex';

    // Close profile dropdown
    const dropdown = document.getElementById('userProfileDropdown');
    if (dropdown) dropdown.style.display = 'none';
}

/**
 * Copy JWT Token to clipboard
 */
async function copyJWTToken() {
    const tokenValue = document.getElementById('jwtTokenValue').value;
    const copyBtn = document.getElementById('copyTokenBtn');

    try {
        await navigator.clipboard.writeText(tokenValue);

        // Update button text temporarily
        const originalHTML = copyBtn.innerHTML;
        copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
        copyBtn.style.background = '#10b981';
        copyBtn.style.color = 'white';

        setTimeout(() => {
            copyBtn.innerHTML = originalHTML;
            copyBtn.style.background = '';
            copyBtn.style.color = '';
        }, 2000);

        showNotification('Success', 'JWT token copied to clipboard', 'success');
    } catch (error) {
        console.error('Failed to copy token:', error);
        showNotification('Error', 'Failed to copy to clipboard', 'error');
    }
}

/**
 * Copy Claude Desktop config to clipboard
 */
async function copyClaudeConfig() {
    const configValue = document.getElementById('claudeConfigValue').value;
    const copyBtn = document.getElementById('copyConfigBtn');

    try {
        await navigator.clipboard.writeText(configValue);

        // Update button text temporarily
        const originalHTML = copyBtn.innerHTML;
        copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
        copyBtn.style.background = '#10b981';
        copyBtn.style.color = 'white';

        setTimeout(() => {
            copyBtn.innerHTML = originalHTML;
            copyBtn.style.background = '';
            copyBtn.style.color = '';
        }, 2000);

        showNotification('Success', 'Claude Desktop config copied to clipboard', 'success');
    } catch (error) {
        console.error('Failed to copy config:', error);
        showNotification('Error', 'Failed to copy to clipboard', 'error');
    }
}

    // Export functions to global scope for onclick handlers
    window.showLoginModal = showLoginModal;
    window.handleLocalLogin = handleLocalLogin;
    window.initiateOAuthLogin = initiateOAuthLogin;
    window.toggleUserProfile = toggleUserProfile;
    window.handleLogout = handleLogout;
    window.changePassword = changePassword;
    window.submitPasswordChange = submitPasswordChange;
    window.showJWTTokenModal = showJWTTokenModal;
    window.copyJWTToken = copyJWTToken;
    window.copyClaudeConfig = copyClaudeConfig;

    // Export authModule API
    window.authModule = {
        getCurrentUser: () => currentUser,
        getAccessToken: () => accessToken,
        isAuthenticated: () => !!accessToken,
        showLoginModal,
        handleLogout
    };

})(); // Close IIFE
