(() => {
    'use strict';

    const MAX_MASCOT_FRAME_SIZE = 100;
    const textEncoder = new TextEncoder();

    const el = {
        file: document.getElementById('sheet-file'),
        prefix: document.getElementById('sheet-prefix'),
        size: document.getElementById('sheet-size'),
        minPixels: document.getElementById('sheet-min-pixels'),
        maxPixels: document.getElementById('sheet-max-pixels'),
        minDim: document.getElementById('sheet-min-dim'),
        maxDim: document.getElementById('sheet-max-dim'),
        rowThreshold: document.getElementById('sheet-row-threshold'),
        detect: document.getElementById('sheet-detect'),
        clear: document.getElementById('sheet-clear'),
        status: document.getElementById('sheet-status'),
        workspace: document.getElementById('sheet-workspace'),
        preview: document.getElementById('sheet-preview'),
        grid: document.getElementById('sheet-sprites'),
        count: document.getElementById('sheet-selection-count'),
        selectAll: document.getElementById('sheet-select-all'),
        selectNone: document.getElementById('sheet-select-none'),
        targetState: document.getElementById('sheet-target-state'),
        targetAnimation: document.getElementById('sheet-target-animation'),
        addSelected: document.getElementById('sheet-add-selected'),
        downloadZip: document.getElementById('sheet-download-zip')
    };

    if (!el.file || !el.preview || !el.grid) return;

    const previewContext = el.preview.getContext('2d');
    let spriteUid = 0;
    let detectionGeneration = 0;
    const sheet = {
        fileName: '',
        image: null,
        imageUrl: '',
        width: 0,
        height: 0,
        rawComponents: 0,
        rows: 0,
        sprites: []
    };

    function nextUid() {
        spriteUid += 1;
        return `sheet-sprite-${spriteUid}`;
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');
    }

    function sanitizePrefix(value) {
        return String(value || '')
            .trim()
            .replace(/\.[^.]+$/, '')
            .replace(/\s+/g, '_')
            .replace(/[^A-Za-z0-9_-]/g, '_')
            .replace(/_+/g, '_')
            .replace(/^_+|_+$/g, '') || 'sprite';
    }

    function integerValue(input, fallback) {
        const value = Number.parseInt(input.value, 10);
        return Number.isFinite(value) ? value : fallback;
    }

    function floatValue(input, fallback) {
        const value = Number.parseFloat(input.value);
        return Number.isFinite(value) ? value : fallback;
    }

    function params() {
        return {
            size: Math.min(MAX_MASCOT_FRAME_SIZE, Math.max(1, integerValue(el.size, 64))),
            minPixels: Math.max(0, integerValue(el.minPixels, 100)),
            maxPixels: Math.max(1, integerValue(el.maxPixels, 10000)),
            minDim: Math.max(0, integerValue(el.minDim, 20)),
            maxDim: Math.max(1, integerValue(el.maxDim, 120)),
            rowThreshold: Math.max(0, floatValue(el.rowThreshold, 30))
        };
    }

    function setStatus(kind, html) {
        el.status.className = `splitter-status ${kind || ''}`.trim();
        el.status.innerHTML = html;
    }

    function disposeSprites() {
        for (const sprite of sheet.sprites) {
            if (sprite.url) URL.revokeObjectURL(sprite.url);
        }
        sheet.sprites = [];
    }

    function disposeSheet() {
        detectionGeneration += 1;
        disposeSprites();
        if (sheet.imageUrl) URL.revokeObjectURL(sheet.imageUrl);
        sheet.fileName = '';
        sheet.image = null;
        sheet.imageUrl = '';
        sheet.width = 0;
        sheet.height = 0;
        sheet.rawComponents = 0;
        sheet.rows = 0;
        el.preview.width = 1;
        el.preview.height = 1;
        previewContext.clearRect(0, 0, 1, 1);
        el.grid.innerHTML = '';
        el.workspace.hidden = true;
        updateSelectionCount();
    }

    function loadImage(url) {
        return new Promise((resolve, reject) => {
            const image = new Image();
            image.onload = () => resolve(image);
            image.onerror = () => reject(new Error('The sprite sheet could not be decoded as an image.'));
            image.src = url;
        });
    }

    async function loadSheetFile(file) {
        if (!file) return;
        disposeSheet();
        if (file.type && file.type !== 'image/png' && !file.name.toLowerCase().endsWith('.png')) {
            throw new Error('Sprite sheets must be PNG files with a transparent background.');
        }
        const url = URL.createObjectURL(file);
        try {
            const image = await loadImage(url);
            sheet.fileName = file.name;
            sheet.image = image;
            sheet.imageUrl = url;
            sheet.width = image.naturalWidth;
            sheet.height = image.naturalHeight;
            el.prefix.value = sanitizePrefix(file.name);
            el.workspace.hidden = false;
            setStatus('info', `<strong>${escapeHtml(file.name)}</strong> loaded · ${sheet.width} × ${sheet.height}px. Detecting sprites…`);
            await detectAndExtract();
        } catch (error) {
            URL.revokeObjectURL(url);
            sheet.imageUrl = '';
            throw error;
        }
    }

    function foreground(data, index) {
        return data[index * 4 + 3] > 0;
    }

    function detectComponents(imageData, width, height, options) {
        const data = imageData.data;
        const total = width * height;
        const visited = new Uint8Array(total);
        let queue = new Int32Array(Math.min(Math.max(4096, width * 2), Math.max(4096, total)));
        let componentCount = 0;
        const boxes = [];

        function ensureQueue(size) {
            if (size < queue.length) return;
            let newSize = queue.length;
            while (newSize <= size) newSize = Math.min(total, Math.max(newSize + 1, newSize * 2));
            const grown = new Int32Array(newSize);
            grown.set(queue);
            queue = grown;
        }

        function enqueue(index, state) {
            if (visited[index] || !foreground(data, index)) return;
            visited[index] = 1;
            ensureQueue(state.tail);
            queue[state.tail] = index;
            state.tail += 1;
        }

        for (let seed = 0; seed < total; seed += 1) {
            if (visited[seed] || !foreground(data, seed)) continue;
            componentCount += 1;
            visited[seed] = 1;
            let head = 0;
            let tail = 1;
            ensureQueue(0);
            queue[0] = seed;

            let pixelCount = 0;
            let minX = width;
            let minY = height;
            let maxX = -1;
            let maxY = -1;

            while (head < tail) {
                const index = queue[head];
                head += 1;
                const y = Math.floor(index / width);
                const x = index - y * width;
                pixelCount += 1;
                if (x < minX) minX = x;
                if (x > maxX) maxX = x;
                if (y < minY) minY = y;
                if (y > maxY) maxY = y;

                const state = { tail };
                if (x > 0) enqueue(index - 1, state);
                if (x + 1 < width) enqueue(index + 1, state);
                if (y > 0) enqueue(index - width, state);
                if (y + 1 < height) enqueue(index + width, state);
                tail = state.tail;
            }

            const w = maxX - minX + 1;
            const h = maxY - minY + 1;
            if (options.minPixels < pixelCount && pixelCount < options.maxPixels &&
                options.minDim < w && w < options.maxDim &&
                options.minDim < h && h < options.maxDim) {
                boxes.push({
                    x1: minX,
                    y1: minY,
                    x2: maxX + 1,
                    y2: maxY + 1,
                    w,
                    h,
                    cx: (minX + maxX + 1) / 2,
                    cy: (minY + maxY + 1) / 2,
                    pixels: pixelCount,
                    row: 0
                });
            }
        }

        boxes.sort((a, b) => a.cy - b.cy);
        const rows = [];
        if (boxes.length) {
            let currentRow = [boxes[0]];
            for (const box of boxes.slice(1)) {
                if (box.cy - currentRow[currentRow.length - 1].cy > options.rowThreshold) {
                    rows.push(currentRow);
                    currentRow = [box];
                } else {
                    currentRow.push(box);
                }
            }
            rows.push(currentRow);
        }

        rows.forEach((row, rowIndex) => {
            row.sort((a, b) => a.cx - b.cx);
            row.forEach(box => { box.row = rowIndex + 1; });
        });

        return {
            componentCount,
            rows,
            boxes: rows.flat()
        };
    }

    function canvasBlob(canvas) {
        return new Promise((resolve, reject) => {
            canvas.toBlob(blob => {
                if (blob) resolve(blob);
                else reject(new Error('Could not encode an extracted sprite as PNG.'));
            }, 'image/png');
        });
    }

    async function extractSprite(box, size, index) {
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const context = canvas.getContext('2d');
        context.clearRect(0, 0, size, size);
        context.imageSmoothingEnabled = false;

        const scale = Math.min(size / box.w, size / box.h);
        const drawW = Math.max(1, Math.floor(box.w * scale));
        const drawH = Math.max(1, Math.floor(box.h * scale));
        const drawX = Math.floor((size - drawW) / 2);
        const drawY = Math.floor((size - drawH) / 2);
        context.drawImage(sheet.image, box.x1, box.y1, box.w, box.h, drawX, drawY, drawW, drawH);

        const blob = await canvasBlob(canvas);
        const bytes = new Uint8Array(await blob.arrayBuffer());
        return {
            uid: nextUid(),
            index,
            row: box.row,
            box,
            bytes,
            url: URL.createObjectURL(blob),
            selected: true,
            size
        };
    }

    function updateSpriteNames() {
        const prefix = sanitizePrefix(el.prefix.value);
        if (el.prefix.value !== prefix) el.prefix.value = prefix;
        sheet.sprites.forEach((sprite, index) => {
            sprite.name = `${prefix}_${String(index + 1).padStart(3, '0')}.png`;
        });
    }

    async function detectAndExtract() {
        if (!sheet.image) {
            setStatus('warning', 'Load a transparent PNG sprite sheet first.');
            return;
        }

        const generation = ++detectionGeneration;
        const options = params();
        el.size.value = options.size;
        el.detect.disabled = true;
        el.addSelected.disabled = true;
        el.downloadZip.disabled = true;
        setStatus('info', `Scanning ${sheet.width} × ${sheet.height}px for connected opaque components…`);

        await new Promise(resolve => requestAnimationFrame(() => resolve()));

        try {
            const work = document.createElement('canvas');
            work.width = sheet.width;
            work.height = sheet.height;
            const workContext = work.getContext('2d', { willReadFrequently: true });
            workContext.clearRect(0, 0, sheet.width, sheet.height);
            workContext.drawImage(sheet.image, 0, 0);
            const imageData = workContext.getImageData(0, 0, sheet.width, sheet.height);
            const result = detectComponents(imageData, sheet.width, sheet.height, options);
            if (generation !== detectionGeneration) return;

            disposeSprites();
            sheet.rawComponents = result.componentCount;
            sheet.rows = result.rows.length;

            for (let index = 0; index < result.boxes.length; index += 1) {
                if (generation !== detectionGeneration) return;
                sheet.sprites.push(await extractSprite(result.boxes[index], options.size, index + 1));
                if (index > 0 && index % 24 === 0) await new Promise(resolve => setTimeout(resolve, 0));
            }
            updateSpriteNames();
            drawSheetPreview();
            renderSpriteGrid();

            if (!sheet.sprites.length) {
                setStatus('warning', `<strong>${result.componentCount}</strong> connected components were found, but none passed the current size filters. Relax the advanced filters and click <strong>Re-detect</strong>.`);
            } else {
                setStatus('ok', `<strong>${sheet.sprites.length} sprites ready</strong> from ${result.componentCount} connected components · ${result.rows.length} detected row${result.rows.length === 1 ? '' : 's'} · output ${options.size} × ${options.size}px.`);
            }
        } catch (error) {
            if (generation === detectionGeneration) setStatus('error', `<strong>Detection failed:</strong> ${escapeHtml(error.message)}`);
        } finally {
            if (generation === detectionGeneration) {
                el.detect.disabled = false;
                updateSelectionCount();
            }
        }
    }

    function drawSheetPreview() {
        if (!sheet.image) return;
        const maxW = 920;
        const maxH = 520;
        const scale = Math.min(1, maxW / sheet.width, maxH / sheet.height);
        const width = Math.max(1, Math.round(sheet.width * scale));
        const height = Math.max(1, Math.round(sheet.height * scale));
        el.preview.width = width;
        el.preview.height = height;
        previewContext.clearRect(0, 0, width, height);
        previewContext.imageSmoothingEnabled = false;
        previewContext.drawImage(sheet.image, 0, 0, width, height);

        previewContext.font = '700 12px system-ui, sans-serif';
        previewContext.textBaseline = 'top';
        sheet.sprites.forEach((sprite, index) => {
            const box = sprite.box;
            const x = box.x1 * scale;
            const y = box.y1 * scale;
            const w = box.w * scale;
            const h = box.h * scale;
            previewContext.lineWidth = Math.max(1, 2 * scale);
            previewContext.strokeStyle = sprite.selected ? '#3bff00' : 'rgba(255,255,255,.45)';
            previewContext.strokeRect(x, y, w, h);
            if (w >= 16 && h >= 16) {
                const label = String(index + 1);
                const metrics = previewContext.measureText(label);
                previewContext.fillStyle = 'rgba(0,0,0,.78)';
                previewContext.fillRect(x, y, metrics.width + 7, 16);
                previewContext.fillStyle = sprite.selected ? '#3bff00' : '#ddd';
                previewContext.fillText(label, x + 3, y + 1);
            }
        });
    }

    function renderSpriteGrid() {
        if (!sheet.sprites.length) {
            el.grid.innerHTML = '<div class="splitter-empty">No extracted sprites yet.</div>';
            updateSelectionCount();
            return;
        }
        el.grid.innerHTML = sheet.sprites.map((sprite, index) => `
            <button type="button" class="splitter-sprite ${sprite.selected ? 'selected' : ''}" data-sprite-index="${index}" aria-pressed="${sprite.selected ? 'true' : 'false'}">
                <span class="splitter-check">${sprite.selected ? '✓' : ''}</span>
                <span class="splitter-thumb"><img src="${escapeHtml(sprite.url)}" alt="${escapeHtml(sprite.name)}"></span>
                <span class="splitter-sprite-name">${escapeHtml(sprite.name)}</span>
                <span class="splitter-sprite-meta">row ${sprite.row} · ${sprite.box.w}×${sprite.box.h} source · ${sprite.box.pixels}px</span>
            </button>
        `).join('');
        updateSelectionCount();
    }

    function selectedSprites() {
        return sheet.sprites.filter(sprite => sprite.selected);
    }

    function updateSelectionCount() {
        const selected = selectedSprites().length;
        const total = sheet.sprites.length;
        el.count.textContent = `${selected} / ${total} selected`;
        const hasSelection = selected > 0;
        const hasTarget = Boolean(el.targetAnimation.value);
        el.addSelected.disabled = !hasSelection || !hasTarget;
        el.downloadZip.disabled = !hasSelection;
    }

    function setAllSelected(value) {
        sheet.sprites.forEach(sprite => { sprite.selected = value; });
        drawSheetPreview();
        renderSpriteGrid();
    }

    function animationCardsForState(state) {
        const root = document.getElementById(`${state}-animations`);
        if (!root) return [];
        return [...root.querySelectorAll(`.animation-card[data-state="${state}"]`)];
    }

    function refreshTargetAnimations() {
        const state = el.targetState.value === 'run' ? 'run' : 'idle';
        const previous = el.targetAnimation.value;
        const cards = animationCardsForState(state);
        el.targetAnimation.innerHTML = cards.length
            ? cards.map(card => {
                const index = Number(card.dataset.animation);
                const name = card.querySelector('.animation-name')?.value?.trim() || `${state} ${index + 1}`;
                return `<option value="${index}">${escapeHtml(name)}</option>`;
            }).join('')
            : '<option value="">No animations available</option>';
        if ([...el.targetAnimation.options].some(option => option.value === previous)) el.targetAnimation.value = previous;
        updateSelectionCount();
    }

    async function addSelectedToAnimation() {
        const sprites = selectedSprites();
        if (!sprites.length) return;
        const state = el.targetState.value === 'run' ? 'run' : 'idle';
        const animationIndex = Number(el.targetAnimation.value);
        const card = document.querySelector(`.animation-card[data-state="${state}"][data-animation="${animationIndex}"]`);
        const input = card?.querySelector('.frame-input');
        if (!input) {
            setStatus('error', 'The selected target animation no longer exists. Choose another animation and try again.');
            refreshTargetAnimations();
            return;
        }
        if (typeof DataTransfer === 'undefined') {
            setStatus('warning', 'This browser cannot transfer generated files directly into the animation editor. Download the sprites ZIP and import the PNGs manually.');
            return;
        }

        try {
            const transfer = new DataTransfer();
            sprites.forEach(sprite => {
                transfer.items.add(new File([sprite.bytes], sprite.name, { type: 'image/png', lastModified: Date.now() }));
            });
            input.files = transfer.files;
            input.dispatchEvent(new Event('change', { bubbles: true }));
            setStatus('ok', `<strong>${sprites.length} extracted sprite${sprites.length === 1 ? '' : 's'}</strong> sent directly to the selected ${state === 'idle' ? 'Idle' : 'Run'} animation.`);
        } catch (error) {
            setStatus('error', `<strong>Could not add frames directly:</strong> ${escapeHtml(error.message)}. You can still download the sprites ZIP and import them manually.`);
        }
    }

    function crcTable() {
        const table = new Uint32Array(256);
        for (let n = 0; n < 256; n += 1) {
            let c = n;
            for (let k = 0; k < 8; k += 1) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
            table[n] = c >>> 0;
        }
        return table;
    }

    const crcLookup = crcTable();

    function crc32(bytes) {
        let c = 0xffffffff;
        for (const byte of bytes) c = crcLookup[(c ^ byte) & 0xff] ^ (c >>> 8);
        return (c ^ 0xffffffff) >>> 0;
    }

    function dosDateTime(date = new Date()) {
        const year = Math.max(1980, date.getFullYear());
        return {
            time: (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2),
            date: ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate()
        };
    }

    function localHeader(nameBytes, bytes, crc, stamp) {
        const out = new Uint8Array(30 + nameBytes.length);
        const view = new DataView(out.buffer);
        view.setUint32(0, 0x04034b50, true);
        view.setUint16(4, 20, true);
        view.setUint16(6, 0x0800, true);
        view.setUint16(8, 0, true);
        view.setUint16(10, stamp.time, true);
        view.setUint16(12, stamp.date, true);
        view.setUint32(14, crc, true);
        view.setUint32(18, bytes.length, true);
        view.setUint32(22, bytes.length, true);
        view.setUint16(26, nameBytes.length, true);
        out.set(nameBytes, 30);
        return out;
    }

    function centralHeader(nameBytes, bytes, crc, stamp, offset) {
        const out = new Uint8Array(46 + nameBytes.length);
        const view = new DataView(out.buffer);
        view.setUint32(0, 0x02014b50, true);
        view.setUint16(4, 20, true);
        view.setUint16(6, 20, true);
        view.setUint16(8, 0x0800, true);
        view.setUint16(10, 0, true);
        view.setUint16(12, stamp.time, true);
        view.setUint16(14, stamp.date, true);
        view.setUint32(16, crc, true);
        view.setUint32(20, bytes.length, true);
        view.setUint32(24, bytes.length, true);
        view.setUint16(28, nameBytes.length, true);
        view.setUint32(42, offset, true);
        out.set(nameBytes, 46);
        return out;
    }

    function endCentral(entryCount, centralSize, centralOffset) {
        const out = new Uint8Array(22);
        const view = new DataView(out.buffer);
        view.setUint32(0, 0x06054b50, true);
        view.setUint16(8, entryCount, true);
        view.setUint16(10, entryCount, true);
        view.setUint32(12, centralSize, true);
        view.setUint32(16, centralOffset, true);
        return out;
    }

    function buildZip(files) {
        const localParts = [];
        const centralParts = [];
        const stamp = dosDateTime();
        let offset = 0;
        for (const file of files) {
            const nameBytes = textEncoder.encode(file.name);
            const bytes = file.bytes;
            const crc = crc32(bytes);
            const local = localHeader(nameBytes, bytes, crc, stamp);
            localParts.push(local, bytes);
            centralParts.push(centralHeader(nameBytes, bytes, crc, stamp, offset));
            offset += local.length + bytes.length;
        }
        const centralSize = centralParts.reduce((sum, part) => sum + part.length, 0);
        return new Blob([...localParts, ...centralParts, endCentral(files.length, centralSize, offset)], { type: 'application/zip' });
    }

    function downloadBlob(blob, filename) {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1500);
    }

    function downloadSelectedZip() {
        const sprites = selectedSprites();
        if (!sprites.length) return;
        const prefix = sanitizePrefix(el.prefix.value);
        downloadBlob(buildZip(sprites.map(sprite => ({ name: sprite.name, bytes: sprite.bytes }))), `${prefix}_sprites.zip`);
    }

    el.file.addEventListener('change', async () => {
        const file = el.file.files?.[0];
        if (!file) return;
        try {
            await loadSheetFile(file);
        } catch (error) {
            setStatus('error', `<strong>Could not load sprite sheet:</strong> ${escapeHtml(error.message)}`);
            disposeSheet();
        } finally {
            el.file.value = '';
        }
    });

    el.detect.addEventListener('click', detectAndExtract);
    el.clear.addEventListener('click', () => {
        disposeSheet();
        setStatus('info', 'Load a transparent PNG sprite sheet to detect and separate its sprites.');
    });
    el.prefix.addEventListener('input', () => {
        if (!sheet.sprites.length) return;
        updateSpriteNames();
        renderSpriteGrid();
    });
    for (const input of [el.size, el.minPixels, el.maxPixels, el.minDim, el.maxDim, el.rowThreshold]) {
        input.addEventListener('change', () => {
            if (sheet.image) detectAndExtract();
        });
    }

    el.grid.addEventListener('click', event => {
        const card = event.target.closest('[data-sprite-index]');
        if (!card) return;
        const index = Number(card.dataset.spriteIndex);
        const sprite = sheet.sprites[index];
        if (!sprite) return;
        sprite.selected = !sprite.selected;
        drawSheetPreview();
        renderSpriteGrid();
    });
    el.selectAll.addEventListener('click', () => setAllSelected(true));
    el.selectNone.addEventListener('click', () => setAllSelected(false));
    el.targetState.addEventListener('change', refreshTargetAnimations);
    el.targetAnimation.addEventListener('change', updateSelectionCount);
    el.addSelected.addEventListener('click', addSelectedToAnimation);
    el.downloadZip.addEventListener('click', downloadSelectedZip);

    const animationObserver = new MutationObserver(refreshTargetAnimations);
    for (const root of [document.getElementById('idle-animations'), document.getElementById('run-animations')]) {
        if (root) animationObserver.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ['value'] });
        root?.addEventListener('input', () => setTimeout(refreshTargetAnimations, 0));
    }

    setStatus('info', 'Load a transparent PNG sprite sheet to detect and separate its sprites.');
    refreshTargetAnimations();
    updateSelectionCount();
})();
