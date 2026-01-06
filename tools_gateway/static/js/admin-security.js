/**
 * Admin Security Management
 * OAuth Provider and RBAC Management
 */

// Global state
let currentUser = null;
let authToken = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    // Check for token in URL (from OAuth callback)
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('token');

    if (token) {
        authToken = token;
        localStorage.setItem('access_token', token); // Use same key as auth.js
        // Clean URL
        window.history.replaceState({}, document.title, window.location.pathname);
    } else {
        // Check both old and new token keys for backward compatibility
        authToken = localStorage.getItem('access_token') || localStorage.getItem('mcp_auth_token');
        if (authToken) {
            // Migrate to new key if using old one
            localStorage.setItem('access_token', authToken);
            localStorage.removeItem('mcp_auth_token');
        }
    }

    if (authToken) {
        await loadCurrentUser();
    }

    setupEventListeners();

    // Listen for login events from auth.js
    window.addEventListener('storage', (e) => {
        if (e.key === 'access_token') {
            if (e.newValue) {
                authToken = e.newValue;
                loadCurrentUser();
            } else {
                authToken = null;
                currentUser = null;
            }
        }
    });

    // Also check if auth module has authenticated user
    setInterval(() => {
        if (window.authModule && window.authModule.isAuthenticated() && !authToken) {
            authToken = window.authModule.getAccessToken();
            if (authToken) {
                loadCurrentUser();
            }
        }
    }, 500); // Check every 500ms
});

// Setup event listeners
function setupEventListeners() {
    // OAuth Provider Management
    const oauthTab = document.querySelector('[data-tab="oauth"]');
    if (oauthTab) {
        oauthTab.addEventListener('click', () => loadOAuthProviders());
    }

    // RBAC Management
    const usersTab = document.querySelector('[data-tab="users"]');
    if (usersTab) {
        usersTab.addEventListener('click', () => {
            loadADConfig();
            loadADMappings();
            loadUsers();
            loadRoles();  // Also load roles since they're in the same tab
        });
    }

    const rolesTab = document.querySelector('[data-tab="roles"]');
    if (rolesTab) {
        rolesTab.addEventListener('click', () => loadRoles());
    }

    // Audit Logs
    const auditTab = document.querySelector('[data-tab="audit"]');
    if (auditTab) {
        auditTab.addEventListener('click', () => loadAuditLogs());
    }
}

// Authentication Functions
async function loadCurrentUser() {
    try {
        const response = await fetch('/auth/user', {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            currentUser = await response.json();
            updateUserInterface();
        } else {
            // Token invalid, clear and redirect to login
            localStorage.removeItem('access_token');
            authToken = null;
            showLoginInterface();
        }
    } catch (error) {
        console.error('Error loading user:', error);
        showLoginInterface();
    }
}

function updateUserInterface() {
    const userInfo = document.getElementById('currentUserInfo');
    if (userInfo && currentUser) {
        userInfo.innerHTML = `
            <div class="user-badge">
                <i class="fas fa-user-circle"></i>
                <span>${currentUser.name || currentUser.email}</span>
                <span class="user-role">${currentUser.roles[0] || 'User'}</span>
            </div>
        `;
    }
}

function showLoginInterface() {
    // Show OAuth login options
    loadOAuthProviders();
}

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
            showNotification('Failed to initiate login', 'error');
        }
    } catch (error) {
        console.error('OAuth login error:', error);
        showNotification('Login error: ' + error.message, 'error');
    }
}

function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('mcp_auth_token'); // Clean up old key too
    authToken = null;
    currentUser = null;
    window.location.reload(); // Reload to show login modal
}

// OAuth Provider Management

// Provider templates with pre-filled configurations
const PROVIDER_TEMPLATES = {
    google: {
        provider_id: 'google',
        provider_name: 'Google',
        authorize_url: 'https://accounts.google.com/o/oauth2/v2/auth',
        token_url: 'https://oauth2.googleapis.com/token',
        userinfo_url: 'https://www.googleapis.com/oauth2/v2/userinfo',
        scopes: ['openid', 'email', 'profile']
    },
    microsoft: {
        provider_id: 'microsoft',
        provider_name: 'Microsoft',
        authorize_url: 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
        token_url: 'https://login.microsoftonline.com/common/oauth2/v2.0/token',
        userinfo_url: 'https://graph.microsoft.com/v1.0/me',
        scopes: ['openid', 'email', 'profile']
    },
    github: {
        provider_id: 'github',
        provider_name: 'GitHub',
        authorize_url: 'https://github.com/login/oauth/authorize',
        token_url: 'https://github.com/login/oauth/access_token',
        userinfo_url: 'https://api.github.com/user',
        scopes: ['read:user', 'user:email']
    }
};

// Current scopes array
let currentScopes = ['openid', 'email', 'profile'];

async function loadOAuthProviders() {
    // ALWAYS try to get token from localStorage first, then from auth module
    authToken = localStorage.getItem('access_token');
    if (!authToken && window.authModule && window.authModule.isAuthenticated()) {
        authToken = window.authModule.getAccessToken();
    }

    try {
        const response = await fetch('/auth/providers');
        const data = await response.json();

        displayOAuthProviders(data.providers);
    } catch (error) {
        console.error('Error loading OAuth providers:', error);
    }
}

function displayOAuthProviders(providers) {
    const container = document.getElementById('oauthProvidersContainer');
    if (!container) return;

    // Sync token from auth module if needed
    if (!authToken && window.authModule && window.authModule.isAuthenticated()) {
        authToken = window.authModule.getAccessToken();
    }

    // Always show management interface in the OAuth Providers tab
    // (This is the OAuth management section, not the login page)
    if (!authToken && providers.length > 0) {
        // Providers exist but user not logged in - show minimal interface with login option
        container.innerHTML = `
            <div class="alert alert-info" style="margin-bottom: 20px;">
                <i class="fas fa-info-circle"></i>
                <strong>Authentication Required</strong>
                <p>Please sign in to manage OAuth providers.</p>
            </div>
            <div class="login-container">
                <h3>Sign In</h3>
                <p>Choose your authentication provider:</p>
                <div class="oauth-providers">
                    ${providers.map(p => `
                        <button class="btn btn-provider" onclick="initiateOAuthLogin('${p.provider_id}')">
                            <i class="fab fa-${p.provider_id}"></i>
                            Sign in with ${p.provider_name}
                        </button>
                    `).join('')}
                </div>
            </div>
            <div class="alert alert-warning" style="margin-top: 20px;">
                <i class="fas fa-shield-alt"></i>
                <strong>Want to add or manage providers?</strong>
                <p>First-time setup allows adding providers without login. If you need to manage existing providers, please sign in as an administrator.</p>
            </div>
        `;
    } else if (!authToken && providers.length === 0) {
        // No providers and not logged in - allow first-time setup
        container.innerHTML = `
            <div class="alert alert-warning" style="margin-bottom: 20px;">
                <i class="fas fa-exclamation-triangle"></i>
                <strong>No OAuth providers configured</strong>
                <p>Configure your first OAuth provider to enable authentication. This is a one-time setup.</p>
            </div>
            <div class="toolbar">
                <button class="btn btn-primary" onclick="showAddOAuthProviderModal()">
                    <i class="fas fa-plus"></i> Add OAuth Provider
                </button>
                <button class="btn btn-outline" onclick="showOAuthSetupGuide()">
                    <i class="fas fa-book"></i> Setup Guide
                </button>
            </div>
            <div class="alert alert-info" style="margin-top: 20px;">
                <i class="fas fa-info-circle"></i>
                <strong>First-time setup:</strong>
                <p>Add Google, Microsoft, or GitHub authentication to enable user login. After adding a provider, you'll be able to sign in and manage additional settings.</p>
            </div>
        `;
    } else {
        // Show management interface
        container.innerHTML = `
            <div class="toolbar">
                <button class="btn btn-primary" onclick="showAddOAuthProviderModal()">
                    <i class="fas fa-plus"></i> Add OAuth Provider
                </button>
                <button class="btn btn-outline" onclick="showOAuthSetupGuide()">
                    <i class="fas fa-book"></i> Setup Guide
                </button>
                <button class="btn btn-outline" onclick="loadOAuthProviders()">
                    <i class="fas fa-sync"></i> Refresh
                </button>
            </div>
            ${providers.length === 0 ? `
                <div class="alert alert-info" style="margin-top: 20px;">
                    <i class="fas fa-info-circle"></i>
                    <strong>No providers configured yet</strong>
                    <p>Click "Add OAuth Provider" to configure Google, Microsoft, or GitHub authentication.</p>
                </div>
            ` : `
                <div class="providers-list">
                    ${providers.map(p => `
                        <div class="provider-card">
                            <div class="provider-icon">
                                <i class="fab fa-${p.provider_id}"></i>
                            </div>
                            <div class="provider-info">
                                <h4>${p.provider_name}</h4>
                                <p>Provider ID: ${p.provider_id}</p>
                                <p>Scopes: ${p.scopes.join(', ')}</p>
                                <span class="badge ${p.enabled ? 'badge-success' : 'badge-danger'}">
                                    ${p.enabled ? 'Enabled' : 'Disabled'}
                                </span>
                            </div>
                            <div class="provider-actions">
                                <button class="btn btn-sm btn-outline" onclick="viewOAuthProviderDetails('${p.provider_id}')">
                                    <i class="fas fa-eye"></i> View Details
                                </button>
                                <button class="btn btn-sm btn-danger" onclick="removeOAuthProvider('${p.provider_id}')">
                                    <i class="fas fa-trash"></i> Remove
                                </button>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `}
        `;
    }
}

// Show Add OAuth Provider Modal
function showAddOAuthProviderModal() {
    // Reset form
    document.getElementById('oauthProviderForm').reset();
    document.getElementById('providerTemplate').value = '';
    currentScopes = ['openid', 'email', 'profile'];
    updateScopesDisplay();

    showModal('addOAuthProviderModal');
}

// Close OAuth Modal
function closeOAuthModal() {
    closeModal('addOAuthProviderModal');
}

// Load Provider Template
function loadProviderTemplate() {
    const templateSelect = document.getElementById('providerTemplate');
    const template = PROVIDER_TEMPLATES[templateSelect.value];

    if (template) {
        document.getElementById('providerId').value = template.provider_id;
        document.getElementById('providerName').value = template.provider_name;
        document.getElementById('authorizeUrl').value = template.authorize_url;
        document.getElementById('tokenUrl').value = template.token_url;
        document.getElementById('userinfoUrl').value = template.userinfo_url;

        currentScopes = [...template.scopes];
        updateScopesDisplay();

        showNotification(`Loaded ${template.provider_name} template. Add your Client ID and Client Secret.`, 'info');
    } else {
        // Clear form for custom provider
        document.getElementById('providerId').value = '';
        document.getElementById('providerName').value = '';
        document.getElementById('authorizeUrl').value = '';
        document.getElementById('tokenUrl').value = '';
        document.getElementById('userinfoUrl').value = '';
        currentScopes = [];
        updateScopesDisplay();
    }
}

// Scopes Management
function updateScopesDisplay() {
    const container = document.getElementById('scopesContainer');
    container.innerHTML = currentScopes.map(scope => `
        <span class="tag">${scope} <button type="button" onclick="removeScope('${scope}')">×</button></span>
    `).join('');
}

function addScope() {
    const input = document.getElementById('newScope');
    const scope = input.value.trim();

    if (scope && !currentScopes.includes(scope)) {
        currentScopes.push(scope);
        updateScopesDisplay();
        input.value = '';
    } else if (currentScopes.includes(scope)) {
        showNotification('Scope already added', 'warning');
    }
}

function removeScope(scope) {
    currentScopes = currentScopes.filter(s => s !== scope);
    updateScopesDisplay();
}

// Save OAuth Provider
async function saveOAuthProvider() {
    const providerId = document.getElementById('providerId').value.trim();
    const providerName = document.getElementById('providerName').value.trim();
    const clientId = document.getElementById('clientId').value.trim();
    const clientSecret = document.getElementById('clientSecret').value.trim();
    const authorizeUrl = document.getElementById('authorizeUrl').value.trim();
    const tokenUrl = document.getElementById('tokenUrl').value.trim();
    const userinfoUrl = document.getElementById('userinfoUrl').value.trim();
    const enabled = document.getElementById('providerEnabled').checked;

    // Validation
    if (!providerId || !providerName || !clientId || !clientSecret ||
        !authorizeUrl || !tokenUrl || !userinfoUrl) {
        showNotification('Please fill in all required fields', 'error');
        return;
    }

    // Validate provider ID format (lowercase, no spaces)
    if (!/^[a-z0-9_-]+$/.test(providerId)) {
        showNotification('Provider ID must be lowercase letters, numbers, hyphens, or underscores only', 'error');
        return;
    }

    if (currentScopes.length === 0) {
        showNotification('Please add at least one scope', 'error');
        return;
    }

    const providerData = {
        provider_id: providerId,
        client_id: clientId,
        client_secret: clientSecret,
        provider_name: providerName,
        authorize_url: authorizeUrl,
        token_url: tokenUrl,
        userinfo_url: userinfoUrl,
        scopes: currentScopes,
        enabled: enabled
    };

    try {
        await addOAuthProvider(providerData);
    } catch (error) {
        console.error('Error saving provider:', error);
    }
}

// Show OAuth Setup Guide
function showOAuthSetupGuide() {
    showModal('oauthSetupGuideModal');
}

async function addOAuthProvider(providerData) {
    try {
        const headers = {
            'Content-Type': 'application/json'
        };

        // Only add auth token if we have one
        if (authToken) {
            headers['Authorization'] = `Bearer ${authToken}`;
        }

        const response = await fetch('/admin/oauth/providers', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(providerData)
        });

        if (response.ok) {
            showNotification('OAuth provider added successfully! You can now sign in with this provider.', 'success');
            loadOAuthProviders();
            closeModal('addOAuthProviderModal');
        } else {
            const error = await response.json();
            showNotification('Failed to add provider: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error adding OAuth provider:', error);
        showNotification('Error adding provider: ' + error.message, 'error');
    }
}

async function removeOAuthProvider(providerId) {
    if (!confirm('Are you sure you want to remove this OAuth provider?')) return;

    try {
        const response = await fetch(`/admin/oauth/providers/${providerId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            showNotification('OAuth provider removed', 'success');
            loadOAuthProviders();
        } else {
            showNotification('Failed to remove provider', 'error');
        }
    } catch (error) {
        console.error('Error removing provider:', error);
    }
}

// View OAuth Provider Details
async function viewOAuthProviderDetails(providerId) {
    try {
        const response = await fetch(`/auth/providers/${providerId}/details`);

        if (response.ok) {
            const provider = await response.json();
            displayOAuthProviderDetails(provider);
        } else {
            showNotification('Failed to load provider details', 'error');
        }
    } catch (error) {
        console.error('Error loading provider details:', error);
        showNotification('Error loading provider details: ' + error.message, 'error');
    }
}

// Display OAuth Provider Details in Modal
function displayOAuthProviderDetails(provider) {
    const modalContent = `
        <div class="provider-details-view">
            <div class="detail-row">
                <label>Provider Name:</label>
                <div class="detail-value">
                    <strong>${provider.provider_name}</strong>
                    <span class="badge ${provider.enabled ? 'badge-success' : 'badge-danger'}">
                        ${provider.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                </div>
            </div>
            <div class="detail-row">
                <label>Provider ID:</label>
                <div class="detail-value"><code>${provider.provider_id}</code></div>
            </div>
            <div class="form-divider"></div>
            <div class="detail-row">
                <label>Client ID:</label>
                <div class="detail-value">
                    <code>${provider.client_id}</code>
                    <button class="btn btn-sm btn-outline" onclick="copyToClipboard('${provider.client_id}')" title="Copy to clipboard">
                        <i class="fas fa-copy"></i>
                    </button>
                </div>
            </div>
            <div class="detail-row">
                <label>Client Secret:</label>
                <div class="detail-value">
                    <code>${provider.client_secret}</code>
                    <small class="text-muted">• Last 4 characters shown for security</small>
                </div>
            </div>
            <div class="form-divider"></div>
            <div class="detail-row">
                <label>Authorization URL:</label>
                <div class="detail-value">
                    <code class="code-block">${provider.authorize_url}</code>
                </div>
            </div>
            <div class="detail-row">
                <label>Token URL:</label>
                <div class="detail-value">
                    <code class="code-block">${provider.token_url}</code>
                </div>
            </div>
            <div class="detail-row">
                <label>User Info URL:</label>
                <div class="detail-value">
                    <code class="code-block">${provider.userinfo_url}</code>
                </div>
            </div>
            <div class="form-divider"></div>
            <div class="detail-row">
                <label>OAuth Scopes:</label>
                <div class="detail-value">
                    ${provider.scopes.map(scope => `<span class="tag">${scope}</span>`).join(' ')}
                </div>
            </div>
            <div class="alert alert-info" style="margin-top: 20px;">
                <i class="fas fa-info-circle"></i>
                <strong>Redirect URI:</strong>
                <p>Make sure your OAuth application is configured with this redirect URI:</p>
                <code>${window.location.origin}/auth/callback</code>
                <button class="btn btn-sm btn-outline" onclick="copyToClipboard('${window.location.origin}/auth/callback')" style="margin-left: 10px;">
                    <i class="fas fa-copy"></i> Copy
                </button>
            </div>
        </div>
    `;

    // Create or update modal content
    const editModal = document.getElementById('editOAuthProviderModal');
    if (editModal) {
        editModal.querySelector('.modal-title').innerHTML = `
            <i class="fas fa-eye"></i>
            OAuth Provider Configuration
        `;
        editModal.querySelector('#editProviderContent').innerHTML = modalContent;
        showModal('editOAuthProviderModal');
    }
}

// Copy to Clipboard helper function
function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            showNotification('Copied to clipboard!', 'success');
        }).catch(err => {
            console.error('Failed to copy:', err);
            showNotification('Failed to copy to clipboard', 'error');
        });
    } else {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        document.body.appendChild(textArea);
        textArea.select();
        try {
            document.execCommand('copy');
            showNotification('Copied to clipboard!', 'success');
        } catch (err) {
            console.error('Failed to copy:', err);
            showNotification('Failed to copy to clipboard', 'error');
        }
        document.body.removeChild(textArea);
    }
}

// User Management (RBAC)
async function loadUsers() {
    const container = document.getElementById('usersContainer');

    // ALWAYS try to get token from localStorage first, then from auth module
    authToken = localStorage.getItem('access_token');
    if (!authToken && window.authModule && window.authModule.isAuthenticated()) {
        authToken = window.authModule.getAccessToken();
    }

    // Check if user is authenticated
    if (!authToken) {
        container.innerHTML = `
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i>
                <strong>Authentication Required</strong>
                <p>Please sign in to view and manage users.</p>
            </div>
        `;
        return;
    }

    try {
        const response = await fetch('/admin/users', {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            displayUsers(data.users);
        } else if (response.status === 403) {
            container.innerHTML = `
                <div class="alert alert-warning">
                    <i class="fas fa-lock"></i>
                    <strong>Access Restricted</strong>
                    <p>You don't have permission to view users. Please contact your administrator for USER_VIEW permission.</p>
                </div>
            `;
        } else if (response.status === 401) {
            container.innerHTML = `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle"></i>
                    <strong>Session Expired</strong>
                    <p>Your session has expired. Please sign in again.</p>
                </div>
            `;
            // Clear invalid token
            localStorage.removeItem('access_token');
            authToken = null;
        } else {
            container.innerHTML = `
                <div class="alert alert-error">
                    <i class="fas fa-exclamation-circle"></i>
                    <strong>Error Loading Users</strong>
                    <p>Failed to load user list. Please try again.</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading users:', error);
        container.innerHTML = `
            <div class="alert alert-error">
                <i class="fas fa-exclamation-circle"></i>
                <strong>Network Error</strong>
                <p>Could not connect to server. Please check your connection.</p>
            </div>
        `;
    }
}

// Store all users globally for filtering
let allUsers = [];
let currentUserPage = 1;
const USERS_PER_PAGE = 5;

function displayUsers(users) {
    const container = document.getElementById('usersContainer');
    if (!container) return;

    // Store users globally
    allUsers = users;

    container.innerHTML = `
        <div class="toolbar">
            <div class="toolbar-left">
                <div class="search-box">
                    <input type="text" class="search-input" id="userSearchInput" placeholder="Search by email..." onkeyup="filterUsers()">
                    <i class="fas fa-search search-icon"></i>
                </div>
            </div>
            <div class="toolbar-right">
                <button class="btn btn-primary" onclick="showAddUserModal()">
                    <i class="fas fa-user-plus"></i> Add User
                </button>
                <button class="btn btn-outline" onclick="loadUsers()">
                    <i class="fas fa-refresh"></i> Refresh
                </button>
            </div>
        </div>
        <div id="usersTableContainer">
            <!-- Users table will be rendered here -->
        </div>
    `;

    // Render the initial table
    renderUsersTable(users);
}

function renderUsersTable(users) {
    const tableContainer = document.getElementById('usersTableContainer');
    if (!tableContainer) return;

    // Calculate pagination
    const startIndex = (currentUserPage - 1) * USERS_PER_PAGE;
    const endIndex = startIndex + USERS_PER_PAGE;
    const paginatedUsers = users.slice(startIndex, endIndex);
    const totalPages = Math.ceil(users.length / USERS_PER_PAGE);

    tableContainer.innerHTML = `
        <table class="admin-table" style="margin-top: 15px;">
            <thead>
                <tr>
                    <th>Email</th>
                    <th>Name</th>
                    <th>Provider</th>
                    <th>Roles</th>
                    <th>Status</th>
                    <th>Last Login</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                ${users.length === 0 ? `
                    <tr>
                        <td colspan="7" style="text-align: center; padding: 40px;">
                            <i class="fas fa-users" style="font-size: 48px; color: #ccc;"></i>
                            <p style="margin-top: 20px; color: #999;">No users found. Try adjusting your search.</p>
                        </td>
                    </tr>
                ` : paginatedUsers.map(u => `
                    <tr>
                        <td>${u.email}</td>
                        <td>${u.name || '-'}</td>
                        <td><span class="badge">${u.provider || 'local'}</span></td>
                        <td>${u.roles.join(', ')}</td>
                        <td>
                            <span class="badge ${u.enabled ? 'badge-success' : 'badge-danger'}">
                                ${u.enabled ? 'Active' : 'Disabled'}
                            </span>
                        </td>
                        <td>${u.last_login ? new Date(u.last_login).toLocaleString() : 'Never'}</td>
                        <td>
                            <button class="btn btn-sm btn-primary" onclick="showManageUserRolesModal('${u.user_id}', '${u.email.replace(/'/g, "\\'")}', ${JSON.stringify(u.roles).replace(/"/g, '&quot;')})">
                                <i class="fas fa-user-cog"></i> Manage Roles
                            </button>
                            <button class="btn btn-sm btn-success" onclick="showAdminGeneratedTokenModal('${u.user_id}', '${u.email.replace(/'/g, "\\'")}', '${u.name ? u.name.replace(/'/g, "\\'") : ''}')">
                                <i class="fas fa-key"></i> Get Token
                            </button>
                            ${u.role_ids && u.role_ids.includes('admin') ?
                                '<button class="btn btn-sm btn-secondary" disabled title="Admin users cannot be deleted"><i class="fas fa-shield-alt"></i> Protected</button>' :
                                `<button class="btn btn-sm btn-danger" onclick="deleteUser('${u.user_id}', '${u.email.replace(/'/g, "\\'")}')"><i class="fas fa-trash"></i> Delete</button>`
                            }
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        ${totalPages > 1 ? `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px;">
                <div style="color: #666;">
                    Showing ${startIndex + 1}-${Math.min(endIndex, users.length)} of ${users.length} users
                </div>
                <div style="display: flex; gap: 10px;">
                    <button class="btn btn-sm btn-outline" onclick="changeUserPage(${currentUserPage - 1})" ${currentUserPage === 1 ? 'disabled' : ''}>
                        <i class="fas fa-chevron-left"></i> Previous
                    </button>
                    <div style="display: flex; gap: 5px;">
                        ${Array.from({length: totalPages}, (_, i) => i + 1).map(page => `
                            <button class="btn btn-sm ${page === currentUserPage ? 'btn-primary' : 'btn-outline'}" onclick="changeUserPage(${page})">
                                ${page}
                            </button>
                        `).join('')}
                    </div>
                    <button class="btn btn-sm btn-outline" onclick="changeUserPage(${currentUserPage + 1})" ${currentUserPage === totalPages ? 'disabled' : ''}>
                        Next <i class="fas fa-chevron-right"></i>
                    </button>
                </div>
            </div>
        ` : ''}
    `;
}

function changeUserPage(page) {
    const searchTerm = document.getElementById('userSearchInput')?.value.toLowerCase() || '';
    let filteredUsers = allUsers;

    if (searchTerm) {
        filteredUsers = allUsers.filter(user =>
            user.email.toLowerCase().includes(searchTerm) ||
            (user.name && user.name.toLowerCase().includes(searchTerm))
        );
    }

    const totalPages = Math.ceil(filteredUsers.length / USERS_PER_PAGE);
    if (page < 1 || page > totalPages) return;

    currentUserPage = page;
    renderUsersTable(filteredUsers);
}

function filterUsers() {
    const searchInput = document.getElementById('userSearchInput');
    if (!searchInput) return;

    const searchTerm = searchInput.value.toLowerCase();

    // Reset to page 1 when searching
    currentUserPage = 1;

    if (!searchTerm) {
        // Show all users
        renderUsersTable(allUsers);
        return;
    }

    // Filter users by email or name
    const filteredUsers = allUsers.filter(user =>
        user.email.toLowerCase().includes(searchTerm) ||
        (user.name && user.name.toLowerCase().includes(searchTerm))
    );

    renderUsersTable(filteredUsers);
}

// Show Manage User Roles Modal with checkboxes (similar to Tool Discovery)
async function showManageUserRolesModal(userId, userEmail, currentRoles) {
    try {
        // Load available roles
        const rolesResponse = await fetch('/admin/roles', {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (!rolesResponse.ok) {
            showNotification('Failed to load roles', 'error');
            return;
        }

        const rolesData = await rolesResponse.json();
        const availableRoles = rolesData.roles;

        // Create a map of role names to role IDs for current roles
        const currentRoleNames = Array.isArray(currentRoles) ? currentRoles : [];
        const currentRoleIds = availableRoles
            .filter(role => currentRoleNames.includes(role.role_name))
            .map(role => role.role_id);

        // Create modal HTML dynamically
        let modalHTML = `
            <div id="manageUserRolesModal" class="modal" style="display: block;">
                <div class="modal-content">
                    <div class="modal-header">
                        <div class="modal-title">
                            <i class="fas fa-user-cog"></i>
                            Manage Roles for ${userEmail}
                        </div>
                        <button class="modal-close" onclick="closeManageUserRolesModal()">&times;</button>
                    </div>
                    <div class="modal-body">
                        <div class="form-group">
                            <label class="form-label">Assign Roles</label>
                            <div id="userRolesCheckboxes" class="checkbox-group">
                                ${availableRoles.map(role => `
                                    <label class="checkbox-item">
                                        <input type="checkbox" name="user-roles" value="${role.role_id}"
                                            data-role-name="${role.role_name}"
                                            ${currentRoleIds.includes(role.role_id) ? 'checked' : ''}>
                                        <span>${role.role_name}</span>
                                        <small>${role.description || 'No description'}</small>
                                    </label>
                                `).join('')}
                            </div>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <button class="btn btn-outline" onclick="closeManageUserRolesModal()">Cancel</button>
                        <button class="btn btn-primary" id="saveUserRolesBtn" data-user-id="${userId}" data-original-roles='${JSON.stringify(currentRoleIds)}'>
                            <i class="fas fa-save"></i> Save Roles
                        </button>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if present
        const existingModal = document.getElementById('manageUserRolesModal');
        if (existingModal) {
            existingModal.remove();
        }

        // Insert modal into DOM
        document.body.insertAdjacentHTML('beforeend', modalHTML);

        // Add event listener to the save button
        const saveBtn = document.getElementById('saveUserRolesBtn');
        if (saveBtn) {
            saveBtn.addEventListener('click', function() {
                const userId = this.getAttribute('data-user-id');
                const originalRoles = JSON.parse(this.getAttribute('data-original-roles'));
                saveUserRoles(userId, originalRoles);
            });
        }

    } catch (error) {
        console.error('Error showing manage user roles modal:', error);
        showNotification('Error loading role management', 'error');
    }
}

// Close Manage User Roles Modal
function closeManageUserRolesModal() {
    const modal = document.getElementById('manageUserRolesModal');
    if (modal) {
        modal.remove();
    }
}

// Save User Roles
async function saveUserRoles(userId, originalRoleIds) {
    try {
        // Get all checked role checkboxes
        const selectedRoleIds = Array.from(document.querySelectorAll('#userRolesCheckboxes input[name="user-roles"]:checked'))
            .map(cb => cb.value);

        if (selectedRoleIds.length === 0) {
            showNotification('Please select at least one role', 'error');
            return;
        }

        // Determine which roles to add and which to remove
        const rolesToAdd = selectedRoleIds.filter(roleId => !originalRoleIds.includes(roleId));
        const rolesToRemove = originalRoleIds.filter(roleId => !selectedRoleIds.includes(roleId));

        console.log('Original roles:', originalRoleIds);
        console.log('Selected roles:', selectedRoleIds);
        console.log('Roles to add:', rolesToAdd);
        console.log('Roles to remove:', rolesToRemove);

        let hasErrors = false;

        // Add new roles
        for (const roleId of rolesToAdd) {
            try {
                const response = await fetch(`/admin/users/${userId}/roles`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${authToken}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ role_id: roleId })
                });

                if (!response.ok) {
                    const error = await response.json();
                    console.error(`Failed to add role ${roleId}:`, error);
                    hasErrors = true;
                }
            } catch (error) {
                console.error(`Error adding role ${roleId}:`, error);
                hasErrors = true;
            }
        }

        // Remove unselected roles
        for (const roleId of rolesToRemove) {
            try {
                const response = await fetch(`/admin/users/${userId}/roles/${roleId}`, {
                    method: 'DELETE',
                    headers: {
                        'Authorization': `Bearer ${authToken}`
                    }
                });

                if (!response.ok) {
                    const error = await response.json();
                    console.error(`Failed to remove role ${roleId}:`, error);
                    hasErrors = true;
                }
            } catch (error) {
                console.error(`Error removing role ${roleId}:`, error);
                hasErrors = true;
            }
        }

        if (hasErrors) {
            showNotification('Some roles could not be updated. Check console for details.', 'warning');
        } else {
            showNotification('Roles updated successfully', 'success');
        }

        closeManageUserRolesModal();
        loadUsers(); // Refresh the user list

    } catch (error) {
        console.error('Error saving user roles:', error);
        showNotification('Error updating roles: ' + error.message, 'error');
    }
}

// Role Management
async function loadRoles() {
    const container = document.getElementById('rolesContainer');

    // ALWAYS try to get token from localStorage first, then from auth module
    authToken = localStorage.getItem('access_token');
    if (!authToken && window.authModule && window.authModule.isAuthenticated()) {
        authToken = window.authModule.getAccessToken();
    }

    // Check if user is authenticated
    if (!authToken) {
        container.innerHTML = `
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i>
                <strong>Authentication Required</strong>
                <p>Please sign in to view and manage roles.</p>
            </div>
        `;
        return;
    }

    try {
        const response = await fetch('/admin/roles', {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            displayRoles(data.roles);
        } else if (response.status === 403) {
            container.innerHTML = `
                <div class="alert alert-warning">
                    <i class="fas fa-lock"></i>
                    <strong>Access Restricted</strong>
                    <p>You don't have permission to view roles. Please contact your administrator for ROLE_VIEW permission.</p>
                </div>
            `;
        } else if (response.status === 401) {
            container.innerHTML = `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle"></i>
                    <strong>Session Expired</strong>
                    <p>Your session has expired. Please sign in again.</p>
                </div>
            `;
            localStorage.removeItem('access_token');
            authToken = null;
        } else {
            container.innerHTML = `
                <div class="alert alert-error">
                    <i class="fas fa-exclamation-circle"></i>
                    <strong>Error Loading Roles</strong>
                    <p>Failed to load roles list. Please try again.</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading roles:', error);
        container.innerHTML = `
            <div class="alert alert-error">
                <i class="fas fa-exclamation-circle"></i>
                <strong>Network Error</strong>
                <p>Could not connect to server. Please check your connection.</p>
            </div>
        `;
    }
}

function displayRoles(roles) {
    const container = document.getElementById('rolesContainer');
    if (!container) return;

    container.innerHTML = `
        <div class="toolbar">
            <button class="btn btn-primary" onclick="showCreateRoleModal()">
                <i class="fas fa-plus"></i> Create Role
            </button>
        </div>
        <div class="roles-grid">
            ${roles.map(r => `
                <div class="role-card ${r.is_system ? 'system-role' : ''}">
                    <div class="role-header">
                        <h4>${r.role_name}</h4>
                        ${r.is_system ? '<span class="badge badge-info">System</span>' : ''}
                    </div>
                    <p class="role-description">${r.description}</p>
                    <div class="role-stats">
                        <span><i class="fas fa-users"></i> ${r.user_count} users</span>
                        <span><i class="fas fa-key"></i> ${r.permissions.length} permissions</span>
                    </div>
                    <div class="role-permissions">
                        ${r.permissions.slice(0, 5).map(p => `<span class="permission-badge">${p}</span>`).join('')}
                        ${r.permissions.length > 5 ? `<span class="more">+${r.permissions.length - 5} more</span>` : ''}
                    </div>
                    <div class="role-actions">
                        <button class="btn btn-sm btn-outline" onclick="viewRoleDetails('${r.role_id}')">
                            <i class="fas fa-eye"></i> View
                        </button>
                        ${!r.is_system ? `
                            <button class="btn btn-sm btn-primary" onclick="showEditRoleModal('${r.role_id}')">
                                <i class="fas fa-edit"></i> Edit
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="deleteRole('${r.role_id}')">
                                <i class="fas fa-trash"></i> Delete
                            </button>
                        ` : ''}
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

// Audit Logs
async function loadAuditLogs() {
    // ALWAYS try to get token from localStorage first, then from auth module
    authToken = localStorage.getItem('access_token');
    if (!authToken && window.authModule && window.authModule.isAuthenticated()) {
        authToken = window.authModule.getAccessToken();
    }

    if (!authToken) {
        const container = document.getElementById('auditLogsContainer');
        if (container) {
            container.innerHTML = `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle"></i>
                    <strong>Authentication Required</strong>
                    <p>Please sign in to view audit logs.</p>
                </div>
            `;
        }
        return;
    }

    try {
        const response = await fetch('/admin/audit/events?limit=100', {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            displayAuditLogs(data.events);
        }

        // Also load statistics
        loadAuditStatistics();
    } catch (error) {
        console.error('Error loading audit logs:', error);
    }
}

function displayAuditLogs(events) {
    const container = document.getElementById('auditLogsContainer');
    if (!container) return;

    container.innerHTML = `
        <table class="admin-table">
            <thead>
                <tr>
                    <th>Timestamp</th>
                    <th>Event Type</th>
                    <th>User</th>
                    <th>Action</th>
                    <th>Severity</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
                ${events.map(e => `
                    <tr class="${e.success ? '' : 'event-failed'}">
                        <td>${new Date(e.timestamp).toLocaleString()}</td>
                        <td><code>${e.event_type}</code></td>
                        <td>${e.user_email || 'System'}</td>
                        <td>${e.action || '-'}</td>
                        <td>
                            <span class="badge badge-${getSeverityClass(e.severity)}">
                                ${e.severity}
                            </span>
                        </td>
                        <td>
                            <i class="fas fa-${e.success ? 'check text-success' : 'times text-danger'}"></i>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

async function loadAuditStatistics() {
    try {
        const response = await fetch('/admin/audit/statistics?hours=24', {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const stats = await response.json();
            displayAuditStatistics(stats);
        }
    } catch (error) {
        console.error('Error loading audit statistics:', error);
    }
}

function displayAuditStatistics(stats) {
    const container = document.getElementById('auditStatsContainer');
    if (!container) return;

    container.innerHTML = `
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">${stats.total_events}</div>
                <div class="stat-label">Total Events (24h)</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.severity_counts.error || 0}</div>
                <div class="stat-label">Errors</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.severity_counts.warning || 0}</div>
                <div class="stat-label">Warnings</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${stats.top_users.length}</div>
                <div class="stat-label">Active Users</div>
            </div>
        </div>
    `;
}

// Utility Functions
function getSeverityClass(severity) {
    const map = {
        'info': 'info',
        'warning': 'warning',
        'error': 'danger',
        'critical': 'danger'
    };
    return map[severity] || 'secondary';
}

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `toast toast-${type}`;
    notification.innerHTML = `
        <div class="toast-content">
            <i class="fas fa-${getNotificationIcon(type)}"></i>
            <span>${message}</span>
        </div>
    `;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        background: ${getNotificationColor(type)};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        z-index: 10000;
        animation: slideIn 0.3s ease-out;
        min-width: 300px;
        max-width: 500px;
        font-family: 'Inter', sans-serif;
    `;

    document.body.appendChild(notification);

    // Auto-remove after 4 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-in';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 4000);
}

function getNotificationIcon(type) {
    const icons = {
        'success': 'check-circle',
        'error': 'exclamation-circle',
        'warning': 'exclamation-triangle',
        'info': 'info-circle'
    };
    return icons[type] || 'info-circle';
}

function getNotificationColor(type) {
    const colors = {
        'success': '#10b981',
        'error': '#ef4444',
        'warning': '#f59e0b',
        'info': '#3b82f6'
    };
    return colors[type] || '#3b82f6';
}

// Add CSS animations for notifications
if (!document.getElementById('toast-animations')) {
    const style = document.createElement('style');
    style.id = 'toast-animations';
    style.textContent = `
        @keyframes slideIn {
            from {
                transform: translateX(400px);
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
                transform: translateX(400px);
                opacity: 0;
            }
        }
        .toast-content {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .toast-content i {
            font-size: 20px;
        }
    `;
    document.head.appendChild(style);
}

function showModal(modalId, data) {
    // Modal management
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'block';
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
    }
}

// ==========================================
// User Management Functions
// ==========================================

// Show Add User Modal
function showAddUserModal() {
    // Load available roles first
    loadRolesForUserModal();
    // Show password field by default (for manual provider)
    togglePasswordField();
    showModal('addUserModal');
}

// Toggle password field visibility based on provider
function togglePasswordField() {
    const provider = document.getElementById('userProvider').value;
    const passwordGroup = document.getElementById('userPasswordGroup');

    // Show password field only for manual/local provider
    if (provider === 'manual') {
        passwordGroup.style.display = 'block';
        document.getElementById('userPassword').setAttribute('required', 'required');
    } else {
        passwordGroup.style.display = 'none';
        document.getElementById('userPassword').removeAttribute('required');
        document.getElementById('userPassword').value = ''; // Clear password field
    }
}

// Load roles for the Add User Modal
async function loadRolesForUserModal() {
    try {
        const response = await fetch('/admin/roles', {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            const rolesSelect = document.getElementById('userRolesSelect');

            rolesSelect.innerHTML = data.roles.map(role => `
                <label class="checkbox-item">
                    <input type="checkbox" name="roles" value="${role.role_id}">
                    <span>${role.role_name}</span>
                    <small>${role.description}</small>
                </label>
            `).join('');
        }
    } catch (error) {
        console.error('Error loading roles:', error);
    }
}

// Save New User
async function saveNewUser() {
    const email = document.getElementById('userEmail').value.trim();
    const name = document.getElementById('userName').value.trim();
    const provider = document.getElementById('userProvider').value;
    const password = document.getElementById('userPassword').value;

    // Get selected roles
    const selectedRoles = Array.from(document.querySelectorAll('#userRolesSelect input[name="roles"]:checked'))
        .map(cb => cb.value);

    // Validation
    if (!email || !name) {
        showNotification('Email and name are required', 'error');
        return;
    }

    // Validate password for manual/local provider
    if (provider === 'manual' && !password) {
        showNotification('Password is required for Manual (Local) authentication', 'error');
        return;
    }

    if (selectedRoles.length === 0) {
        showNotification('Please select at least one role', 'error');
        return;
    }

    // Map "manual" to "local" for backend compatibility
    const backendProvider = provider === 'manual' ? 'local' : provider;

    // Build request body
    const requestBody = {
        email: email,
        name: name,
        roles: selectedRoles,
        provider: backendProvider
    };

    // Only include password for local provider
    if (provider === 'manual' && password) {
        requestBody.password = password;
    }

    try {
        const response = await fetch('/admin/users', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestBody)
        });

        if (response.ok) {
            showNotification('User added successfully', 'success');
            closeModal('addUserModal');
            loadUsers();
        } else {
            const error = await response.json();
            showNotification('Failed to add user: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error adding user:', error);
        showNotification('Error adding user: ' + error.message, 'error');
    }
}

// Delete User
async function deleteUser(userId, userEmail) {
    if (!confirm(`Are you sure you want to delete user "${userEmail}"?\n\nThis action cannot be undone and will remove all role assignments for this user.`)) {
        return;
    }

    try {
        const response = await fetch(`/admin/users/${userId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            showNotification(`User "${userEmail}" deleted successfully`, 'success');
            loadUsers(); // Refresh the users list
        } else if (response.status === 400) {
            const error = await response.json();
            showNotification(error.detail || 'Cannot delete user', 'error');
        } else if (response.status === 403) {
            showNotification('You do not have permission to delete users', 'error');
        } else if (response.status === 404) {
            showNotification('User not found', 'error');
        } else {
            const error = await response.json();
            showNotification('Failed to delete user: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error deleting user:', error);
        showNotification('Error deleting user: ' + error.message, 'error');
    }
}

// ==========================================
// Role Management Functions
// ==========================================

// Show Create Role Modal
function showCreateRoleModal() {
    loadPermissionsGrid();
    showModal('createRoleModal');
}

// Load all available permissions into the grid
async function loadPermissionsGrid() {
    const permissionsGrid = document.getElementById('permissionsGrid');

    // All available permissions (must match Python Permission enum values in rbac.py)
    const allPermissions = [
        { id: 'server:view', name: 'Server View', description: 'View MCP servers and configurations' },
        { id: 'server:add', name: 'Server Add', description: 'Add new MCP servers' },
        { id: 'server:edit', name: 'Server Edit', description: 'Modify MCP servers' },
        { id: 'server:delete', name: 'Server Delete', description: 'Remove MCP servers' },
        { id: 'server:test', name: 'Server Test', description: 'Test MCP server connections' },
        { id: 'tool:view', name: 'Tool View', description: 'View available tools' },
        { id: 'tool:execute', name: 'Tool Execute', description: 'Execute tools from MCP servers' },
        { id: 'tool:manage', name: 'Tool Manage', description: 'Manage tool permissions' },
        { id: 'config:view', name: 'Config View', description: 'View gateway configuration' },
        { id: 'config:edit', name: 'Config Edit', description: 'Modify gateway configuration' },
        { id: 'user:view', name: 'User View', description: 'View users and their information' },
        { id: 'user:manage', name: 'User Manage', description: 'Add, modify, or remove users' },
        { id: 'role:view', name: 'Role View', description: 'View roles and permissions' },
        { id: 'role:manage', name: 'Role Manage', description: 'Create, modify, or delete roles' },
        { id: 'audit:view', name: 'Audit View', description: 'View audit logs and statistics' },
        { id: 'oauth:manage', name: 'OAuth Manage', description: 'Manage OAuth providers' }
    ];

    permissionsGrid.innerHTML = allPermissions.map(perm => `
        <label class="checkbox-item">
            <input type="checkbox" name="permissions" value="${perm.id}">
            <div>
                <strong>${perm.name}</strong>
                <small>${perm.description}</small>
            </div>
        </label>
    `).join('');
}

// Save New Role
async function saveNewRole() {
    const roleName = document.getElementById('roleName').value.trim();
    const description = document.getElementById('roleDescription').value.trim();

    // Get selected permissions
    const selectedPermissions = Array.from(document.querySelectorAll('#permissionsGrid input[name="permissions"]:checked'))
        .map(cb => cb.value);

    // Validation
    if (!roleName) {
        showNotification('Role name is required', 'error');
        return;
    }

    if (selectedPermissions.length === 0) {
        showNotification('Please select at least one permission', 'error');
        return;
    }

    try {
        const response = await fetch('/admin/roles', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                role_name: roleName,
                description: description,
                permissions: selectedPermissions
            })
        });

        if (response.ok) {
            showNotification('Role created successfully', 'success');
            closeModal('createRoleModal');
            loadRoles();
        } else {
            const error = await response.json();
            showNotification('Failed to create role: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error creating role:', error);
        showNotification('Error creating role: ' + error.message, 'error');
    }
}

// Delete Role
async function deleteRole(roleId) {
    if (!confirm('Are you sure you want to delete this role? Users with this role will lose their assigned permissions.')) {
        return;
    }

    try {
        const response = await fetch(`/admin/roles/${roleId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            showNotification('Role deleted successfully', 'success');
            loadRoles();
        } else {
            const error = await response.json();
            showNotification('Failed to delete role: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error deleting role:', error);
        showNotification('Error deleting role: ' + error.message, 'error');
    }
}

// Show Edit Role Modal
async function showEditRoleModal(roleId) {
    try {
        // Fetch role details
        const response = await fetch(`/admin/roles`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            const role = data.roles.find(r => r.role_id === roleId);

            if (!role) {
                showNotification('Role not found', 'error');
                return;
            }

            // Populate edit form
            document.getElementById('editRoleId').value = role.role_id;
            document.getElementById('editRoleName').value = role.role_name;
            document.getElementById('editRoleDescription').value = role.description || '';

            // Load permissions grid for edit
            await loadPermissionsForEdit(role.permissions);

            // Show modal
            showModal('editRoleModal');
        } else {
            showNotification('Failed to load role details', 'error');
        }
    } catch (error) {
        console.error('Error loading role for edit:', error);
        showNotification('Error loading role: ' + error.message, 'error');
    }
}

// Load permissions grid for editing with pre-selected permissions
async function loadPermissionsForEdit(selectedPermissions) {
    const permissionsGrid = document.getElementById('editPermissionsGrid');

    // All available permissions (must match Python Permission enum values in rbac.py)
    const allPermissions = [
        { id: 'server:view', name: 'Server View', description: 'View MCP servers and configurations' },
        { id: 'server:add', name: 'Server Add', description: 'Add new MCP servers' },
        { id: 'server:edit', name: 'Server Edit', description: 'Modify MCP servers' },
        { id: 'server:delete', name: 'Server Delete', description: 'Remove MCP servers' },
        { id: 'server:test', name: 'Server Test', description: 'Test MCP server connections' },
        { id: 'tool:view', name: 'Tool View', description: 'View available tools' },
        { id: 'tool:execute', name: 'Tool Execute', description: 'Execute tools from MCP servers' },
        { id: 'tool:manage', name: 'Tool Manage', description: 'Manage tool permissions' },
        { id: 'config:view', name: 'Config View', description: 'View gateway configuration' },
        { id: 'config:edit', name: 'Config Edit', description: 'Modify gateway configuration' },
        { id: 'user:view', name: 'User View', description: 'View users and their information' },
        { id: 'user:manage', name: 'User Manage', description: 'Add, modify, or remove users' },
        { id: 'role:view', name: 'Role View', description: 'View roles and permissions' },
        { id: 'role:manage', name: 'Role Manage', description: 'Create, modify, or delete roles' },
        { id: 'audit:view', name: 'Audit View', description: 'View audit logs and statistics' },
        { id: 'oauth:manage', name: 'OAuth Manage', description: 'Manage OAuth providers' }
    ];

    permissionsGrid.innerHTML = allPermissions.map(perm => {
        const isChecked = selectedPermissions.includes(perm.id);
        return `
            <label class="checkbox-item">
                <input type="checkbox" name="editPermissions" value="${perm.id}" ${isChecked ? 'checked' : ''}>
                <div>
                    <strong>${perm.name}</strong>
                    <small>${perm.description}</small>
                </div>
            </label>
        `;
    }).join('');
}

// Update Role
async function updateRole() {
    const roleId = document.getElementById('editRoleId').value;
    const roleName = document.getElementById('editRoleName').value.trim();
    const description = document.getElementById('editRoleDescription').value.trim();

    // Get selected permissions
    const selectedPermissions = Array.from(document.querySelectorAll('#editPermissionsGrid input[name="editPermissions"]:checked'))
        .map(cb => cb.value);

    // Validation
    if (!roleName) {
        showNotification('Role name is required', 'error');
        return;
    }

    if (selectedPermissions.length === 0) {
        showNotification('Please select at least one permission', 'error');
        return;
    }

    try {
        const response = await fetch(`/admin/roles/${roleId}`, {
            method: 'PUT',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                role_name: roleName,
                description: description,
                permissions: selectedPermissions
            })
        });

        if (response.ok) {
            showNotification('Role updated successfully', 'success');
            closeModal('editRoleModal');
            loadRoles();
        } else {
            const error = await response.json();
            showNotification('Failed to update role: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error updating role:', error);
        showNotification('Error updating role: ' + error.message, 'error');
    }
}

// View Role Details
async function viewRoleDetails(roleId) {
    try {
        // Fetch role details
        const response = await fetch(`/admin/roles`, {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            const role = data.roles.find(r => r.role_id === roleId);

            if (!role) {
                showNotification('Role not found', 'error');
                return;
            }

            // Build role details display
            const permissionsList = role.permissions.map(p => `
                <li><span class="permission-badge">${p}</span></li>
            `).join('');

            const viewContent = document.getElementById('viewRoleContent');
            viewContent.innerHTML = `
                <div class="role-details-view">
                    <div class="detail-row">
                        <label>Role Name:</label>
                        <div class="detail-value">
                            <strong>${role.role_name}</strong>
                            ${role.is_system ? '<span class="badge badge-info">System Role</span>' : ''}
                        </div>
                    </div>
                    <div class="detail-row">
                        <label>Description:</label>
                        <div class="detail-value">${role.description || '<em>No description</em>'}</div>
                    </div>
                    <div class="detail-row">
                        <label>Role ID:</label>
                        <div class="detail-value"><code>${role.role_id}</code></div>
                    </div>
                    <div class="detail-row">
                        <label>Users:</label>
                        <div class="detail-value">${role.user_count} users assigned to this role</div>
                    </div>
                    <div class="detail-row">
                        <label>Permissions (${role.permissions.length}):</label>
                        <div class="detail-value">
                            <ul class="permissions-list">
                                ${permissionsList}
                            </ul>
                        </div>
                    </div>
                    ${role.is_system ? `
                        <div class="alert alert-info" style="margin-top: 20px;">
                            <i class="fas fa-info-circle"></i>
                            <strong>System Role</strong>
                            <p>This is a system-defined role and cannot be modified or deleted.</p>
                        </div>
                    ` : ''}
                </div>
            `;

            // Show modal
            showModal('viewRoleModal');
        } else {
            showNotification('Failed to load role details', 'error');
        }
    } catch (error) {
        console.error('Error loading role details:', error);
        showNotification('Error loading role: ' + error.message, 'error');
    }
}

// ==========================================
// Active Directory Integration Functions
// ==========================================

// Global AD config storage
let adConfigData = {
    server: '',
    port: 389,
    base_dn: '',
    bind_dn: '',
    bind_password: '',
    group_filter: '(objectClass=organizationalUnit)',
    use_ssl: false
};

// Test AD Connection
async function testADConnection() {
    const server = document.getElementById('adConfigServer').value.trim();
    const port = parseInt(document.getElementById('adConfigPort').value);
    const baseDN = document.getElementById('adConfigBaseDN').value.trim();
    const bindDN = document.getElementById('adConfigBindDN').value.trim();
    const bindPassword = document.getElementById('adConfigPassword').value;
    const useSSL = document.getElementById('adConfigUseSSL').checked;

    if (!server || !baseDN || !bindDN || !bindPassword) {
        showNotification('Please fill in all required fields', 'error');
        return;
    }

    const statusDiv = document.getElementById('adConfigStatus');
    statusDiv.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Testing connection...</div>';

    try {
        const response = await fetch('/admin/ad/query-groups', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                server: server,
                port: port,
                bind_dn: bindDN,
                bind_password: bindPassword,
                base_dn: baseDN,
                group_filter: '(objectClass=organizationalUnit)',  // Standard LDAP filter for organizational units
                use_ssl: useSSL
            })
        });

        if (response.ok) {
            statusDiv.innerHTML = `
                <div class="alert alert-success">
                    <i class="fas fa-check-circle"></i>
                    <strong>Connection Successful!</strong>
                    <p>Successfully connected to Active Directory server.</p>
                </div>
            `;
            showNotification('AD connection test successful', 'success');
        } else {
            const error = await response.json();
            statusDiv.innerHTML = `
                <div class="alert alert-error">
                    <i class="fas fa-exclamation-circle"></i>
                    <strong>Connection Failed</strong>
                    <p>${error.detail || 'Could not connect to Active Directory'}</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error testing AD connection:', error);
        statusDiv.innerHTML = `
            <div class="alert alert-error">
                <i class="fas fa-exclamation-circle"></i>
                <strong>Connection Error</strong>
                <p>${error.message}</p>
            </div>
        `;
    }
}

// Save AD Configuration
async function saveADConfig() {
    const server = document.getElementById('adConfigServer').value.trim();
    const port = parseInt(document.getElementById('adConfigPort').value);
    const baseDN = document.getElementById('adConfigBaseDN').value.trim();
    const bindDN = document.getElementById('adConfigBindDN').value.trim();
    const bindPassword = document.getElementById('adConfigPassword').value;
    const groupFilter = document.getElementById('adConfigGroupFilter').value.trim();
    const useSSL = document.getElementById('adConfigUseSSL').checked;

    if (!server || !baseDN || !bindDN || !bindPassword) {
        showNotification('Please fill in all required fields', 'error');
        return;
    }

    // Store configuration in memory (including password for session)
    adConfigData = {
        server: server,
        port: port,
        base_dn: baseDN,
        bind_dn: bindDN,
        bind_password: bindPassword,
        group_filter: groupFilter,
        use_ssl: useSSL
    };

    try {
        // Save to database (password excluded for security)
        const headers = {
            'Content-Type': 'application/json'
        };

        // Only add auth token if we have one
        if (authToken) {
            headers['Authorization'] = `Bearer ${authToken}`;
        }

        const response = await fetch('/admin/ad/config', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({
                server: server,
                port: port,
                base_dn: baseDN,
                bind_dn: bindDN,
                group_filter: groupFilter,
                use_ssl: useSSL
            })
        });

        if (response.ok) {
            showNotification('AD configuration saved to database successfully', 'success');
            // Load existing mappings
            loadADMappings();
        } else {
            const error = await response.json();
            showNotification('Failed to save AD configuration: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error saving AD configuration:', error);
        showNotification('Error saving AD configuration: ' + error.message, 'error');
    }
}

// Load AD Configuration from database
async function loadADConfig() {
    // ALWAYS try to get token from localStorage first, then from auth module
    authToken = localStorage.getItem('access_token');
    if (!authToken && window.authModule && window.authModule.isAuthenticated()) {
        authToken = window.authModule.getAccessToken();
    }

    try {
        const headers = {};

        // Only add auth token if we have one
        if (authToken) {
            headers['Authorization'] = `Bearer ${authToken}`;
        }

        const response = await fetch('/admin/ad/config', {
            headers: headers
        });

        if (response.ok) {
            const data = await response.json();
            const config = data.config;

            if (config && Object.keys(config).length > 0) {
                document.getElementById('adConfigServer').value = config.server || '';
                document.getElementById('adConfigPort').value = config.port || 389;
                document.getElementById('adConfigBaseDN').value = config.base_dn || '';
                document.getElementById('adConfigBindDN').value = config.bind_dn || '';
                document.getElementById('adConfigGroupFilter').value = config.group_filter || '(objectClass=organizationalUnit)';
                document.getElementById('adConfigUseSSL').checked = config.use_ssl || false;

                // Update adConfigData (password needs to be re-entered)
                adConfigData = { ...config, bind_password: '' };

                console.log('AD configuration loaded from database');
            }
        } else if (response.status !== 403 && response.status !== 401) {
            console.error('Failed to load AD configuration');
        }
    } catch (error) {
        console.error('Error loading AD configuration:', error);
    }
}

// Query AD Groups from saved configuration (Deprecated - now using user search)
async function queryADGroupsFromConfig() {
    // Get current form values
    const server = document.getElementById('adConfigServer').value.trim();
    const port = parseInt(document.getElementById('adConfigPort').value);
    const baseDN = document.getElementById('adConfigBaseDN').value.trim();
    const bindDN = document.getElementById('adConfigBindDN').value.trim();
    const bindPassword = document.getElementById('adConfigPassword').value;
    const groupFilter = document.getElementById('adConfigGroupFilter').value.trim();
    const useSSL = document.getElementById('adConfigUseSSL').checked;

    if (!server || !baseDN || !bindDN || !bindPassword) {
        showNotification('Please fill in and save AD configuration first', 'error');
        return;
    }

    // Update adConfigData
    adConfigData = {
        server: server,
        port: port,
        base_dn: baseDN,
        bind_dn: bindDN,
        bind_password: bindPassword,
        group_filter: groupFilter,
        use_ssl: useSSL
    };

    // Show modal for user search (new simplified flow)
    showADSyncModal();
    // Auto-populate user filter and show instructions
    document.getElementById('adUserFilter').value = '(objectClass=person)';
    document.getElementById('adUsersResult').innerHTML = `
        <div class="alert alert-info">
            <i class="fas fa-info-circle"></i>
            <strong>Search for AD Users</strong>
            <p>Click "Search Users" to find users in your Active Directory. Common filters:</p>
            <ul style="margin: 10px 0 0 20px;">
                <li><code>(objectClass=person)</code> - All person objects</li>
                <li><code>(objectClass=user)</code> - All user objects (Active Directory)</li>
                <li><code>(&(objectClass=person)(cn=John*))</code> - Users starting with "John"</li>
                <li><code>(&(objectClass=person)(mail=*@example.com))</code> - Users with specific email domain</li>
            </ul>
        </div>
    `;
}

// Load AD Group Mappings
async function loadADMappings() {
    const container = document.getElementById('adMappingsContainer');

    // Check if user is authenticated
    if (!authToken) {
        container.innerHTML = '<p class="text-muted">Sign in to view AD group mappings.</p>';
        return;
    }

    try {
        const response = await fetch('/admin/ad/group-mappings', {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            displayADMappings(data.mappings);
        } else if (response.status === 403 || response.status === 401) {
            container.innerHTML = '<p class="text-muted">You don\'t have permission to view AD mappings.</p>';
        } else {
            container.innerHTML = '<p class="text-muted">No AD group mappings configured.</p>';
        }
    } catch (error) {
        console.error('Error loading AD mappings:', error);
        container.innerHTML = '<p class="text-muted">No AD group mappings configured. Query groups and map them to roles.</p>';
    }
}

// Display AD Mappings
async function displayADMappings(mappings) {
    const container = document.getElementById('adMappingsContainer');

    if (!mappings || mappings.length === 0) {
        container.innerHTML = '<p class="text-muted">No AD group mappings configured. Query groups and map them to roles.</p>';
        return;
    }

    // Load roles to display role names
    let rolesMap = {};
    try {
        const response = await fetch('/admin/roles', {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            rolesMap = Object.fromEntries(data.roles.map(r => [r.role_id, r.role_name]));
        }
    } catch (error) {
        console.error('Error loading roles:', error);
    }

    container.innerHTML = `
        <table class="admin-table">
            <thead>
                <tr>
                    <th>AD Group</th>
                    <th>Mapped Role</th>
                    <th>Auto-Sync</th>
                    <th>Last Sync</th>
                    <th>Synced Users</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                ${mappings.map(m => `
                    <tr>
                        <td><code style="font-size: 11px;">${m.group_dn}</code></td>
                        <td><span class="badge">${rolesMap[m.role_id] || m.role_id}</span></td>
                        <td>
                            <span class="badge ${m.auto_sync ? 'badge-success' : 'badge-secondary'}">
                                ${m.auto_sync ? 'Enabled' : 'Disabled'}
                            </span>
                        </td>
                        <td>${m.last_sync ? new Date(m.last_sync).toLocaleString() : 'Never'}</td>
                        <td>${m.synced_users || 0} users</td>
                        <td>
                            <button class="btn btn-sm btn-primary" onclick="syncADMapping('${m.mapping_id}', '${m.group_dn}', '${m.role_id}')" title="Manually sync users from AD group">
                                <i class="fas fa-sync"></i> Sync Now
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="deleteADMapping('${m.mapping_id}')">
                                <i class="fas fa-trash"></i> Remove
                            </button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

// Sync AD Group Mapping Manually
async function syncADMapping(mappingId, groupDN, roleId) {
    // Check if we have AD configuration
    if (!adConfigData.server || !adConfigData.bind_dn) {
        showNotification('AD configuration incomplete. Please configure AD connection in the configuration section.', 'error');
        return;
    }

    // Prompt for password if not in memory
    let bindPassword = adConfigData.bind_password;
    if (!bindPassword) {
        bindPassword = prompt('Enter AD bind password to sync:');
        if (!bindPassword) {
            return; // User cancelled
        }
    }

    if (!confirm(`Sync users from this AD group?\n\nThis will:\n- Fetch all members from the AD group\n- Create user accounts if they don't exist\n- Assign the mapped role to all group members`)) {
        return;
    }

    try {
        // First, get group members
        showNotification('Fetching AD group members...', 'info');

        const membersResponse = await fetch('/admin/ad/query-group-members', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                server: adConfigData.server,
                port: adConfigData.port,
                bind_dn: adConfigData.bind_dn,
                bind_password: bindPassword,
                group_dn: groupDN,
                use_ssl: adConfigData.use_ssl || false
            })
        });

        if (!membersResponse.ok) {
            const error = await membersResponse.json();
            showNotification('Failed to fetch AD group members: ' + (error.detail || 'Unknown error'), 'error');
            return;
        }

        const membersData = await membersResponse.json();
        const members = membersData.members;

        if (members.length === 0) {
            showNotification('No members found in AD group', 'warning');
            return;
        }

        showNotification(`Found ${members.length} members. Creating/updating users...`, 'info');

        // Create/update users and assign roles
        let syncedCount = 0;
        let errorCount = 0;

        for (const member of members) {
            try {
                // Create or get user
                const userResponse = await fetch('/admin/users', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${authToken}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        email: member.email,
                        name: member.display_name,
                        provider: 'active_directory',
                        roles: [roleId]
                    })
                });

                if (userResponse.ok || userResponse.status === 409) {
                    // User created or already exists
                    // Try to assign role (in case user existed but didn't have this role)
                    if (userResponse.ok) {
                        const userData = await userResponse.json();
                        // Role already assigned during creation
                        syncedCount++;
                    } else {
                        // User exists, need to ensure role is assigned
                        // Get user ID first
                        const usersListResponse = await fetch('/admin/users', {
                            headers: {
                                'Authorization': `Bearer ${authToken}`
                            }
                        });

                        if (usersListResponse.ok) {
                            const usersData = await usersListResponse.json();
                            const existingUser = usersData.users.find(u => u.email === member.email);

                            if (existingUser) {
                                // Check if role is already assigned
                                if (!existingUser.role_ids || !existingUser.role_ids.includes(roleId)) {
                                    // Assign role
                                    const roleResponse = await fetch(`/admin/users/${existingUser.user_id}/roles`, {
                                        method: 'POST',
                                        headers: {
                                            'Authorization': `Bearer ${authToken}`,
                                            'Content-Type': 'application/json'
                                        },
                                        body: JSON.stringify({ role_id: roleId })
                                    });

                                    if (roleResponse.ok) {
                                        syncedCount++;
                                    } else {
                                        errorCount++;
                                    }
                                } else {
                                    syncedCount++; // Already has role
                                }
                            }
                        }
                    }
                } else {
                    errorCount++;
                }
            } catch (error) {
                console.error(`Error syncing user ${member.email}:`, error);
                errorCount++;
            }
        }

        if (errorCount > 0) {
            showNotification(`Sync completed with errors. Synced: ${syncedCount}, Failed: ${errorCount}`, 'warning');
        } else {
            showNotification(`Successfully synced ${syncedCount} users from AD group`, 'success');
        }

        // Refresh UI
        // Ensure we stay on users tab
        if (typeof switchTab === 'function') {
            switchTab('users');
        }

        setTimeout(() => {
            loadUsers();
            loadADMappings();
        }, 100);

    } catch (error) {
        console.error('Error syncing AD mapping:', error);
        showNotification('Error syncing AD group: ' + error.message, 'error');
    }
}

// Delete AD Mapping
async function deleteADMapping(mappingId) {
    if (!confirm('Are you sure you want to remove this AD group mapping?')) {
        return;
    }

    try {
        const response = await fetch(`/admin/ad/group-mappings/${mappingId}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            showNotification('AD mapping removed successfully', 'success');
            loadADMappings();
        } else {
            showNotification('Failed to remove mapping', 'error');
        }
    } catch (error) {
        console.error('Error removing mapping:', error);
        showNotification('Error removing mapping: ' + error.message, 'error');
    }
}

// Show AD Sync Modal
function showADSyncModal() {
    // New simplified modal - just clear previous results
    // AD configuration is already stored in adConfigData
    const resultsDiv = document.getElementById('adUsersResult');
    if (resultsDiv) {
        resultsDiv.innerHTML = '';
    }

    // Set default user filter if field exists
    const userFilterInput = document.getElementById('adUserFilter');
    if (userFilterInput && !userFilterInput.value) {
        userFilterInput.value = '(objectClass=person)';
    }

    showModal('adSyncModal');
}

// Query Active Directory Groups
async function queryADGroups() {
    const adServer = document.getElementById('adServer').value.trim();
    const adPort = document.getElementById('adPort').value;
    const bindDN = document.getElementById('adBindDN').value.trim();
    const bindPassword = document.getElementById('adPassword').value;
    const baseDN = document.getElementById('adBaseDN').value.trim();
    const groupFilter = document.getElementById('adGroupFilter').value.trim();

    // Validation
    if (!adServer || !bindDN || !bindPassword || !baseDN) {
        showNotification('Please fill in all required AD connection fields', 'error');
        return;
    }

    const resultDiv = document.getElementById('adGroupsResult');
    resultDiv.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Querying Active Directory...</div>';

    try {
        const response = await fetch('/admin/ad/query-groups', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                server: adServer,
                port: parseInt(adPort),
                bind_dn: bindDN,
                bind_password: bindPassword,
                base_dn: baseDN,
                group_filter: groupFilter
            })
        });

        if (response.ok) {
            const data = await response.json();
            displayADGroups(data.groups);

            // Store fetched groups locally
            if (typeof storeFetchedADData === 'function') {
                storeFetchedADData(data.groups, []);
            }
        } else {
            const error = await response.json();
            resultDiv.innerHTML = `
                <div class="alert alert-error">
                    <i class="fas fa-exclamation-circle"></i>
                    <strong>AD Query Failed</strong>
                    <p>${error.detail || 'Failed to connect to Active Directory'}</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error querying AD:', error);
        resultDiv.innerHTML = `
            <div class="alert alert-error">
                <i class="fas fa-exclamation-circle"></i>
                <strong>Connection Error</strong>
                <p>${error.message}</p>
            </div>
        `;
    }
}

// Display AD Groups with mapping options
function displayADGroups(groups) {
    const resultDiv = document.getElementById('adGroupsResult');

    if (groups.length === 0) {
        resultDiv.innerHTML = `
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i>
                <strong>No groups found</strong>
                <p>No groups matched the search criteria. Try adjusting your filter.</p>
            </div>
        `;
        return;
    }

    resultDiv.innerHTML = `
        <div class="alert alert-success">
            <i class="fas fa-check-circle"></i>
            <strong>Found ${groups.length} groups</strong>
            <p>Click "Add Users" to import users from these groups with the "Standard User" role.</p>
        </div>
        <table class="admin-table" style="margin-top: 15px;">
            <thead>
                <tr>
                    <th>Group Name</th>
                    <th>Distinguished Name</th>
                    <th>Members</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                ${groups.map(group => `
                    <tr>
                        <td><strong>${group.name}</strong></td>
                        <td><code style="font-size: 11px;">${group.dn}</code></td>
                        <td>${group.member_count || 0} users</td>
                        <td>
                            <button class="btn btn-sm btn-success"
                                    data-action="add-users"
                                    data-group-dn="${group.dn.replace(/"/g, '&quot;')}"
                                    data-group-name="${group.name.replace(/"/g, '&quot;')}">
                                <i class="fas fa-user-plus"></i> Add Users
                            </button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;

    // Add event listeners to Add Users buttons
    resultDiv.querySelectorAll('button[data-action="add-users"]').forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            const groupDN = this.getAttribute('data-group-dn');
            const groupName = this.getAttribute('data-group-name');
            addUsersFromADGroup(groupDN, groupName);
        });
    });
}

// Query AD Users (Direct User Search)
async function queryADUsers() {
    // Check if we have AD configuration
    if (!adConfigData.server || !adConfigData.bind_dn || !adConfigData.bind_password) {
        showNotification('AD configuration incomplete. Please configure and save AD connection first.', 'error');
        return;
    }

    const userFilter = document.getElementById('adUserFilter').value.trim();

    if (!userFilter) {
        showNotification('Please enter a user search filter', 'error');
        return;
    }

    const resultDiv = document.getElementById('adUsersResult');
    resultDiv.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Querying Active Directory...</div>';

    try {
        const response = await fetch('/admin/ad/query-users', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                server: adConfigData.server,
                port: adConfigData.port,
                bind_dn: adConfigData.bind_dn,
                bind_password: adConfigData.bind_password,
                base_dn: adConfigData.base_dn,
                user_filter: userFilter,
                use_ssl: adConfigData.use_ssl || false
            })
        });

        if (response.ok) {
            const data = await response.json();
            displayADUsers(data.users);
        } else {
            const error = await response.json();
            resultDiv.innerHTML = `
                <div class="alert alert-error">
                    <i class="fas fa-exclamation-circle"></i>
                    <strong>AD Query Failed</strong>
                    <p>${error.detail || 'Failed to query users from Active Directory'}</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error querying AD users:', error);
        resultDiv.innerHTML = `
            <div class="alert alert-error">
                <i class="fas fa-exclamation-circle"></i>
                <strong>Connection Error</strong>
                <p>${error.message}</p>
            </div>
        `;
    }
}

// Display AD Users with checkboxes for selection
function displayADUsers(users) {
    const resultDiv = document.getElementById('adUsersResult');

    if (users.length === 0) {
        resultDiv.innerHTML = `
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i>
                <strong>No users found</strong>
                <p>No users matched the search criteria. Try adjusting your filter.</p>
            </div>
        `;
        return;
    }

    resultDiv.innerHTML = `
        <div class="alert alert-success">
            <i class="fas fa-check-circle"></i>
            <strong>Found ${users.length} users</strong>
            <p>Select users to add them to the system with the "Standard User" role.</p>
        </div>
        <div style="margin-bottom: 15px;">
            <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                <input type="checkbox" id="selectAllUsers" onchange="toggleSelectAllUsers()">
                <strong>Select All Users</strong>
            </label>
        </div>
        <table class="admin-table" style="margin-top: 15px;">
            <thead>
                <tr>
                    <th style="width: 40px;">
                        <input type="checkbox" style="display: none;">
                    </th>
                    <th>Username</th>
                    <th>Display Name</th>
                    <th>Email</th>
                </tr>
            </thead>
            <tbody>
                ${users.map((user, index) => `
                    <tr>
                        <td>
                            <input type="checkbox" class="user-checkbox" data-user-index="${index}">
                        </td>
                        <td><strong>${user.username}</strong></td>
                        <td>${user.display_name}</td>
                        <td>${user.email}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
        <div style="margin-top: 20px;">
            <button type="button" class="btn btn-success" onclick="addSelectedADUsers()">
                <i class="fas fa-user-plus"></i> Add Selected Users
            </button>
        </div>
    `;

    // Store users data globally for later access
    window.fetchedADUsers = users;
}

// Toggle select all users
function toggleSelectAllUsers() {
    const selectAll = document.getElementById('selectAllUsers');
    const checkboxes = document.querySelectorAll('.user-checkbox');

    checkboxes.forEach(checkbox => {
        checkbox.checked = selectAll.checked;
    });
}

// Add selected AD users with Standard User role
async function addSelectedADUsers() {
    const checkboxes = document.querySelectorAll('.user-checkbox:checked');

    if (checkboxes.length === 0) {
        showNotification('Please select at least one user to add', 'warning');
        return;
    }

    // Get the 'user' role (Standard User)
    try {
        showNotification('Loading roles...', 'info');
        const rolesResponse = await fetch('/admin/roles', {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (!rolesResponse.ok) {
            showNotification('Failed to load roles', 'error');
            return;
        }

        const rolesData = await rolesResponse.json();
        const standardUserRole = rolesData.roles.find(r => r.role_id === 'user');

        if (!standardUserRole) {
            showNotification('Standard User role not found. Please contact administrator.', 'error');
            return;
        }

        // Get selected users
        const selectedUsers = [];
        checkboxes.forEach(checkbox => {
            const index = parseInt(checkbox.getAttribute('data-user-index'));
            if (window.fetchedADUsers && window.fetchedADUsers[index]) {
                selectedUsers.push(window.fetchedADUsers[index]);
            }
        });

        if (selectedUsers.length === 0) {
            showNotification('No valid users selected', 'error');
            return;
        }

        showNotification(`Adding ${selectedUsers.length} users from Active Directory...`, 'info');

        let successCount = 0;
        let errorCount = 0;
        const errors = [];

        // Add each user
        for (const user of selectedUsers) {
            try {
                const userResponse = await fetch('/admin/users', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${authToken}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        email: user.email,
                        name: user.display_name,
                        provider: 'active_directory',
                        roles: ['user']
                    })
                });

                if (userResponse.ok || userResponse.status === 409) {
                    successCount++;
                } else {
                    errorCount++;
                    errors.push(`${user.username}: ${userResponse.statusText}`);
                }
            } catch (error) {
                console.error(`Error adding user ${user.username}:`, error);
                errorCount++;
                errors.push(`${user.username}: ${error.message}`);
            }
        }

        // Show results
        if (errorCount === 0) {
            showNotification(`Successfully added ${successCount} users with Standard User role!`, 'success');
        } else {
            showNotification(`Added ${successCount} users, ${errorCount} failed. Check console for details.`, 'warning');
            if (errors.length > 0) {
                console.error('Failed users:', errors);
            }
        }

        // Close modal first
        closeModal('adSyncModal');

        // Ensure we stay on users tab
        if (typeof switchTab === 'function') {
            switchTab('users');
        }

        // Refresh users list after a short delay to ensure tab is active
        setTimeout(() => {
            loadUsers();
        }, 100);

    } catch (error) {
        console.error('Error adding AD users:', error);
        showNotification('Error adding users: ' + error.message, 'error');
    }
}

// Add Users from AD Group (Simplified Flow)
async function addUsersFromADGroup(groupDN, groupName) {
    // Check if we have AD configuration
    if (!adConfigData.server || !adConfigData.bind_dn || !adConfigData.bind_password) {
        showNotification('AD configuration incomplete. Please configure and save AD connection first.', 'error');
        return;
    }

    // Confirm action
    if (!confirm(`Import all users from "${groupName}"?\n\nUsers will be added with the "Standard User" role.\nYou can change their roles later from User Management.`)) {
        return;
    }

    try {
        // Step 1: Get standard_user role ID
        showNotification('Loading roles...', 'info');
        const rolesResponse = await fetch('/admin/roles', {
            headers: { 'Authorization': `Bearer ${authToken}` }
        });

        if (!rolesResponse.ok) {
            showNotification('Failed to load roles', 'error');
            return;
        }

        const rolesData = await rolesResponse.json();
        const standardUserRole = rolesData.roles.find(r => r.role_id === 'user');

        if (!standardUserRole) {
            showNotification('Standard User role not found. Please contact administrator.', 'error');
            return;
        }

        // Step 2: Fetch group members from AD
        showNotification('Fetching users from AD group...', 'info');
        const membersResponse = await fetch('/admin/ad/query-group-members', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                server: adConfigData.server,
                port: adConfigData.port,
                bind_dn: adConfigData.bind_dn,
                bind_password: adConfigData.bind_password,
                group_dn: groupDN,
                use_ssl: adConfigData.use_ssl || false
            })
        });

        if (!membersResponse.ok) {
            const error = await membersResponse.json();
            showNotification('Failed to fetch AD group members: ' + (error.detail || 'Unknown error'), 'error');
            return;
        }

        const membersData = await membersResponse.json();
        const members = membersData.members;

        if (members.length === 0) {
            showNotification('No members found in this AD group', 'warning');
            return;
        }

        // Step 3: Add users
        showNotification(`Adding ${members.length} users...`, 'info');
        let addedCount = 0;
        let existingCount = 0;
        let errorCount = 0;

        for (const member of members) {
            try {
                const userResponse = await fetch('/admin/users', {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${authToken}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        email: member.email,
                        name: member.display_name,
                        provider: 'active_directory',
                        roles: ['user']
                    })
                });

                if (userResponse.ok) {
                    addedCount++;
                } else if (userResponse.status === 409) {
                    // User already exists
                    existingCount++;
                } else {
                    errorCount++;
                }
            } catch (error) {
                console.error(`Error adding user ${member.email}:`, error);
                errorCount++;
            }
        }

        // Step 4: Show results
        let message = `Completed!\n`;
        if (addedCount > 0) message += `✓ Added: ${addedCount} users\n`;
        if (existingCount > 0) message += `• Already existed: ${existingCount} users\n`;
        if (errorCount > 0) message += `✗ Failed: ${errorCount} users`;

        if (errorCount > 0) {
            showNotification(message, 'warning');
        } else {
            showNotification(message, 'success');
        }

        // Close modal and refresh users list
        closeModal('adSyncModal');

        // Ensure we stay on users tab
        if (typeof switchTab === 'function') {
            switchTab('users');
        }

        // Refresh users list after a short delay
        setTimeout(() => {
            loadUsers();
        }, 100);

    } catch (error) {
        console.error('Error adding users from AD group:', error);
        showNotification('Error: ' + error.message, 'error');
    }
}

// Show Group to Role Mapping Modal
async function showGroupMappingModal(groupDN, groupName) {
    // Store group info in the modal
    document.getElementById('selectedGroupDN').value = groupDN;
    document.getElementById('selectedGroupName').textContent = groupName;

    // Load available roles
    try {
        const response = await fetch('/admin/roles', {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            const roleSelect = document.getElementById('mappingRoleId');

            roleSelect.innerHTML = '<option value="">Select a role...</option>' +
                data.roles.map(role => `
                    <option value="${role.role_id}">${role.role_name} - ${role.description}</option>
                `).join('');
        }
    } catch (error) {
        console.error('Error loading roles:', error);
    }

    // Preview group members
    await previewGroupMembers(groupDN);

    closeModal('adSyncModal');
    showModal('groupMappingModal');
}

// Preview Group Members before syncing
async function previewGroupMembers(groupDN) {
    const previewContainer = document.getElementById('groupMembersPreview');
    if (!previewContainer) {
        // Create preview container if it doesn't exist
        const modalBody = document.querySelector('#groupMappingModal .modal-body');
        if (modalBody) {
            const previewDiv = document.createElement('div');
            previewDiv.id = 'groupMembersPreview';
            previewDiv.style.marginTop = '15px';
            modalBody.appendChild(previewDiv);
        }
        return;
    }

    previewContainer.innerHTML = '<div class="loading"><i class="fas fa-spinner fa-spin"></i> Loading group members...</div>';

    try {
        const response = await fetch('/admin/ad/query-group-members', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                server: adConfigData.server,
                port: adConfigData.port,
                bind_dn: adConfigData.bind_dn,
                bind_password: adConfigData.bind_password,
                group_dn: groupDN,
                use_ssl: adConfigData.use_ssl || false
            })
        });

        if (response.ok) {
            const data = await response.json();
            const members = data.members;

            if (members.length === 0) {
                previewContainer.innerHTML = `
                    <div class="alert alert-info">
                        <i class="fas fa-info-circle"></i>
                        <strong>No Members Found</strong>
                        <p>This group has no members.</p>
                    </div>
                `;
            } else {
                previewContainer.innerHTML = `
                    <div class="alert alert-success">
                        <i class="fas fa-users"></i>
                        <strong>Found ${members.length} user(s) in this group</strong>
                        <p>These users will be added to the system and assigned the selected role:</p>
                    </div>
                    <div style="max-height: 200px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; border-radius: 4px; background: #f9f9f9;">
                        ${members.map(m => `
                            <div style="padding: 5px 0; border-bottom: 1px solid #eee;">
                                <strong>${m.display_name}</strong><br>
                                <small style="color: #666;">
                                    Email: ${m.email}<br>
                                    Username: ${m.username}
                                </small>
                            </div>
                        `).join('')}
                    </div>
                `;
            }
        } else {
            previewContainer.innerHTML = `
                <div class="alert alert-warning">
                    <i class="fas fa-exclamation-triangle"></i>
                    <strong>Could not load group members</strong>
                    <p>Unable to fetch members for preview. You can still create the mapping.</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading group members:', error);
        previewContainer.innerHTML = `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle"></i>
                <strong>Could not load group members</strong>
                <p>Unable to fetch members for preview. You can still create the mapping.</p>
            </div>
        `;
    }
}

// Save Group to Role Mapping and Sync Users
async function saveGroupMapping() {
    const groupDN = document.getElementById('selectedGroupDN').value;
    const roleId = document.getElementById('mappingRoleId').value;
    const autoSync = document.getElementById('autoSyncEnabled').checked;

    if (!roleId) {
        showNotification('Please select a role', 'error');
        return;
    }

    // Check if we have AD config to sync users
    if (!adConfigData.server || !adConfigData.bind_dn || !adConfigData.bind_password) {
        showNotification('AD configuration incomplete. Please configure AD connection first.', 'error');
        return;
    }

    try {
        const response = await fetch('/admin/ad/group-mappings', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                group_dn: groupDN,
                role_id: roleId,
                auto_sync: autoSync,
                ad_config: {
                    server: adConfigData.server,
                    port: adConfigData.port,
                    bind_dn: adConfigData.bind_dn,
                    bind_password: adConfigData.bind_password,
                    use_ssl: adConfigData.use_ssl || false
                }
            })
        });

        if (response.ok) {
            const data = await response.json();
            showNotification(`Group mapping saved! Synced ${data.synced_users} users.`, 'success');
            closeModal('groupMappingModal');
            loadUsers(); // Refresh users list
            loadADMappings(); // Refresh AD mappings
        } else {
            const error = await response.json();
            showNotification('Failed to save mapping: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error saving group mapping:', error);
        showNotification('Error saving mapping: ' + error.message, 'error');
    }
}

// =====================================================================
// ADMIN TOKEN GENERATION
// =====================================================================

/**
 * Show Admin Generated Token Modal
 * Generates and displays a JWT token for a specific user (admin only)
 */
async function showAdminGeneratedTokenModal(userId, userEmail, userName) {
    try {
        // Show loading state
        showNotification('Generating JWT token...', 'info');

        // Call the admin endpoint to generate token
        const response = await fetch(`/admin/users/${userId}/token`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${authToken}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            const error = await response.json();
            showNotification('Failed to generate token: ' + (error.detail || 'Unknown error'), 'error');
            return;
        }

        const data = await response.json();
        const token = data.access_token;
        const user = data.user;

        // Get ngrok URL from the log or use default
        const ngrokUrl = 'https://ce666863018f.ngrok-free.app';

        // Use the same JWT token modal from auth.js
        const modal = document.getElementById('jwtTokenModal');
        if (!modal) {
            showNotification('JWT Token modal not found', 'error');
            return;
        }

        // Update modal title to indicate admin generation
        const modalTitle = modal.querySelector('.modal-title');
        if (modalTitle) {
            modalTitle.innerHTML = `<i class="fas fa-key"></i> JWT Token for ${userEmail}`;
        }

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

        showNotification(`JWT token generated for ${userEmail}`, 'success');
    } catch (error) {
        console.error('Error generating admin token:', error);
        showNotification('Error generating token: ' + error.message, 'error');
    }
}

// Export to global scope
window.showAdminGeneratedTokenModal = showAdminGeneratedTokenModal;
