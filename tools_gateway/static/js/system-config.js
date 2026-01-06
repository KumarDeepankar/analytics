// System Configuration Management Functions

// Load system configuration
async function loadSystemConfig() {
    try {
        const response = await fetch('/config/system');
        const config = await response.json();

        // Populate form fields (RS256/JWKS fields only)
        document.getElementById('jwtKeyId').value = config.jwt_key_id || 'Not generated';
        document.getElementById('jwtExpiryMinutes').value = config.jwt_expiry_minutes;
        document.getElementById('logLevel').value = config.log_level;

        document.getElementById('systemConfigStatus').textContent = 'Loaded';
        document.getElementById('systemConfigStatus').className = 'test-status success';
    } catch (error) {
        console.error('Error loading system config:', error);
        showNotification('Failed to load system configuration', 'error');
        document.getElementById('systemConfigStatus').textContent = 'Error';
        document.getElementById('systemConfigStatus').className = 'test-status error';
    }
}

// Save system configuration
async function saveSystemConfig() {
    try {
        const config = {
            jwt_expiry_minutes: parseInt(document.getElementById('jwtExpiryMinutes').value),
            log_level: document.getElementById('logLevel').value
        };

        const response = await fetch('/config/system', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        const result = await response.json();

        if (result.success) {
            showNotification('System configuration saved successfully!', 'success');
            document.getElementById('systemConfigStatus').textContent = 'Saved';
            document.getElementById('systemConfigStatus').className = 'test-status success';

            // Reload to show updated values
            setTimeout(() => loadSystemConfig(), 500);
        } else {
            showNotification('Failed to save configuration: ' + (result.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error saving system config:', error);
        showNotification('Failed to save system configuration', 'error');
    }
}

// Generate new RSA keys for JWT signing
async function generateRSAKeys() {
    if (!confirm('⚠️  WARNING: This will generate new RSA keys and invalidate ALL existing tokens.\n\nUsers will need to log in again. Continue?')) {
        return;
    }

    try {
        showNotification('Generating new RSA key pair...', 'info');

        const response = await fetch('/config/jwt/generate-rsa-keys', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        const result = await response.json();

        if (result.success) {
            showNotification('✓ RSA keys generated successfully! New Key ID: ' + result.key_id, 'success');

            // Reload configuration to show new key ID
            setTimeout(() => loadSystemConfig(), 500);
        } else {
            showNotification('Failed to generate RSA keys: ' + (result.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error generating RSA keys:', error);
        showNotification('Failed to generate RSA keys', 'error');
    }
}

// Load registered services
async function loadRegisteredServices() {
    try {
        const response = await fetch('/config/services');
        const data = await response.json();
        
        const container = document.getElementById('registeredServicesContainer');
        
        if (data.services.length === 0) {
            container.innerHTML = '<p class="text-muted">No services registered yet.</p>';
            return;
        }
        
        let html = '<div class="services-list">';
        
        for (const service of data.services) {
            const statusBadge = service.enabled 
                ? '<span class="badge badge-success">Enabled</span>' 
                : '<span class="badge badge-secondary">Disabled</span>';
            
            const authBadge = service.requires_auth 
                ? '<span class="badge badge-primary">Auth Required</span>' 
                : '<span class="badge badge-warning">No Auth</span>';
            
            html += `
                <div class="service-card" style="border: 1px solid #e0e0e0; padding: 15px; margin-bottom: 15px; border-radius: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div style="flex: 1;">
                            <h4 style="margin: 0 0 8px 0; color: #333;">
                                <i class="fas fa-server"></i> ${service.service_name}
                            </h4>
                            <p style="margin: 0 0 8px 0; color: #666; font-size: 0.9em;">
                                <strong>ID:</strong> ${service.service_id}
                            </p>
                            <p style="margin: 0 0 8px 0; color: #666; font-size: 0.9em;">
                                <strong>URL:</strong> <code>${service.service_url}</code>
                            </p>
                            ${service.description ? `<p style="margin: 0 0 8px 0; color: #888; font-size: 0.85em;">${service.description}</p>` : ''}
                            <div style="margin-top: 10px;">
                                ${statusBadge}
                                ${authBadge}
                            </div>
                        </div>
                        <div>
                            <button class="btn btn-sm btn-outline" onclick="deleteService('${service.service_id}')" title="Delete service">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            `;
        }
        
        html += '</div>';
        container.innerHTML = html;
    } catch (error) {
        console.error('Error loading registered services:', error);
        document.getElementById('registeredServicesContainer').innerHTML = 
            '<p class="text-error">Error loading services</p>';
    }
}

// Show add service modal
function showAddServiceModal() {
    document.getElementById('addServiceModal').style.display = 'flex';
    document.getElementById('addServiceForm').reset();
}

// Save new service
async function saveNewService() {
    try {
        const serviceData = {
            service_id: document.getElementById('serviceId').value,
            service_name: document.getElementById('serviceName').value,
            service_url: document.getElementById('serviceUrl').value,
            description: document.getElementById('serviceDescription').value,
            enabled: document.getElementById('serviceEnabled').checked,
            requires_auth: document.getElementById('serviceRequiresAuth').checked
        };
        
        const response = await fetch('/config/services', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(serviceData)
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification('Service registered successfully!', 'success');
            closeModal('addServiceModal');
            loadRegisteredServices();
        } else {
            showNotification('Failed to register service: ' + (result.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error saving service:', error);
        showNotification('Failed to register service', 'error');
    }
}

// Delete service
async function deleteService(serviceId) {
    if (!confirm(`Are you sure you want to unregister the service "${serviceId}"?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/config/services/${serviceId}`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification('Service unregistered successfully', 'success');
            loadRegisteredServices();
        } else {
            showNotification('Failed to unregister service: ' + (result.error || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error deleting service:', error);
        showNotification('Failed to unregister service', 'error');
    }
}

// Auto-load configuration when Configuration tab is opened
document.addEventListener('DOMContentLoaded', function() {
    // Hook into tab switching to load config
    const configTab = document.querySelector('[data-tab="configuration"]');
    if (configTab) {
        configTab.addEventListener('click', function() {
            setTimeout(() => {
                loadSystemConfig();
                loadRegisteredServices();
            }, 100);
        });
    }
});
