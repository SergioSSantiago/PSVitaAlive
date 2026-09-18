(() => {
    'use strict';

    const SCREEN_W = 960;
    const SCREEN_H = 544;
    const SAFE_MARGIN = 16;
    const SPRITE_W = 100;
    const SPRITE_H = 100;
    const MIN_RUN_DISTANCE = 100;
    const textEncoder = new TextEncoder();
    const textDecoder = new TextDecoder();

    const el = {
        form: document.getElementById('mascot-form'),
        mascotId: document.getElementById('mascot-id'),
        mascotName: document.getElementById('mascot-name'),
        nativeFacing: document.getElementById('native-facing'),
        runSpeed: document.getElementById('run-speed'),
        runMax: document.getElementById('run-max'),
        idleMin: document.getElementById('idle-min'),
        idleMax: document.getElementById('idle-max'),
        idleAnimations: document.getElementById('idle-animations'),
        runAnimations: document.getElementById('run-animations'),
        validation: document.getElementById('validation-summary'),
        jsonPreview: document.getElementById('json-preview'),
        copyJson: document.getElementById('copy-json'),
        downloadJson: document.getElementById('download-json'),
        downloadZip: document.getElementById('download-zip'),
        importZip: document.getElementById('import-zip'),
        importJson: document.getElementById('import-json'),
        importImages: document.getElementById('import-images'),
        resetProject: document.getElementById('reset-project'),
        restartPreview: document.getElementById('restart-preview'),
        previewAnimation: document.getElementById('preview-animation'),
        canvas: document.getElementById('vita-preview'),
        runtimeState: document.getElementById('runtime-state'),
        runtimeFacing: document.getElementById('runtime-facing'),
        runtimeAnimation: document.getElementById('runtime-animation'),
        debugSafe: document.getElementById('debug-safe'),
        debugBounds: document.getElementById('debug-bounds'),
        debugTarget: document.getElementById('debug-target')
    };

    const ctx = el.canvas.getContext('2d');
    let uidCounter = 0;
    let previewMode = 'auto';
    let project = createDefaultProject();
    let dragFrame = null;

    const runtime = {
        state: 'idle',
        x: 140,
        y: 310,
        targetX: 600,
        targetY: 300,
        facingRight: true,
        animationIndex: 0,
        frameIndex: 0,
        stateStartedAt: 0,
        stateDuration: 3000,
        frameStartedAt: 0,
        lastTick: performance.now(),
        animationName: '—'
    };

    function uid() {
        uidCounter += 1;
        return `m${Date.now().toString(36)}${uidCounter.toString(36)}`;
    }

    function createDefaultProject() {
        return {
            id: '',
            name: '',
            native_facing: 'right',
            width: 100,
            height: 100,
            behavior: {
                run_speed: 150,
                idle_min_ms: 2000,
                idle_max_ms: 5000,
                run_max_ms: 4000
            },
            animations: {
                idle: [createAnimation('idle', 'normal', 150)],
                run: [createAnimation('run', 'run', 90)]
            }
        };
    }

    function createAnimation(state, name, frameMs) {
        return {
            uid: uid(),
            state,
            name,
            frame_ms: frameMs,
            frames: []
        };
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replaceAll('&', '&amp;')
            .replaceAll('<', '&lt;')
            .replaceAll('>', '&gt;')
            .replaceAll('"', '&quot;')
            .replaceAll("'", '&#039;');
    }

    function basename(path) {
        return String(path || '').replaceAll('\\', '/').split('/').pop() || '';
    }

    function sanitizeFilename(name) {
        const base = basename(name).trim().replace(/\s+/g, '_').replace(/[^A-Za-z0-9._-]/g, '_');
        if (!base) return 'frame.png';
        return base.toLowerCase().endsWith('.png') ? base : `${base}.png`;
    }

    function sanitizeId(value) {
        return String(value || '').toLowerCase().trim().replace(/\s+/g, '-').replace(/[^a-z0-9_-]/g, '');
    }

    function allFrames() {
        return [...project.animations.idle, ...project.animations.run].flatMap(animation => animation.frames);
    }

    function usedFrameNames(exceptFrame = null) {
        return new Set(allFrames().filter(frame => frame !== exceptFrame).map(frame => frame.name));
    }

    function uniqueFrameName(name, exceptFrame = null) {
        const clean = sanitizeFilename(name);
        const used = usedFrameNames(exceptFrame);
        if (!used.has(clean)) return clean;
        const dot = clean.lastIndexOf('.');
        const stem = dot > 0 ? clean.slice(0, dot) : clean;
        const ext = dot > 0 ? clean.slice(dot) : '.png';
        let number = 2;
        while (used.has(`${stem}_${number}${ext}`)) number += 1;
        return `${stem}_${number}${ext}`;
    }

    function isPng(bytes) {
        return bytes && bytes.length >= 8 &&
            bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47 &&
            bytes[4] === 0x0d && bytes[5] === 0x0a && bytes[6] === 0x1a && bytes[7] === 0x0a;
    }

    function loadImageFromUrl(url) {
        return new Promise((resolve, reject) => {
            const image = new Image();
            image.onload = () => resolve(image);
            image.onerror = () => reject(new Error('The PNG could not be decoded.'));
            image.src = url;
        });
    }

    function canvasToPngBytes(image, width, height) {
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const canvasContext = canvas.getContext('2d');
        canvasContext.clearRect(0, 0, width, height);
        // Mascot assets are usually pixel-art sprites. Keep resize deterministic and crisp.
        canvasContext.imageSmoothingEnabled = false;
        canvasContext.drawImage(image, 0, 0, width, height);
        return new Promise((resolve, reject) => {
            canvas.toBlob(async blob => {
                if (!blob) {
                    reject(new Error('Could not normalize the PNG frame.'));
                    return;
                }
                resolve(new Uint8Array(await blob.arrayBuffer()));
            }, 'image/png');
        });
    }

    async function frameFromBytes(name, bytes, allowMissing = false) {
        if (!bytes) {
            if (allowMissing) return {
                uid: uid(), name: sanitizeFilename(name), bytes: null, url: '', image: null,
                width: 0, height: 0, sourceWidth: 0, sourceHeight: 0, normalized: false, missing: true
            };
            throw new Error(`Missing image data for ${name}`);
        }
        if (!isPng(bytes)) throw new Error(`${name} is not a PNG file.`);

        let outputBytes = bytes;
        let blob = new Blob([outputBytes], { type: 'image/png' });
        let url = URL.createObjectURL(blob);
        try {
            let image = await loadImageFromUrl(url);
            const sourceWidth = image.naturalWidth;
            const sourceHeight = image.naturalHeight;
            if (sourceWidth <= 0 || sourceHeight <= 0) throw new Error(`${name} has invalid PNG dimensions.`);

            let normalized = false;
            if (sourceWidth > SPRITE_W || sourceHeight > SPRITE_H) {
                const scale = Math.min(SPRITE_W / sourceWidth, SPRITE_H / sourceHeight);
                const targetWidth = Math.max(1, Math.round(sourceWidth * scale));
                const targetHeight = Math.max(1, Math.round(sourceHeight * scale));
                outputBytes = await canvasToPngBytes(image, targetWidth, targetHeight);
                URL.revokeObjectURL(url);
                blob = new Blob([outputBytes], { type: 'image/png' });
                url = URL.createObjectURL(blob);
                image = await loadImageFromUrl(url);
                normalized = true;
            }

            return {
                uid: uid(),
                name: sanitizeFilename(name),
                bytes: outputBytes,
                url,
                image,
                width: image.naturalWidth,
                height: image.naturalHeight,
                sourceWidth,
                sourceHeight,
                normalized,
                missing: false
            };
        } catch (error) {
            URL.revokeObjectURL(url);
            throw error;
        }
    }

    async function frameFromFile(file) {
        const bytes = new Uint8Array(await file.arrayBuffer());
        const frame = await frameFromBytes(file.name, bytes);
        frame.name = uniqueFrameName(file.name);
        return frame;
    }

    function disposeFrame(frame) {
        if (frame && frame.url) URL.revokeObjectURL(frame.url);
    }

    function disposeProjectFrames() {
        allFrames().forEach(disposeFrame);
    }

    function syncProjectFromForm() {
        project.id = sanitizeId(el.mascotId.value);
        if (el.mascotId.value !== project.id) el.mascotId.value = project.id;
        project.name = el.mascotName.value.trim();
        project.native_facing = el.nativeFacing.value === 'left' ? 'left' : 'right';
        project.behavior.run_speed = Number(el.runSpeed.value) || 0;
        project.behavior.idle_min_ms = Number(el.idleMin.value) || 0;
        project.behavior.idle_max_ms = Number(el.idleMax.value) || 0;
        project.behavior.run_max_ms = Number(el.runMax.value) || 0;
    }

    function syncFormFromProject() {
        el.mascotId.value = project.id;
        el.mascotName.value = project.name;
        el.nativeFacing.value = project.native_facing;
        el.runSpeed.value = project.behavior.run_speed;
        el.idleMin.value = project.behavior.idle_min_ms;
        el.idleMax.value = project.behavior.idle_max_ms;
        el.runMax.value = project.behavior.run_max_ms;
    }

    function manifestObject() {
        syncProjectFromForm();
        return {
            schema_version: 1,
            name: project.name,
            native_facing: project.native_facing,
            width: 100,
            height: 100,
            behavior: {
                run_speed: project.behavior.run_speed,
                idle_min_ms: project.behavior.idle_min_ms,
                idle_max_ms: project.behavior.idle_max_ms,
                run_max_ms: project.behavior.run_max_ms
            },
            animations: {
                idle: project.animations.idle.map(animation => ({
                    name: animation.name.trim(),
                    frame_ms: Number(animation.frame_ms) || 0,
                    frames: animation.frames.map(frame => frame.name)
                })),
                run: project.animations.run.map(animation => ({
                    name: animation.name.trim(),
                    frame_ms: Number(animation.frame_ms) || 0,
                    frames: animation.frames.map(frame => frame.name)
                }))
            }
        };
    }

    function manifestJson() {
        return `${JSON.stringify(manifestObject(), null, 2)}\n`;
    }

    function validateProject() {
        syncProjectFromForm();
        const errors = [];
        const warnings = [];

        if (!project.id) errors.push('Mascot ID is required.');
        else if (!/^[a-z0-9_-]+$/.test(project.id)) errors.push('Mascot ID may only contain lowercase letters, numbers, hyphens and underscores.');
        if (!project.name) errors.push('Display name is required.');
        if (!['left', 'right'].includes(project.native_facing)) errors.push('Native facing must be left or right.');
        if (project.behavior.run_speed <= 0) errors.push('Run speed must be greater than 0.');
        if (project.behavior.idle_min_ms <= 0) errors.push('Idle minimum must be greater than 0.');
        if (project.behavior.idle_max_ms < project.behavior.idle_min_ms) errors.push('Idle maximum must be greater than or equal to Idle minimum.');
        if (project.behavior.run_max_ms <= 0) errors.push('Run maximum must be greater than 0.');

        for (const state of ['idle', 'run']) {
            const list = project.animations[state];
            if (!list.length) errors.push(`At least one ${state === 'idle' ? 'Idle' : 'Run'} animation is required.`);
            const names = new Set();
            list.forEach((animation, animationIndex) => {
                const label = `${state === 'idle' ? 'Idle' : 'Run'} animation ${animationIndex + 1}`;
                if (!animation.name.trim()) errors.push(`${label} needs a name.`);
                else if (names.has(animation.name.trim())) warnings.push(`${label} repeats the animation name “${animation.name.trim()}”.`);
                names.add(animation.name.trim());
                if (!(Number(animation.frame_ms) > 0)) errors.push(`${label} frame time must be greater than 0 ms.`);
                if (!animation.frames.length) errors.push(`${label} needs at least one PNG frame.`);
                animation.frames.forEach(frame => {
                    if (frame.missing || !frame.bytes) errors.push(`${label} is missing frame file ${frame.name}.`);
                    if (frame.bytes && !isPng(frame.bytes)) errors.push(`${frame.name} is not a valid PNG.`);
                    if (frame.bytes && (frame.width <= 0 || frame.height <= 0)) errors.push(`${frame.name} has invalid dimensions.`);
                    if (frame.bytes && (frame.width > SPRITE_W || frame.height > SPRITE_H)) errors.push(`${frame.name} exceeds the 100×100 asset limit after normalization.`);
                    if (frame.normalized) warnings.push(`${frame.name} was normalized from ${frame.sourceWidth}×${frame.sourceHeight} to ${frame.width}×${frame.height} without changing its aspect ratio.`);
                });
            });
        }

        const frameNames = allFrames().map(frame => frame.name);
        const duplicateFrameNames = frameNames.filter((name, index) => frameNames.indexOf(name) !== index);
        [...new Set(duplicateFrameNames)].forEach(name => errors.push(`Frame filename ${name} is used more than once. Every frame filename must be unique.`));

        if (allFrames().length > 30) warnings.push(`This mascot uses ${allFrames().length} frames. Keep texture count modest for PS Vita memory usage.`);
        return { errors, warnings };
    }

    function renderValidation() {
        const result = validateProject();
        el.downloadJson.disabled = result.errors.length > 0;
        el.downloadZip.disabled = result.errors.length > 0;
        const groups = [];
        if (result.errors.length) groups.push(`<div class="validation-group"><strong>Errors (${result.errors.length})</strong><ul>${result.errors.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></div>`);
        if (result.warnings.length) groups.push(`<div class="validation-group"><strong>Warnings (${result.warnings.length})</strong><ul>${result.warnings.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></div>`);
        if (!result.errors.length && !result.warnings.length) {
            el.validation.className = 'validation-summary ok';
            el.validation.innerHTML = '<strong>Ready to export.</strong> The manifest and all referenced PNG frames pass the current mascot package checks.';
        } else {
            el.validation.className = `validation-summary ${result.errors.length ? 'error' : 'warning'}`;
            el.validation.innerHTML = groups.join('');
        }
        return result;
    }

    function renderJson() {
        el.jsonPreview.textContent = manifestJson();
    }

    function animationCardHtml(animation, state, index) {
        const frames = animation.frames.length ? animation.frames.map((frame, frameIndex) => {
            const thumb = frame.image && frame.url
                ? `<img src="${escapeHtml(frame.url)}" alt="${escapeHtml(frame.name)}">`
                : `<div class="frame-thumb missing">Missing<br>${escapeHtml(frame.name)}</div>`;
            const thumbWrap = frame.image && frame.url ? `<div class="frame-thumb">${thumb}</div>` : thumb;
            const dimensions = frame.bytes
                ? (frame.normalized ? `${frame.width}×${frame.height} · normalized from ${frame.sourceWidth}×${frame.sourceHeight}` : `${frame.width}×${frame.height}`)
                : 'not loaded';
            return `<div class="frame-card" draggable="true" data-state="${state}" data-animation="${index}" data-frame="${frameIndex}">
                ${thumbWrap}
                <div class="frame-name">${escapeHtml(frame.name)}</div>
                <div class="frame-meta">${escapeHtml(dimensions)}</div>
                <div class="frame-actions">
                    <button type="button" data-action="frame-left" title="Move left">←</button>
                    <button type="button" data-action="frame-right" title="Move right">→</button>
                    <button type="button" class="danger" data-action="frame-remove" title="Remove">×</button>
                </div>
            </div>`;
        }).join('') : '<div class="empty-animations">No frames yet. Drop or choose PNG files below. Smaller sprites are kept as-is; larger ones are normalized to fit 100×100.</div>';

        return `<article class="animation-card" data-state="${state}" data-animation="${index}">
            <div class="animation-card-header">
                <label><span>Animation name</span><input class="animation-name" value="${escapeHtml(animation.name)}" placeholder="${state === 'idle' ? 'blink' : 'run'}"></label>
                <label><span>Frame time</span><input class="animation-frame-ms" type="number" min="1" step="1" value="${Number(animation.frame_ms) || 0}"></label>
                <button class="small-button remove-button" data-action="animation-remove" type="button">Remove</button>
            </div>
            <label class="dropzone" data-state="${state}" data-animation="${index}">
                <strong>Add PNG frames</strong><br>Click or drag files here · order can be changed below
                <input class="frame-input" type="file" accept="image/png,.png" multiple>
            </label>
            <div class="frame-list">${frames}</div>
        </article>`;
    }

    function renderAnimations() {
        el.idleAnimations.innerHTML = project.animations.idle.length
            ? project.animations.idle.map((animation, index) => animationCardHtml(animation, 'idle', index)).join('')
            : '<div class="empty-animations">No Idle animations. Add one to continue.</div>';
        el.runAnimations.innerHTML = project.animations.run.length
            ? project.animations.run.map((animation, index) => animationCardHtml(animation, 'run', index)).join('')
            : '<div class="empty-animations">No Run animations. Add one to continue.</div>';
        renderPreviewAnimationOptions();
    }

    function renderPreviewAnimationOptions() {
        const state = previewMode === 'run' ? 'run' : 'idle';
        const previous = el.previewAnimation.value;
        const options = ['<option value="random">Random</option>'];
        project.animations[state].forEach((animation, index) => {
            options.push(`<option value="${index}">${escapeHtml(animation.name || `${state} ${index + 1}`)}</option>`);
        });
        el.previewAnimation.innerHTML = options.join('');
        if ([...el.previewAnimation.options].some(option => option.value === previous)) el.previewAnimation.value = previous;
    }

    function syncUi() {
        renderJson();
        renderValidation();
    }

    function addAnimation(state) {
        const list = project.animations[state];
        const number = list.length + 1;
        list.push(createAnimation(state, state === 'idle' ? `idle_${number}` : `run_${number}`, state === 'idle' ? 150 : 90));
        renderAnimations();
        syncUi();
        restartPreview();
    }

    function moveFrame(state, animationIndex, frameIndex, delta) {
        const frames = project.animations[state]?.[animationIndex]?.frames;
        if (!frames) return;
        const target = frameIndex + delta;
        if (target < 0 || target >= frames.length) return;
        [frames[frameIndex], frames[target]] = [frames[target], frames[frameIndex]];
        renderAnimations();
        syncUi();
    }

    async function addFilesToAnimation(state, animationIndex, files) {
        const animation = project.animations[state]?.[animationIndex];
        if (!animation) return;
        const failures = [];
        for (const file of files) {
            try {
                const cleanIncoming = sanitizeFilename(file.name);
                const missingIndex = animation.frames.findIndex(frame => frame.missing && frame.name === cleanIncoming);
                const frame = await frameFromFile(file);
                if (missingIndex >= 0) {
                    disposeFrame(animation.frames[missingIndex]);
                    frame.name = cleanIncoming;
                    animation.frames[missingIndex] = frame;
                } else {
                    animation.frames.push(frame);
                }
            } catch (error) {
                failures.push(`${file.name}: ${error.message}`);
            }
        }
        renderAnimations();
        syncUi();
        restartPreview();
        if (failures.length) alert(`Some files were skipped:\n\n${failures.join('\n')}`);
    }

    async function importImagesGlobally(files) {
        const unmatched = [];
        const failures = [];
        for (const file of files) {
            const clean = sanitizeFilename(file.name);
            let target = null;
            for (const state of ['idle', 'run']) {
                for (const animation of project.animations[state]) {
                    const index = animation.frames.findIndex(frame => frame.missing && frame.name === clean);
                    if (index >= 0) {
                        target = { animation, index };
                        break;
                    }
                }
                if (target) break;
            }
            if (!target) {
                unmatched.push(file.name);
                continue;
            }
            try {
                const bytes = new Uint8Array(await file.arrayBuffer());
                const frame = await frameFromBytes(clean, bytes);
                frame.name = clean;
                disposeFrame(target.animation.frames[target.index]);
                target.animation.frames[target.index] = frame;
            } catch (error) {
                failures.push(`${file.name}: ${error.message}`);
            }
        }
        renderAnimations();
        syncUi();
        restartPreview();
        const messages = [];
        if (unmatched.length) messages.push(`No matching missing frame reference for:\n${unmatched.join('\n')}`);
        if (failures.length) messages.push(`Could not load:\n${failures.join('\n')}`);
        if (messages.length) alert(messages.join('\n\n'));
    }

    function animationEventContext(target) {
        const card = target.closest('.animation-card');
        if (!card) return null;
        return { state: card.dataset.state, animationIndex: Number(card.dataset.animation), card };
    }

    function handleAnimationInput(event) {
        const context = animationEventContext(event.target);
        if (!context) return;
        const animation = project.animations[context.state]?.[context.animationIndex];
        if (!animation) return;
        if (event.target.classList.contains('animation-name')) animation.name = event.target.value;
        if (event.target.classList.contains('animation-frame-ms')) animation.frame_ms = Number(event.target.value) || 0;
        syncUi();
        renderPreviewAnimationOptions();
    }

    async function handleAnimationChange(event) {
        if (!event.target.classList.contains('frame-input')) return;
        const context = animationEventContext(event.target);
        if (!context) return;
        await addFilesToAnimation(context.state, context.animationIndex, [...event.target.files]);
        event.target.value = '';
    }

    function handleAnimationClick(event) {
        const action = event.target.dataset.action;
        if (!action) return;
        const context = animationEventContext(event.target);
        if (!context) return;
        const animation = project.animations[context.state]?.[context.animationIndex];
        if (!animation) return;

        if (action === 'animation-remove') {
            animation.frames.forEach(disposeFrame);
            project.animations[context.state].splice(context.animationIndex, 1);
            renderAnimations();
            syncUi();
            restartPreview();
            return;
        }

        const frameCard = event.target.closest('.frame-card');
        if (!frameCard) return;
        const frameIndex = Number(frameCard.dataset.frame);
        if (action === 'frame-left') moveFrame(context.state, context.animationIndex, frameIndex, -1);
        if (action === 'frame-right') moveFrame(context.state, context.animationIndex, frameIndex, 1);
        if (action === 'frame-remove') {
            const [removed] = animation.frames.splice(frameIndex, 1);
            disposeFrame(removed);
            renderAnimations();
            syncUi();
            restartPreview();
        }
    }

    function handleDragStart(event) {
        const card = event.target.closest('.frame-card');
        if (!card) return;
        dragFrame = {
            state: card.dataset.state,
            animationIndex: Number(card.dataset.animation),
            frameIndex: Number(card.dataset.frame)
        };
        card.classList.add('dragging');
        event.dataTransfer.effectAllowed = 'move';
    }

    function handleDragOver(event) {
        const frameCard = event.target.closest('.frame-card');
        const dropzone = event.target.closest('.dropzone');
        if (frameCard || dropzone) {
            event.preventDefault();
            event.dataTransfer.dropEffect = frameCard ? 'move' : 'copy';
        }
        if (frameCard && dragFrame) frameCard.classList.add('drag-over');
        if (dropzone && !dragFrame) dropzone.classList.add('drag-over');
    }

    function handleDragLeave(event) {
        event.target.closest('.frame-card')?.classList.remove('drag-over');
        event.target.closest('.dropzone')?.classList.remove('drag-over');
    }

    async function handleDrop(event) {
        const frameCard = event.target.closest('.frame-card');
        const dropzone = event.target.closest('.dropzone');
        if (!frameCard && !dropzone) return;
        event.preventDefault();

        if (dragFrame && frameCard) {
            const target = {
                state: frameCard.dataset.state,
                animationIndex: Number(frameCard.dataset.animation),
                frameIndex: Number(frameCard.dataset.frame)
            };
            if (dragFrame.state === target.state && dragFrame.animationIndex === target.animationIndex && dragFrame.frameIndex !== target.frameIndex) {
                const frames = project.animations[target.state][target.animationIndex].frames;
                const [moved] = frames.splice(dragFrame.frameIndex, 1);
                frames.splice(target.frameIndex, 0, moved);
            }
            dragFrame = null;
            renderAnimations();
            syncUi();
            return;
        }

        if (dropzone && event.dataTransfer.files?.length) {
            const state = dropzone.dataset.state;
            const animationIndex = Number(dropzone.dataset.animation);
            await addFilesToAnimation(state, animationIndex, [...event.dataTransfer.files]);
        }
    }

    function handleDragEnd() {
        dragFrame = null;
        document.querySelectorAll('.frame-card.dragging, .frame-card.drag-over, .dropzone.drag-over').forEach(node => node.classList.remove('dragging', 'drag-over'));
    }

    function randomBetween(min, max) {
        return min + Math.random() * Math.max(0, max - min);
    }

    function randomInt(maxExclusive) {
        return maxExclusive > 0 ? Math.floor(Math.random() * maxExclusive) : 0;
    }

    function selectedAnimationIndex(state) {
        if (previewMode === 'auto') return null;
        const value = el.previewAnimation.value;
        if (value === 'random') return null;
        const index = Number(value);
        return Number.isInteger(index) && project.animations[state][index] ? index : null;
    }

    function chooseAnimationIndex(state) {
        const forced = selectedAnimationIndex(state);
        if (forced !== null) return forced;
        const candidates = project.animations[state]
            .map((animation, index) => ({ animation, index }))
            .filter(item => item.animation.frames.some(frame => frame.image && !frame.missing));
        return candidates.length ? candidates[randomInt(candidates.length)].index : 0;
    }

    function chooseRunTarget() {
        const minX = SAFE_MARGIN;
        const maxX = SCREEN_W - SAFE_MARGIN - SPRITE_W;
        const minY = SAFE_MARGIN;
        const maxY = SCREEN_H - SAFE_MARGIN - SPRITE_H;
        let best = { x: randomBetween(minX, maxX), y: randomBetween(minY, maxY) };
        for (let attempt = 0; attempt < 12; attempt += 1) {
            const candidate = { x: randomBetween(minX, maxX), y: randomBetween(minY, maxY) };
            const dx = candidate.x - runtime.x;
            const dy = candidate.y - runtime.y;
            best = candidate;
            if (Math.hypot(dx, dy) >= MIN_RUN_DISTANCE) break;
        }
        runtime.targetX = best.x;
        runtime.targetY = best.y;
        if (Math.abs(runtime.targetX - runtime.x) > 0.5) runtime.facingRight = runtime.targetX > runtime.x;
    }

    function startRuntimeState(state, now = performance.now()) {
        runtime.state = state;
        runtime.stateStartedAt = now;
        runtime.frameStartedAt = now;
        runtime.frameIndex = 0;
        runtime.animationIndex = chooseAnimationIndex(state);
        const animation = project.animations[state][runtime.animationIndex];
        runtime.animationName = animation?.name || '—';
        if (state === 'idle') {
            runtime.stateDuration = randomBetween(project.behavior.idle_min_ms, project.behavior.idle_max_ms);
        } else {
            runtime.stateDuration = Math.max(1, project.behavior.run_max_ms);
            chooseRunTarget();
        }
        updateRuntimeLabels();
    }

    function restartPreview() {
        syncProjectFromForm();
        runtime.x = randomBetween(SAFE_MARGIN, SCREEN_W - SAFE_MARGIN - SPRITE_W);
        runtime.y = randomBetween(SAFE_MARGIN, SCREEN_H - SAFE_MARGIN - SPRITE_H);
        runtime.facingRight = project.native_facing === 'right';
        runtime.lastTick = performance.now();
        const initial = previewMode === 'run' ? 'run' : previewMode === 'idle' ? 'idle' : (Math.random() < 0.5 ? 'idle' : 'run');
        startRuntimeState(initial, runtime.lastTick);
    }

    function nextRuntimeState(now) {
        if (previewMode === 'idle') return startRuntimeState('idle', now);
        if (previewMode === 'run') return startRuntimeState('run', now);
        startRuntimeState(Math.random() < 0.5 ? 'idle' : 'run', now);
    }

    function currentAnimation() {
        return project.animations[runtime.state]?.[runtime.animationIndex] || null;
    }

    function advanceAnimation(now) {
        const animation = currentAnimation();
        if (!animation || !animation.frames.length) return;
        const frameMs = Math.max(1, Number(animation.frame_ms) || 1);
        if (now - runtime.frameStartedAt >= frameMs) {
            const steps = Math.max(1, Math.floor((now - runtime.frameStartedAt) / frameMs));
            runtime.frameIndex = (runtime.frameIndex + steps) % animation.frames.length;
            runtime.frameStartedAt += steps * frameMs;
        }
    }

    function updateRuntime(now) {
        const dt = Math.min(0.05, Math.max(0, (now - runtime.lastTick) / 1000));
        runtime.lastTick = now;
        advanceAnimation(now);

        if (runtime.state === 'idle') {
            if (now - runtime.stateStartedAt >= runtime.stateDuration) nextRuntimeState(now);
            return;
        }

        const dx = runtime.targetX - runtime.x;
        const dy = runtime.targetY - runtime.y;
        const distance = Math.hypot(dx, dy);
        const step = Math.max(0, project.behavior.run_speed) * dt;
        if (Math.abs(dx) > 0.5) runtime.facingRight = dx > 0;
        if (distance <= Math.max(1, step)) {
            runtime.x = runtime.targetX;
            runtime.y = runtime.targetY;
            nextRuntimeState(now);
        } else if (distance > 0) {
            runtime.x += (dx / distance) * step;
            runtime.y += (dy / distance) * step;
        }

        runtime.x = Math.min(SCREEN_W - SAFE_MARGIN - SPRITE_W, Math.max(SAFE_MARGIN, runtime.x));
        runtime.y = Math.min(SCREEN_H - SAFE_MARGIN - SPRITE_H, Math.max(SAFE_MARGIN, runtime.y));
        if (runtime.state === 'run' && now - runtime.stateStartedAt >= runtime.stateDuration) nextRuntimeState(now);
    }

    function drawProtectionUi() {
        ctx.save();
        ctx.fillStyle = '#000';
        ctx.fillRect(0, 0, SCREEN_W, SCREEN_H);
        ctx.textBaseline = 'top';
        ctx.font = '700 30px system-ui, sans-serif';
        ctx.fillStyle = '#3bff00';
        ctx.fillText('PSVitaAlive', 310, 162);
        ctx.font = '600 22px system-ui, sans-serif';
        ctx.fillStyle = '#d2d2d2';
        ctx.fillText('Downloading', 310, 207);
        ctx.font = '800 42px system-ui, sans-serif';
        ctx.fillStyle = '#3bff00';
        ctx.fillText('62%', 310, 243);
        ctx.font = '500 19px system-ui, sans-serif';
        ctx.fillStyle = '#9a9a9a';
        ctx.fillText('ETA 03:42', 310, 300);
        ctx.fillText('Press any button to return', 310, 334);
        ctx.restore();
    }

    function drawDebug() {
        ctx.save();
        if (el.debugSafe.checked) {
            ctx.setLineDash([8, 7]);
            ctx.strokeStyle = 'rgba(59,255,0,.55)';
            ctx.lineWidth = 2;
            ctx.strokeRect(SAFE_MARGIN, SAFE_MARGIN, SCREEN_W - SAFE_MARGIN * 2, SCREEN_H - SAFE_MARGIN * 2);
        }
        if (el.debugBounds.checked) {
            ctx.setLineDash([]);
            ctx.strokeStyle = 'rgba(255,255,255,.65)';
            ctx.lineWidth = 2;
            ctx.strokeRect(runtime.x, runtime.y, SPRITE_W, SPRITE_H);
        }
        if (el.debugTarget.checked && runtime.state === 'run') {
            ctx.setLineDash([5, 5]);
            ctx.strokeStyle = '#ffcc44';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(runtime.x + SPRITE_W / 2, runtime.y + SPRITE_H / 2);
            ctx.lineTo(runtime.targetX + SPRITE_W / 2, runtime.targetY + SPRITE_H / 2);
            ctx.stroke();
            ctx.setLineDash([]);
            ctx.beginPath();
            ctx.arc(runtime.targetX + SPRITE_W / 2, runtime.targetY + SPRITE_H / 2, 7, 0, Math.PI * 2);
            ctx.stroke();
        }
        ctx.restore();
    }

    function drawMascot() {
        const animation = currentAnimation();
        const frame = animation?.frames?.[runtime.frameIndex % Math.max(1, animation.frames.length)];
        if (!frame?.image || frame.missing) return;

        // 100×100 is the logical mascot area, not a required source-image size.
        // Scale the frame until one side fills the logical area, preserve aspect ratio,
        // then center the other side. This lets 64×64 sprites fill the full 100×100 area
        // while rectangular sprites remain undistorted.
        const sourceWidth = Math.max(1, frame.width || frame.image.naturalWidth || 1);
        const sourceHeight = Math.max(1, frame.height || frame.image.naturalHeight || 1);
        const scale = Math.min(SPRITE_W / sourceWidth, SPRITE_H / sourceHeight);
        const drawWidth = sourceWidth * scale;
        const drawHeight = sourceHeight * scale;
        const offsetX = (SPRITE_W - drawWidth) * 0.5;
        const offsetY = (SPRITE_H - drawHeight) * 0.5;

        const nativeRight = project.native_facing === 'right';
        const mirror = nativeRight !== runtime.facingRight;
        ctx.save();
        ctx.imageSmoothingEnabled = false;
        if (mirror) {
            ctx.translate(runtime.x + SPRITE_W, runtime.y);
            ctx.scale(-1, 1);
            ctx.drawImage(frame.image, offsetX, offsetY, drawWidth, drawHeight);
        } else {
            ctx.drawImage(frame.image, runtime.x + offsetX, runtime.y + offsetY, drawWidth, drawHeight);
        }
        ctx.restore();
    }

    function updateRuntimeLabels() {
        el.runtimeState.textContent = runtime.state === 'idle' ? 'Idle' : 'Run';
        el.runtimeFacing.textContent = runtime.facingRight ? 'Right' : 'Left';
        el.runtimeAnimation.textContent = runtime.animationName || '—';
    }

    function previewLoop(now) {
        updateRuntime(now);
        drawProtectionUi();
        drawMascot();
        drawDebug();
        updateRuntimeLabels();
        requestAnimationFrame(previewLoop);
    }

    function setPreviewMode(mode) {
        previewMode = ['auto', 'idle', 'run'].includes(mode) ? mode : 'auto';
        document.querySelectorAll('.preview-mode').forEach(button => button.classList.toggle('active', button.dataset.mode === previewMode));
        renderPreviewAnimationOptions();
        restartPreview();
    }

    function parseManifest(raw) {
        const manifest = typeof raw === 'string' ? JSON.parse(raw) : raw;
        if (!manifest || typeof manifest !== 'object') throw new Error('Manifest root must be a JSON object.');
        if (Number(manifest.schema_version) !== 1) throw new Error(`Unsupported schema_version: ${manifest.schema_version ?? 'missing'}. This editor currently supports version 1.`);
        const behavior = manifest.behavior || {};
        const animations = manifest.animations || {};
        return {
            id: '',
            name: String(manifest.name || ''),
            native_facing: manifest.native_facing === 'left' ? 'left' : 'right',
            width: 100,
            height: 100,
            behavior: {
                run_speed: Number(behavior.run_speed) || 0,
                idle_min_ms: Number(behavior.idle_min_ms) || 0,
                idle_max_ms: Number(behavior.idle_max_ms) || 0,
                run_max_ms: Number(behavior.run_max_ms) || 0
            },
            animations: {
                idle: Array.isArray(animations.idle) ? animations.idle.map(item => manifestAnimation('idle', item)) : [],
                run: Array.isArray(animations.run) ? animations.run.map(item => manifestAnimation('run', item)) : []
            }
        };
    }

    function manifestAnimation(state, item) {
        return {
            uid: uid(),
            state,
            name: String(item?.name || ''),
            frame_ms: Number(item?.frame_ms) || 0,
            frames: Array.isArray(item?.frames) ? item.frames.map(name => ({
                uid: uid(), name: sanitizeFilename(name), bytes: null, url: '', image: null,
                width: 0, height: 0, sourceWidth: 0, sourceHeight: 0, normalized: false, missing: true
            })) : []
        };
    }

    async function importManifestFile(file) {
        const text = await file.text();
        const next = parseManifest(text);
        disposeProjectFrames();
        next.id = sanitizeId(file.name.replace(/\.json$/i, '')) === 'mascot' ? '' : sanitizeId(file.name.replace(/\.json$/i, ''));
        project = next;
        syncFormFromProject();
        renderAnimations();
        syncUi();
        restartPreview();
    }

    function findEndOfCentralDirectory(bytes) {
        const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
        const min = Math.max(0, bytes.length - 65557);
        for (let offset = bytes.length - 22; offset >= min; offset -= 1) {
            if (view.getUint32(offset, true) === 0x06054b50) return offset;
        }
        return -1;
    }

    async function inflateRaw(bytes) {
        if (typeof DecompressionStream === 'undefined') throw new Error('This browser cannot import DEFLATE-compressed ZIP entries. Use a modern browser or a ZIP exported by this tool.');
        let stream;
        try {
            stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
        } catch (error) {
            throw new Error('This browser does not support raw DEFLATE ZIP import.');
        }
        return new Uint8Array(await new Response(stream).arrayBuffer());
    }

    async function readZip(arrayBuffer) {
        const bytes = new Uint8Array(arrayBuffer);
        const view = new DataView(arrayBuffer);
        const eocd = findEndOfCentralDirectory(bytes);
        if (eocd < 0) throw new Error('ZIP end-of-central-directory record was not found.');
        const entryCount = view.getUint16(eocd + 10, true);
        let cursor = view.getUint32(eocd + 16, true);
        const entries = new Map();

        for (let i = 0; i < entryCount; i += 1) {
            if (view.getUint32(cursor, true) !== 0x02014b50) throw new Error('Invalid ZIP central directory.');
            const method = view.getUint16(cursor + 10, true);
            const compressedSize = view.getUint32(cursor + 20, true);
            const uncompressedSize = view.getUint32(cursor + 24, true);
            const nameLength = view.getUint16(cursor + 28, true);
            const extraLength = view.getUint16(cursor + 30, true);
            const commentLength = view.getUint16(cursor + 32, true);
            const localOffset = view.getUint32(cursor + 42, true);
            const nameBytes = bytes.slice(cursor + 46, cursor + 46 + nameLength);
            const name = textDecoder.decode(nameBytes);
            cursor += 46 + nameLength + extraLength + commentLength;
            if (name.endsWith('/')) continue;

            if (view.getUint32(localOffset, true) !== 0x04034b50) throw new Error(`Invalid ZIP local header for ${name}.`);
            const localNameLength = view.getUint16(localOffset + 26, true);
            const localExtraLength = view.getUint16(localOffset + 28, true);
            const dataStart = localOffset + 30 + localNameLength + localExtraLength;
            const compressed = bytes.slice(dataStart, dataStart + compressedSize);
            let data;
            if (method === 0) data = compressed;
            else if (method === 8) data = await inflateRaw(compressed);
            else throw new Error(`ZIP compression method ${method} is not supported (${name}).`);
            if (uncompressedSize && data.length !== uncompressedSize) throw new Error(`ZIP size mismatch for ${name}.`);
            entries.set(name.replaceAll('\\', '/'), data);
        }
        return entries;
    }

    async function importZipFile(file) {
        const entries = await readZip(await file.arrayBuffer());
        const manifestPath = [...entries.keys()].find(name => basename(name).toLowerCase() === 'mascot.json');
        if (!manifestPath) throw new Error('The ZIP does not contain mascot.json.');
        const base = manifestPath.slice(0, manifestPath.length - basename(manifestPath).length);
        const next = parseManifest(textDecoder.decode(entries.get(manifestPath)));
        const folderName = base.replace(/\/$/, '').split('/').pop();
        next.id = sanitizeId(folderName || file.name.replace(/\.zip$/i, ''));

        for (const state of ['idle', 'run']) {
            for (const animation of next.animations[state]) {
                for (let index = 0; index < animation.frames.length; index += 1) {
                    const placeholder = animation.frames[index];
                    const exactPath = `${base}${placeholder.name}`;
                    const matchingPath = entries.has(exactPath)
                        ? exactPath
                        : [...entries.keys()].find(name => base === '' && basename(name) === placeholder.name);
                    const data = matchingPath ? entries.get(matchingPath) : null;
                    if (data) {
                        try {
                            const loaded = await frameFromBytes(placeholder.name, data);
                            loaded.name = placeholder.name;
                            animation.frames[index] = loaded;
                        } catch (error) {
                            animation.frames[index] = placeholder;
                        }
                    }
                }
            }
        }

        disposeProjectFrames();
        project = next;
        syncFormFromProject();
        renderAnimations();
        syncUi();
        restartPreview();
    }

    const crcTable = (() => {
        const table = new Uint32Array(256);
        for (let n = 0; n < 256; n += 1) {
            let c = n;
            for (let k = 0; k < 8; k += 1) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
            table[n] = c >>> 0;
        }
        return table;
    })();

    function crc32(bytes) {
        let c = 0xffffffff;
        for (const byte of bytes) c = crcTable[(c ^ byte) & 0xff] ^ (c >>> 8);
        return (c ^ 0xffffffff) >>> 0;
    }

    function dosDateTime(date = new Date()) {
        const year = Math.max(1980, date.getFullYear());
        const time = (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2);
        const day = ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate();
        return { time, date: day };
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
        view.setUint16(28, 0, true);
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
        view.setUint16(30, 0, true);
        view.setUint16(32, 0, true);
        view.setUint16(34, 0, true);
        view.setUint16(36, 0, true);
        view.setUint32(38, 0, true);
        view.setUint32(42, offset, true);
        out.set(nameBytes, 46);
        return out;
    }

    function endCentral(entryCount, centralSize, centralOffset) {
        const out = new Uint8Array(22);
        const view = new DataView(out.buffer);
        view.setUint32(0, 0x06054b50, true);
        view.setUint16(4, 0, true);
        view.setUint16(6, 0, true);
        view.setUint16(8, entryCount, true);
        view.setUint16(10, entryCount, true);
        view.setUint32(12, centralSize, true);
        view.setUint32(16, centralOffset, true);
        view.setUint16(20, 0, true);
        return out;
    }

    function buildZip(files) {
        const localParts = [];
        const centralParts = [];
        const stamp = dosDateTime();
        let offset = 0;
        for (const file of files) {
            const nameBytes = textEncoder.encode(file.name);
            const bytes = file.bytes instanceof Uint8Array ? file.bytes : new Uint8Array(file.bytes);
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

    function downloadManifest() {
        const validation = renderValidation();
        if (validation.errors.length) return;
        downloadBlob(new Blob([manifestJson()], { type: 'application/json;charset=utf-8' }), 'mascot.json');
    }

    function downloadPackage() {
        const validation = renderValidation();
        if (validation.errors.length) return;
        const id = project.id;
        const files = [{ name: `${id}/mascot.json`, bytes: textEncoder.encode(manifestJson()) }];
        const seen = new Set();
        for (const frame of allFrames()) {
            if (!frame.bytes || seen.has(frame.name)) continue;
            seen.add(frame.name);
            files.push({ name: `${id}/${frame.name}`, bytes: frame.bytes });
        }
        downloadBlob(buildZip(files), `${id}.zip`);
    }

    function resetProject() {
        disposeProjectFrames();
        project = createDefaultProject();
        syncFormFromProject();
        renderAnimations();
        syncUi();
        setPreviewMode('auto');
    }

    async function copyJson() {
        try {
            await navigator.clipboard.writeText(manifestJson());
            const previous = el.copyJson.textContent;
            el.copyJson.textContent = 'Copied';
            setTimeout(() => { el.copyJson.textContent = previous; }, 1200);
        } catch (error) {
            alert('Could not access the clipboard in this browser.');
        }
    }

    document.querySelectorAll('.add-animation').forEach(button => button.addEventListener('click', () => addAnimation(button.dataset.state)));
    el.form.addEventListener('input', event => {
        if (event.target.closest('.animation-card')) return;
        syncProjectFromForm();
        syncUi();
    });
    el.idleAnimations.addEventListener('input', handleAnimationInput);
    el.runAnimations.addEventListener('input', handleAnimationInput);
    el.idleAnimations.addEventListener('change', handleAnimationChange);
    el.runAnimations.addEventListener('change', handleAnimationChange);
    el.idleAnimations.addEventListener('click', handleAnimationClick);
    el.runAnimations.addEventListener('click', handleAnimationClick);
    for (const root of [el.idleAnimations, el.runAnimations]) {
        root.addEventListener('dragstart', handleDragStart);
        root.addEventListener('dragover', handleDragOver);
        root.addEventListener('dragleave', handleDragLeave);
        root.addEventListener('drop', handleDrop);
        root.addEventListener('dragend', handleDragEnd);
    }

    document.querySelectorAll('.preview-mode').forEach(button => button.addEventListener('click', () => setPreviewMode(button.dataset.mode)));
    el.previewAnimation.addEventListener('change', restartPreview);
    el.restartPreview.addEventListener('click', restartPreview);
    el.copyJson.addEventListener('click', copyJson);
    el.downloadJson.addEventListener('click', downloadManifest);
    el.downloadZip.addEventListener('click', downloadPackage);
    el.resetProject.addEventListener('click', resetProject);

    el.importJson.addEventListener('change', async () => {
        const file = el.importJson.files?.[0];
        if (!file) return;
        try { await importManifestFile(file); }
        catch (error) { alert(`Could not import mascot.json:\n${error.message}`); }
        finally { el.importJson.value = ''; }
    });

    el.importZip.addEventListener('change', async () => {
        const file = el.importZip.files?.[0];
        if (!file) return;
        try { await importZipFile(file); }
        catch (error) { alert(`Could not import mascot ZIP:\n${error.message}`); }
        finally { el.importZip.value = ''; }
    });

    el.importImages.addEventListener('change', async () => {
        const files = [...(el.importImages.files || [])];
        if (files.length) await importImagesGlobally(files);
        el.importImages.value = '';
    });

    syncFormFromProject();
    renderAnimations();
    syncUi();
    restartPreview();
    requestAnimationFrame(previewLoop);
})();
