(() => {
    'use strict';

    const SAMPLE_RADIUS = 2;
    const DEFAULT_TOLERANCE = 24;

    const el = {
        file: document.getElementById('sheet-file'),
        clear: document.getElementById('sheet-clear'),
        enable: document.getElementById('sheet-bg-enable'),
        tools: document.getElementById('sheet-bg-tools'),
        preview: document.getElementById('sheet-bg-preview'),
        tolerance: document.getElementById('sheet-bg-tolerance'),
        edgeOnly: document.getElementById('sheet-bg-edge-only'),
        reset: document.getElementById('sheet-bg-reset'),
        swatch: document.getElementById('sheet-bg-swatch'),
        color: document.getElementById('sheet-bg-color'),
        status: document.getElementById('sheet-bg-status'),
        previewMode: document.getElementById('sheet-bg-preview-mode')
    };

    if (!el.file || !el.enable || !el.preview) return;

    simplifyBackgroundUi();

    const previewContext = el.preview.getContext('2d');
    let injecting = false;
    let loadGeneration = 0;
    let processGeneration = 0;

    const state = {
        originalFile: null,
        originalImage: null,
        originalUrl: '',
        width: 0,
        height: 0,
        sampled: false,
        sampleX: 0,
        sampleY: 0,
        color: { r: 0, g: 0, b: 0 },
        autoTolerance: DEFAULT_TOLERANCE,
        manualTolerance: false,
        processedCanvas: null,
        removedPixels: 0,
        recoveredOutlinePixels: 0
    };

    function simplifyBackgroundUi() {
        const controls = document.querySelector('.background-controls');
        if (controls && !controls.closest('.background-expert')) {
            const details = document.createElement('details');
            details.className = 'splitter-advanced background-expert';
            details.style.marginTop = '12px';
            const summary = document.createElement('summary');
            summary.textContent = 'Background cleanup settings (usually not needed)';
            controls.parentNode.insertBefore(details, controls);
            details.appendChild(summary);
            details.appendChild(controls);
        }
        const hint = document.querySelector('.background-hint');
        if (hint) {
            hint.innerHTML = '<strong>Recommended:</strong> just tap a clean part of the background once. The tool chooses a safe tolerance automatically and protects dark pixel-art outlines when possible. Open the settings above only if the preview still needs adjustment.';
        }
        const badge = document.querySelector('.background-badge');
        if (badge) badge.textContent = 'ONE TAP · AUTO CLEANUP';
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');
    }

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }

    function setStatus(kind, html) {
        if (!el.status) return;
        el.status.className = `background-status ${kind || ''}`.trim();
        el.status.innerHTML = html;
    }

    function loadImage(url) {
        return new Promise((resolve, reject) => {
            const image = new Image();
            image.onload = () => resolve(image);
            image.onerror = () => reject(new Error('The Sprite Sheet could not be decoded.'));
            image.src = url;
        });
    }

    function canvasBlob(canvas) {
        return new Promise((resolve, reject) => {
            canvas.toBlob(blob => {
                if (blob) resolve(blob);
                else reject(new Error('Could not encode the cleaned Sprite Sheet as PNG.'));
            }, 'image/png');
        });
    }

    function toleranceValue() {
        if (!state.manualTolerance) return state.autoTolerance;
        const value = Number.parseInt(el.tolerance?.value, 10);
        return clamp(Number.isFinite(value) ? value : state.autoTolerance, 0, 255);
    }

    function disposeOriginal() {
        loadGeneration += 1;
        processGeneration += 1;
        if (state.originalUrl) URL.revokeObjectURL(state.originalUrl);
        state.originalFile = null;
        state.originalImage = null;
        state.originalUrl = '';
        state.width = 0;
        state.height = 0;
        state.sampled = false;
        state.sampleX = 0;
        state.sampleY = 0;
        state.color = { r: 0, g: 0, b: 0 };
        state.autoTolerance = DEFAULT_TOLERANCE;
        state.manualTolerance = false;
        state.processedCanvas = null;
        state.removedPixels = 0;
        state.recoveredOutlinePixels = 0;
        el.preview.width = 1;
        el.preview.height = 1;
        previewContext.clearRect(0, 0, 1, 1);
        if (el.tools) el.tools.hidden = !el.enable.checked;
        updateSampleDisplay();
    }

    function updateSampleDisplay() {
        if (!el.swatch || !el.color) return;
        if (!state.sampled) {
            el.swatch.style.background = 'transparent';
            el.swatch.classList.add('empty');
            el.color.textContent = 'No color sampled';
            return;
        }
        const { r, g, b } = state.color;
        el.swatch.classList.remove('empty');
        el.swatch.style.background = `rgb(${r}, ${g}, ${b})`;
        el.color.textContent = `rgb(${r}, ${g}, ${b})`;
    }

    function drawPreview(source = null, mode = 'original') {
        const image = source || state.originalImage;
        if (!image || !state.width || !state.height) return;
        const maxWidth = 920;
        const maxHeight = 420;
        const scale = Math.min(1, maxWidth / state.width, maxHeight / state.height);
        const width = Math.max(1, Math.round(state.width * scale));
        const height = Math.max(1, Math.round(state.height * scale));
        el.preview.width = width;
        el.preview.height = height;
        previewContext.clearRect(0, 0, width, height);
        previewContext.imageSmoothingEnabled = false;
        previewContext.drawImage(image, 0, 0, width, height);

        if (state.sampled) {
            const x = (state.sampleX / state.width) * width;
            const y = (state.sampleY / state.height) * height;
            previewContext.save();
            previewContext.lineWidth = 2;
            previewContext.strokeStyle = '#3bff00';
            previewContext.fillStyle = 'rgba(0,0,0,.72)';
            previewContext.beginPath();
            previewContext.arc(x, y, 8, 0, Math.PI * 2);
            previewContext.fill();
            previewContext.stroke();
            previewContext.beginPath();
            previewContext.moveTo(x - 12, y);
            previewContext.lineTo(x + 12, y);
            previewContext.moveTo(x, y - 12);
            previewContext.lineTo(x, y + 12);
            previewContext.stroke();
            previewContext.restore();
        }
        if (el.previewMode) el.previewMode.textContent = mode === 'processed' ? 'processed preview' : 'original preview';
    }

    async function rememberOriginalFile(file) {
        if (!file) return;
        const generation = ++loadGeneration;
        processGeneration += 1;
        if (state.originalUrl) URL.revokeObjectURL(state.originalUrl);
        state.originalFile = null;
        state.originalImage = null;
        state.originalUrl = '';
        state.processedCanvas = null;
        state.sampled = false;
        state.removedPixels = 0;
        state.recoveredOutlinePixels = 0;
        state.manualTolerance = false;
        updateSampleDisplay();

        const url = URL.createObjectURL(file);
        try {
            const image = await loadImage(url);
            if (generation !== loadGeneration) {
                URL.revokeObjectURL(url);
                return;
            }
            state.originalFile = file;
            state.originalImage = image;
            state.originalUrl = url;
            state.width = image.naturalWidth;
            state.height = image.naturalHeight;
            if (el.tools) el.tools.hidden = !el.enable.checked;
            drawPreview(image, 'original');
            if (el.enable.checked) {
                setStatus('info', '<strong>Ready.</strong> Tap or click once on a clean part of the solid background. The tool will choose the cleanup tolerance automatically.');
            } else {
                setStatus('info', 'If this sheet has a solid-color background, enable <strong>Remove solid background</strong> and tap that background once.');
            }
        } catch (error) {
            URL.revokeObjectURL(url);
            if (generation === loadGeneration) setStatus('error', `<strong>Background preview failed:</strong> ${escapeHtml(error.message)}`);
        }
    }

    function sampleOriginalArea(x, y) {
        if (!state.originalImage) throw new Error('Load a Sprite Sheet first.');
        const centerX = clamp(Math.round(x), 0, state.width - 1);
        const centerY = clamp(Math.round(y), 0, state.height - 1);
        const x1 = Math.max(0, centerX - SAMPLE_RADIUS);
        const y1 = Math.max(0, centerY - SAMPLE_RADIUS);
        const x2 = Math.min(state.width, centerX + SAMPLE_RADIUS + 1);
        const y2 = Math.min(state.height, centerY + SAMPLE_RADIUS + 1);
        const width = Math.max(1, x2 - x1);
        const height = Math.max(1, y2 - y1);

        const sampleCanvas = document.createElement('canvas');
        sampleCanvas.width = width;
        sampleCanvas.height = height;
        const context = sampleCanvas.getContext('2d', { willReadFrequently: true });
        context.imageSmoothingEnabled = false;
        context.drawImage(state.originalImage, x1, y1, width, height, 0, 0, width, height);
        const data = context.getImageData(0, 0, width, height).data;
        const samples = [];
        let red = 0;
        let green = 0;
        let blue = 0;
        for (let i = 0; i < data.length; i += 4) {
            if (data[i + 3] === 0) continue;
            const sample = { r: data[i], g: data[i + 1], b: data[i + 2] };
            samples.push(sample);
            red += sample.r;
            green += sample.g;
            blue += sample.b;
        }
        if (!samples.length) throw new Error('The tapped area is already transparent. Tap an opaque part of the solid background instead.');

        const color = {
            r: Math.round(red / samples.length),
            g: Math.round(green / samples.length),
            b: Math.round(blue / samples.length)
        };
        let maxDistance = 0;
        for (const sample of samples) {
            const distance = Math.hypot(sample.r - color.r, sample.g - color.g, sample.b - color.b);
            if (distance > maxDistance) maxDistance = distance;
        }

        state.sampleX = centerX;
        state.sampleY = centerY;
        state.color = color;
        state.autoTolerance = clamp(Math.ceil(Math.max(DEFAULT_TOLERANCE, maxDistance * 2.5 + 8)), 12, 72);
        state.manualTolerance = false;
        state.sampled = true;
        if (el.tolerance) el.tolerance.value = state.autoTolerance;
        updateSampleDisplay();
    }

    function isBackgroundCandidate(data, pixelIndex, toleranceSquared) {
        const offset = pixelIndex * 4;
        if (data[offset + 3] === 0) return false;
        const dr = data[offset] - state.color.r;
        const dg = data[offset + 1] - state.color.g;
        const db = data[offset + 2] - state.color.b;
        return dr * dr + dg * dg + db * db <= toleranceSquared;
    }

    function removeMatchingBackground(imageData, width, height, tolerance, edgeOnly) {
        const data = imageData.data;
        const total = width * height;
        const toleranceSquared = tolerance * tolerance;
        const removedMask = new Uint8Array(total);
        let removed = 0;

        function remove(index) {
            if (removedMask[index]) return;
            removedMask[index] = 1;
            data[index * 4 + 3] = 0;
            removed += 1;
        }

        if (!edgeOnly) {
            for (let index = 0; index < total; index += 1) {
                if (isBackgroundCandidate(data, index, toleranceSquared)) remove(index);
            }
            return { removed, removedMask };
        }

        const visited = new Uint8Array(total);
        const queue = new Int32Array(total);
        let head = 0;
        let tail = 0;

        function enqueue(index) {
            if (index < 0 || index >= total || visited[index]) return;
            visited[index] = 1;
            if (!isBackgroundCandidate(data, index, toleranceSquared)) return;
            queue[tail++] = index;
        }

        for (let x = 0; x < width; x += 1) {
            enqueue(x);
            if (height > 1) enqueue((height - 1) * width + x);
        }
        for (let y = 1; y + 1 < height; y += 1) {
            enqueue(y * width);
            if (width > 1) enqueue(y * width + width - 1);
        }

        while (head < tail) {
            const index = queue[head++];
            const y = Math.floor(index / width);
            const x = index - y * width;
            remove(index);
            if (x > 0) enqueue(index - 1);
            if (x + 1 < width) enqueue(index + 1);
            if (y > 0) enqueue(index - width);
            if (y + 1 < height) enqueue(index + width);
            if (x > 0 && y > 0) enqueue(index - width - 1);
            if (x + 1 < width && y > 0) enqueue(index - width + 1);
            if (x > 0 && y + 1 < height) enqueue(index + width - 1);
            if (x + 1 < width && y + 1 < height) enqueue(index + width + 1);
        }
        return { removed, removedMask };
    }

    function recoverDarkOutlinePixels(imageData, originalData, width, height, removedMask, edgeOnly) {
        if (!edgeOnly) return 0;
        const luminance = 0.2126 * state.color.r + 0.7152 * state.color.g + 0.0722 * state.color.b;
        if (luminance > 48) return 0;
        const data = imageData.data;
        const total = width * height;
        const surviving = new Uint8Array(total);
        for (let index = 0; index < total; index += 1) surviving[index] = data[index * 4 + 3] > 0 ? 1 : 0;
        let recovered = 0;

        for (let index = 0; index < total; index += 1) {
            if (!removedMask[index]) continue;
            const y = Math.floor(index / width);
            const x = index - y * width;
            let neighbors = 0;
            for (let oy = -1; oy <= 1; oy += 1) {
                for (let ox = -1; ox <= 1; ox += 1) {
                    if (!ox && !oy) continue;
                    const nx = x + ox;
                    const ny = y + oy;
                    if (nx < 0 || nx >= width || ny < 0 || ny >= height) continue;
                    if (surviving[ny * width + nx]) neighbors += 1;
                }
            }
            if (neighbors < 2) continue;
            const offset = index * 4;
            data[offset] = originalData[offset];
            data[offset + 1] = originalData[offset + 1];
            data[offset + 2] = originalData[offset + 2];
            data[offset + 3] = originalData[offset + 3];
            recovered += 1;
        }
        return recovered;
    }

    function setFileInput(file) {
        if (typeof DataTransfer === 'undefined') throw new Error('This browser cannot pass the cleaned image to the Sprite Sheet detector automatically.');
        const transfer = new DataTransfer();
        transfer.items.add(file);
        injecting = true;
        el.file.files = transfer.files;
        el.file.dispatchEvent(new Event('change', { bubbles: true }));
    }

    async function injectOriginal() {
        if (!state.originalFile) return;
        state.processedCanvas = null;
        state.removedPixels = 0;
        state.recoveredOutlinePixels = 0;
        drawPreview(state.originalImage, 'original');
        setFileInput(state.originalFile);
    }

    async function applyBackgroundRemoval() {
        if (!el.enable.checked || !state.originalImage || !state.sampled) return;
        const generation = ++processGeneration;
        const tolerance = toleranceValue();
        if (el.tolerance) el.tolerance.value = tolerance;
        setStatus('info', 'Cleaning the sampled background and re-running Smart detection…');
        await new Promise(resolve => requestAnimationFrame(resolve));

        try {
            const work = document.createElement('canvas');
            work.width = state.width;
            work.height = state.height;
            const context = work.getContext('2d', { willReadFrequently: true });
            context.clearRect(0, 0, state.width, state.height);
            context.drawImage(state.originalImage, 0, 0);
            const imageData = context.getImageData(0, 0, state.width, state.height);
            const originalData = new Uint8ClampedArray(imageData.data);
            const result = removeMatchingBackground(imageData, state.width, state.height, tolerance, Boolean(el.edgeOnly?.checked));
            const recovered = recoverDarkOutlinePixels(imageData, originalData, state.width, state.height, result.removedMask, Boolean(el.edgeOnly?.checked));
            const finalRemoved = Math.max(0, result.removed - recovered);
            context.putImageData(imageData, 0, 0);
            if (generation !== processGeneration) return;

            const blob = await canvasBlob(work);
            if (generation !== processGeneration) return;
            state.processedCanvas = work;
            state.removedPixels = finalRemoved;
            state.recoveredOutlinePixels = recovered;
            drawPreview(work, 'processed');

            const fileName = state.originalFile?.name || 'sprite_sheet.png';
            const cleaned = new File([blob], fileName, {
                type: 'image/png',
                lastModified: state.originalFile?.lastModified || Date.now()
            });
            setFileInput(cleaned);

            const automatic = state.manualTolerance ? 'manual' : 'automatic';
            const outlineText = recovered ? ` · ${recovered.toLocaleString()} dark edge pixels protected` : '';
            setStatus('ok', `<strong>Background cleaned automatically.</strong> ${finalRemoved.toLocaleString()} pixels removed · ${automatic} tolerance ${tolerance}${outlineText}. Smart detection is using this transparent copy now.`);
        } catch (error) {
            if (generation === processGeneration) setStatus('error', `<strong>Background removal failed:</strong> ${escapeHtml(error.message)}`);
        }
    }

    async function handlePreviewPointer(event) {
        if (!el.enable.checked || !state.originalImage) return;
        event.preventDefault();
        const rect = el.preview.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        const canvasX = (event.clientX - rect.left) * (el.preview.width / rect.width);
        const canvasY = (event.clientY - rect.top) * (el.preview.height / rect.height);
        const sourceX = (canvasX / el.preview.width) * state.width;
        const sourceY = (canvasY / el.preview.height) * state.height;
        try {
            sampleOriginalArea(sourceX, sourceY);
            drawPreview(state.originalImage, 'original');
            await applyBackgroundRemoval();
        } catch (error) {
            setStatus('warning', `<strong>Choose another point:</strong> ${escapeHtml(error.message)}`);
        }
    }

    el.file.addEventListener('change', event => {
        if (injecting) {
            injecting = false;
            return;
        }
        const file = event.target.files?.[0];
        if (file) rememberOriginalFile(file);
    });

    el.enable.addEventListener('change', async () => {
        if (el.tools) el.tools.hidden = !el.enable.checked;
        if (!state.originalImage) {
            setStatus('info', el.enable.checked
                ? 'Load a Sprite Sheet, then tap its solid background once.'
                : 'Background removal is disabled.');
            return;
        }
        if (!el.enable.checked) {
            processGeneration += 1;
            await injectOriginal();
            setStatus('info', 'Background removal disabled. The untouched original Sprite Sheet is being used.');
            return;
        }
        drawPreview(state.processedCanvas || state.originalImage, state.processedCanvas ? 'processed' : 'original');
        if (state.sampled) await applyBackgroundRemoval();
        else setStatus('info', '<strong>Tap or click once on a clean background area.</strong> No dragging and no technical setup is required.');
    });

    el.preview.addEventListener('pointerup', handlePreviewPointer);
    el.preview.addEventListener('contextmenu', event => {
        if (el.enable.checked) event.preventDefault();
    });

    el.tolerance?.addEventListener('change', () => {
        state.manualTolerance = true;
        if (state.sampled && el.enable.checked) applyBackgroundRemoval();
    });
    el.edgeOnly?.addEventListener('change', () => {
        if (state.sampled && el.enable.checked) applyBackgroundRemoval();
    });

    el.reset?.addEventListener('click', async () => {
        processGeneration += 1;
        state.sampled = false;
        state.processedCanvas = null;
        state.removedPixels = 0;
        state.recoveredOutlinePixels = 0;
        state.manualTolerance = false;
        state.autoTolerance = DEFAULT_TOLERANCE;
        if (el.tolerance) el.tolerance.value = DEFAULT_TOLERANCE;
        updateSampleDisplay();
        if (state.originalImage) drawPreview(state.originalImage, 'original');
        if (state.originalFile && el.enable.checked) await injectOriginal();
        setStatus('info', state.originalImage
            ? '<strong>Sample cleared.</strong> Tap another clean background area once.'
            : 'Load a Sprite Sheet first.');
    });

    el.clear?.addEventListener('click', () => {
        disposeOriginal();
        setStatus('info', 'Load a Sprite Sheet. Solid-background cleanup is optional and always works on a local copy of the original image.');
    });

    if (el.tolerance) el.tolerance.value = DEFAULT_TOLERANCE;
    if (el.tools) el.tools.hidden = !el.enable.checked;
    updateSampleDisplay();
    setStatus('info', 'Load a Sprite Sheet. If it has a solid background, enable background removal and tap that background once.');
})();