document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const fileList = document.getElementById('file-list');
    const mergeBtn = document.getElementById('merge-btn');
    const loader = document.getElementById('loader');
    const resultsContent = document.getElementById('results-content');
    const emptyState = document.getElementById('empty-state');
    const configJson = document.getElementById('config-json');
    const schemaJson = document.getElementById('schema-json');
    
    const dropZoneStructured = document.getElementById('drop-zone-structured');
    const fileInputStructured = document.getElementById('file-input-structured');
    const fileListStructured = document.getElementById('file-list-structured');
    
    const dropZoneUnstructured = document.getElementById('drop-zone-unstructured');
    const fileInputUnstructured = document.getElementById('file-input-unstructured');
    const fileListUnstructured = document.getElementById('file-list-unstructured');
    
    const githubUrl = document.getElementById('github-url');
    const linkedinUrl = document.getElementById('linkedin-url');
    
    const mergeBtn = document.getElementById('merge-btn');
    
    let structuredFiles = [];
    let unstructuredFiles = [];

    // --- Helpers ---
    function setupDropZone(dropZone, fileInput, fileArray, listElement) {
        dropZone.addEventListener('click', () => fileInput.click());
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });
        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });
        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            handleFiles(e.dataTransfer.files, fileArray, listElement);
        });
        fileInput.addEventListener('change', (e) => {
            handleFiles(e.target.files, fileArray, listElement);
        });
    }

    function handleFiles(files, fileArray, listElement) {
        for (const file of files) {
            if (!fileArray.some(f => f.name === file.name)) {
                fileArray.push(file);
            }
        }
        updateFileList(fileArray, listElement);
        validateInputs();
    }

    function updateFileList(fileArray, listElement) {
        listElement.innerHTML = '';
        fileArray.forEach((file, index) => {
            const el = document.createElement('div');
            el.className = 'file-item';
            el.innerHTML = `
                <span>${file.name}</span>
                <span class="remove" data-index="${index}">&times;</span>
            `;
            listElement.appendChild(el);
        });

        listElement.querySelectorAll('.remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const index = e.target.getAttribute('data-index');
                fileArray.splice(index, 1);
                updateFileList(fileArray, listElement);
                validateInputs();
            });
        });
    }
    
    function validateInputs() {
        const hasStructured = structuredFiles.length > 0;
        const hasUnstructured = unstructuredFiles.length > 0 || githubUrl.value.trim() !== '' || linkedinUrl.value.trim() !== '';
        
        const hasAny = hasStructured || hasUnstructured;
        
        const ind = document.querySelector('.source-ind');
        if (ind) ind.style.backgroundColor = hasAny ? '#10B981' : '#EF4444';
        
        mergeBtn.disabled = !hasAny;
    }

    // --- Setup ---
    setupDropZone(dropZoneStructured, fileInputStructured, structuredFiles, fileListStructured);
    setupDropZone(dropZoneUnstructured, fileInputUnstructured, unstructuredFiles, fileListUnstructured);
    
    githubUrl.addEventListener('input', validateInputs);
    linkedinUrl.addEventListener('input', validateInputs);

    // Tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            e.target.classList.add('active');
            const targetId = e.target.getAttribute('data-target');
            document.getElementById(`${targetId}-tab`).classList.add('active');
        });
    });

    // Run pipeline
    mergeBtn.addEventListener('click', async () => {
        if (selectedFiles.length === 0) return;

        // Verify JSON
        try {
            JSON.parse(configJson.value);
            JSON.parse(schemaJson.value);
        } catch (e) {
            alert('Invalid JSON in Configuration or Output Schema');
            return;
        }

        const formData = new FormData();
        formData.append('config_json', configJson.value);
        formData.append('output_schema_json', schemaJson.value);
        
        if (githubUrl.value.trim()) formData.append('github_url', githubUrl.value.trim());
        if (linkedinUrl.value.trim()) formData.append('linkedin_url', linkedinUrl.value.trim());
        
        structuredFiles.forEach(file => formData.append('files', file));
        unstructuredFiles.forEach(file => formData.append('files', file));

        // UI updates
        emptyState.classList.add('hidden');
        resultsContent.classList.add('hidden');
        loader.classList.remove('hidden');
        mergeBtn.disabled = true;

        try {
            const response = await fetch('/v1/merge', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.detail || 'Pipeline failed');
            }

            document.getElementById('profiles-json').textContent = JSON.stringify(data.profiles, null, 2);
            document.getElementById('report-json').textContent = JSON.stringify(data.report, null, 2);
            
            loader.classList.add('hidden');
            resultsContent.classList.remove('hidden');
        } catch (error) {
            alert('Error: ' + error.message);
            loader.classList.add('hidden');
            emptyState.classList.remove('hidden');
        } finally {
            mergeBtn.disabled = false;
        }
    });
});
