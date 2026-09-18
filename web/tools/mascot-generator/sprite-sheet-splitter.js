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
    let manualPickMode = false;

    const sheet = {
        fileName: '',
        image: null,
        imageUrl: '',
        width: 0,
        height: 0,
        rawComponents: [],
        rawComponentCount: 0,
        mergedComponentCount: 0,
        rows: 0,
        sprites: [],
        imageData: null,
        lastOptions: null,
        typical: null
    };

    const smartUi = createSmartUi();

    function createSmartUi() {
        const splitter = document.getElementById('sprite-sheet-splitter');
        const advanced = splitter?.querySelector('.splitter-advanced');
        if (el.detect) el.detect.textContent = 'Smart detect';
        if (el.grid) el.grid.style.maxHeight = 'none';

        const backgroundControls = splitter?.querySelector('.background-controls');
        if (backgroundControls && !backgroundControls.closest('.background-expert')) {
            const details = document.createElement('details');
            details.className = 'splitter-advanced background-expert';
            details.style.marginTop = '12px';
            const summary = document.createElement('summary');
            summary.textContent = 'Background cleanup settings (usually not needed)';
            backgroundControls.parentNode.insertBefore(details, backgroundControls);
            details.appendChild(summary);
            details.appendChild(backgroundControls);
            const hint = splitter?.querySelector('.background-hint');
            if (hint) hint.innerHTML = '<strong>Recommended:</strong> tap a clean part of the background once and keep the default cleanup settings. Open these controls only if the processed preview still needs adjustment.';
        }

        let mode = document.getElementById('sheet-detection-mode');
        if (!mode && advanced) {
            const block = document.createElement('div');
            block.className = 'field-grid';
            block.style.marginTop = '16px';
            block.innerHTML = `
                <div class="field">
                    <label for="sheet-detection-mode">Detection mode</label>
                    <select id="sheet-detection-mode">
                        <option value="auto" selected>Automatic — recommended</option>
                        <option value="sensitive">Sensitive — finds small/detached pieces</option>
                        <option value="strict">Strict — ignores more noise</option>
                        <option value="expert">Expert — use manual values below</option>
                    </select>
                    <small id="sheet-detection-help">Automatic analyzes this Sprite Sheet and chooses the technical thresholds for you.</small>
                </div>
                <div class="field">
                    <label>Missed a sprite?</label>
                    <button id="sheet-add-missed" class="button secondary-button" type="button" disabled>Add missed sprite</button>
                    <small>Tap this button, then tap the missing sprite directly in the detected-sheet preview.</small>
                </div>`;
            advanced.parentNode.insertBefore(block, advanced);
            mode = block.querySelector('#sheet-detection-mode');
        }

        const addMissed = document.getElementById('sheet-add-missed');
        if (advanced) {
            const summary = advanced.querySelector('summary');
            if (summary) summary.textContent = 'Expert detection settings (usually not needed)';
            const grid = advanced.querySelector('.field-grid');
            if (grid && !document.getElementById('sheet-merge-gap')) {
                const field = document.createElement('div');
                field.className = 'field';
                field.innerHTML = `
                    <label for="sheet-merge-gap">Detached-piece merge distance</label>
                    <div class="input-with-unit"><input id="sheet-merge-gap" type="number" min="0" max="64" step="1" value="6"><span>px</span></div>
                    <small>Expert mode only. Nearby disconnected pieces inside one visual frame may be merged automatically.</small>`;
                grid.appendChild(field);
            }
            const hint = document.createElement('div');
            hint.id = 'sheet-expert-hint';
            hint.className = 'splitter-note';
            hint.style.padding = '0 14px 14px';
            hint.innerHTML = '<strong>Tip:</strong> leave Detection mode on <strong>Automatic</strong> unless a very unusual sheet still needs manual tuning.';
            advanced.appendChild(hint);
        }

        const note = splitter?.querySelector('.splitter-note');
        if (note) {
            note.innerHTML = '<strong>Smart detection:</strong> the transparent working copy is scanned with 8-direction connectivity, nearby detached pieces are grouped when safe, technical thresholds are estimated from the sheet itself, and frames are ordered top-to-bottom then left-to-right. Use <strong>Add missed sprite</strong> only when automatic detection skips a frame.';
        }

        return {
            mode,
            addMissed,
            mergeGap: document.getElementById('sheet-merge-gap'),
            help: document.getElementById('sheet-detection-help'),
            advanced
        };
    }

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
        const value = Number.parseInt(input?.value, 10);
        return Number.isFinite(value) ? value : fallback;
    }

    function floatValue(input, fallback) {
        const value = Number.parseFloat(input?.value);
        return Number.isFinite(value) ? value : fallback;
    }

    function median(values) {
        if (!values.length) return 0;
        const sorted = [...values].sort((a, b) => a - b);
        const middle = Math.floor(sorted.length / 2);
        return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
    }

    function clamp(value, min, max) {
        return Math.min(max, Math.max(min, value));
    }

    function detectionMode() {
        return ['auto', 'sensitive', 'strict', 'expert'].includes(smartUi.mode?.value)
            ? smartUi.mode.value
            : 'auto';
    }

    function outputSize() {
        return Math.min(MAX_MASCOT_FRAME_SIZE, Math.max(1, integerValue(el.size, 64)));
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

    function setManualPickMode(enabled) {
        manualPickMode = Boolean(enabled && sheet.image && sheet.rawComponents.length);
        if (smartUi.addMissed) {
            smartUi.addMissed.textContent = manualPickMode ? 'Cancel missed-sprite mode' : 'Add missed sprite';
            smartUi.addMissed.disabled = !sheet.image || !sheet.rawComponents.length;
        }
        el.preview.style.cursor = manualPickMode ? 'crosshair' : 'pointer';
        el.preview.style.touchAction = manualPickMode ? 'none' : 'manipulation';
        if (manualPickMode) {
            setStatus('info', '<strong>Add missed sprite:</strong> tap or click the missing visual frame in the detected-sheet preview. The tool will find the nearest foreground pieces and build a frame automatically.');
        }
    }

    function disposeSheet() {
        detectionGeneration += 1;
        setManualPickMode(false);
        disposeSprites();
        if (sheet.imageUrl) URL.revokeObjectURL(sheet.imageUrl);
        sheet.fileName = '';
        sheet.image = null;
        sheet.imageUrl = '';
        sheet.width = 0;
        sheet.height = 0;
        sheet.rawComponents = [];
        sheet.rawComponentCount = 0;
        sheet.mergedComponentCount = 0;
        sheet.rows = 0;
        sheet.imageData = null;
        sheet.lastOptions = null;
        sheet.typical = null;
        el.preview.width = 1;
        el.preview.height = 1;
        previewContext.clearRect(0, 0, 1, 1);
        el.grid.innerHTML = '';
        el.workspace.hidden = true;
        if (smartUi.addMissed) smartUi.addMissed.disabled = true;
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
            throw new Error('Sprite sheets must be PNG files.');
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
            setStatus('info', `<strong>${escapeHtml(file.name)}</strong> loaded · ${sheet.width} × ${sheet.height}px. Smart detection is analyzing the sheet…`);
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

    function detectRawComponents(imageData, width, height) {
        const data = imageData.data;
        const total = width * height;
        const visited = new Uint8Array(total);
        const queue = new Int32Array(total);
        const components = [];

        function enqueue(index, state) {
            if (index < 0 || index >= total || visited[index] || !foreground(data, index)) return;
            visited[index] = 1;
            queue[state.tail++] = index;
        }

        for (let seed = 0; seed < total; seed += 1) {
            if (visited[seed] || !foreground(data, seed)) continue;
            visited[seed] = 1;
            let head = 0;
            let tail = 1;
            queue[0] = seed;
            let pixelCount = 0;
            let minX = width;
            let minY = height;
            let maxX = -1;
            let maxY = -1;

            while (head < tail) {
                const index = queue[head++];
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
                if (x > 0 && y > 0) enqueue(index - width - 1, state);
                if (x + 1 < width && y > 0) enqueue(index - width + 1, state);
                if (x > 0 && y + 1 < height) enqueue(index + width - 1, state);
                if (x + 1 < width && y + 1 < height) enqueue(index + width + 1, state);
                tail = state.tail;
            }

            const w = maxX - minX + 1;
            const h = maxY - minY + 1;
            components.push({
                x1: minX,
                y1: minY,
                x2: maxX + 1,
                y2: maxY + 1,
                w,
                h,
                cx: (minX + maxX + 1) / 2,
                cy: (minY + maxY + 1) / 2,
                pixels: pixelCount,
                members: 1,
                manual: false,
                row: 0
            });
        }
        return components;
    }

    function boxGap(a, b) {
        const dx = Math.max(0, Math.max(a.x1, b.x1) - Math.min(a.x2, b.x2));
        const dy = Math.max(0, Math.max(a.y1, b.y1) - Math.min(a.y2, b.y2));
        return { dx, dy, distance: Math.hypot(dx, dy) };
    }

    function unionFind(count) {
        const parent = new Int32Array(count);
        const rank = new Uint8Array(count);
        for (let i = 0; i < count; i += 1) parent[i] = i;
        function find(value) {
            let root = value;
            while (parent[root] !== root) root = parent[root];
            while (parent[value] !== value) {
                const next = parent[value];
                parent[value] = root;
                value = next;
            }
            return root;
        }
        function join(a, b) {
            let ra = find(a);
            let rb = find(b);
            if (ra === rb) return;
            if (rank[ra] < rank[rb]) [ra, rb] = [rb, ra];
            parent[rb] = ra;
            if (rank[ra] === rank[rb]) rank[ra] += 1;
        }
        return { find, join };
    }

    function aggregateBoxes(items) {
        const x1 = Math.min(...items.map(item => item.x1));
        const y1 = Math.min(...items.map(item => item.y1));
        const x2 = Math.max(...items.map(item => item.x2));
        const y2 = Math.max(...items.map(item => item.y2));
        return {
            x1,
            y1,
            x2,
            y2,
            w: x2 - x1,
            h: y2 - y1,
            cx: (x1 + x2) / 2,
            cy: (y1 + y2) / 2,
            pixels: items.reduce((sum, item) => sum + item.pixels, 0),
            members: items.reduce((sum, item) => sum + (item.members || 1), 0),
            manual: items.some(item => item.manual),
            row: 0
        };
    }

    function deriveTypical(components, width, height) {
        const sane = components.filter(item =>
            item.pixels >= 6 &&
            item.w < width * 0.35 &&
            item.h < height * 0.35 &&
            item.w >= 2 && item.h >= 2
        );
        const pool = sane.length ? sane : components;
        return {
            w: Math.max(1, median(pool.map(item => item.w))),
            h: Math.max(1, median(pool.map(item => item.h))),
            pixels: Math.max(1, median(pool.map(item => item.pixels)))
        };
    }

    function smartOptions(rawComponents) {
        const mode = detectionMode();
        const typical = deriveTypical(rawComponents, sheet.width, sheet.height);
        const baseDim = Math.max(1, Math.min(typical.w, typical.h));
        let mergeGap = clamp(Math.round(baseDim * 0.16), 2, 10);
        let minPixelsFactor = 0.08;
        let minDimFactor = 0.18;
        let maxPixelsFactor = 10;
        let maxWidthFactor = 3.6;
        let maxHeightFactor = 3.1;
        let rowFactor = 0.55;
        let tinyPieceFactor = 0.22;

        if (mode === 'sensitive') {
            mergeGap = clamp(mergeGap + 3, 3, 14);
            minPixelsFactor = 0.025;
            minDimFactor = 0.08;
            maxPixelsFactor = 20;
            maxWidthFactor = 5;
            maxHeightFactor = 4.2;
            rowFactor = 0.65;
            tinyPieceFactor = 0.35;
        } else if (mode === 'strict') {
            mergeGap = clamp(mergeGap - 1, 1, 8);
            minPixelsFactor = 0.18;
            minDimFactor = 0.30;
            maxPixelsFactor = 6;
            maxWidthFactor = 2.8;
            maxHeightFactor = 2.6;
            rowFactor = 0.48;
            tinyPieceFactor = 0.14;
        } else if (mode === 'expert') {
            mergeGap = clamp(integerValue(smartUi.mergeGap, 6), 0, 64);
            const maxDim = Math.max(1, integerValue(el.maxDim, 120));
            return {
                mode,
                size: outputSize(),
                mergeGap,
                tinyPieceGap: Math.max(mergeGap, Math.round(mergeGap * 1.8)),
                tinyPiecePixels: Math.max(1, integerValue(el.minPixels, 100)),
                minPixels: Math.max(0, integerValue(el.minPixels, 100)),
                maxPixels: Math.max(1, integerValue(el.maxPixels, 10000)),
                minDim: Math.max(0, integerValue(el.minDim, 20)),
                maxW: maxDim,
                maxH: maxDim,
                rowThreshold: Math.max(0, floatValue(el.rowThreshold, 30)),
                typical
            };
        }

        return {
            mode,
            size: outputSize(),
            mergeGap,
            tinyPieceGap: clamp(Math.round(mergeGap * 1.8), mergeGap, 22),
            tinyPiecePixels: Math.max(4, Math.round(typical.pixels * tinyPieceFactor)),
            minPixels: Math.max(4, Math.round(typical.pixels * minPixelsFactor)),
            maxPixels: Math.max(64, Math.round(typical.pixels * maxPixelsFactor)),
            minDim: Math.max(2, Math.round(baseDim * minDimFactor)),
            maxW: Math.max(16, Math.round(typical.w * maxWidthFactor)),
            maxH: Math.max(16, Math.round(typical.h * maxHeightFactor)),
            rowThreshold: Math.max(6, Math.round(typical.h * rowFactor)),
            typical
        };
    }

    function mergeNearbyComponents(components, options) {
        const candidates = components
            .map((box, index) => ({ box, index }))
            .filter(item => item.box.pixels >= 2)
            .sort((a, b) => a.box.x1 - b.box.x1);
        const uf = unionFind(components.length);

        for (let ai = 0; ai < candidates.length; ai += 1) {
            const aItem = candidates[ai];
            const a = aItem.box;
            for (let bi = ai + 1; bi < candidates.length; bi += 1) {
                const bItem = candidates[bi];
                const b = bItem.box;
                const maxSearch = Math.max(options.mergeGap, options.tinyPieceGap);
                if (b.x1 > a.x2 + maxSearch) break;
                const gap = boxGap(a, b);
                const aTiny = a.pixels <= options.tinyPiecePixels;
                const bTiny = b.pixels <= options.tinyPiecePixels;
                const allowedGap = (aTiny || bTiny) ? options.tinyPieceGap : options.mergeGap;
                if (gap.dx > allowedGap || gap.dy > allowedGap || gap.distance > allowedGap * 1.45) continue;
                const combinedW = Math.max(a.x2, b.x2) - Math.min(a.x1, b.x1);
                const combinedH = Math.max(a.y2, b.y2) - Math.min(a.y1, b.y1);
                if (combinedW > options.maxW * 1.12 || combinedH > options.maxH * 1.12) continue;
                uf.join(aItem.index, bItem.index);
            }
        }

        const groups = new Map();
        components.forEach((box, index) => {
            if (box.pixels < 2) return;
            const root = uf.find(index);
            if (!groups.has(root)) groups.set(root, []);
            groups.get(root).push(box);
        });
        return [...groups.values()].map(aggregateBoxes);
    }

    function filterSmartBoxes(groups, options) {
        return groups.filter(box => {
            if (box.pixels < options.minPixels || box.pixels > options.maxPixels) return false;
            if (Math.max(box.w, box.h) < options.minDim) return false;
            if (box.w > options.maxW || box.h > options.maxH) return false;
            return true;
        });
    }

    function orderBoxesIntoRows(boxes, rowThreshold) {
        const sorted = [...boxes].sort((a, b) => a.cy - b.cy || a.cx - b.cx);
        const rows = [];
        for (const box of sorted) {
            let bestRow = null;
            let bestDistance = Infinity;
            for (const row of rows) {
                const distance = Math.abs(box.cy - row.centerY);
                if (distance <= rowThreshold && distance < bestDistance) {
                    bestDistance = distance;
                    bestRow = row;
                }
            }
            if (!bestRow) {
                bestRow = { centerY: box.cy, boxes: [] };
                rows.push(bestRow);
            }
            bestRow.boxes.push(box);
            bestRow.centerY = bestRow.boxes.reduce((sum, item) => sum + item.cy, 0) / bestRow.boxes.length;
        }
        rows.sort((a, b) => a.centerY - b.centerY);
        rows.forEach((row, rowIndex) => {
            row.boxes.sort((a, b) => a.cx - b.cx);
            row.boxes.forEach(box => { box.row = rowIndex + 1; });
        });
        return rows;
    }

    function canvasBlob(canvas) {
        return new Promise((resolve, reject) => {
            canvas.toBlob(blob => {
                if (blob) resolve(blob);
                else reject(new Error('Could not encode an extracted sprite as PNG.'));
            }, 'image/png');
        });
    }

    function uncertaintyFor(box, options) {
        if (box.manual) return false;
        const typical = options.typical;
        return box.pixels < typical.pixels * 0.22 ||
            box.w > typical.w * 2.3 || box.h > typical.h * 2.3 ||
            box.members > 3;
    }

    async function extractSprite(box, size, index, options = sheet.lastOptions) {
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
            size,
            uncertain: options ? uncertaintyFor(box, options) : false,
            manual: Boolean(box.manual)
        };
    }

    function updateSpriteNames() {
        const prefix = sanitizePrefix(el.prefix.value);
        if (el.prefix.value !== prefix) el.prefix.value = prefix;
        sheet.sprites.forEach((sprite, index) => {
            sprite.index = index + 1;
            sprite.name = `${prefix}_${String(index + 1).padStart(3, '0')}.png`;
        });
    }

    function detectOpaqueBackground(rawComponents) {
        if (!rawComponents.length) return false;
        const largest = rawComponents.reduce((best, item) => item.pixels > best.pixels ? item : best, rawComponents[0]);
        const sheetArea = Math.max(1, sheet.width * sheet.height);
        const coversMostPixels = largest.pixels / sheetArea > 0.55;
        const coversMostBounds = largest.w / sheet.width > 0.85 && largest.h / sheet.height > 0.85;
        return coversMostPixels || (coversMostBounds && largest.pixels / sheetArea > 0.25);
    }

    async function detectAndExtract() {
        if (!sheet.image) {
            setStatus('warning', 'Load a PNG Sprite Sheet first.');
            return;
        }

        setManualPickMode(false);
        const generation = ++detectionGeneration;
        const size = outputSize();
        el.size.value = size;
        el.detect.disabled = true;
        el.addSelected.disabled = true;
        el.downloadZip.disabled = true;
        setStatus('info', `Smart scanning ${sheet.width} × ${sheet.height}px…`);
        await new Promise(resolve => requestAnimationFrame(resolve));

        try {
            const work = document.createElement('canvas');
            work.width = sheet.width;
            work.height = sheet.height;
            const workContext = work.getContext('2d', { willReadFrequently: true });
            workContext.clearRect(0, 0, sheet.width, sheet.height);
            workContext.drawImage(sheet.image, 0, 0);
            const imageData = workContext.getImageData(0, 0, sheet.width, sheet.height);
            const raw = detectRawComponents(imageData, sheet.width, sheet.height);
            if (generation !== detectionGeneration) return;

            disposeSprites();
            sheet.imageData = imageData;
            sheet.rawComponents = raw;
            sheet.rawComponentCount = raw.length;

            if (detectOpaqueBackground(raw)) {
                sheet.mergedComponentCount = raw.length;
                sheet.rows = 0;
                sheet.lastOptions = null;
                drawSheetPreview();
                renderSpriteGrid();
                setStatus('warning', '<strong>Solid background detected.</strong> Enable <strong>Remove solid background</strong>, then tap the background once. Smart detection will run again automatically after cleanup.');
                return;
            }

            const options = smartOptions(raw);
            sheet.lastOptions = options;
            sheet.typical = options.typical;
            const merged = mergeNearbyComponents(raw, options);
            sheet.mergedComponentCount = merged.length;
            const accepted = filterSmartBoxes(merged, options);
            const rows = orderBoxesIntoRows(accepted, options.rowThreshold);
            const ordered = rows.flatMap(row => row.boxes);
            sheet.rows = rows.length;

            for (let index = 0; index < ordered.length; index += 1) {
                if (generation !== detectionGeneration) return;
                sheet.sprites.push(await extractSprite(ordered[index], size, index + 1, options));
                if (index > 0 && index % 24 === 0) await new Promise(resolve => setTimeout(resolve, 0));
            }
            updateSpriteNames();
            drawSheetPreview();
            renderSpriteGrid();
            if (smartUi.addMissed) smartUi.addMissed.disabled = !sheet.rawComponents.length;

            const uncertain = sheet.sprites.filter(sprite => sprite.uncertain).length;
            if (!sheet.sprites.length) {
                setStatus('warning', '<strong>No usable frames were found.</strong> Try <strong>Sensitive</strong> detection. If the sheet has a solid background, remove it first with one tap.');
            } else {
                const modeLabel = options.mode === 'auto' ? 'Automatic' : options.mode[0].toUpperCase() + options.mode.slice(1);
                const review = uncertain ? ` · ${uncertain} unusual frame${uncertain === 1 ? '' : 's'} marked for review` : '';
                setStatus('ok', `<strong>${sheet.sprites.length} frames detected</strong> · ${sheet.rows} row${sheet.rows === 1 ? '' : 's'} · ${modeLabel} mode${review}. You usually do not need the Expert settings.`);
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
        const maxH = 620;
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
            previewContext.strokeStyle = sprite.manual
                ? '#5c9dff'
                : sprite.uncertain
                    ? '#f0d77a'
                    : sprite.selected ? '#3bff00' : 'rgba(255,255,255,.45)';
            previewContext.strokeRect(x, y, w, h);
            if (w >= 14 && h >= 14) {
                const label = `${index + 1}${sprite.uncertain ? '?' : ''}`;
                const metrics = previewContext.measureText(label);
                previewContext.fillStyle = 'rgba(0,0,0,.78)';
                previewContext.fillRect(x, y, metrics.width + 7, 16);
                previewContext.fillStyle = sprite.manual ? '#9ec1ff' : sprite.uncertain ? '#f0d77a' : sprite.selected ? '#3bff00' : '#ddd';
                previewContext.fillText(label, x + 3, y + 1);
            }
        });

        if (manualPickMode) {
            previewContext.save();
            previewContext.fillStyle = 'rgba(92,157,255,.12)';
            previewContext.fillRect(0, 0, width, height);
            previewContext.font = '800 15px system-ui, sans-serif';
            previewContext.fillStyle = '#9ec1ff';
            previewContext.fillText('Tap the missing sprite', 12, 12);
            previewContext.restore();
        }
    }

    function renderSpriteGrid() {
        if (!sheet.sprites.length) {
            el.grid.innerHTML = '<div class="splitter-empty">No extracted sprites yet.</div>';
            updateSelectionCount();
            return;
        }
        el.grid.innerHTML = sheet.sprites.map((sprite, index) => {
            const badge = sprite.manual ? ' · added manually' : sprite.uncertain ? ' · review' : '';
            return `
            <button type="button" class="splitter-sprite ${sprite.selected ? 'selected' : ''}" data-sprite-index="${index}" aria-pressed="${sprite.selected ? 'true' : 'false'}">
                <span class="splitter-check">${sprite.selected ? '✓' : ''}</span>
                <span class="splitter-thumb"><img src="${escapeHtml(sprite.url)}" alt="${escapeHtml(sprite.name)}"></span>
                <span class="splitter-sprite-name">${escapeHtml(sprite.name)}</span>
                <span class="splitter-sprite-meta">row ${sprite.row} · ${sprite.box.w}×${sprite.box.h}${escapeHtml(badge)}</span>
            </button>`;
        }).join('');
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

    function distancePointToBox(x, y, box) {
        const dx = x < box.x1 ? box.x1 - x : x > box.x2 ? x - box.x2 : 0;
        const dy = y < box.y1 ? box.y1 - y : y > box.y2 ? y - box.y2 : 0;
        return Math.hypot(dx, dy);
    }

    function overlapRatio(a, b) {
        const x1 = Math.max(a.x1, b.x1);
        const y1 = Math.max(a.y1, b.y1);
        const x2 = Math.min(a.x2, b.x2);
        const y2 = Math.min(a.y2, b.y2);
        if (x2 <= x1 || y2 <= y1) return 0;
        const intersection = (x2 - x1) * (y2 - y1);
        return intersection / Math.min(Math.max(1, a.w * a.h), Math.max(1, b.w * b.h));
    }

    function manualGroupFromSeed(seed) {
        const options = sheet.lastOptions || smartOptions(sheet.rawComponents);
        const typical = options.typical || deriveTypical(sheet.rawComponents, sheet.width, sheet.height);
        const maxGap = Math.max(8, Math.round(options.mergeGap * 2.2));
        const maxW = Math.max(24, options.maxW * 1.25, typical.w * 4.5);
        const maxH = Math.max(24, options.maxH * 1.25, typical.h * 4);
        const chosen = [seed];
        const chosenSet = new Set([seed]);
        let combined = aggregateBoxes(chosen);
        let changed = true;

        while (changed) {
            changed = false;
            for (const candidate of sheet.rawComponents) {
                if (chosenSet.has(candidate) || candidate.pixels < 2) continue;
                const gap = boxGap(combined, candidate);
                if (gap.dx > maxGap || gap.dy > maxGap || gap.distance > maxGap * 1.5) continue;
                const test = aggregateBoxes([...chosen, candidate]);
                if (test.w > maxW || test.h > maxH) continue;
                chosen.push(candidate);
                chosenSet.add(candidate);
                combined = test;
                changed = true;
            }
        }
        combined.manual = true;
        return combined;
    }

    async function addMissedSpriteAt(sourceX, sourceY) {
        if (!sheet.rawComponents.length) {
            setStatus('warning', 'Run Smart detect first.');
            return;
        }
        const typical = sheet.typical || deriveTypical(sheet.rawComponents, sheet.width, sheet.height);
        const searchRadius = Math.max(30, Math.round(Math.max(typical.w, typical.h) * 1.35));
        let best = null;
        let bestDistance = Infinity;
        for (const component of sheet.rawComponents) {
            const distance = distancePointToBox(sourceX, sourceY, component);
            if (distance < bestDistance) {
                best = component;
                bestDistance = distance;
            }
        }
        if (!best || bestDistance > searchRadius) {
            setStatus('warning', 'No foreground pixels were close enough to that point. Tap closer to the visible sprite.');
            return;
        }

        const box = manualGroupFromSeed(best);
        const existingIndex = sheet.sprites.findIndex(sprite => overlapRatio(sprite.box, box) >= 0.55);
        if (existingIndex >= 0) {
            sheet.sprites[existingIndex].selected = true;
            setManualPickMode(false);
            drawSheetPreview();
            renderSpriteGrid();
            setStatus('info', `<strong>That frame was already detected</strong> as ${escapeHtml(sheet.sprites[existingIndex].name)}. It has been selected for you.`);
            return;
        }

        const sprite = await extractSprite(box, outputSize(), sheet.sprites.length + 1, sheet.lastOptions);
        sprite.manual = true;
        sprite.uncertain = false;
        sheet.sprites.push(sprite);
        sortSpritesSpatially();
        updateSpriteNames();
        setManualPickMode(false);
        drawSheetPreview();
        renderSpriteGrid();
        setStatus('ok', `<strong>Missed sprite added.</strong> ${escapeHtml(sprite.name)} was built from the foreground pieces nearest your tap.`);
    }

    function sortSpritesSpatially() {
        const threshold = sheet.lastOptions?.rowThreshold || Math.max(8, Math.round((sheet.typical?.h || 40) * 0.55));
        const rows = orderBoxesIntoRows(sheet.sprites.map(sprite => sprite.box), threshold);
        const order = rows.flatMap(row => row.boxes);
        const map = new Map(sheet.sprites.map(sprite => [sprite.box, sprite]));
        sheet.sprites = order.map(box => {
            const sprite = map.get(box);
            sprite.row = box.row;
            return sprite;
        });
        sheet.rows = rows.length;
    }

    async function handlePreviewTap(event) {
        if (!sheet.image) return;
        const rect = el.preview.getBoundingClientRect();
        if (!rect.width || !rect.height) return;
        const canvasX = (event.clientX - rect.left) * (el.preview.width / rect.width);
        const canvasY = (event.clientY - rect.top) * (el.preview.height / rect.height);
        const sourceX = (canvasX / el.preview.width) * sheet.width;
        const sourceY = (canvasY / el.preview.height) * sheet.height;

        if (manualPickMode) {
            event.preventDefault();
            await addMissedSpriteAt(sourceX, sourceY);
            return;
        }

        let bestIndex = -1;
        let bestArea = Infinity;
        sheet.sprites.forEach((sprite, index) => {
            const box = sprite.box;
            if (sourceX >= box.x1 && sourceX <= box.x2 && sourceY >= box.y1 && sourceY <= box.y2) {
                const area = box.w * box.h;
                if (area < bestArea) {
                    bestArea = area;
                    bestIndex = index;
                }
            }
        });
        if (bestIndex >= 0) {
            sheet.sprites[bestIndex].selected = !sheet.sprites[bestIndex].selected;
            drawSheetPreview();
            renderSpriteGrid();
        }
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

    function updateModeHelp() {
        if (!smartUi.help) return;
        const messages = {
            auto: 'Automatic analyzes this Sprite Sheet and chooses the technical thresholds for you.',
            sensitive: 'Sensitive keeps smaller pieces and uses a larger safe merge distance. Use it when Automatic misses several frames.',
            strict: 'Strict ignores more small/noisy components. Use it when Automatic finds decorations that are not sprites.',
            expert: 'Expert uses the numeric values inside “Expert detection settings”.'
        };
        smartUi.help.textContent = messages[detectionMode()];
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
        setStatus('info', 'Load a PNG Sprite Sheet. Automatic detection is recommended; solid backgrounds can be removed with one tap.');
    });
    el.prefix.addEventListener('input', () => {
        if (!sheet.sprites.length) return;
        updateSpriteNames();
        renderSpriteGrid();
    });
    el.size.addEventListener('change', () => {
        if (sheet.image) detectAndExtract();
    });

    smartUi.mode?.addEventListener('change', () => {
        updateModeHelp();
        if (sheet.image) detectAndExtract();
    });
    smartUi.addMissed?.addEventListener('click', () => setManualPickMode(!manualPickMode));

    for (const input of [el.minPixels, el.maxPixels, el.minDim, el.maxDim, el.rowThreshold, smartUi.mergeGap]) {
        input?.addEventListener('change', () => {
            if (sheet.image && detectionMode() === 'expert') detectAndExtract();
        });
    }

    el.preview.addEventListener('pointerup', handlePreviewTap);
    el.preview.addEventListener('contextmenu', event => {
        if (manualPickMode) event.preventDefault();
    });

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

    updateModeHelp();
    setStatus('info', 'Load a PNG Sprite Sheet. <strong>Automatic</strong> detection is recommended; you should not need to change the Expert settings.');
    refreshTargetAnimations();
    updateSelectionCount();
})();