const StudentCheckIn = (() => {
    let cameraStream = null;

    let videoTrack = null;

    let currentZoom = 1;
    let minZoom = 1;
    let maxZoom = 1;
    let zoomStep = 0.2;
    let pinchStartDistance = null;
    let isPinching = false;

    function isSecureContext() {
        return window.isSecureContext === true;
    }


    async function checkCameraPermission() {
        try {
            if (!navigator.permissions) return "unsupported";
            const result = await navigator.permissions.query({ name: "camera" });
            return result.state; // "granted", "denied", "prompt"
        } catch {
            return "unsupported"; // Firefox doesn't support camera permission query
        }
    }


    async function checkGeoPermission() {
        try {
            if (!navigator.permissions) return "unsupported";
            const result = await navigator.permissions.query({ name: "geolocation" });
            return result.state;
        } catch {
            return "unsupported";
        }
    }


    async function requestCamera(videoElement, facingMode = "user") {
        // Check secure context first
        if (!isSecureContext()) {
            return {
                ok: false,
                error: "Camera requires HTTPS. If accessing over WiFi, use https:// instead of http:// (accept the security warning).",
                errorType: "insecure"
            };
        }
    
        // Check if getUserMedia is available
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            return {
                ok: false,
                error: "Camera not supported on this browser. Please use Chrome, Firefox, or Safari.",
                errorType: "unsupported"
            };
        }

        try {
            // This triggers the browser's permission prompt (like Google Meet)
            // If already granted, it won't prompt again
            const stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode },
                audio: false,
            });

            cameraStream = stream;
            videoElement.srcObject = stream;
            await videoElement.play();

            // Detect zoom capability
try {

    videoTrack = stream.getVideoTracks()[0];

    const capabilities =
        videoTrack.getCapabilities();

    if (capabilities.zoom) {

        minZoom =
            capabilities.zoom.min;

        maxZoom =
            capabilities.zoom.max;

        currentZoom =
            minZoom;

        console.log(
            "Zoom supported:",
            minZoom,
            maxZoom
        );

    }
    else {

        console.log(
            "Zoom not supported"
        );

    }

}
catch (err) {

    console.log(
        "Zoom detection error:",
        err
    );

}

            return { ok: true, stream };

        } catch (err) {
            console.error("Camera error:", err.name, err.message);

            if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
                return {
                    ok: false,
                    error: "Camera permission denied. Please allow camera access in your browser settings and reload.",
                    errorType: "denied"
                };
            }
            if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
                return {
                    ok: false,
                    error: "No camera found on this device.",
                    errorType: "not_found"
                };
            }
            if (err.name === "NotReadableError" || err.name === "TrackStartError") {
                return {
                    ok: false,
                    error: "Camera is in use by another app. Close other apps using the camera and try again.",
                    errorType: "in_use"
                };
            }
            if (err.name === "OverconstrainedError") {
                // Retry without facing mode constraint
                try {
                    const stream = await navigator.mediaDevices.getUserMedia({
                        video: true, audio: false,
                    });
                    cameraStream = stream;
                    videoElement.srcObject = stream;
                    await videoElement.play();
                    return { ok: true, stream };
                } catch {
                    return { ok: false, error: "Camera configuration error.", errorType: "constraint" };
                }
            }

            return {
                ok: false,
                error: `Camera error: ${err.message || "Unknown error"}. Try reloading the page.`,
                errorType: "unknown"
            };
        }
    }

    function captureFrame(videoElement, canvasElement) {
        const ctx = canvasElement.getContext("2d");
        canvasElement.width = videoElement.videoWidth || 640;
        canvasElement.height = videoElement.videoHeight || 480;
        ctx.drawImage(videoElement, 0, 0);
        return canvasElement.toDataURL("image/jpeg", 0.8);
    }

    function stopCamera() {
        if (cameraStream) {
            cameraStream.getTracks().forEach(t => t.stop());
            cameraStream = null;
        }
    }


    async function getLocation(classroomLat, classroomLng, timeoutMs = 10000) {
    if (!isSecureContext()) {
        return { ok: false, error: "Location requires HTTPS.", errorType: "insecure" };
    }

    if (!navigator.geolocation) {
        return { ok: false, error: "Geolocation not supported.", errorType: "unsupported" };
    }

    const permState = await checkGeoPermission();
    if (permState === "denied") {
        return { ok: false, error: "Location permission denied. Update settings and reload.", errorType: "denied" };
    }

    try {
        const position = await new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject, {
                enableHighAccuracy: true,
                timeout: timeoutMs,
                // 🔥 THE FIX: maximumAge: 0 forces the phone to get a NEW coordinate 
                // instead of using a 30s old cached one.
                maximumAge: 0, 
            });
        });

        const now = Date.now();
        const locationAge = now - position.timestamp;

        // 🛑 ANTI-SPOOF 1: Check for "Frozen" locations (stale for > 10 seconds)
        // Common in mock location apps that feed static data.
        if (locationAge > 10000) {
            return { ok: false, error: "Stale location detected. Disable spoofing apps.", errorType: 'spoof' };
        }

        // 🛑 ANTI-SPOOF 2: Check for "Perfect" accuracy 
        // Real GPS indoors is never 0.1m accurate; this catches browser sensor emulators.
        if (position.coords.accuracy <= 0.1) {
            return { ok: false, error: "Invalid location precision. Prohibited software detected.", errorType: 'spoof' };
        }

        const lat = position.coords.latitude;
        const lng = position.coords.longitude;
        const accuracy = position.coords.accuracy;

        // Calculate distance (Haversine math)
        const R = 6371000;
        const dLat = (lat - classroomLat) * Math.PI / 180;
        const dLon = (lng - classroomLng) * Math.PI / 180;
        const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                  Math.cos(classroomLat * Math.PI / 180) * Math.cos(lat * Math.PI / 180) *
                  Math.sin(dLon/2) * Math.sin(dLon/2);
        const distance = R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));

        // Define Trust levels based on your 50m rule
        let trustLevel = 'reject';
        let trustScore = 0;

        if (distance <= 15) { trustLevel = 'strong'; trustScore = 100; }
        else if (distance <= 25) { trustLevel = 'moderate'; trustScore = 70; }
        else if (distance <= 50) { trustLevel = 'weak'; trustScore = 40; }

        return {
            ok: true,
            lat, lng, accuracy,
            distance: Math.round(distance),
            trustScore, trustLevel,
        };

    } catch (err) {
        console.error("Geolocation error:", err.code, err.message);
        let msg = `Location error: ${err.message}`;
        let type = "unknown";

        if (err.code === 1) { msg = "Permission denied."; type = "denied"; }
        else if (err.code === 2) { msg = "Location unavailable. Turn on GPS."; type = "unavailable"; }
        else if (err.code === 3) { msg = "Location timed out. Move to a window."; type = "timeout"; }

        return { ok: false, error: msg, errorType: type };
    }
}
    /**
     * Haversine distance between two lat/lng points in meters.
     */
    function haversineDistance(lat1, lng1, lat2, lng2) {
        const R = 6371000; // Earth radius in meters
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLng = (lng2 - lng1) * Math.PI / 180;
        const a = Math.sin(dLat / 2) ** 2 +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLng / 2) ** 2;
        return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    }

    function calculateTrustScore(distanceMeters, accuracyMeters) {
        let score;
        let level;

        if (distanceMeters <= 15) {
            score = 100;
            level = "strong";
        } else if (distanceMeters <= 25) {
            score = 70;
            level = "moderate";
        } else if (distanceMeters <= 50) {
            score = 40;
            level = "weak";
        } else {
            score = 10;
            level = "reject";
        }

        // Accuracy penalty — don't trust inaccurate GPS
        if (accuracyMeters > 30) {
            const penalty = Math.min((accuracyMeters - 30) * 0.5, 40);
            score = Math.max(score - penalty, 5);

            // If accuracy is terrible (>100m), downgrade level
            if (accuracyMeters > 100) {
                level = "weak";
            }
        }

        return { trustScore: Math.round(score), trustLevel: level };
    }


    async function safeJson(res) {
        const text = await res.text();
        try {
            return JSON.parse(text);
        } catch {
            // Server returned HTML (probably redirect to login)
            if (text.includes("<!DOCTYPE") || text.includes("<html")) {
                return { valid: false, error: "Session expired. Please reload and log in again.", reason: "Session expired. Please reload and log in again." };
            }
            return { valid: false, error: "Unexpected server response.", reason: "Unexpected server response." };
        }
    }

    async function submitPin(sessId, pin, geoData = null, deviceInfo = null) {
        try {
            const body = { pin };
            if (geoData && geoData.ok) {
                body.geo_lat = geoData.lat;
                body.geo_lng = geoData.lng;
                body.geo_accuracy = geoData.accuracy;
                body.geo_distance = geoData.distance;
                body.geo_trust_score = geoData.trustScore;
                body.geo_trust_level = geoData.trustLevel;
            }
            if (deviceInfo) body.device_info = deviceInfo;

            const res = await fetch(`/api/session/${sessId}/validate`, {
                method: "POST",
                credentials: "include", // 🔥 FIX: Required for Ngrok mobile testing
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
            return await safeJson(res);
        } catch (err) {
            console.error("PIN submit error:", err);
            return { valid: false, reason: "Network error. Try again." };
        }
    }

    async function submitQR(sessionId, rawData, geoData, deviceInfo) {
        try {
            // Build the payload safely handling missing or failed geoData
            const payload = {
                qr_data: rawData,
                geo_lat: (geoData && geoData.ok) ? geoData.lat : null,
                geo_lng: (geoData && geoData.ok) ? geoData.lng : null,
                geo_accuracy: (geoData && geoData.ok) ? geoData.accuracy : null,
                geo_distance: (geoData && geoData.ok) ? geoData.distance : null,
                geo_trust_score: (geoData && geoData.ok) ? geoData.trustScore : null,
                geo_trust_level: (geoData && geoData.ok) ? geoData.trustLevel : null,
                // 🔥 Attach the device info for the hardware lock
                device_info: deviceInfo 
            };

            const response = await fetch(`/api/session/${sessionId}/validate`, {
                method: 'POST',
                credentials: 'include', // 🔥 CRITICAL: Required for Ngrok mobile testing & Session cookies!
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            // Parse and return the JSON from the Python backend
            return await response.json();

        } catch (err) {
            console.error("QR submit error:", err);
            return { valid: false, reason: "Network error during validation. Please check your connection." };
        }
    }

    async function uploadSelfie(sessId, base64Data) {
        try {
            const res = await fetch(`/api/session/${sessId}/selfie`, {
                method: "POST",
                credentials: "include", // 🔥 FIX: Required for Ngrok mobile testing
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ selfie_data: base64Data }),
            });
            return await safeJson(res);
        } catch (err) {
            console.error("Selfie upload error:", err);
            return { error: "Failed to upload selfie." };
        }
    }


let scanInterval = null;

    // --- LIVE QR MOTION DETECTION ---
let lastQrTimestamp = null;
let motionDetected = false;
let motionStartTime = null;


    /**
     * Anti-Proxy: Detects if the camera is looking at a digital screen 
     * by analyzing high-frequency noise/Moiré patterns.
     */
    // function isScanningDigitalScreen(videoElement) {
    //     const canvas = document.createElement('canvas');
    //     const ctx = canvas.getContext('2d');
    //     // Low resolution is sufficient for texture analysis
    //     canvas.width = 160; 
    //     canvas.height = 120;
        
    //     ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
    //     const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    //     const data = imageData.data;

    //     let noiseCount = 0;
    
    //     // Sample pixels to find unnatural "shimmer" or "scanlines"
    //     for (let i = 0; i < data.length; i += 12) {
    //         const brightness = (data[i] + data[i+1] + data[i+2]) / 3;
    //         if (brightness > 250 || brightness < 5) noiseCount++;
    //     }

    //     const noiseRatio = noiseCount / (data.length / 12);
    //     // If noise > 10%, it's likely a backlit digital display (another phone)
    //     return noiseRatio > 0.10; 
    // }


    function isScanningDigitalScreen(videoElement) {
    // 🔥 DEV MODE BYPASS: Instantly return false so you can test on your laptop!
    // Remember to remove this line when you deploy to the real classroom.

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    // Low resolution is sufficient for texture analysis
    canvas.width = 160; 
    canvas.height = 120;
    
    ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const data = imageData.data;

    let noiseCount = 0;
    // Sample pixels to find unnatural "shimmer" or "scanlines"
    for (let i = 0; i < data.length; i += 12) {
        const brightness = (data[i] + data[i+1] + data[i+2]) / 3;
        if (brightness > 250 || brightness < 5) noiseCount++;
    }

    const noiseRatio = noiseCount / (data.length / 12);
    // If noise > 10%, it's likely a backlit digital display (another phone)
    return noiseRatio > 0.10; 
}

    async function startQRScanner(videoElement, onDetect) {

    const result =
        await requestCamera(
            videoElement,
            "environment"
        );

    if (!result.ok) {
        return {
            ok: false,
            error: result.error,
            errorType: result.errorType
        };
    }

    // Enable pinch zoom ONLY for QR scanning
    enablePinchZoom(videoElement);

    if ("BarcodeDetector" in window) {

        const detector =
            new BarcodeDetector({
                formats: ["qr_code"]
            });

        scanInterval =
            setInterval(async () => {
                try {
                    const barcodes =
                        await detector.detect(
                            videoElement
                        );

                    if (barcodes.length > 0) {

    // --- ANTI-PHOTO CHECK ---
    if (isScanningDigitalScreen(videoElement)) {

        alert(
            "Security Alert: Scanning from a photo or another screen is blocked."
        );

        return;

    }

    const rawData =
        barcodes[0].rawValue;

    try {

        const qrObj =
            JSON.parse(rawData);

        const currentTs =
            qrObj.ts;

        // First detection
        if (lastQrTimestamp === null) {

            lastQrTimestamp =
                currentTs;

            motionStartTime =
                Date.now();

            console.log(
                "Waiting for QR motion..."
            );

            return;

        }

        // Check timestamp change
        if (currentTs !== lastQrTimestamp) {

            motionDetected = true;

        }

        lastQrTimestamp =
            currentTs;

        // Require motion
        if (!motionDetected) {

            const elapsed =
                Date.now() -
                motionStartTime;

            if (elapsed < 1500) {

                console.log(
                    "QR still static..."
                );

                return;

            }

            alert(
                "QR is not moving. Please scan the live projector."
            );

            return;

        }

        // Motion confirmed
        stopQRScanner();

        onDetect(rawData);

    }
    catch (err) {

        console.log(
            "Invalid QR format"
        );

    }

}
                }
                catch {
                    // frame not ready
                }
            }, 300);

        return { ok: true };

    } else {

        return {
            ok: false,
            error:
                "QR scanning not supported. Use PIN input instead.",
            errorType: "unsupported"
        };

    }

}

function stopQRScanner() {

    if (scanInterval) {

        clearInterval(scanInterval);

        scanInterval = null;

    }

    stopCamera();

}

function getDeviceInfo() {

    return `${navigator.userAgent.slice(0, 100)}|${screen.width}x${screen.height}|${navigator.language}`;

}


async function setZoom(level) {

    if (!videoTrack)
        return;

    try {

        await videoTrack.applyConstraints({
            advanced: [
                { zoom: level }
            ]
        });

        currentZoom =
            level;

    }
    catch (error) {

        console.error(
            "Zoom error:",
            error
        );

    }

}

function zoomIn() {

    let newZoom =
        currentZoom + zoomStep;

    if (newZoom > maxZoom)
        newZoom = maxZoom;

    setZoom(newZoom);

}

function zoomOut() {

    let newZoom =
        currentZoom - zoomStep;

    if (newZoom < minZoom)
        newZoom = minZoom;

    setZoom(newZoom);

}

function enablePinchZoom(videoElement) {

    videoElement.addEventListener("touchstart", (e) => {

        if (e.touches.length === 2) {

            isPinching = true;

            pinchStartDistance =
                getTouchDistance(e.touches);

        }

    });

    videoElement.addEventListener("touchmove", (e) => {

    if (!isPinching)
        return;

    if (e.touches.length !== 2)
        return;

    // IMPORTANT — stop browser page zoom
    e.preventDefault();

    const newDistance =
        getTouchDistance(e.touches);

    const delta =
        newDistance - pinchStartDistance;

    if (Math.abs(delta) > 5) {

        if (delta > 0) {

            zoomIn();

        } else {

            zoomOut();

        }

        pinchStartDistance =
            newDistance;

    }

}, { passive: false });

    videoElement.addEventListener("touchend", () => {

        isPinching = false;

    });

}

function getTouchDistance(touches) {

    const dx =
        touches[0].clientX -
        touches[1].clientX;

    const dy =
        touches[0].clientY -
        touches[1].clientY;

    return Math.sqrt(
        dx * dx +
        dy * dy
    );

}


// 🔥 NEW: Generate or retrieve a permanent Device ID for this specific phone/browser
    function getDeviceId() {
        let deviceId = localStorage.getItem('attendx_device_id');
        if (!deviceId) {
            // Create a unique random string (e.g., device_x8jf9_171239102)
            deviceId = 'device_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
            localStorage.setItem('attendx_device_id', deviceId);
        }
        return deviceId;
    }

    // 🔥 NEW: Combine the ID with the browser info to send to the Python backend
    function getDeviceInfo() {
        const uniqueId = getDeviceId();
        const userAgent = navigator.userAgent;
        // We combine them so the backend has the unique lock ID, but you can still audit the device type
        return `${uniqueId}|${userAgent}`; 
    }


    return {
        isSecureContext,
        checkCameraPermission,
        checkGeoPermission,
        requestCamera,
        captureFrame,
        stopCamera,
        getLocation,
        calculateTrustScore,
        submitPin,
        submitQR,
        uploadSelfie,
        startQRScanner,
        stopQRScanner,
        getDeviceInfo,
        zoomIn,
        zoomOut,
        getDeviceInfo,
    };
})();
