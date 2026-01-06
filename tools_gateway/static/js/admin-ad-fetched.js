/**
 * Fetched AD Groups & Users Management
 * Local storage and display of AD data for authorization
 */

// ===========================================================================
// LOCAL STORAGE FOR FETCHED AD DATA
// ===========================================================================

// Store fetched AD groups and users locally
function storeFetchedADData(groups, users) {
    const adData = {
        groups: groups,
        users: users,
        timestamp: new Date().toISOString()
    };

    localStorage.setItem('fetched_ad_data', JSON.stringify(adData));
    showNotification(`Stored ${groups.length} groups and ${users.length} users locally`, 'success');

    // Refresh the display
    displayFetchedADData();
}

// Get stored AD data from localStorage
function getFetchedADData() {
    const stored = localStorage.getItem('fetched_ad_data');
    if (stored) {
        try {
            return JSON.parse(stored);
        } catch (e) {
            console.error('Error parsing stored AD data:', e);
            return null;
        }
    }
    return null;
}

// Clear stored AD data
function clearFetchedADData() {
    if (confirm('Are you sure you want to clear all fetched AD data from local storage?')) {
        localStorage.removeItem('fetched_ad_data');
        showNotification('Fetched AD data cleared', 'success');
        displayFetchedADData();
    }
}

// ===========================================================================
// DISPLAY FETCHED AD DATA
// ===========================================================================

// Display fetched AD groups and users
function displayFetchedADData() {
    const container = document.getElementById('fetchedADContainer');
    if (!container) return;

    const adData = getFetchedADData();

    if (!adData || !adData.groups || adData.groups.length === 0) {
        container.innerHTML = `
            <div class="alert alert-info">
                <i class="fas fa-info-circle"></i>
                <strong>No Data</strong>
                <p>No AD data fetched yet. Use "Query Groups" in AD Configuration to fetch groups and users.</p>
            </div>
        `;
        return;
    }

    const fetchTime = new Date(adData.timestamp).toLocaleString();

    // Filter to get only actual groups (organizational units with members)
    const actualGroups = adData.groups.filter(g =>
        g.dn.startsWith('ou=') || g.member_count > 0
    );

    container.innerHTML = `
        <div class="toolbar" style="margin-bottom: 15px;">
            <div style="flex: 1;">
                <p class="text-muted" style="margin: 0;">
                    <i class="fas fa-clock"></i> Last fetched: ${fetchTime}
                </p>
            </div>
            <button class="btn btn-sm btn-outline" onclick="refreshFetchedADData()">
                <i class="fas fa-sync"></i> Refresh from AD
            </button>
            <button class="btn btn-sm btn-danger" onclick="clearFetchedADData()">
                <i class="fas fa-trash"></i> Clear Data
            </button>
        </div>

        <div class="fetched-groups-grid">
            ${actualGroups.map(group => `
                <div class="group-card" onclick="toggleGroupMembers('${group.dn}')">
                    <div class="group-header">
                        <div class="group-icon">
                            <i class="fas fa-users"></i>
                        </div>
                        <div class="group-info">
                            <h4>${group.name}</h4>
                            <p class="group-dn">${group.dn}</p>
                            <span class="badge badge-info">${group.member_count || 0} members</span>
                        </div>
                        <div class="group-toggle">
                            <i class="fas fa-chevron-down"></i>
                        </div>
                    </div>
                    <div class="group-members" id="members-${escapeId(group.dn)}" style="display: none;">
                        <div class="loading"><i class="fas fa-spinner fa-spin"></i> Loading members...</div>
                    </div>
                </div>
            `).join('')}
        </div>

        <style>
            .fetched-groups-grid {
                display: grid;
                gap: 15px;
                margin-top: 15px;
            }

            .group-card {
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                overflow: hidden;
                cursor: pointer;
                transition: all 0.2s;
            }

            .group-card:hover {
                border-color: #3b82f6;
                box-shadow: 0 2px 8px rgba(59, 130, 246, 0.1);
            }

            .group-header {
                display: flex;
                align-items: center;
                padding: 15px;
                gap: 12px;
            }

            .group-icon {
                width: 40px;
                height: 40px;
                background: #3b82f6;
                border-radius: 8px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 20px;
            }

            .group-info {
                flex: 1;
            }

            .group-info h4 {
                margin: 0 0 4px 0;
                font-size: 16px;
                color: #111827;
            }

            .group-dn {
                margin: 4px 0;
                font-size: 11px;
                color: #6b7280;
                font-family: monospace;
            }

            .group-toggle {
                color: #9ca3af;
                transition: transform 0.2s;
            }

            .group-card.expanded .group-toggle {
                transform: rotate(180deg);
            }

            .group-members {
                border-top: 1px solid #e5e7eb;
                padding: 15px;
                background: #f9fafb;
            }

            .member-list {
                display: grid;
                gap: 8px;
            }

            .member-item {
                background: white;
                padding: 10px;
                border-radius: 6px;
                display: flex;
                align-items: center;
                gap: 10px;
                border: 1px solid #e5e7eb;
            }

            .member-icon {
                width: 32px;
                height: 32px;
                background: #10b981;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 14px;
            }

            .member-details {
                flex: 1;
            }

            .member-name {
                font-weight: 500;
                color: #111827;
                margin: 0;
            }

            .member-email {
                font-size: 13px;
                color: #6b7280;
                margin: 2px 0 0 0;
            }
        </style>
    `;
}

// Escape DN for use as HTML ID
function escapeId(dn) {
    return dn.replace(/[^a-zA-Z0-9]/g, '_');
}

// Toggle group members display
async function toggleGroupMembers(groupDN) {
    const memberDiv = document.getElementById(`members-${escapeId(groupDN)}`);
    const groupCard = memberDiv.closest('.group-card');

    if (!memberDiv) return;

    // Toggle expanded class
    groupCard.classList.toggle('expanded');

    // If already expanded, just collapse
    if (memberDiv.style.display !== 'none') {
        memberDiv.style.display = 'none';
        return;
    }

    // Show and load members
    memberDiv.style.display = 'block';

    // Load members from API
    await loadGroupMembers(groupDN, memberDiv);
}

// Load group members from API
async function loadGroupMembers(groupDN, containerDiv) {
    try {
        // Get AD config
        const server = document.getElementById('adConfigServer').value.trim();
        const port = parseInt(document.getElementById('adConfigPort').value);
        const bindDN = document.getElementById('adConfigBindDN').value.trim();
        const bindPassword = document.getElementById('adConfigPassword').value;
        const useSSL = document.getElementById('adConfigUseSSL').checked;

        if (!server || !bindDN || !bindPassword) {
            containerDiv.innerHTML = `
                <div class="alert alert-warning">
                    <i class="fas fa-exclamation-triangle"></i>
                    Please configure and save AD connection settings first.
                </div>
            `;
            return;
        }

        // Get auth token
        const authToken = localStorage.getItem('access_token');
        if (!authToken) {
            containerDiv.innerHTML = `
                <div class="alert alert-warning">
                    <i class="fas fa-exclamation-triangle"></i>
                    Authentication required. Please sign in.
                </div>
            `;
            return;
        }

        const response = await fetch('/admin/ad/query-group-members', {
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
                group_dn: groupDN,
                use_ssl: useSSL
            })
        });

        if (response.ok) {
            const data = await response.json();
            displayGroupMembers(data.members, containerDiv);

            // Update local storage with member details
            updateStoredGroupMembers(groupDN, data.members);
        } else {
            const error = await response.json();
            containerDiv.innerHTML = `
                <div class="alert alert-error">
                    <i class="fas fa-exclamation-circle"></i>
                    Failed to load members: ${error.detail || 'Unknown error'}
                </div>
            `;
        }
    } catch (error) {
        console.error('Error loading group members:', error);
        containerDiv.innerHTML = `
            <div class="alert alert-error">
                <i class="fas fa-exclamation-circle"></i>
                Error: ${error.message}
            </div>
        `;
    }
}

// Display group members
function displayGroupMembers(members, containerDiv) {
    if (!members || members.length === 0) {
        containerDiv.innerHTML = `
            <p class="text-muted">No members found in this group.</p>
        `;
        return;
    }

    containerDiv.innerHTML = `
        <div class="member-list">
            ${members.map(member => `
                <div class="member-item">
                    <div class="member-icon">
                        <i class="fas fa-user"></i>
                    </div>
                    <div class="member-details">
                        <p class="member-name">${member.display_name || member.username}</p>
                        <p class="member-email">${member.email}</p>
                    </div>
                    <span class="badge">${member.username}</span>
                </div>
            `).join('')}
        </div>
    `;
}

// Update stored group members
function updateStoredGroupMembers(groupDN, members) {
    const adData = getFetchedADData();
    if (!adData) return;

    // Find and update the group
    const group = adData.groups.find(g => g.dn === groupDN);
    if (group) {
        group.members = members;
        group.member_count = members.length;
        localStorage.setItem('fetched_ad_data', JSON.stringify(adData));
    }
}

// ===========================================================================
// REFRESH FUNCTIONS
// ===========================================================================

// Refresh fetched AD data from server
async function refreshFetchedADData() {
    const server = document.getElementById('adConfigServer').value.trim();
    const port = parseInt(document.getElementById('adConfigPort').value);
    const baseDN = document.getElementById('adConfigBaseDN').value.trim();
    const bindDN = document.getElementById('adConfigBindDN').value.trim();
    const bindPassword = document.getElementById('adConfigPassword').value;
    const groupFilter = document.getElementById('adConfigGroupFilter').value.trim();
    const useSSL = document.getElementById('adConfigUseSSL').checked;

    if (!server || !baseDN || !bindDN || !bindPassword) {
        showNotification('Please configure AD connection settings first', 'error');
        return;
    }

    // Get auth token
    const authToken = localStorage.getItem('access_token');
    if (!authToken) {
        showNotification('Authentication required. Please sign in.', 'error');
        return;
    }

    try {
        showNotification('Fetching AD data...', 'info');

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
                group_filter: groupFilter || '(objectClass=*)',
                use_ssl: useSSL
            })
        });

        if (response.ok) {
            const data = await response.json();

            // Store groups
            storeFetchedADData(data.groups, []);

            showNotification(`Successfully fetched ${data.groups.length} groups`, 'success');
        } else {
            const error = await response.json();
            showNotification('Failed to fetch AD data: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error refreshing AD data:', error);
        showNotification('Error: ' + error.message, 'error');
    }
}

// ===========================================================================
// INITIALIZE ON PAGE LOAD
// ===========================================================================

// Load and display fetched AD data when the Users & Roles tab is opened
document.addEventListener('DOMContentLoaded', () => {
    const usersTab = document.querySelector('[data-tab="users"]');
    if (usersTab) {
        usersTab.addEventListener('click', () => {
            // Small delay to ensure DOM is ready
            setTimeout(() => {
                displayFetchedADData();
            }, 100);
        });
    }
});
