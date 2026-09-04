(() => {
    const activeKey = 'tutor-lamp-study-active';
    const trackerVideoId = 'focusTrackerVideo';
    const trackerCanvasId = 'focusTrackerCanvas';
    let video;
    let faceMesh;
    let objectModel;
    let stream;
    let running = false;
    let processing = false;
    let lastLogTime = 0;
    let lastObjectCheck = 0;
    let phoneDetected = false;
    let navigationStarted = false;

    function isActive() {
        return localStorage.getItem(activeKey) === 'true';
    }

    function getOrCreateElement(tag, id) {
        let element = document.getElementById(id);
        if (!element) {
            element = document.createElement(tag);
            element.id = id;
            element.className = 'hidden';
            document.body.appendChild(element);
        }
        return element;
    }

    function distance(first, second) {
        return Math.hypot(first.x - second.x, first.y - second.y);
    }

    function eyeAspectRatio(landmarks, points) {
        const [outer, upperA, lowerA, inner, upperB, lowerB] = points.map(index => landmarks[index]);
        return (distance(upperA, lowerA) + distance(upperB, lowerB)) / (2 * distance(outer, inner));
    }

    function updateStatus(text, focused) {
        const badge = document.getElementById('statusBadge');
        const angle = document.getElementById('poseAngleText');
        if (badge) {
            badge.innerText = text;
            badge.className = focused
                ? 'px-4 py-2 rounded-xl text-sm font-semibold glass text-green-400 border border-green-500/30 bg-green-950/20'
                : 'px-4 py-2 rounded-xl text-sm font-semibold glass text-red-400 border border-red-500/40 bg-red-950/20';
        }
        const trackerStatus = document.getElementById('trackerStatus');
        if (trackerStatus) trackerStatus.innerText = text;
        if (angle && !focused && text.includes('No Face')) angle.innerText = 'Yaw: N/A | Pitch: N/A';
    }

    function updateButton() {
        const button = document.getElementById('studySessionBtn');
        if (!button) return;
        const active = isActive();
        button.innerText = active ? 'Stop Study Session' : 'Start Study Session';
        button.className = active
            ? 'px-4 py-2 bg-red-600 hover:bg-red-500 text-white font-bold rounded-xl text-sm transition'
            : 'px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-bold rounded-xl text-sm transition';
        button.setAttribute('aria-pressed', String(active));
    }

    function updateTrackingMessage(active) {
        const message = document.getElementById('focusTrackingMessage');
        const description = document.getElementById('focusTrackingDescription');
        if (message) message.innerText = active ? 'Focus tracking is active' : 'Focus tracking is inactive';
        if (description) description.innerText = active
            ? 'Your camera is analyzed privately to detect focus. The camera view is never shown here.'
            : 'Start a study session to privately analyze your focus. The camera view is never shown here.';
    }

    function setInactiveStatus() {
        const badge = document.getElementById('statusBadge');
        if (badge) {
            badge.innerText = 'Study session inactive';
            badge.className = 'px-4 py-2 rounded-xl text-sm font-semibold glass text-gray-400 border border-gray-500/30 bg-gray-950/20';
        }
        const trackerStatus = document.getElementById('trackerStatus');
        if (trackerStatus) trackerStatus.innerText = 'Study session inactive';
        const angle = document.getElementById('poseAngleText');
        if (angle) angle.innerText = 'Yaw: N/A | Pitch: N/A';
    }

    async function resetServerSession(url) {
        try {
            await fetch(url, { method: 'POST', keepalive: true });
        } catch (error) {
            console.warn('Study session update failed.', error);
        }
    }

    async function startSession() {
        await resetServerSession('/study_session/start');
        localStorage.setItem(activeKey, 'true');
        updateButton();
        updateTrackingMessage(true);
        window.dispatchEvent(new CustomEvent('tutorLampStudySessionChange', { detail: { active: true } }));
        startTracker();
    }

    async function stopSession() {
        localStorage.removeItem(activeKey);
        stopTracker();
        updateButton();
        updateTrackingMessage(false);
        setInactiveStatus();
        await resetServerSession('/study_session/stop');
        window.dispatchEvent(new CustomEvent('tutorLampStudySessionChange', { detail: { active: false } }));
    }

    function stopTracker() {
        running = false;
        processing = false;
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            stream = null;
        }
        if (video) video.srcObject = null;
    }

    async function checkForPhone() {
        if (!objectModel || !video || video.readyState < 2) return;
        const now = Date.now();
        if (now - lastObjectCheck < 1200) return;
        lastObjectCheck = now;
        try {
            const predictions = await objectModel.detect(video);
            phoneDetected = predictions.some(item => item.class === 'cell phone' && item.score >= 0.45);
        } catch (error) {
            phoneDetected = false;
        }
    }

    async function processFrame() {
        if (!running || !faceMesh || !video || processing || video.readyState < 2) return;
        processing = true;
        try {
            await checkForPhone();
            await faceMesh.send({ image: video });
        } finally {
            processing = false;
        }
    }

    function onResults(results) {
        if (!running) return;
        let status = 'Distracted (No Face Detected)';
        let focused = false;
        const angle = document.getElementById('poseAngleText');
        const faces = results && results.multiFaceLandmarks;

        if (faces && faces.length) {
            const landmarks = faces[0];
            const leftCheek = landmarks[234];
            const rightCheek = landmarks[454];
            const chin = landmarks[152];
            const forehead = landmarks[10];
            const faceCenterX = (leftCheek.x + rightCheek.x) / 2;
            const faceCenterY = (forehead.y + chin.y) / 2;
            const faceWidth = Math.abs(rightCheek.x - leftCheek.x);
            const faceHeight = Math.abs(chin.y - forehead.y);
            const yaw = Math.round((faceCenterX - 0.5) * 180);
            const pitch = Math.round((faceCenterY - 0.5) * 180);
            if (angle) angle.innerText = `Yaw: ${yaw}° | Pitch: ${pitch}°`;

            const centered = faceCenterX > 0.18 && faceCenterX < 0.82 && faceCenterY > 0.2 && faceCenterY < 0.8;
            const largeEnough = faceWidth > 0.18 && faceHeight > 0.22;
            const leftEyeClosed = eyeAspectRatio(landmarks, [33, 160, 144, 133, 158, 153]) < 0.19;
            const rightEyeClosed = eyeAspectRatio(landmarks, [362, 385, 380, 263, 386, 374]) < 0.19;

            if (phoneDetected) status = 'Distracted (Phone Detected)';
            else if (leftEyeClosed && rightEyeClosed) status = 'Distracted (Eyes Closed)';
            else if (!centered || !largeEnough) status = 'Distracted (Not Facing Monitor)';
            else {
                status = 'Focused (Facing Monitor)';
                focused = true;
            }
        }

        updateStatus(status, focused);
        const now = Date.now();
        if (now - lastLogTime > 3000) {
            lastLogTime = now;
            fetch('/log_event', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status, active: true })
            }).catch(() => {});
        }
    }

    async function startTracker() {
        if (running || !isActive()) return;
        if (!window.FaceMesh || !window.Camera) {
            localStorage.removeItem(activeKey);
            updateButton();
            updateTrackingMessage(false);
            updateStatus('Focus tracking unavailable', false);
            return;
        }
        try {
            video = getOrCreateElement('video', trackerVideoId);
            getOrCreateElement('canvas', trackerCanvasId);
            stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false });
            video.srcObject = stream;
            await video.play();
            faceMesh = new FaceMesh({ locateFile: file => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}` });
            faceMesh.setOptions({ maxNumFaces: 1, refineLandmarks: true, minDetectionConfidence: 0.5, minTrackingConfidence: 0.5 });
            faceMesh.onResults(onResults);
            if (window.cocoSsd) objectModel = await cocoSsd.load();
            running = true;
            updateStatus('Focus tracking starting...', false);
            const camera = new Camera(video, { onFrame: processFrame, width: 640, height: 480 });
            camera.start();
        } catch (error) {
            stopTracker();
            localStorage.removeItem(activeKey);
            updateButton();
            updateTrackingMessage(false);
            updateStatus('Camera permission required', false);
        }
    }

    function handlePageNavigation(event) {
        if (event.target.closest && event.target.closest('a[href]')) navigationStarted = true;
    }

    document.addEventListener('click', handlePageNavigation, true);
    window.addEventListener('storage', event => {
        if (event.key !== activeKey) return;
        updateButton();
        if (event.newValue === 'true') startTracker();
        else {
            stopTracker();
            updateTrackingMessage(false);
            setInactiveStatus();
        }
    });
    window.addEventListener('beforeunload', event => {
        if (isActive() && !navigationStarted) {
            navigator.sendBeacon('/study_session/stop', new Blob([], { type: 'application/json' }));
            localStorage.removeItem(activeKey);
        }
    });

    document.addEventListener('DOMContentLoaded', () => {
        const button = document.getElementById('studySessionBtn');
        if (button) button.addEventListener('click', () => isActive() ? stopSession() : startSession());
        updateButton();
        const active = isActive();
        updateTrackingMessage(active);
        if (active) startTracker();
        else setInactiveStatus();
    });

    window.tutorLampStudySession = { start: startSession, stop: stopSession, isActive };
})();
