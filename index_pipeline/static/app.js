// Tab switching functionality
document.addEventListener('DOMContentLoaded', () => {
    // Tab switching
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabName = button.getAttribute('data-tab');

            // Update buttons
            tabButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');

            // Update content
            tabContents.forEach(content => content.classList.remove('active'));
            document.getElementById(`${tabName}-tab`).classList.add('active');

            // Auto-load current prompt when opening the Extraction Prompts tab
            if (tabName === 'prompts') {
                // Only auto-load if the textarea is empty
                const customPromptTextarea = document.getElementById('custom_prompt');
                if (customPromptTextarea && customPromptTextarea.value.trim() === '') {
                    loadCurrentPrompt();
                }
            }
        });
    });

    // Load initial configuration
    loadConfiguration();

    // Auto-refresh status every 5 seconds when on neo4j tab
    // Add delay to prevent flash when first switching to tab
    let lastTabSwitch = Date.now();
    let currentActiveTab = 's3'; // Default tab (s3 is active by default)

    // Track tab switches
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            lastTabSwitch = Date.now();
            currentActiveTab = button.getAttribute('data-tab');
        });
    });

    setInterval(() => {
        const neo4jTab = document.getElementById('neo4j-tab');
        // Only refresh if:
        // 1. Neo4j tab is active
        // 2. Tab has been active for at least 2 seconds
        // 3. Current active tab is actually 'neo4j'
        if (neo4jTab &&
            neo4jTab.classList.contains('active') &&
            currentActiveTab === 'neo4j' &&
            (Date.now() - lastTabSwitch > 2000)) {
            refreshStatus();
        }
    }, 5000);

    // Sub-tab switching for Neo4j nested tabs
    const subTabButtons = document.querySelectorAll('.sub-tab-button');
    const subTabContents = document.querySelectorAll('.sub-tab-content');

    console.log('Found sub-tab buttons:', subTabButtons.length);
    console.log('Found sub-tab contents:', subTabContents.length);

    subTabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const subtab = button.getAttribute('data-subtab');
            console.log('Sub-tab clicked:', subtab);

            // Update sub-tab buttons
            subTabButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');

            // Update sub-tab content
            subTabContents.forEach(content => content.classList.remove('active'));
            const targetContent = document.getElementById(subtab);
            if (targetContent) {
                targetContent.classList.add('active');
                console.log('Activated sub-tab:', subtab);
            } else {
                console.error('Sub-tab content not found:', subtab);
            }
        });
    });
});

// Load configuration from API
async function loadConfiguration() {
    try {
        const response = await fetch('/neo4j/config');
        const config = await response.json();

        // S3 Config
        document.getElementById('use_s3').checked = config.s3.use_s3;
        document.getElementById('aws_region').value = config.s3.aws_region;
        document.getElementById('input_bucket').value = config.s3.input_bucket;
        document.getElementById('input_prefix').value = config.s3.input_prefix;
        document.getElementById('output_bucket').value = config.s3.output_bucket;
        document.getElementById('output_prefix').value = config.s3.output_prefix;
        document.getElementById('max_files').value = config.s3.max_files;

        // Neo4j Config
        document.getElementById('neo4j_uri').value = config.neo4j.uri;
        document.getElementById('neo4j_username').value = config.neo4j.username;
        document.getElementById('neo4j_password').value = config.neo4j.password;
        document.getElementById('neo4j_database').value = config.neo4j.database;

        // LLM Gateway Config
        document.getElementById('llm_model_name').value = config.llm.model_name;
        document.getElementById('llm_api_url').value = config.llm.api_url;
        document.getElementById('llm_api_key').value = config.llm.api_key || '';
        document.getElementById('llm_response_format').value = config.llm.response_format || 'ollama';

        // Embedding Gateway Config
        document.getElementById('embedding_model_name').value = config.embedding.model_name;
        document.getElementById('embedding_api_url').value = config.embedding.api_url;
        document.getElementById('embedding_api_key').value = config.embedding.api_key || '';
        document.getElementById('embedding_response_format').value = config.embedding.response_format || 'ollama';

        // Processing Config
        // docs_folder removed - it's only used internally as temp directory for S3 downloads
        document.getElementById('chunk_size').value = config.processing.chunk_size;
        document.getElementById('chunk_overlap').value = config.processing.chunk_overlap;
        document.getElementById('max_triplets_per_chunk').value = config.processing.max_triplets_per_chunk;
        document.getElementById('prompt_template').value = config.processing.prompt_template || 'default';
        document.getElementById('store_chunk_embeddings').checked = config.processing.store_chunk_embeddings !== false;
        document.getElementById('store_entity_embeddings').checked = config.processing.store_entity_embeddings !== false;

        // Extraction Prompt Config
        document.getElementById('custom_prompt').value = config.extraction_prompt?.custom_prompt || '';

        // Schema Config
        document.getElementById('document_id_field').value = config.schema?.document_id_field || 'id';
        document.getElementById('content_fields').value = (config.schema?.content_fields || ['content']).join(',');
        document.getElementById('metadata_fields').value = (config.schema?.metadata_fields || ['subject', 'author', 'category', 'tags']).join(',');

    } catch (error) {
        console.error('Failed to load configuration:', error);
        // Don't show notification on initial load to avoid flash
    }
}

// Save configuration
async function saveConfiguration() {
    const config = {
        s3: {
            use_s3: document.getElementById('use_s3').checked,
            aws_region: document.getElementById('aws_region').value,
            input_bucket: document.getElementById('input_bucket').value,
            input_prefix: document.getElementById('input_prefix').value,
            output_bucket: document.getElementById('output_bucket').value,
            output_prefix: document.getElementById('output_prefix').value,
            max_files: parseInt(document.getElementById('max_files').value),
        },
        neo4j: {
            uri: document.getElementById('neo4j_uri').value,
            username: document.getElementById('neo4j_username').value,
            password: document.getElementById('neo4j_password').value,
            database: document.getElementById('neo4j_database').value,
        },
        llm: {
            model_name: document.getElementById('llm_model_name').value,
            api_url: document.getElementById('llm_api_url').value,
            api_key: document.getElementById('llm_api_key').value,
            response_format: document.getElementById('llm_response_format').value,
            custom_response_parser: "",
            temperature: 0.1,
            max_tokens: 2048,
            custom_headers: {}
        },
        embedding: {
            model_name: document.getElementById('embedding_model_name').value,
            api_url: document.getElementById('embedding_api_url').value,
            api_key: document.getElementById('embedding_api_key').value,
            response_format: document.getElementById('embedding_response_format').value,
            custom_response_parser: "",
            custom_headers: {}
        },
        processing: {
            docs_folder: 'sample_docs', // Fixed value - used internally as temp directory for S3 downloads
            chunk_size: parseInt(document.getElementById('chunk_size').value),
            chunk_overlap: parseInt(document.getElementById('chunk_overlap').value),
            max_triplets_per_chunk: parseInt(document.getElementById('max_triplets_per_chunk').value),
            prompt_template: document.getElementById('prompt_template').value,
            store_chunk_embeddings: document.getElementById('store_chunk_embeddings').checked,
            store_entity_embeddings: document.getElementById('store_entity_embeddings').checked,
        },
        schema: {
            document_id_field: document.getElementById('document_id_field').value,
            content_fields: document.getElementById('content_fields').value.split(',').map(f => f.trim()).filter(f => f),
            metadata_fields: document.getElementById('metadata_fields').value.split(',').map(f => f.trim()).filter(f => f),
        },
        extraction_prompt: {
            custom_prompt: document.getElementById('custom_prompt').value,
        }
    };

    try {
        const response = await fetch('/neo4j/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(config)
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        showNotification('Configuration saved successfully', 'success');

        // Reload configuration from server to confirm changes
        await loadConfiguration();

    } catch (error) {
        console.error('Failed to save configuration:', error);
        showNotification('Failed to save configuration: ' + error.message, 'error');
    }
}

// Save S3 configuration only (no pipeline reinitialization)
async function saveS3Configuration() {
    console.log('saveS3Configuration called');

    const s3Config = {
        use_s3: document.getElementById('use_s3').checked,
        aws_region: document.getElementById('aws_region').value,
        input_bucket: document.getElementById('input_bucket').value,
        input_prefix: document.getElementById('input_prefix').value,
        output_bucket: document.getElementById('output_bucket').value,
        output_prefix: document.getElementById('output_prefix').value,
        max_files: parseInt(document.getElementById('max_files').value),
    };

    console.log('S3 Config to save:', s3Config);

    try {
        showNotification('Saving S3 configuration...', 'info');

        const response = await fetch('/s3/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(s3Config)
        });

        console.log('Response status:', response.status);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            console.error('Error response:', errorData);
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        console.log('Save successful:', result);
        showNotification('S3 configuration saved successfully!', 'success');

        // Reload configuration from server to confirm changes
        await loadConfiguration();

    } catch (error) {
        console.error('Failed to save S3 configuration:', error);
        showNotification('Failed to save S3 configuration: ' + error.message, 'error');
    }
}

// Test S3 connection using dedicated test endpoint
async function testS3Connection() {
    showNotification('Testing S3 connection...', 'info');

    try {
        const response = await fetch('/s3/test');
        const data = await response.json();

        const statusBox = document.getElementById('s3-status');
        statusBox.style.display = 'block';

        if (response.ok) {
            if (data.status === 'success') {
                statusBox.className = 'status-box status-success';
                statusBox.innerHTML = `
                    <strong>✓ S3 Connection Successful</strong><br>
                    <strong>Bucket:</strong> ${data.bucket}<br>
                    <strong>Region:</strong> ${data.region}<br>
                    <strong>Prefix:</strong> ${data.prefix}<br>
                    <strong>Files Found:</strong> ${data.file_count} JSON files
                `;
                showNotification(`S3 connection successful! Found ${data.file_count} files`, 'success');
            } else if (data.status === 'disabled') {
                statusBox.className = 'status-box status-warning';
                statusBox.innerHTML = `<strong>⚠ ${data.message}</strong>`;
                showNotification(data.message, 'warning');
            }
        } else {
            // Handle HTTP errors
            const errorDetail = data.detail || 'Unknown error';
            statusBox.className = 'status-box status-error';
            statusBox.innerHTML = `<strong>✗ S3 Connection Failed</strong><br>${errorDetail}`;
            showNotification('S3 connection failed: ' + errorDetail, 'error');
        }
    } catch (error) {
        const statusBox = document.getElementById('s3-status');
        statusBox.style.display = 'block';
        statusBox.className = 'status-box status-error';
        statusBox.innerHTML = `<strong>✗ S3 Connection Failed</strong><br>${error.message}`;
        showNotification('S3 connection failed: ' + error.message, 'error');
    }
}

// Test Neo4j connection
async function testNeo4jConnection() {
    showNotification('Testing Neo4j connection...', 'info');

    try {
        // Get Neo4j configuration from form fields
        const neo4jConfig = {
            uri: document.getElementById('neo4j_uri').value,
            username: document.getElementById('neo4j_username').value,
            password: document.getElementById('neo4j_password').value,
            database: document.getElementById('neo4j_database').value
        };

        console.log('Testing Neo4j connection with:', {
            uri: neo4jConfig.uri,
            username: neo4jConfig.username,
            database: neo4jConfig.database
        });

        const response = await fetch('/neo4j/test', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(neo4jConfig)
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
        }

        const result = await response.json();
        const nodeCount = result.node_count || 0;
        showNotification(
            `✓ ${result.message} (${nodeCount} nodes found)`,
            'success'
        );

    } catch (error) {
        console.error('Neo4j connection test failed:', error);
        showNotification('✗ Neo4j connection failed: ' + error.message, 'error');
    }
}

// Test Ollama connection
async function testOllamaConnection() {
    showNotification('Testing Ollama connection...', 'info');

    try {
        const llmUrl = document.getElementById('llm_url').value;
        const response = await fetch(`${llmUrl}/api/tags`);

        if (response.ok) {
            const data = await response.json();
            const modelCount = data.models ? data.models.length : 0;
            showNotification(`Ollama connection successful! Found ${modelCount} models`, 'success');
        } else {
            throw new Error('Failed to connect to Ollama');
        }
    } catch (error) {
        showNotification('Ollama connection failed: ' + error.message, 'error');
    }
}

// Build graph
async function buildGraph() {
    const clearExisting = document.getElementById('clear_before_build').checked;

    try {
        const response = await fetch('/neo4j/build', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                clear_first: clearExisting
            })
        });

        const data = await response.json();
        showNotification(data.message, 'success');

        // Start polling status
        const interval = setInterval(async () => {
            await refreshStatus();
            const statusEl = document.getElementById('pipeline-status');
            if (statusEl.classList.contains('status-completed') || statusEl.classList.contains('status-error')) {
                clearInterval(interval);
            }
        }, 2000);

    } catch (error) {
        showNotification('Build failed: ' + error.message, 'error');
    }
}

// Cache last status to prevent unnecessary updates
let lastStatusUpdate = null;

// Refresh pipeline status
async function refreshStatus() {
    try {
        const response = await fetch('/neo4j/status');
        const data = await response.json();

        const statusBox = document.getElementById('pipeline-status');
        const statusText = document.getElementById('status-text');
        const statusMessage = document.getElementById('status-message');

        if (!statusBox || !statusText || !statusMessage) {
            return; // Elements not in DOM yet
        }

        // Only update if status actually changed
        const statusKey = JSON.stringify(data);
        if (lastStatusUpdate === statusKey) {
            return; // No change, skip update
        }
        lastStatusUpdate = statusKey;

        // Batch DOM updates to minimize reflows
        requestAnimationFrame(() => {
            statusBox.className = 'status-box status-' + data.status;
            statusText.textContent = data.status.toUpperCase();

            let message = '';
            if (data.message) message += data.message;
            if (data.current_step) message += `<br><strong>Step:</strong> ${data.current_step}`;
            if (data.documents_processed) message += `<br><strong>Processed:</strong> ${data.documents_processed}`;
            if (data.documents_skipped) message += `<br><strong>Skipped:</strong> ${data.documents_skipped} (already in Neo4j)`;
            if (data.documents_failed) message += `<br><strong>Failed:</strong> ${data.documents_failed}`;
            statusMessage.innerHTML = message;
        });

        // Fetch and display stats if completed
        if (data.status === 'completed' || data.status === 'idle') {
            await fetchGraphStats();
        }

    } catch (error) {
        console.error('Failed to refresh status:', error);
    }
}

// Cache last stats to prevent unnecessary updates
let lastStatsUpdate = null;

// Fetch graph statistics
async function fetchGraphStats() {
    try {
        const response = await fetch('/neo4j/stats');
        const statsDiv = document.getElementById('graph-stats');
        if (!statsDiv) {
            return; // Element not in DOM yet
        }

        // Handle Neo4j not connected (503)
        if (response.status === 503) {
            const statsKey = 'neo4j_disconnected';
            if (lastStatsUpdate === statsKey) {
                return; // No change, skip update
            }
            lastStatsUpdate = statsKey;
            requestAnimationFrame(() => {
                statsDiv.innerHTML = `
                    <div class="stats-disconnected">
                        <p>Neo4j not connected</p>
                        <p><small>Use POST /neo4j/connect to establish connection</small></p>
                    </div>
                `;
            });
            return;
        }

        const stats = await response.json();

        // Only update if stats actually changed
        const statsKey = JSON.stringify(stats);
        if (lastStatsUpdate === statsKey) {
            return; // No change, skip update
        }
        lastStatsUpdate = statsKey;

        // Batch DOM updates to minimize reflows
        requestAnimationFrame(() => {
            statsDiv.innerHTML = `
                <div class="stats-grid">
                    ${Object.entries(stats).map(([key, value]) => `
                        <div class="stat-card">
                            <div class="stat-value">${value}</div>
                            <div class="stat-label">${key}</div>
                        </div>
                    `).join('')}
                </div>
            `;
        });

    } catch (error) {
        console.error('Failed to fetch stats:', error);
    }
}

// Notification deduplication
const activeNotifications = new Map();

// Show notification with deduplication
function showNotification(message, type = 'info') {
    // Create unique key for this notification
    const key = `${type}:${message}`;

    // If this exact notification is already showing, don't show it again
    if (activeNotifications.has(key)) {
        return;
    }

    // Create notification element with CSS classes instead of inline styles
    const notification = document.createElement('div');
    notification.className = `toast-notification toast-${type} toast-slide-in`;
    notification.textContent = message;

    document.body.appendChild(notification);

    // Mark as active
    activeNotifications.set(key, notification);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.classList.remove('toast-slide-in');
        notification.classList.add('toast-slide-out');
        setTimeout(() => {
            notification.remove();
            activeNotifications.delete(key);
        }, 300);
    }, 5000);
}

// Load current prompt being used
async function loadCurrentPrompt() {
    try {
        const response = await fetch('/neo4j/prompt/current');
        const data = await response.json();

        document.getElementById('custom_prompt').value = data.prompt;

        if (data.source === 'custom') {
            showNotification('Loaded your custom prompt', 'info');
        } else {
            showNotification(`Loaded current prompt (${data.template_name} template)`, 'info');
        }
    } catch (error) {
        console.error('Failed to load current prompt:', error);
        showNotification('Failed to load current prompt: ' + error.message, 'error');
    }
}

// Load default prompt template
function loadDefaultPrompt() {
    const templateName = document.getElementById('prompt_template').value;
    // Map template names to example prompts
    const prompts = {
        'default': `Some text is provided below. Given the text, extract up to {max_knowledge_triplets} knowledge triplets in the form of (subject, predicate, object). Avoid stopwords.
---------------------
Example:
Text: Alice is Bob's mother.
Triplets:
(Alice, is mother of, Bob)

Text: Philz is a coffee shop founded in Berkeley in 1982.
Triplets:
(Philz, is, coffee shop)
(Philz, founded in, Berkeley)
(Philz, founded in, 1982)
---------------------
Text: {text}
Triplets:`,
        'enhanced': `Extract up to {max_knowledge_triplets} knowledge triplets from the text below.

INSTRUCTIONS:
- Format: (subject, predicate, object)
- Focus on meaningful entities and relationships
- Include: people, organizations, locations, events, concepts
- Use specific, descriptive predicates (not just 'is' or 'has')
- Avoid stopwords and generic terms
- Break complex sentences into multiple simple triplets
---------------------
Text: {text}
Triplets:`,
        'business': `Extract up to {max_knowledge_triplets} business-related knowledge triplets.

FOCUS ON:
- People and their roles/positions
- Organizations and their relationships
- Products, services, and offerings
- Events, meetings, and transactions
---------------------
Text: {text}
Triplets:`,
        'research': `Extract up to {max_knowledge_triplets} research-related knowledge triplets.

FOCUS ON:
- Researchers and their affiliations
- Research topics and areas
- Publications and findings
- Methods and techniques
---------------------
Text: {text}
Triplets:`
    };

    document.getElementById('custom_prompt').value = prompts[templateName] || prompts['default'];
    showNotification('Loaded ' + templateName + ' template', 'info');
}

// Clear custom prompt
function clearCustomPrompt() {
    document.getElementById('custom_prompt').value = '';
    showNotification('Custom prompt cleared', 'info');
}

// Add toast notification styles
const style = document.createElement('style');
style.textContent = `
    /* Toast notifications */
    .toast-notification {
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        color: white;
        border-radius: 4px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        z-index: 10000;
        max-width: 400px;
        font-size: 14px;
        pointer-events: auto;
    }

    .toast-success {
        background: #4caf50;
    }

    .toast-error {
        background: #f44336;
    }

    .toast-warning {
        background: #ff9800;
    }

    .toast-info {
        background: #2196f3;
    }

    .toast-slide-in {
        animation: toastSlideIn 0.3s ease forwards;
    }

    .toast-slide-out {
        animation: toastSlideOut 0.3s ease forwards;
    }

    @keyframes toastSlideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes toastSlideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
    .stats-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 10px;
        margin: 10px 0;
        contain: layout;
    }
    .stat-card {
        background: #f5f5f5;
        padding: 15px;
        border-radius: 4px;
        text-align: center;
        border: 1px solid #ddd;
        contain: layout style;
    }
    .stat-value {
        font-size: 24px;
        font-weight: bold;
        color: #333;
    }
    .stat-label {
        font-size: 11px;
        color: #666;
        margin-top: 5px;
    }
    .status-box {
        padding: 12px;
        border-radius: 4px;
        margin: 10px 0;
        border-left: 4px solid;
        contain: layout style;
    }
    .status-idle {
        background: #e3f2fd;
        border-color: #2196f3;
        color: #1976d2;
    }
    .status-running {
        background: #fff3e0;
        border-color: #ff9800;
        color: #f57c00;
    }
    .status-completed {
        background: #e8f5e9;
        border-color: #4caf50;
        color: #388e3c;
    }
    .status-error {
        background: #ffebee;
        border-color: #f44336;
        color: #d32f2f;
    }
    .status-success {
        background: #e8f5e9;
        border-color: #4caf50;
        color: #388e3c;
    }
    .status-warning {
        background: #fff3e0;
        border-color: #ff9800;
        color: #f57c00;
    }
`;
document.head.appendChild(style);

// Vector Index Management Functions
async function checkVectorIndexes() {
    try {
        const statusBox = document.getElementById('vector-index-status');
        statusBox.style.display = 'block';
        statusBox.className = 'status-box status-info';
        statusBox.innerHTML = '<strong>Checking vector indexes...</strong>';

        const response = await fetch('/neo4j/vector-indexes/status');

        // Check if the response is OK (status 200-299)
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        let statusHtml = '<strong>Vector Index Status</strong><br><br>';

        // Entity Index
        if (data.entity_index_exists) {
            statusHtml += `✅ <strong>Entity Index:</strong> EXISTS<br>`;
            statusHtml += `   - Entities with embeddings: ${data.entity_embeddings.count}<br>`;
            if (data.entity_embeddings.dimension) {
                statusHtml += `   - Dimension: ${data.entity_embeddings.dimension}<br>`;
            }
        } else {
            statusHtml += `❌ <strong>Entity Index:</strong> MISSING<br>`;
            statusHtml += `   - Entities with embeddings: ${data.entity_embeddings.count}<br>`;
            if (data.entity_embeddings.count > 0) {
                statusHtml += `   - Dimension: ${data.entity_embeddings.dimension}<br>`;
                statusHtml += `   - ⚠️ You can create this index now!<br>`;
            } else {
                statusHtml += `   - ⚠️ Run pipeline with store_entity_embeddings=True first<br>`;
            }
        }

        statusHtml += '<br>';

        // Chunk Index
        if (data.chunk_index_exists) {
            statusHtml += `✅ <strong>Chunk Index:</strong> EXISTS<br>`;
            statusHtml += `   - Chunks with embeddings: ${data.chunk_embeddings.count}<br>`;
            if (data.chunk_embeddings.dimension) {
                statusHtml += `   - Dimension: ${data.chunk_embeddings.dimension}<br>`;
            }
        } else {
            statusHtml += `❌ <strong>Chunk Index:</strong> MISSING<br>`;
            statusHtml += `   - Chunks with embeddings: ${data.chunk_embeddings.count}<br>`;
            if (data.chunk_embeddings.count > 0) {
                statusHtml += `   - Dimension: ${data.chunk_embeddings.dimension}<br>`;
                statusHtml += `   - ⚠️ You can create this index now!<br>`;
            } else {
                statusHtml += `   - ⚠️ Run pipeline with store_chunk_embeddings=True first<br>`;
            }
        }

        // All other vector indexes
        const otherIndexes = Object.keys(data.vector_indexes).filter(
            name => name !== 'entity' && name !== 'chunk_embedding'
        );
        if (otherIndexes.length > 0) {
            statusHtml += '<br><strong>Other Vector Indexes:</strong><br>';
            otherIndexes.forEach(name => {
                statusHtml += `✅ ${name}<br>`;
            });
        }

        statusBox.className = 'status-box status-info';
        statusBox.innerHTML = statusHtml;
        showNotification('Vector index status checked', 'success');

    } catch (error) {
        const statusBox = document.getElementById('vector-index-status');
        statusBox.style.display = 'block';
        statusBox.className = 'status-box status-error';
        statusBox.innerHTML = `<strong>Error:</strong> ${error.message}`;
        showNotification('Failed to check vector indexes: ' + error.message, 'error');
    }
}

async function createVectorIndexes() {
    if (!confirm('Create/update vector indexes in Neo4j?')) {
        return;
    }

    try {
        const statusBox = document.getElementById('vector-index-status');
        statusBox.style.display = 'block';
        statusBox.className = 'status-box status-running';
        statusBox.innerHTML = '<strong>Creating vector indexes...</strong>';

        // Get dimension values from input fields
        const entityDimInput = document.getElementById('entity_dimension');
        const chunkDimInput = document.getElementById('chunk_dimension');

        const requestBody = {};
        if (entityDimInput && entityDimInput.value) {
            requestBody.entity_dimension = parseInt(entityDimInput.value);
        }
        if (chunkDimInput && chunkDimInput.value) {
            requestBody.chunk_dimension = parseInt(chunkDimInput.value);
        }

        const response = await fetch('/neo4j/vector-indexes/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(requestBody)
        });

        // Check if the response is OK (status 200-299)
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        let statusHtml = '<strong>Vector Index Creation Results</strong><br><br>';

        if (data.dropped_indexes && data.dropped_indexes.length > 0) {
            statusHtml += '<strong>🔄 Updated:</strong><br>';
            data.dropped_indexes.forEach(idx => {
                statusHtml += `   - ${idx.name} (dimension ${idx.new_dimension})<br>`;
            });
            statusHtml += '<br>';
        }

        if (data.created_indexes && data.created_indexes.length > 0) {
            statusHtml += '<strong>✅ Created Indexes:</strong><br>';
            data.created_indexes.forEach(idx => {
                const source = idx.source ? ` [${idx.source}]` : '';
                statusHtml += `   - ${idx.name} (${idx.dimension} dimensions${source})<br>`;
                if (idx.entities_with_embeddings) {
                    statusHtml += `     ${idx.entities_with_embeddings} entities with embeddings<br>`;
                }
                if (idx.chunks_with_embeddings) {
                    statusHtml += `     ${idx.chunks_with_embeddings} chunks with embeddings<br>`;
                }
            });
        }

        if (data.errors && data.errors.length > 0) {
            statusHtml += '<br><strong>⚠️ Errors/Warnings:</strong><br>';
            data.errors.forEach(err => {
                statusHtml += `   - ${err}<br>`;
            });
        }

        statusHtml += `<br><strong>Status:</strong> ${data.message}`;

        statusBox.className = data.status === 'success' ? 'status-box status-success' : 'status-box status-warning';
        statusBox.innerHTML = statusHtml;

        if (data.status === 'success') {
            showNotification('Vector indexes created successfully!', 'success');
        } else {
            showNotification(data.message, 'warning');
        }

        // Auto-refresh status after 2 seconds
        setTimeout(checkVectorIndexes, 2000);

    } catch (error) {
        const statusBox = document.getElementById('vector-index-status');
        statusBox.style.display = 'block';
        statusBox.className = 'status-box status-error';
        statusBox.innerHTML = `<strong>Error:</strong> ${error.message}`;
        showNotification('Failed to create vector indexes: ' + error.message, 'error');
    }
}

// ============================================================================
// OpenSearch Mapping File Upload/Download
// ============================================================================

async function downloadMappingFile() {
    try {
        showNotification('Downloading mapping file...', 'info');

        const response = await fetch('/opensearch/mapping/download');

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Download failed');
        }

        // Get the blob from response
        const blob = await response.blob();

        // Get filename from Content-Disposition header or use default
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'events_mapping.json';
        if (contentDisposition) {
            // Match filename with or without quotes, and trim any trailing quotes/underscores
            const filenameMatch = contentDisposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
            if (filenameMatch && filenameMatch[1]) {
                // Remove quotes and trim whitespace
                filename = filenameMatch[1].replace(/['"]/g, '').trim();
            }
        }

        // Create download link and trigger download
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);

        showNotification('Mapping file downloaded successfully!', 'success');

    } catch (error) {
        console.error('Download error:', error);
        showNotification('Failed to download mapping file: ' + error.message, 'error');
    }
}

async function handleMappingFileUpload(event) {
    const file = event.target.files[0];
    if (!file) {
        return;
    }

    // Validate file type
    if (!file.name.endsWith('.json')) {
        showNotification('Invalid file type. Please upload a JSON file.', 'error');
        event.target.value = ''; // Reset file input
        return;
    }

    const statusBox = document.getElementById('mapping-upload-status');
    statusBox.style.display = 'block';
    statusBox.className = 'status-box';
    statusBox.innerHTML = '<strong>⏳ Uploading mapping file...</strong>';

    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch('/opensearch/mapping/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Upload failed');
        }

        // Show success message with details
        let statusHtml = '<strong>✅ Mapping File Uploaded Successfully!</strong><br><br>';
        statusHtml += `<strong>Uploaded:</strong> ${data.filename}<br>`;
        statusHtml += `<strong>Saved as:</strong> ${data.saved_as}<br>`;
        statusHtml += `<strong>Backup created:</strong> ${data.backup_created}<br>`;
        statusHtml += `<strong>Fields in mapping:</strong> ${data.field_count}<br><br>`;
        statusHtml += `<strong>⚠️ Important:</strong> ${data.note}`;

        statusBox.className = 'status-box status-success';
        statusBox.innerHTML = statusHtml;

        showNotification('Mapping file uploaded successfully! Use "Clear existing data" to apply changes.', 'success');

        // Reset file input
        event.target.value = '';

        // Auto-hide status after 10 seconds
        setTimeout(() => {
            statusBox.style.display = 'none';
        }, 10000);

    } catch (error) {
        console.error('Upload error:', error);

        statusBox.className = 'status-box status-error';
        statusBox.innerHTML = `<strong>❌ Upload Failed:</strong><br>${error.message}`;

        showNotification('Failed to upload mapping file: ' + error.message, 'error');

        // Reset file input
        event.target.value = '';
    }
}

// Sub-tab switching for Neo4j nested tabs
document.addEventListener('DOMContentLoaded', () => {
    const subTabButtons = document.querySelectorAll('.sub-tab-button');
    const subTabContents = document.querySelectorAll('.sub-tab-content');

    subTabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const subtab = button.getAttribute('data-subtab');

            // Update sub-tab buttons
            subTabButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');

            // Update sub-tab content
            subTabContents.forEach(content => content.classList.remove('active'));
            const targetContent = document.getElementById(subtab);
            if (targetContent) {
                targetContent.classList.add('active');
            }
        });
    });
});
