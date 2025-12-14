// OpenSearch Management Functions
// Handles all OpenSearch-related UI interactions and API calls

// Load OpenSearch configuration from server
async function loadOpenSearchConfiguration() {
    try {
        const response = await fetch('/opensearch/config');
        const fullConfig = await response.json();

        // OpenSearch connection settings
        const config = fullConfig.opensearch || fullConfig;
        document.getElementById('opensearch_host').value = config.host || 'localhost';
        document.getElementById('opensearch_port').value = config.port || 9200;
        document.getElementById('opensearch_username').value = config.username || '';
        document.getElementById('opensearch_password').value = config.password || '';
        document.getElementById('opensearch_index_name').value = config.index_name || 'documents';
        document.getElementById('opensearch_use_ssl').checked = config.use_ssl || false;

        // Processing configuration
        const processing = fullConfig.processing || {};
        document.getElementById('opensearch_chunk_size').value = processing.chunk_size || 512;
        document.getElementById('opensearch_chunk_overlap').value = processing.chunk_overlap || 50;

        // Embedding configuration
        const embedding = fullConfig.embedding || {};
        document.getElementById('opensearch_embedding_provider').value = embedding.provider || 'local';
        document.getElementById('opensearch_embedding_dimension').value = embedding.embedding_dimension || 768;
        document.getElementById('opensearch_embedding_model').value = embedding.model_name || 'nomic-embed-text';
        document.getElementById('opensearch_embedding_api_url').value = embedding.api_url || 'http://localhost:11434/api/embeddings';
        document.getElementById('opensearch_embedding_api_key').value = embedding.api_key || '';
        document.getElementById('opensearch_embedding_use_bearer').checked = embedding.use_bearer_token || false;
        document.getElementById('opensearch_embedding_response_format').value = embedding.response_format || 'ollama';
        document.getElementById('opensearch_embedding_custom_parser').value = embedding.custom_response_parser || '';
        document.getElementById('opensearch_gemini_api_key').value = embedding.gemini_api_key || '';
        document.getElementById('opensearch_gemini_model').value = embedding.gemini_model || 'models/text-embedding-004';

        // Toggle provider sections visibility
        toggleEmbeddingProviderSections();

        // Schema configuration
        const schema = fullConfig.schema || {};
        document.getElementById('opensearch_document_id_field').value = schema.document_id_field || 'id';
        document.getElementById('opensearch_content_fields').value = (schema.content_fields || ['content']).join(',');

        // Mapping file configuration
        const mapping = fullConfig.mapping || {};
        document.getElementById('opensearch_mapping_file').value = mapping.mapping_file || 'events_mapping.json';

        // Auto-generate mapping configuration
        const autoGenerate = mapping.auto_generate || false;
        document.getElementById('opensearch_auto_generate_mapping').checked = autoGenerate;
        document.getElementById('opensearch_sample_size').value = mapping.sample_size || 100;

        // Toggle visibility of manual vs auto sections
        toggleMappingSections(autoGenerate);

    } catch (error) {
        console.error('Failed to load OpenSearch configuration:', error);
    }
}

// Toggle visibility between manual mapping and auto-generate sections
function toggleMappingSections(autoGenerate) {
    const manualSection = document.getElementById('manual-mapping-section');
    const autoSection = document.getElementById('auto-mapping-section');

    if (autoGenerate) {
        manualSection.style.display = 'none';
        autoSection.style.display = 'block';
    } else {
        manualSection.style.display = 'block';
        autoSection.style.display = 'none';
    }
}

// Save OpenSearch configuration to server
async function saveOpenSearchConfiguration() {
    // Note: S3 configuration is managed separately via the main S3 Configuration tab
    // This function only saves OpenSearch-specific settings
    const fullConfig = {
        opensearch: {
            host: document.getElementById('opensearch_host').value,
            port: parseInt(document.getElementById('opensearch_port').value),
            username: document.getElementById('opensearch_username').value,
            password: document.getElementById('opensearch_password').value,
            index_name: document.getElementById('opensearch_index_name').value,
            use_ssl: document.getElementById('opensearch_use_ssl').checked,
            verify_certs: false,
            number_of_shards: 1,
            number_of_replicas: 0
        },
        processing: {
            chunk_size: parseInt(document.getElementById('opensearch_chunk_size').value),
            chunk_overlap: parseInt(document.getElementById('opensearch_chunk_overlap').value)
        },
        embedding: {
            provider: document.getElementById('opensearch_embedding_provider').value,
            model_name: document.getElementById('opensearch_embedding_model').value,
            api_url: document.getElementById('opensearch_embedding_api_url').value,
            api_key: document.getElementById('opensearch_embedding_api_key').value,
            use_bearer_token: document.getElementById('opensearch_embedding_use_bearer').checked,
            custom_headers: {},
            request_body_template: null,
            response_format: document.getElementById('opensearch_embedding_response_format').value,
            custom_response_parser: document.getElementById('opensearch_embedding_custom_parser').value,
            embedding_dimension: parseInt(document.getElementById('opensearch_embedding_dimension').value),
            gemini_api_key: document.getElementById('opensearch_gemini_api_key').value,
            gemini_model: document.getElementById('opensearch_gemini_model').value
        },
        schema: {
            document_id_field: document.getElementById('opensearch_document_id_field').value,
            content_fields: document.getElementById('opensearch_content_fields').value.split(',').map(f => f.trim()).filter(f => f)
        },
        mapping: {
            mapping_file: document.getElementById('opensearch_mapping_file').value,
            auto_generate: document.getElementById('opensearch_auto_generate_mapping').checked,
            sample_size: parseInt(document.getElementById('opensearch_sample_size').value) || 100
        }
    };

    try {
        const response = await fetch('/opensearch/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(fullConfig)
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        showNotification('OpenSearch configuration saved successfully', 'success');

    } catch (error) {
        console.error('Failed to save OpenSearch configuration:', error);
        showNotification('Failed to save OpenSearch configuration: ' + error.message, 'error');
    }
}

// Test OpenSearch connection
async function testOpenSearchConnection() {
    showNotification('Testing OpenSearch connection...', 'info');

    try {
        const statusBox = document.getElementById('opensearch-status');
        statusBox.style.display = 'block';
        statusBox.className = 'status-box status-running';
        statusBox.innerHTML = '<strong>Testing connection...</strong>';

        const response = await fetch('/opensearch/test');
        const data = await response.json();

        if (response.ok && data.status === 'success') {
            statusBox.className = 'status-box status-success';
            statusBox.innerHTML = `
                <strong>✓ OpenSearch Connection Successful</strong><br>
                Version: ${data.version}<br>
                Cluster: ${data.cluster_name}
            `;
            showNotification('OpenSearch connection successful!', 'success');
        } else {
            throw new Error(data.message || 'Connection failed');
        }
    } catch (error) {
        const statusBox = document.getElementById('opensearch-status');
        statusBox.style.display = 'block';
        statusBox.className = 'status-box status-error';
        statusBox.innerHTML = `<strong>✗ OpenSearch Connection Failed</strong><br>${error.message}`;
        showNotification('OpenSearch connection failed: ' + error.message, 'error');
    }
}

// Build OpenSearch index with data from S3 or local files
async function buildOpenSearchIndex() {
    // Get clear_first checkbox value
    const clearFirst = document.getElementById('opensearch_clear_first').checked;

    let confirmMessage = 'Load data to OpenSearch?\n\nThis will:\n- Process all documents from S3\n- Create text chunks\n- Generate embeddings for hybrid search\n- Index with both TF-IDF and vector capabilities';

    if (clearFirst) {
        confirmMessage += '\n\n⚠️ WARNING: Existing data will be CLEARED first (force reload)';
    } else {
        confirmMessage += '\n\n✓ Existing documents will be skipped (idempotent)';
    }

    if (!confirm(confirmMessage)) {
        return;
    }

    try {
        const statusBox = document.getElementById('opensearch-index-status');
        statusBox.style.display = 'block';
        statusBox.className = 'status-box status-running';
        statusBox.innerHTML = clearFirst
            ? '<strong>Clearing index and starting fresh load...</strong>'
            : '<strong>Starting OpenSearch indexing...</strong>';

        const response = await fetch('/opensearch/build', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ clear_first: clearFirst })
        });

        const data = await response.json();

        if (response.ok) {
            showNotification(data.message, 'success');

            // Poll for status updates
            const interval = setInterval(async () => {
                try {
                    const statusResp = await fetch('/opensearch/status');
                    const statusData = await statusResp.json();

                    let statusHtml = `<strong>Status:</strong> ${statusData.status.toUpperCase()}<br>`;

                    if (statusData.current_step) {
                        statusHtml += `<strong>Step:</strong> ${statusData.current_step}<br>`;
                    }

                    statusHtml += `<strong>Processed:</strong> ${statusData.documents_processed} documents<br>`;
                    statusHtml += `<strong>Skipped:</strong> ${statusData.documents_skipped} (already indexed)<br>`;

                    if (statusData.documents_failed > 0) {
                        statusHtml += `<strong>Failed:</strong> ${statusData.documents_failed}<br>`;
                    }

                    statusBox.innerHTML = statusHtml;

                    if (statusData.status === 'completed') {
                        clearInterval(interval);
                        statusBox.className = 'status-box status-success';

                        // Build final summary with all counts
                        let finalHtml = '<strong>✅ OpenSearch Indexing Complete!</strong><br><br>';
                        finalHtml += `<strong>Job Summary:</strong><br>`;
                        finalHtml += `   ✅ Processed: ${statusData.documents_processed} documents<br>`;
                        finalHtml += `   ⊘ Skipped: ${statusData.documents_skipped} (already indexed)<br>`;

                        if (statusData.documents_failed > 0) {
                            finalHtml += `   ❌ Failed: ${statusData.documents_failed}<br>`;
                        }

                        const total = statusData.documents_processed + statusData.documents_skipped + statusData.documents_failed;
                        finalHtml += `   📊 Total handled: ${total}<br><br>`;

                        if (statusData.completed_at) {
                            finalHtml += `<small>Completed: ${new Date(statusData.completed_at).toLocaleString()}</small>`;
                        }

                        statusBox.innerHTML = finalHtml;
                        showNotification('OpenSearch indexing completed!', 'success');

                        // Final summary stays visible (no auto-refresh)
                    } else if (statusData.status === 'error') {
                        clearInterval(interval);
                        statusBox.className = 'status-box status-error';

                        // Build error summary with counts
                        let errorHtml = '<strong>❌ OpenSearch Indexing Failed</strong><br><br>';
                        errorHtml += `<strong>Error:</strong> ${statusData.message}<br><br>`;
                        errorHtml += `<strong>Progress before failure:</strong><br>`;
                        errorHtml += `   Processed: ${statusData.documents_processed}<br>`;
                        errorHtml += `   Skipped: ${statusData.documents_skipped}<br>`;
                        errorHtml += `   Failed: ${statusData.documents_failed}<br>`;

                        statusBox.innerHTML = errorHtml;
                        showNotification('OpenSearch indexing failed', 'error');
                    }
                } catch (pollError) {
                    console.error('Error polling status:', pollError);
                }
            }, 2000);

        } else {
            throw new Error(data.message || 'Build failed');
        }

    } catch (error) {
        const statusBox = document.getElementById('opensearch-index-status');
        statusBox.className = 'status-box status-error';
        statusBox.innerHTML = `<strong>Error:</strong> ${error.message}`;
        showNotification('Failed to build OpenSearch index: ' + error.message, 'error');
    }
}

// Delete OpenSearch index
async function deleteOpenSearchIndex() {
    if (!confirm('⚠️ WARNING: This will permanently delete the entire OpenSearch index and all documents!\n\nAre you sure you want to continue?')) {
        return;
    }

    try {
        const statusBox = document.getElementById('opensearch-index-status');
        statusBox.style.display = 'block';
        statusBox.className = 'status-box status-running';
        statusBox.innerHTML = '<strong>Deleting index...</strong>';

        const response = await fetch('/opensearch/index/delete', {
            method: 'POST'
        });

        const data = await response.json();

        if (response.ok) {
            statusBox.className = 'status-box status-success';
            statusBox.innerHTML = `<strong>✓ Index deleted successfully</strong><br>The index and all documents have been removed.`;
            showNotification('OpenSearch index deleted', 'success');
        } else {
            throw new Error(data.message || 'Failed to delete index');
        }

    } catch (error) {
        const statusBox = document.getElementById('opensearch-index-status');
        statusBox.className = 'status-box status-error';
        statusBox.innerHTML = `<strong>Error:</strong> ${error.message}`;
        showNotification('Failed to delete index: ' + error.message, 'error');
    }
}

// Auto-load configuration when OpenSearch tab is opened
document.addEventListener('DOMContentLoaded', () => {
    const opensearchTab = document.querySelector('[data-tab="opensearch"]');
    if (opensearchTab) {
        opensearchTab.addEventListener('click', () => {
            // Load configuration when tab is clicked
            loadOpenSearchConfiguration();
        });
    }

    // Add event listener for auto-generate mapping checkbox
    const autoGenerateCheckbox = document.getElementById('opensearch_auto_generate_mapping');
    if (autoGenerateCheckbox) {
        autoGenerateCheckbox.addEventListener('change', (e) => {
            toggleMappingSections(e.target.checked);
        });
    }
});

// Toggle visibility between local and Gemini embedding sections
function toggleEmbeddingProviderSections() {
    const provider = document.getElementById('opensearch_embedding_provider').value;
    const localSection = document.getElementById('local-embedding-section');
    const geminiSection = document.getElementById('gemini-embedding-section');

    if (provider === 'gemini') {
        localSection.style.display = 'none';
        geminiSection.style.display = 'block';
    } else {
        localSection.style.display = 'block';
        geminiSection.style.display = 'none';
    }
}

// Preview generated mapping from sample data
async function previewGeneratedMapping() {
    const previewBox = document.getElementById('generated-mapping-preview');
    previewBox.style.display = 'block';
    previewBox.className = 'status-box status-running';
    previewBox.innerHTML = '<strong>Generating mapping from sample data...</strong>';

    try {
        const sampleSize = parseInt(document.getElementById('opensearch_sample_size').value) || 100;

        const response = await fetch('/opensearch/mapping/generate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ sample_size: sampleSize })
        });

        const data = await response.json();

        if (response.ok) {
            previewBox.className = 'status-box status-success';

            // Format the mapping for display
            let html = '<strong>✓ Generated Mapping Preview</strong><br><br>';
            html += `<strong>Fields detected:</strong> ${data.field_count}<br>`;
            html += `<strong>Sample file:</strong> ${data.sample_file || 'N/A'}<br><br>`;

            // Show field summary
            if (data.field_summary) {
                html += '<strong>Field Types:</strong><br>';
                html += `<small style="font-family: monospace;">`;
                for (const [fieldType, fields] of Object.entries(data.field_summary)) {
                    html += `  ${fieldType}: ${fields.join(', ')}<br>`;
                }
                html += '</small><br>';
            }

            // Show full mapping in collapsible section
            html += '<details style="margin-top: 10px;">';
            html += '<summary style="cursor: pointer; color: #2196f3;">View Full Mapping JSON</summary>';
            html += `<pre style="background: #f5f5f5; padding: 10px; border-radius: 4px; overflow-x: auto; max-height: 400px; font-size: 11px;">${JSON.stringify(data.mapping, null, 2)}</pre>`;
            html += '</details>';

            previewBox.innerHTML = html;
        } else {
            throw new Error(data.detail || 'Failed to generate mapping');
        }

    } catch (error) {
        previewBox.className = 'status-box status-error';
        previewBox.innerHTML = `<strong>Error:</strong> ${error.message}`;
        showNotification('Failed to generate mapping preview: ' + error.message, 'error');
    }
}
