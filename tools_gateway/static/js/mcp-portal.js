// MCP Portal JavaScript - VERSION 9 WITH SQUARE EXPANDABLE CAPABILITY CARDS
console.log('🚀 MCP Portal JS v9 loaded - Square expandable capability cards!');
// Dynamic URL configuration for both local development and Kubernetes deployment
const MANAGE_URL = (() => {
    const pathname = window.location.pathname;
    const hostname = window.location.hostname;
    const protocol = window.location.protocol;

    console.log('MCP Portal URL Detection:', { pathname, hostname, protocol });

    // Check if we're running via ngrok (HTTPS tunnel)
    if (hostname.includes('ngrok') || protocol === 'https:') {
        console.log('Detected ngrok/HTTPS environment');
        return '/manage';
    }

    // Detect if we're running in Kubernetes by checking the URL path prefix
    if (pathname.startsWith('/toolbox/')) {
        console.log('Detected Kubernetes deployment with /toolbox/ prefix');
        return '/toolbox/manage';
    }

    // Local development (localhost, 127.0.0.1, 0.0.0.0, or any local IP) or direct access
    if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '0.0.0.0' ||
        hostname.startsWith('192.168.') || hostname.startsWith('10.') || hostname.startsWith('172.') ||
        pathname === '/') {
        console.log('Detected local development environment');
        return '/manage';
    }

    // Fallback - try relative path
    console.log('Using fallback relative path');
    return 'manage';
})();

console.log('MCP Portal using MANAGE_URL:', MANAGE_URL);

// Dynamic MCP endpoint URL configuration
const MCP_URL = (() => {
    const pathname = window.location.pathname;
    const hostname = window.location.hostname;
    const protocol = window.location.protocol;

    console.log('MCP URL Detection:', { pathname, hostname, protocol });

    // Check if we're running via ngrok (HTTPS tunnel)
    if (hostname.includes('ngrok') || protocol === 'https:') {
        console.log('Detected ngrok/HTTPS environment for MCP');
        return '/mcp';
    }

    // Detect if we're running in Kubernetes by checking the URL path prefix
    if (pathname.startsWith('/toolbox/')) {
        console.log('Detected Kubernetes deployment with /toolbox/ prefix for MCP');
        return '/toolbox/mcp';
    }

    // Local development (localhost, 127.0.0.1, 0.0.0.0, or any local IP) or direct access
    if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '0.0.0.0' ||
        hostname.startsWith('192.168.') || hostname.startsWith('10.') || hostname.startsWith('172.') ||
        pathname === '/') {
        console.log('Detected local development environment for MCP');
        return '/mcp';
    }

    // Fallback - try relative path
    console.log('Using fallback relative path for MCP');
    return 'mcp';
})();

console.log('MCP Portal using MCP_URL:', MCP_URL);

let currentServers = {};
let discoveredTools = [];
let currentCapabilities = {};
let currentTab = 'servers';
let availableOAuthProviders = [];  // Store available OAuth providers
let capabilitiesPage = 1;
const CAPABILITIES_PER_PAGE = 6; // Show 6 cards at a time

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    console.log('🔧 DOM loaded, initializing...');
    console.log('🔧 Current location:', window.location.href);
    console.log('🔧 Environment details:', {
        hostname: window.location.hostname,
        protocol: window.location.protocol,
        pathname: window.location.pathname,
        isNgrok: window.location.hostname.includes('ngrok'),
        isHTTPS: window.location.protocol === 'https:'
    });

    initializeTabNavigation();

    loadServers();
});

// Tab Navigation
function initializeTabNavigation() {
    const navLinks = document.querySelectorAll('.nav-link');
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const tabName = this.getAttribute('data-tab');
            switchTab(tabName);
        });
    });
}

function switchTab(tabName) {
    // Update navigation
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
    });
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

    // Update content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(tabName).classList.add('active');

    // Update header title
    const titles = {
        'servers': 'MCP Servers',
        'tools': 'Tool Discovery',
        'capabilities': 'Tool Capabilities',
        'testing': 'Tool Testing',
        'configuration': 'Configuration',
        'oauth': 'OAuth Providers',
        'users': 'Users & Roles',
        'audit': 'Audit Logs'
    };
    document.querySelector('.header-title').textContent = titles[tabName] || 'Dashboard';

    // Show/hide header actions based on tab
    const headerActions = document.querySelector('.header-actions');
    if (tabName === 'servers') {
        headerActions.style.display = 'flex';
    } else {
        headerActions.style.display = 'none';
    }

    currentTab = tabName;

    // Load data for specific tabs
    if (tabName === 'tools' && discoveredTools.length === 0) {
        discoverTools();
    } else if (tabName === 'capabilities' && Object.keys(currentCapabilities).length === 0) {
        loadCapabilities();
    } else if (tabName === 'configuration') {
        loadAllConfig();
        loadServerHealth();
    }
}

// Server Management
async function loadServers() {
    console.log('🔧 loadServers() called, using MANAGE_URL:', MANAGE_URL);

    try {
        const response = await fetch(MANAGE_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "server.list",
                id: `load-servers-${Date.now()}`
            })
        });

        console.log('🔧 loadServers response status:', response.status);
        console.log('🔧 loadServers response headers:', Object.fromEntries(response.headers.entries()));

        const data = await response.json();
        if (data.result && data.result.server_cards) {
            currentServers = data.result.server_cards;
            displayServers(currentServers);
        } else {
            // No servers found, show empty state
            currentServers = {};
            displayServers(currentServers);
        }
    } catch (error) {
        console.error('Failed to load servers:', error);
        showAlert('Failed to load servers: ' + error.message, 'error');
    }
}

function displayServers(servers) {
    const tableBody = document.getElementById('serversTableBody');
    
    if (Object.keys(servers).length === 0) {
        tableBody.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-server"></i>
                <h3>No MCP Servers</h3>
                <p>Add your first MCP server to get started</p>
                <button class="btn btn-primary" onclick="showAddServerModal()">
                    <i class="fas fa-plus"></i>
                    Add Server
                </button>
            </div>
        `;
        return;
    }

    let html = '';
    for (const [serverId, server] of Object.entries(servers)) {
        const status = getServerStatus(server);
        const statusClass = status.toLowerCase();
        
        html += `
            <div class="server-row">
                <div class="col-checkbox">
                    <input type="checkbox" class="server-checkbox" data-server-id="${serverId}">
                </div>
                <div class="col-status">
                    <span class="status-badge status-${statusClass}">${status}</span>
                </div>
                <div class="col-name">
                    <div class="server-name">${server.name}</div>
                    <div class="server-id">${serverId}</div>
                </div>
                <div class="col-endpoint">
                    <div class="endpoint-url">${server.url}</div>
                </div>
                <div class="col-capabilities">
                    <span class="capabilities-count">${server.tool_count || 0}</span>
                </div>
                <div class="col-version">
                    <span class="version-tag">${server.metadata?.protocol_version || 'N/A'}</span>
                </div>
                <div class="col-actions">
                    <div class="action-buttons">
                        <button class="action-btn" onclick="testServer('${serverId}')" title="Test Connection">
                            <i class="fas fa-plug"></i>
                        </button>
                        <button class="action-btn" onclick="viewServerDetails('${serverId}')" title="View Details">
                            <i class="fas fa-info-circle"></i>
                        </button>
                        <button class="action-btn danger" onclick="deleteServer('${serverId}')" title="Delete Server">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    tableBody.innerHTML = html;
}

function getServerStatus(server) {
    // Use actual health status from backend if available
    if (server.status) {
        return server.status.charAt(0).toUpperCase() + server.status.slice(1);
    }

    // Fallback to time-based status if health status not available
    const now = new Date();
    const updated = new Date(server.updated_at);
    const diffHours = (now - updated) / (1000 * 60 * 60);

    if (diffHours < 1) return 'Online';
    if (diffHours < 24) return 'Pending';
    return 'Offline';
}

// Add Server Modal
function showAddServerModal() {
    document.getElementById('addServerModal').style.display = 'block';
}

function closeAddServerModal() {
    document.getElementById('addServerModal').style.display = 'none';
    document.getElementById('modalServerUrl').value = '';
    document.getElementById('modalServerDescription').value = '';
}

async function addServer() {
    const serverUrl = document.getElementById('modalServerUrl').value.trim();
    const description = document.getElementById('modalServerDescription').value.trim();

    if (!serverUrl) {
        showAlert('Please enter a server URL', 'warning');
        return;
    }

    try {
        const response = await fetch(MANAGE_URL, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "server.add",
                params: {
                    server_url: serverUrl,
                    description: description
                },
                id: `add-server-${Date.now()}`
            })
        });

        const data = await response.json();
        if (data.result && data.result.success) {
            showAlert('Server added successfully!', 'success');
            closeAddServerModal();
            loadServers();
        } else {
            throw new Error(data.error ? data.error.message : 'Failed to add server');
        }
    } catch (error) {
        console.error('Failed to add server:', error);
        showAlert('Failed to add server: ' + error.message, 'error');
    }
}

// Server Actions
async function testServer(serverId) {
    try {
        const response = await fetch(MANAGE_URL, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "server.test",
                params: { server_id: serverId },
                id: `test-server-${Date.now()}`
            })
        });

        const data = await response.json();
        if (data.result) {
            const result = data.result;
            const statusIcon = result.status === 'healthy' ? '✅' : '❌';
            showAlert(`${statusIcon} Server Test: ${result.status} (${Math.round(result.response_time * 1000)}ms)`, 
                     result.status === 'healthy' ? 'success' : 'error');
        } else {
            throw new Error(data.error ? data.error.message : 'Test failed');
        }
    } catch (error) {
        console.error('Server test failed:', error);
        showAlert('Server test failed: ' + error.message, 'error');
    }
}

function viewServerDetails(serverId) {
    const server = currentServers[serverId];
    if (!server) return;

    const detailsHtml = `
        <div class="server-details">
            <div class="form-group">
                <label class="form-label">Server ID</label>
                <input type="text" class="form-control" value="${serverId}" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Name</label>
                <input type="text" class="form-control" value="${server.name}" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">URL</label>
                <input type="text" class="form-control" value="${server.url}" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Description</label>
                <textarea class="form-control" rows="2" readonly>${server.description || 'No description'}</textarea>
            </div>
            <div class="form-group">
                <label class="form-label">Capabilities</label>
                <pre class="test-results">${JSON.stringify(server.capabilities, null, 2)}</pre>
            </div>
            <div class="form-group">
                <label class="form-label">Metadata</label>
                <pre class="test-results">${JSON.stringify(server.metadata, null, 2)}</pre>
            </div>
        </div>
    `;

    document.getElementById('serverDetailsContent').innerHTML = detailsHtml;
    document.getElementById('serverDetailsModal').style.display = 'block';
}

async function deleteServer(serverId) {
    const server = currentServers[serverId];
    if (!server) return;

    if (!confirm(`Are you sure you want to delete server "${server.name}"?`)) return;

    try {
        const response = await fetch(MANAGE_URL, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "server.remove",
                params: { server_id: serverId },
                id: `remove-server-${Date.now()}`
            })
        });

        const data = await response.json();
        if (data.result && data.result.success) {
            showAlert('Server deleted successfully!', 'success');
            loadServers();
        } else {
            throw new Error(data.error ? data.error.message : 'Failed to delete server');
        }
    } catch (error) {
        console.error('Failed to delete server:', error);
        showAlert('Failed to delete server: ' + error.message, 'error');
    }
}

// Tool Discovery
async function discoverTools() {
    console.log('🔧 discoverTools() called');
    console.log('🔧 MANAGE_URL:', MANAGE_URL);
    console.log('🔧 MCP_URL:', MCP_URL);
    console.log('🔧 Current location:', window.location.href);

    const loadingElement = document.getElementById('toolsTableBody');
    loadingElement.innerHTML = '<div class="loading">Discovering tools...</div>';

    try {
        // Step 1: Initialize MCP session
        console.log('🔧 Step 1: Initializing MCP session at:', MCP_URL);
        const initResponse = await fetch(MCP_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream',
                'MCP-Protocol-Version': '2025-06-18'
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "initialize",
                params: {
                    protocolVersion: "2025-06-18",
                    clientInfo: {
                        name: "mcp-portal-ui",
                        version: "1.0.0"
                    }
                },
                id: `init-${Date.now()}`
            })
        });

        console.log('🔧 Init response status:', initResponse.status);
        const initData = await initResponse.json();
        console.log('🔧 Init response data:', initData);
        const sessionId = initResponse.headers.get('Mcp-Session-Id');
        console.log('🔧 Session ID:', sessionId);

        if (!initData.result || !sessionId) {
            throw new Error('Failed to initialize MCP session');
        }

        // Step 2: Send initialized notification
        await fetch(MCP_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream',
                'MCP-Protocol-Version': '2025-06-18',
                'Mcp-Session-Id': sessionId
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "notifications/initialized"
            })
        });

        // Step 3: Get tools list with session
        const response = await fetch(MCP_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream',
                'MCP-Protocol-Version': '2025-06-18',
                'Mcp-Session-Id': sessionId
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "tools/list",
                id: `tools-list-${Date.now()}`
            })
        });

        const data = await response.json();
        if (data.result && data.result.tools) {
            discoveredTools = data.result.tools;
            displayTools(discoveredTools);
            populateToolSelect(discoveredTools);
        } else {
            throw new Error(data.error ? data.error.message : 'Failed to discover tools');
        }
    } catch (error) {
        console.error('Failed to discover tools:', error);
        showAlert('Failed to discover tools: ' + error.message, 'error');
        loadingElement.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-exclamation-triangle"></i>
                <h3>Discovery Failed</h3>
                <p>${error.message}</p>
            </div>
        `;
    }
}

let availableRoles = [];  // Store available roles

async function loadRolesForToolDropdown() {
    console.log('🔐 Loading roles from /admin/roles for tool dropdown...');
    try {
        // Get auth token from localStorage (set by admin-security.js / auth.js)
        const authToken = localStorage.getItem('access_token');
        console.log('🔐 Auth token present:', !!authToken);

        if (!authToken) {
            console.warn('🔐 No auth token available');
            availableRoles = [];
            return;
        }

        const response = await fetch('/admin/roles', {
            headers: {
                'Authorization': `Bearer ${authToken}`
            }
        });
        console.log('🔐 Roles response status:', response.status);
        console.log('🔐 Roles response ok:', response.ok);

        const data = await response.json();
        console.log('🔐 Roles response data:', data);
        console.log('🔐 data.roles exists:', !!data.roles);
        console.log('🔐 data.roles type:', typeof data.roles);
        console.log('🔐 data.roles value:', data.roles);

        if (data.roles) {
            availableRoles = data.roles;
            console.log('🔐 Total roles loaded:', availableRoles.length);
            console.log('🔐 availableRoles after assignment:', availableRoles);
        } else {
            console.warn('🔐 No roles array in response:', data);
            availableRoles = [];
        }
    } catch (error) {
        console.error('🔐 Failed to load roles:', error);
        availableRoles = [];
    }
}

async function displayTools(tools) {
    const tableBody = document.getElementById('toolsTableBody');

    if (tools.length === 0) {
        tableBody.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-tools"></i>
                <h3>No Tools Found</h3>
                <p>No tools were discovered from the registered servers</p>
            </div>
        `;
        return;
    }

    // Load roles if not already loaded
    console.log('🔐 displayTools: availableRoles.length =', availableRoles.length);
    if (availableRoles.length === 0) {
        console.log('🔐 displayTools: Loading roles...');
        try {
            await loadRolesForToolDropdown();
            console.log('🔐 displayTools: After loadRolesForToolDropdown(), availableRoles.length =', availableRoles.length);
        } catch (error) {
            console.error('🔐 displayTools: ERROR calling loadRolesForToolDropdown():', error);
            console.error('🔐 displayTools: Error stack:', error.stack);
        }
    }

    let html = '';
    tools.forEach(tool => {
        const paramCount = getParameterCount(tool.inputSchema);
        const serverId = tool._server_id || '';
        const toolName = tool.name || '';
        const accessRoles = tool._access_roles || [];

        // Create multi-select dropdown for Access Roles
        const selectedRoleIds = accessRoles.map(r => r.role_id);
        const roleDropdownId = `role-${serverId}-${toolName.replace(/[^a-zA-Z0-9]/g, '_')}`;

        console.log(`🔐 Tool: ${toolName}, availableRoles.length: ${availableRoles.length}, accessRoles:`, accessRoles);

        html += `
            <div class="server-row" data-server-id="${serverId}" data-tool-name="${toolName}">
                <div class="col-name">
                    <div class="server-name">${toolName}</div>
                    <div class="server-id">${tool._server_url || 'Unknown Server'}</div>
                </div>
                <div class="col-endpoint">
                    <div style="font-size: 0.875rem; color: var(--text-secondary);">
                        ${tool.description || 'No description available'}
                    </div>
                </div>
                <div class="col-capabilities">
                    <span class="capabilities-count">${paramCount}</span>
                </div>
                <div class="col-version">
                    ${availableRoles.length > 0 ? `
                        <div class="tool-roles-container" id="roles-container-${serverId}-${toolName.replace(/[^a-zA-Z0-9]/g, '_')}">
                            <button class="tool-roles-button" onclick="openToolRoleModal('${serverId}', '${toolName.replace(/'/g, '\\\'')}', '${tool._server_url || 'Unknown Server'}')">
                                <div class="tool-roles-button-content">
                                    ${accessRoles.length > 0 ?
                                        accessRoles.map(r => `<span class="role-badge-small">${r.role_name}</span>`).join('') :
                                        '<span class="placeholder-text"><i class="fas fa-user-shield"></i> Assign Roles</span>'
                                    }
                                </div>
                            </button>
                        </div>
                    ` : `
                        <div style="font-size: 0.75rem; color: var(--text-muted); padding: 4px;">
                            No roles configured
                        </div>
                    `}
                </div>
                <div class="col-actions">
                    <div class="action-buttons">
                        <button class="action-btn" onclick="selectToolForTesting('${toolName}')" title="Test Tool">
                            <i class="fas fa-play"></i>
                        </button>
                        <button class="action-btn" onclick="viewToolDetails('${toolName}')" title="View Details">
                            <i class="fas fa-info-circle"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
    });

    tableBody.innerHTML = html;
}

function getParameterCount(inputSchema) {
    if (!inputSchema || !inputSchema.properties) return 0;
    return Object.keys(inputSchema.properties).length;
}

function populateToolSelect(tools) {
    const select = document.getElementById('testToolSelect');
    select.innerHTML = '<option value="">Select a tool...</option>';

    tools.forEach(tool => {
        const option = document.createElement('option');
        option.value = tool.name;
        option.textContent = `${tool.name} - ${tool.description || 'No description'}`;
        select.appendChild(option);
    });

    select.addEventListener('change', function() {
        const selectedTool = discoveredTools.find(t => t.name === this.value);
        if (selectedTool) {
            displayToolParameters(selectedTool);
            document.getElementById('executeToolBtn').disabled = false;
        } else {
            document.getElementById('toolParameters').innerHTML = '';
            document.getElementById('executeToolBtn').disabled = true;
        }
    });
}

function selectToolForTesting(toolName) {
    // Switch to testing tab and select the tool
    switchTab('testing');
    document.getElementById('testToolSelect').value = toolName;
    document.getElementById('testToolSelect').dispatchEvent(new Event('change'));
}

function viewToolDetails(toolName) {
    const tool = discoveredTools.find(t => t.name === toolName);
    if (!tool) return;

    const detailsHtml = `
        <div class="tool-details">
            <div class="form-group">
                <label class="form-label">Tool Name</label>
                <input type="text" class="form-control" value="${tool.name}" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Description</label>
                <textarea class="form-control" rows="2" readonly>${tool.description || 'No description'}</textarea>
            </div>
            <div class="form-group">
                <label class="form-label">Server URL</label>
                <input type="text" class="form-control" value="${tool._server_url || 'Unknown'}" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Input Schema</label>
                <pre class="test-results">${JSON.stringify(tool.inputSchema, null, 2)}</pre>
            </div>
        </div>
    `;

    document.getElementById('toolDetailsContent').innerHTML = detailsHtml;
    document.getElementById('toolDetailsModal').style.display = 'block';
}

// Tool Testing
function displayToolParameters(tool) {
    const container = document.getElementById('toolParameters');
    const schema = tool.inputSchema;

    if (!schema || !schema.properties) {
        container.innerHTML = '<p class="text-muted">This tool requires no parameters.</p>';
        return;
    }

    let html = '<div class="form-row">';
    for (const [key, param] of Object.entries(schema.properties)) {
        const required = schema.required && schema.required.includes(key);
        const type = param.type || 'string';
        const description = param.description || '';

        html += `
            <div class="form-group">
                <label class="form-label">
                    ${key} ${required ? '<span style="color: var(--error-color);">*</span>' : ''}
                    <small class="text-muted">(${type})</small>
                </label>
        `;

        // Check if parameter has enum constraint - use dropdown
        if (param.enum && Array.isArray(param.enum)) {
            html += `
                <select class="form-control" id="param-${key}" ${required ? 'required' : ''}>
                    <option value="">-- Select ${key} --</option>
                    ${param.enum.map(enumValue => `
                        <option value="${enumValue}">${enumValue}</option>
                    `).join('')}
                </select>
            `;
        } else {
            // Regular text input for non-enum parameters
            html += `
                <input type="text" class="form-control" id="param-${key}"
                       placeholder="${description}" ${required ? 'required' : ''}>
            `;
        }

        html += `
                ${description ? `<small class="text-muted">${description}</small>` : ''}
            </div>
        `;
    }
    html += '</div>';

    container.innerHTML = html;
}

async function executeTool() {
    const toolName = document.getElementById('testToolSelect').value;
    if (!toolName) return;

    const selectedTool = discoveredTools.find(t => t.name === toolName);
    if (!selectedTool) return;

    const executeBtn = document.getElementById('executeToolBtn');
    const originalText = executeBtn.innerHTML;
    executeBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Executing...';
    executeBtn.disabled = true;

    // Collect parameters
    const params = {};
    const schema = selectedTool.inputSchema;

    if (schema && schema.properties) {
        for (const [key, param] of Object.entries(schema.properties)) {
            const element = document.getElementById(`param-${key}`);
            if (element && element.value) {
                let value = element.value;
                if (param.type === 'integer') {
                    value = parseInt(value, 10);
                } else if (param.type === 'number') {
                    value = parseFloat(value);
                } else if (param.type === 'boolean') {
                    value = value.toLowerCase() === 'true';
                } else if (param.type === 'array' || param.type === 'object') {
                    try {
                        value = JSON.parse(value);
                    } catch (e) {
                        // Keep as string if parsing fails
                    }
                }
                params[key] = value;
            }
        }
    }

    try {
        // Step 1: Initialize MCP session for tool execution
        const initResponse = await fetch(MCP_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream',
                'MCP-Protocol-Version': '2025-06-18'
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "initialize",
                params: {
                    protocolVersion: "2025-06-18",
                    clientInfo: {
                        name: "mcp-portal-ui",
                        version: "1.0.0"
                    }
                },
                id: `init-exec-${Date.now()}`
            })
        });

        const initData = await initResponse.json();
        const sessionId = initResponse.headers.get('Mcp-Session-Id');

        if (!initData.result || !sessionId) {
            throw new Error('Failed to initialize MCP session for tool execution');
        }

        // Step 2: Send initialized notification
        await fetch(MCP_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream',
                'MCP-Protocol-Version': '2025-06-18',
                'Mcp-Session-Id': sessionId
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "notifications/initialized"
            })
        });

        // Step 3: Execute tool with session
        const response = await fetch(MCP_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream',
                'MCP-Protocol-Version': '2025-06-18',
                'Mcp-Session-Id': sessionId
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "tools/call",
                params: {
                    name: toolName,
                    arguments: params
                },
                id: `execution-${Date.now()}`
            })
        });

        if (response.headers.get('Content-Type')?.includes('text/event-stream')) {
            await handleStreamingResponse(response);
        } else {
            const data = await response.json();
            displayTestResults(data);
        }
    } catch (error) {
        console.error('Tool execution failed:', error);
        displayTestResults({ error: { message: error.message } });
    } finally {
        executeBtn.innerHTML = originalText;
        executeBtn.disabled = false;
    }
}

async function handleStreamingResponse(response) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let responses = [];

    const resultsContainer = document.getElementById('testResults');
    resultsContainer.style.display = 'block';
    resultsContainer.innerHTML = 'Streaming response...\n\n';

    while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        let boundary;
        while ((boundary = buffer.indexOf('\n\n')) !== -1) {
            const message = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);

            const lines = message.split('\n');
            let data = '';
            lines.forEach(line => {
                if (line.startsWith('data:')) {
                    data += line.substring(5).trim();
                }
            });

            if (data) {
                try {
                    const jsonData = JSON.parse(data);
                    responses.push(jsonData);
                    resultsContainer.innerHTML += '\n---\n' + JSON.stringify(jsonData, null, 2);
                    resultsContainer.scrollTop = resultsContainer.scrollHeight;
                } catch (e) {
                    console.error('Failed to parse streaming data:', e);
                }
            }
        }
    }
}

function displayTestResults(data) {
    const resultsContainer = document.getElementById('testResults');
    resultsContainer.style.display = 'block';
    resultsContainer.innerHTML = JSON.stringify(data, null, 2);
}

// Utility Functions
// Tool Capabilities
async function loadCapabilities() {
    const container = document.getElementById('capabilitiesContainer');
    container.innerHTML = '<div class="loading">Loading tool capabilities...</div>';

    try {
        // Step 1: Initialize MCP session
        const initResponse = await fetch(MCP_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream',
                'MCP-Protocol-Version': '2025-06-18'
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "initialize",
                params: {
                    protocolVersion: "2025-06-18",
                    clientInfo: {
                        name: "mcp-portal-ui",
                        version: "1.0.0"
                    }
                },
                id: `init-${Date.now()}`
            })
        });

        const initData = await initResponse.json();
        const sessionId = initResponse.headers.get('Mcp-Session-Id');

        if (!initData.result || !sessionId) {
            throw new Error('Failed to initialize MCP session');
        }

        // Step 2: Send initialized notification
        await fetch(MCP_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream',
                'MCP-Protocol-Version': '2025-06-18',
                'Mcp-Session-Id': sessionId
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "notifications/initialized"
            })
        });

        // Step 3: Get tools using existing endpoint
        const toolsResponse = await fetch(MCP_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream',
                'MCP-Protocol-Version': '2025-06-18',
                'Mcp-Session-Id': sessionId
            },
            body: JSON.stringify({
                jsonrpc: "2.0",
                method: "tools/list",
                id: `tools-${Date.now()}`
            })
        });

        const toolsData = await toolsResponse.json();

        if (toolsData.result) {
            const tools = toolsData.result.tools || [];
            
            // Group tools by server URL
            const serverUrls = [...new Set(tools.map(tool => tool._server_url).filter(Boolean))];
            const capabilities = {};
            
            serverUrls.forEach(url => {
                const serverTools = tools.filter(tool => tool._server_url === url);
                if (serverTools.length > 0) {
                    const serverId = url.replace('http://', '').replace('https://', '').replace(/[^a-zA-Z0-9]/g, '_');
                    capabilities[serverId] = {
                        server_info: {
                            server_id: serverId,
                            name: url.replace('http://', '').replace('https://', ''),
                            url: url,
                            description: `MCP Server at ${url}`,
                            protocol_version: "2025-06-18"
                        },
                        tools: serverTools.map(tool => ({
                            name: tool.name,
                            description: tool.description,
                            input_schema: tool.inputSchema,
                            raw_json: tool,
                            parameter_count: Object.keys(tool.inputSchema?.properties || {}).length,
                            required_params: tool.inputSchema?.required || [],
                            discovery_timestamp: tool._discovery_timestamp,
                            server_url: tool._server_url
                        }))
                    };
                }
            });
            
            currentCapabilities = capabilities;
            displayCapabilities(currentCapabilities);
        } else {
            throw new Error('Failed to load tools');
        }
    } catch (error) {
        console.error('Failed to load capabilities:', error);
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-exclamation-triangle"></i>
                <h3>Loading Failed</h3>
                <p>${error.message}</p>
            </div>
        `;
    }
}

function displayCapabilities(capabilities) {
    const container = document.getElementById('capabilitiesContainer');

    if (Object.keys(capabilities).length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-brain"></i>
                <h3>No Capabilities Found</h3>
                <p>No tool capabilities were discovered from the registered servers</p>
            </div>
        `;
        return;
    }

    let html = '<div class="capability-square-grid">';

    for (const [serverId, capabilityData] of Object.entries(capabilities)) {
        const server = capabilityData.server_info;
        const tools = capabilityData.tools;

        // Generate server icon (first letter of server name)
        const serverInitial = server.name.charAt(0).toUpperCase();

        html += `
            <div class="capability-square-card ${!isCardExpanded(serverId) ? '' : 'expanded'}" id="card-${serverId}" onclick="toggleCardExpansion('${serverId}')">
                <!-- Collapsed View (Square) -->
                <div class="square-card-front">
                    <div class="square-icon">${serverInitial}</div>
                    <div class="square-title">${server.name}</div>
                    <div class="square-count">${tools.length} tool${tools.length === 1 ? '' : 's'}</div>
                    <div class="square-expand-hint">
                        <i class="fas fa-chevron-down"></i>
                        Click to expand
                    </div>
                </div>

                <!-- Expanded View (Details) -->
                <div class="square-card-expanded" onclick="event.stopPropagation()">
                    <div class="expanded-header">
                        <div class="expanded-header-left">
                            <div class="expanded-icon">${serverInitial}</div>
                            <div>
                                <div class="expanded-title">${server.name}</div>
                                <div class="expanded-meta">
                                    <span class="meta-badge">
                                        <i class="fas fa-tools"></i> ${tools.length} tools
                                    </span>
                                    <span class="meta-badge">
                                        <i class="fas fa-code"></i> ${server.protocol_version}
                                    </span>
                                </div>
                            </div>
                        </div>
                        <button class="collapse-btn" onclick="toggleCardExpansion('${serverId}'); event.stopPropagation();">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>

                    <div class="expanded-description">
                        ${server.description}
                    </div>

                    <div class="expanded-url">
                        <i class="fas fa-link"></i>
                        <span>${server.url}</span>
                    </div>

                    <div class="expanded-tools">
                        <div class="expanded-tools-header">
                            <i class="fas fa-cube"></i> Available Tools
                        </div>
                        <div class="expanded-tools-list">
                            ${tools.map(tool => `
                                <div class="expanded-tool-item">
                                    <div class="expanded-tool-header">
                                        <span class="expanded-tool-name">${tool.name}</span>
                                        <span class="expanded-tool-params">${tool.parameter_count}p</span>
                                    </div>
                                    <div class="expanded-tool-desc">${tool.description || 'No description'}</div>
                                    <div class="expanded-tool-actions">
                                        <button class="tool-action-btn" onclick="toggleRawJson('${serverId}-${tool.name}'); event.stopPropagation();">
                                            <i class="fas fa-code"></i> JSON
                                        </button>
                                        <button class="tool-action-btn primary" onclick="testFirstTool('${tool.name}'); event.stopPropagation();">
                                            <i class="fas fa-play"></i> Test
                                        </button>
                                    </div>
                                    <div id="raw-${serverId}-${tool.name}" class="tool-raw-json">
                                        ${syntaxHighlight(JSON.stringify(tool.raw_json, null, 2))}
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    html += '</div>';
    container.innerHTML = html;
}

// Track expanded cards
let expandedCards = new Set();

function isCardExpanded(serverId) {
    return expandedCards.has(serverId);
}

function toggleCardExpansion(serverId) {
    const card = document.getElementById(`card-${serverId}`);
    if (!card) return;

    if (expandedCards.has(serverId)) {
        expandedCards.delete(serverId);
        card.classList.remove('expanded');
    } else {
        expandedCards.add(serverId);
        card.classList.add('expanded');
    }
}

function toggleRawJson(toolId) {
    const viewer = document.getElementById(`raw-${toolId}`);
    viewer.classList.toggle('show');
}

function testToolFromCapabilities(toolName) {
    // Switch to testing tab and select the tool
    switchTab('testing');
    document.getElementById('testToolSelect').value = toolName;
    document.getElementById('testToolSelect').dispatchEvent(new Event('change'));
}

// Marketplace card helper functions
function testFirstTool(toolName) {
    if (!toolName) return;
    switchTab('testing');
    document.getElementById('testToolSelect').value = toolName;
    document.getElementById('testToolSelect').dispatchEvent(new Event('change'));
}

function viewAllServerTools(serverId) {
    const capabilityData = currentCapabilities[serverId];
    if (!capabilityData) return;

    const server = capabilityData.server_info;
    const tools = capabilityData.tools;

    const modalHtml = `
        <div class="server-tools-modal-content">
            <div class="modal-header-section">
                <div class="server-icon-large">${server.name.charAt(0).toUpperCase()}</div>
                <div>
                    <h2>${server.name}</h2>
                    <p class="modal-server-url"><i class="fas fa-link"></i> ${server.url}</p>
                </div>
            </div>

            <div class="modal-tools-grid">
                ${tools.map(tool => `
                    <div class="modal-tool-card">
                        <div class="modal-tool-header">
                            <span class="modal-tool-name">${tool.name}</span>
                            <span class="tool-params-badge">${tool.parameter_count} params</span>
                        </div>
                        <div class="modal-tool-description">${tool.description || 'No description available'}</div>
                        <div class="modal-tool-actions">
                            <button class="btn btn-sm btn-outline" onclick="toggleRawJson('modal-${serverId}-${tool.name}')">
                                <i class="fas fa-code"></i> JSON
                            </button>
                            <button class="btn btn-sm btn-primary" onclick="testFirstTool('${tool.name}'); hideModal('serverToolsModal')">
                                <i class="fas fa-play"></i> Test
                            </button>
                        </div>
                        <div id="raw-modal-${serverId}-${tool.name}" class="raw-json-viewer">
                            ${syntaxHighlight(JSON.stringify(tool.raw_json, null, 2))}
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;

    const modal = document.getElementById('serverToolsModal');
    if (!modal) {
        // Create modal if it doesn't exist
        const newModal = document.createElement('div');
        newModal.id = 'serverToolsModal';
        newModal.className = 'modal';
        newModal.innerHTML = `
            <div class="modal-content modal-large">
                <span class="close" onclick="hideModal('serverToolsModal')">&times;</span>
                <div id="serverToolsModalContent"></div>
            </div>
        `;
        document.body.appendChild(newModal);
        document.getElementById('serverToolsModalContent').innerHTML = modalHtml;
        newModal.style.display = 'block';
    } else {
        document.getElementById('serverToolsModalContent').innerHTML = modalHtml;
        modal.style.display = 'block';
    }
}

function expandServerTools(serverId) {
    viewAllServerTools(serverId);
}

function exportCapabilities() {
    if (Object.keys(currentCapabilities).length === 0) {
        showAlert('No capabilities to export. Please load capabilities first.', 'warning');
        return;
    }

    const dataStr = JSON.stringify(currentCapabilities, null, 2);
    const dataBlob = new Blob([dataStr], {type: 'application/json'});
    const url = URL.createObjectURL(dataBlob);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = `mcp-tool-capabilities-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    showAlert('Capabilities exported successfully!', 'success');
}

function filterCapabilities() {
    const searchTerm = document.getElementById('capabilitySearch').value.toLowerCase();
    const capabilityCards = document.querySelectorAll('.capability-card');
    
    capabilityCards.forEach(card => {
        const title = card.querySelector('.capability-card-title')?.textContent.toLowerCase() || '';
        const tools = Array.from(card.querySelectorAll('.tool-capability-name')).map(el => el.textContent.toLowerCase()).join(' ');
        const description = card.querySelector('.tool-capability-description')?.textContent.toLowerCase() || '';
        
        const matches = searchTerm === '' || title.includes(searchTerm) || tools.includes(searchTerm) || description.includes(searchTerm);
        card.style.display = matches ? 'block' : 'none';
    });
}

function syntaxHighlight(json) {
    return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
        var cls = 'json-number';
        if (/^"/.test(match)) {
            if (/:$/.test(match)) {
                cls = 'json-key';
            } else {
                cls = 'json-string';
            }
        } else if (/true|false/.test(match)) {
            cls = 'json-boolean';
        } else if (/null/.test(match)) {
            cls = 'json-null';
        }
        return '<span class="' + cls + '">' + match + '</span>';
    });
}

function refreshAll() {
    if (currentTab === 'servers') {
        loadServers();
    } else if (currentTab === 'tools') {
        discoverTools();
    } else if (currentTab === 'capabilities') {
        loadCapabilities();
    }
}

function showAlert(message, type = 'info') {
    // Create alert element
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()" style="float: right; background: none; border: none; font-size: 1.2rem; cursor: pointer;">&times;</button>
    `;

    // Insert at top of content area
    const contentArea = document.querySelector('.content-area');
    contentArea.insertBefore(alert, contentArea.firstChild);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (alert.parentElement) {
            alert.remove();
        }
    }, 5000);
}

function hideModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

// Bulk operations
function toggleSelectAll() {
    const selectAll = document.getElementById('selectAll');
    const checkboxes = document.querySelectorAll('.server-checkbox');
    checkboxes.forEach(cb => cb.checked = selectAll.checked);
}

function bulkDeleteServers() {
    const checkedBoxes = document.querySelectorAll('.server-checkbox:checked');
    if (checkedBoxes.length === 0) {
        showAlert('Please select servers to delete', 'warning');
        return;
    }

    if (!confirm(`Are you sure you want to delete ${checkedBoxes.length} selected server(s)?`)) {
        return;
    }

    // Delete each selected server
    checkedBoxes.forEach(async (checkbox) => {
        const serverId = checkbox.getAttribute('data-server-id');
        await deleteServer(serverId);
    });
}

// Search and filtering
function filterServers() {
    const searchTerm = document.getElementById('serverSearch').value.toLowerCase();
    const statusFilter = document.getElementById('statusFilter').value.toLowerCase();
    
    const serverRows = document.querySelectorAll('.server-row');
    
    serverRows.forEach(row => {
        const name = row.querySelector('.server-name')?.textContent.toLowerCase() || '';
        const url = row.querySelector('.endpoint-url')?.textContent.toLowerCase() || '';
        const status = row.querySelector('.status-badge')?.textContent.toLowerCase() || '';
        
        const matchesSearch = searchTerm === '' || name.includes(searchTerm) || url.includes(searchTerm);
        const matchesStatus = statusFilter === '' || status.includes(statusFilter);
        
        row.style.display = matchesSearch && matchesStatus ? 'flex' : 'none';
    });
}

function filterTools() {
    const searchTerm = document.getElementById('toolSearch').value.toLowerCase();

    const toolRows = document.querySelectorAll('#toolsTableBody .server-row');

    toolRows.forEach(row => {
        const name = row.querySelector('.server-name')?.textContent.toLowerCase() || '';
        const description = row.querySelector('.col-endpoint')?.textContent.toLowerCase() || '';

        const matches = searchTerm === '' || name.includes(searchTerm) || description.includes(searchTerm);
        row.style.display = matches ? 'flex' : 'none';
    });
}

// ===== OAuth Provider Management for Tools =====

async function loadOAuthProviders() {
    console.log('🔐 Loading OAuth providers from /auth/providers...');
    try {
        const response = await fetch('/auth/providers');
        console.log('🔐 OAuth providers response status:', response.status);
        const data = await response.json();
        console.log('🔐 OAuth providers response data:', data);

        if (data.providers) {
            availableOAuthProviders = data.providers.filter(p => p.enabled);
            console.log('🔐 Filtered enabled OAuth providers:', availableOAuthProviders);
            console.log('🔐 Total OAuth providers loaded:', availableOAuthProviders.length);
        } else {
            console.warn('🔐 No providers array in response:', data);
            availableOAuthProviders = [];
        }
    } catch (error) {
        console.error('🔐 Failed to load OAuth providers:', error);
        availableOAuthProviders = [];
    }
}

async function updateToolOAuthProviders(serverId, toolName) {
    const selectElement = document.querySelector(`select[data-server-id="${serverId}"][data-tool-name="${toolName}"]`);
    if (!selectElement) return;

    const selectedOptions = Array.from(selectElement.selectedOptions);
    const selectedProviderIds = selectedOptions.map(option => option.value);

    try {
        const response = await fetch(`/admin/tools/${encodeURIComponent(serverId)}/${encodeURIComponent(toolName)}/oauth-providers`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                oauth_provider_ids: selectedProviderIds
            })
        });

        const result = await response.json();

        if (result.success) {
            showAlert(`OAuth providers updated for tool: ${toolName}`, 'success');
        } else {
            showAlert(`Failed to update OAuth providers: ${result.message || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('Failed to update tool OAuth providers:', error);
        showAlert('Failed to update OAuth providers: ' + error.message, 'error');
    }
}

// Tool Role Assignment Modal Functions
let currentToolRoleModalData = null;

function openToolRoleModal(serverId, toolName, serverUrl) {
    // Store current tool data
    currentToolRoleModalData = { serverId, toolName, serverUrl };

    // Set tool information in modal
    document.getElementById('modalToolName').value = toolName;
    document.getElementById('modalToolServer').value = serverUrl;

    // Get current tool's access roles
    const tool = discoveredTools.find(t => t.name === toolName && t._server_id === serverId);
    const currentRoleIds = tool ? (tool._access_roles || []).map(r => r.role_id) : [];

    // Populate roles checklist
    const rolesList = document.getElementById('toolRoleModalRolesList');
    if (availableRoles.length === 0) {
        rolesList.innerHTML = `
            <div class="empty-state" style="padding: 2rem;">
                <i class="fas fa-exclamation-circle"></i>
                <p>No roles available. Please create roles first.</p>
            </div>
        `;
    } else {
        rolesList.innerHTML = availableRoles.map(role => `
            <label class="tool-role-modal-checkbox">
                <input type="checkbox" value="${role.role_id}" ${currentRoleIds.includes(role.role_id) ? 'checked' : ''}>
                <div class="tool-role-modal-checkbox-content">
                    <strong>${role.role_name}</strong>
                    <small>${role.description || 'No description'}</small>
                </div>
            </label>
        `).join('');
    }

    // Show modal
    document.getElementById('toolRoleAssignmentModal').style.display = 'block';
}

function closeToolRoleModal() {
    document.getElementById('toolRoleAssignmentModal').style.display = 'none';
    currentToolRoleModalData = null;
}

async function saveToolRolesFromModal() {
    if (!currentToolRoleModalData) return;

    const { serverId, toolName } = currentToolRoleModalData;
    const rolesList = document.getElementById('toolRoleModalRolesList');
    const checkedBoxes = rolesList.querySelectorAll('input[type="checkbox"]:checked');
    const selectedRoleIds = Array.from(checkedBoxes).map(cb => cb.value);

    // Get auth token from localStorage
    const authToken = localStorage.getItem('access_token');

    if (!authToken) {
        showAlert('Authentication required. Please log in.', 'error');
        return;
    }

    try {
        const response = await fetch(`/admin/tools/${encodeURIComponent(serverId)}/${encodeURIComponent(toolName)}/roles`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`
            },
            body: JSON.stringify({
                role_ids: selectedRoleIds
            })
        });

        const result = await response.json();

        if (result.success) {
            showAlert(`Access roles updated for tool: ${toolName}`, 'success');
            closeToolRoleModal();

            // Update the underlying tool data in discoveredTools array
            const toolIndex = discoveredTools.findIndex(t => t.name === toolName && t._server_id === serverId);
            if (toolIndex !== -1) {
                // Update the _access_roles with the new selection
                discoveredTools[toolIndex]._access_roles = Array.from(checkedBoxes).map(cb => {
                    const content = cb.nextElementSibling;
                    return {
                        role_id: cb.value,
                        role_name: content.querySelector('strong').textContent,
                        description: content.querySelector('small').textContent
                    };
                });
            }

            // Update the visual display in the table
            const toolId = toolName.replace(/[^a-zA-Z0-9]/g, '_');
            const buttonContent = document.querySelector(`#roles-container-${serverId}-${toolId} .tool-roles-button-content`);

            if (buttonContent) {
                if (checkedBoxes.length > 0) {
                    buttonContent.innerHTML = Array.from(checkedBoxes).map(cb => {
                        const label = cb.nextElementSibling.querySelector('strong').textContent;
                        return `<span class="role-badge-small">${label}</span>`;
                    }).join('');
                } else {
                    buttonContent.innerHTML = '<span class="placeholder-text"><i class="fas fa-user-shield"></i> Assign Roles</span>';
                }
            }
        } else {
            showAlert(`Failed to update access roles: ${result.message || 'Unknown error'}`, 'error');
        }
    } catch (error) {
        console.error('Failed to update tool access roles:', error);
        showAlert('Failed to update access roles: ' + error.message, 'error');
    }
}
// ===== Configuration Management Functions =====

// Load all configuration
async function loadAllConfig() {
    console.log('loadAllConfig() called');
    try {
        const response = await fetch('/config');
        console.log('Config response status:', response.status);
        const config = await response.json();
        console.log('Config data received:', config);

        // Load health config
        if (config.connection_health) {
            loadHealthConfigData(config.connection_health);
        }

        // Load origin config
        if (config.origin) {
            loadOriginConfigData(config.origin);
        }

        return config;
    } catch (error) {
        console.error('Error loading configuration:', error);
        showNotification('Failed to load configuration', 'error');
    }
}

// Health Configuration
function loadHealthConfigData(healthConfig) {
    document.getElementById('healthEnabled').checked = healthConfig.enabled;
    document.getElementById('healthCheckInterval').value = healthConfig.check_interval_seconds;
    document.getElementById('healthStaleTimeout').value = healthConfig.stale_timeout_seconds;
    document.getElementById('healthMaxRetry').value = healthConfig.max_retry_attempts;
    document.getElementById('healthRetryDelay').value = healthConfig.retry_delay_seconds;
    
    document.getElementById('healthConfigStatus').textContent = 'Loaded';
    document.getElementById('healthConfigStatus').className = 'test-status success';
}

async function loadHealthConfig() {
    const config = await loadAllConfig();
    if (config) {
        showNotification('Health configuration reloaded', 'success');
    }
}

function updateHealthConfigStatus() {
    document.getElementById('healthConfigStatus').textContent = 'Modified';
    document.getElementById('healthConfigStatus').className = 'test-status pending';
}

async function saveHealthConfig() {
    const healthConfig = {
        enabled: document.getElementById('healthEnabled').checked,
        check_interval_seconds: parseInt(document.getElementById('healthCheckInterval').value),
        stale_timeout_seconds: parseInt(document.getElementById('healthStaleTimeout').value),
        max_retry_attempts: parseInt(document.getElementById('healthMaxRetry').value),
        retry_delay_seconds: parseInt(document.getElementById('healthRetryDelay').value)
    };
    
    try {
        const response = await fetch('/config/health', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(healthConfig)
        });
        
        const result = await response.json();
        
        if (result.success) {
            document.getElementById('healthConfigStatus').textContent = 'Saved';
            document.getElementById('healthConfigStatus').className = 'test-status success';
            showNotification('Health configuration saved successfully', 'success');
        } else {
            showNotification('Failed to save health configuration', 'error');
        }
    } catch (error) {
        console.error('Error saving health config:', error);
        showNotification('Error saving health configuration', 'error');
    }
}

// Origin Configuration
function loadOriginConfigData(originConfig) {
    console.log('Loading origin config:', originConfig);

    if (originConfig && originConfig.allowed_origins) {
        renderAllowedOrigins(originConfig.allowed_origins);
    } else {
        console.warn('No allowed_origins in config:', originConfig);
        renderAllowedOrigins([]);
    }

    document.getElementById('originConfigStatus').textContent = 'Loaded';
    document.getElementById('originConfigStatus').className = 'test-status success';
}

function renderAllowedOrigins(origins) {
    console.log('Rendering allowed origins:', origins);
    const container = document.getElementById('allowedOriginsList');

    if (!container) {
        console.error('allowedOriginsList container not found!');
        return;
    }

    console.log('Container found:', container);

    if (!origins || origins.length === 0) {
        console.log('No origins, setting empty state');
        container.innerHTML = '<span class="empty-state">No origins configured</span>';
        return;
    }

    const html = origins.map(origin => `
        <span class="tag">
            ${origin}
            <button class="tag-remove" onclick="removeOrigin('${origin}')">&times;</button>
        </span>
    `).join('');

    console.log('Setting innerHTML to:', html);
    container.innerHTML = html;
    console.log('After setting, container.innerHTML is:', container.innerHTML);
}

async function loadOriginConfig() {
    const config = await loadAllConfig();
    if (config) {
        showNotification('Origin configuration reloaded', 'success');
    }
}

function updateOriginConfigStatus() {
    document.getElementById('originConfigStatus').textContent = 'Modified';
    document.getElementById('originConfigStatus').className = 'test-status pending';
}

async function addOrigin() {
    const newOrigin = document.getElementById('newOrigin').value.trim();
    if (!newOrigin) {
        showNotification('Please enter an origin', 'error');
        return;
    }
    
    try {
        const response = await fetch('/config/origin/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ origin: newOrigin })
        });
        
        const result = await response.json();
        
        if (result.success) {
            document.getElementById('newOrigin').value = '';
            await loadOriginConfig();
            showNotification(`Origin '${newOrigin}' added successfully`, 'success');
        } else {
            showNotification('Failed to add origin', 'error');
        }
    } catch (error) {
        console.error('Error adding origin:', error);
        showNotification('Error adding origin', 'error');
    }
}

async function removeOrigin(origin) {
    try {
        const response = await fetch('/config/origin/remove', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ origin: origin })
        });
        
        const result = await response.json();
        
        if (result.success) {
            await loadOriginConfig();
            showNotification(`Origin '${origin}' removed successfully`, 'success');
        } else {
            showNotification('Failed to remove origin', 'error');
        }
    } catch (error) {
        console.error('Error removing origin:', error);
        showNotification('Error removing origin', 'error');
    }
}

// Removed saveOriginConfig - origins are now saved individually via add/remove

// Server Health Status
async function loadServerHealth() {
    try {
        const response = await fetch('/health/servers');
        const healthData = await response.json();
        
        const container = document.getElementById('serverHealthList');
        
        if (Object.keys(healthData).length === 0) {
            container.innerHTML = '<p class="empty-state">No server health data available</p>';
            return;
        }
        
        container.innerHTML = Object.entries(healthData).map(([url, health]) => `
            <div class="health-card">
                <div class="health-card-header">
                    <div class="health-server-url">${url}</div>
                    <div class="health-status ${health.is_healthy ? 'healthy' : 'unhealthy'}">
                        <i class="fas fa-${health.is_healthy ? 'check-circle' : 'exclamation-circle'}"></i>
                        ${health.is_healthy ? 'Healthy' : 'Unhealthy'}
                    </div>
                </div>
                <div class="health-card-body">
                    <div class="health-info-row">
                        <span class="health-label">Last Success:</span>
                        <span class="health-value">${health.last_success || 'Never'}</span>
                    </div>
                    <div class="health-info-row">
                        <span class="health-label">Last Check:</span>
                        <span class="health-value">${health.last_check || 'Never'}</span>
                    </div>
                    <div class="health-info-row">
                        <span class="health-label">Consecutive Failures:</span>
                        <span class="health-value">${health.consecutive_failures}</span>
                    </div>
                    ${health.last_error ? `
                        <div class="health-info-row">
                            <span class="health-label">Last Error:</span>
                            <span class="health-value error">${health.last_error}</span>
                        </div>
                    ` : ''}
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading server health:', error);
        showNotification('Failed to load server health status', 'error');
    }
}

// Configuration loading is now handled in switchTab() function

// Tool credentials management removed - using role-based access control instead

