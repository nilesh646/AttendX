/**
 * Dual-Key Projector Engine (WebSocket Edition) - Refactored for Anti-Proxy
 */

const DualKeyEngine = (() => {
    let sessionId = null;
    let socket = null; // WebSocket connection
    let countdownInterval = null;
    let secondsLeft = 5;
    let currentPhase = 'entry';
    let isRunning = false;

    // ── DOM references ──
    let elPin = null;
    let elQrImg = null;
    let elTimer = null;
    let elTimerBar = null;
    let elPhaseLabel = null;
    let elStatusDot = null;

    // 🔥 CRITICAL: Match the high-speed backend rotation for anti-photo logic
    const REFRESH_SECONDS = 6; 

    // ═══════════════════════════════════════════════════
    //  INIT
    // ═══════════════════════════════════════════════════
    function init(elements) {
    elQrImg      = elements.qrImg;
    elTimer      = elements.timer;
    elTimerBar   = elements.timerBar;
    elPhaseLabel = elements.phaseLabel;
    elStatusDot  = elements.statusDot;
}

    function _connectWebSocket(sid) {
    if (socket) socket.disconnect();
    
    socket = io();

    socket.on('connect', () => {
        console.log("Connected to Server. Joining Room...");
        socket.emit('join_session', { session_id: sid });
    });

    socket.on('token_update', (tokenData) => {
        console.log("Token Received!");
        _updateDisplay(tokenData);
        _resetCountdown(); // This forces the timer back to 15
    });

    socket.on('connect_error', (err) => {
        console.error("Connection failed. Check Ngrok:", err);
    });
}

    // ═══════════════════════════════════════════════════
    //  START SESSION
    // ═══════════════════════════════════════════════════
    async function startSession(timetableId, lat = null, lng = null) {
        try {
            // 1. Build the dynamic payload
            const payload = { timetable_id: timetableId };
            
            // 2. Attach teacher coordinates if they were successfully grabbed
            if (lat !== null && lng !== null) {
                payload.teacher_lat = lat;
                payload.teacher_lng = lng;
            }

            const res = await fetch('/api/session/start', {
               method: 'POST',
               credentials: 'include',
               headers: { 'Content-Type': 'application/json' },
               body: JSON.stringify(payload), // Send the dynamic payload here
            });
            const data = await res.json();

            if (!res.ok) {
                return { error: data.error || 'Failed to start session.' };
            }

            sessionId = data.session_id;
            currentPhase = data.phase || 'entry';
            isRunning = true;

            // Display initial tokens immediately
            _updateDisplay(data);
            _startCountdown();

            _connectWebSocket(sessionId); 

            return data;
        } catch (err) {
            console.error('Start session error:', err);
            return { error: 'Network error.' };
        }
    }

    // ═══════════════════════════════════════════════════
    //  RESUME SESSION (WebSocket Reconnect)
    // ═══════════════════════════════════════════════════
    function resumeSession(existingSessionId) {
        sessionId = existingSessionId;
        _connectWebSocket(sessionId);
        isRunning = true;
        
        _startCountdown();
    }



    

    // ═══════════════════════════════════════════════════
    //  END SESSION
    // ═══════════════════════════════════════════════════
    async function endSession() {
        if (!sessionId) return;

        if (socket) {
            socket.disconnect();
            socket = null;
        }

        _stopCountdown();
        isRunning = false;

        try {
            // 🔥 FIX: Move sessionId into the URL path to match Python @api_bp.route
            const res = await fetch(`/api/session/${sessionId}/end`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' }
                // We don't need the body anymore because the ID is in the URL!
            });
            
            const data = await res.json();
            sessionId = null;
            return data;
        } catch (err) {
            console.error('End session error:', err);
            return { error: 'Network error.' };
        }
    }

    async function switchPhase(newPhase) {
        if (!sessionId) return;

        try {
            // 🔥 FIX: Move sessionId into the URL path for consistency
            const res = await fetch(`/api/session/${sessionId}/switch-phase`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ phase: newPhase }),
            });
            
            const data = await res.json();

            if (res.ok) {
                currentPhase = newPhase;
                if (elPhaseLabel) {
                    elPhaseLabel.textContent = currentPhase === 'entry' ? 'ENTRY' : 'EXIT';
                    elPhaseLabel.className = 'phase-label phase-' + currentPhase;
                }
            }

            return data;
        } catch (err) {
            console.error('Switch phase error:', err);
            return { error: 'Network error.' };
        }
    }
    // ═══════════════════════════════════════════════════
    //  COUNTDOWN TIMER VISUALS
    // ═══════════════════════════════════════════════════
    function _startCountdown() {

    _stopCountdown();

    // 🔥 Align countdown to the current 15-second window
    const now = Date.now() / 1000;
    secondsLeft = Math.ceil(
        REFRESH_SECONDS - (now % REFRESH_SECONDS)
    );

    if (elTimer) elTimer.textContent = secondsLeft;

    countdownInterval = setInterval(() => {

        secondsLeft--;

        if (secondsLeft <= 0) {
            secondsLeft = REFRESH_SECONDS;
        }

        if (elTimer) {
            elTimer.textContent = secondsLeft;
        }

        if (elTimerBar) {

            const pct =
                (secondsLeft / REFRESH_SECONDS) * 100;

            elTimerBar.style.width = pct + "%";

            if (secondsLeft > 7) {
                elTimerBar.style.background =
                    "var(--accent)";
            }
            else if (secondsLeft > 3) {
                elTimerBar.style.background =
                    "var(--warning)";
            }
            else {
                elTimerBar.style.background =
                    "var(--danger)";
            }
        }

        if (elStatusDot && secondsLeft <= 3) {
            elStatusDot.classList.add(
                "pulse-danger"
            );
        }

    }, 1000);
}

    function _resetCountdown() {
        secondsLeft = REFRESH_SECONDS;
        if (elStatusDot) elStatusDot.classList.remove('pulse-danger');
    }

    function _stopCountdown() {
        if (countdownInterval) {
            clearInterval(countdownInterval);
            countdownInterval = null;
        }
    }

    // ═══════════════════════════════════════════════════
    //  DISPLAY UPDATE
    // ═══════════════════════════════════════════════════
    function _updateDisplay(data) {
        if (elPin && data.pin) {
            elPin.style.opacity = '0';
            elPin.style.transform = 'scale(0.8)';
            setTimeout(() => {
                elPin.textContent = data.pin;
                elPin.style.opacity = '1';
                elPin.style.transform = 'scale(1)';
            }, 150);
        }

        if (elQrImg && data.qr_image) {
    if (elQrImg.src !== data.qr_image) {

        const img = new Image();

        img.onload = () => {
            elQrImg.src = data.qr_image;
            elQrImg.style.display = 'block';
        };

        img.src = data.qr_image;
    }
}

        if (elPhaseLabel && data.phase) {
            currentPhase = data.phase;
            elPhaseLabel.textContent = currentPhase === 'entry' ? 'ENTRY' : 'EXIT';
            elPhaseLabel.className = 'phase-label phase-' + currentPhase;
        }
    }

    return {
        init,
        startSession,
        resumeSession,
        endSession,
        switchPhase,
        getSessionId: () => sessionId,
        getPhase: () => currentPhase,
        isActive: () => isRunning,
    };
})();

// ═══════════════════════════════════════════════════════════════
//  ROSTER POLLER
// ═══════════════════════════════════════════════════════════════
const RosterPoller = (() => {
    let interval = null;
    let callback = null;

    function start(sessionId, onUpdate, pollMs = 5000) {
        stop();
        callback = onUpdate;
        _fetch(sessionId);
        interval = setInterval(() => _fetch(sessionId), pollMs);
    }

    function stop() {
        if (interval) {
            clearInterval(interval);
            interval = null;
        }
    }

    async function _fetch(sessionId) {
        try {
            const res = await fetch(`/api/session/${sessionId}/roster`, { credentials: 'include' });
            if (res.ok) {
                const data = await res.json();
                if (callback) callback(data);
            }
        } catch (err) {
            console.error('Roster poll error:', err);
        }
    }

    return { start, stop };
})();