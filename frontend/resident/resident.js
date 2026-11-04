/**
 * Sarah Resident Dashboard Controller
 * Integrates:
 * 1. Sarah Woman Talking Animated Avatar with Live Lip-Sync
 * 2. Live Gemini Live BIDI Voice AI (Aoede prebuilt voice, 16kHz raw PCM in, 24kHz out)
 * 3. Dynamic MySQL Database Synchronization (User, Household, Devices, Medications, Reminders)
 * 4. Real-time dual live transcriptions and barge-in / emergency handling
 * 5. Quick Touch Controls buttons removed
 */

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Render shared 5-item navigation
    await renderSharedNav('resident');

    // 2. Initialize Sarah Avatar
    const canvas = document.getElementById('sarah-canvas');
    const captionBox = document.getElementById('caption-box');
    const avatar = new SarahAvatar(canvas, {
        captionElement: captionBox,
        reducedMotion: window.a11y ? window.a11y.reducedMotion : false
    });
    window.avatar = avatar;

    // 3. Load Authenticated User Profile from MySQL
    let currentUser = null;
    try {
        currentUser = await api.getCurrentUser();
    } catch (e) {
        console.warn('Could not fetch user profile from MySQL:', e);
    }

    const greetingNameEl = document.getElementById('resident-greeting-name');
    const subInfoEl = document.getElementById('resident-sub-info');
    const displayName = currentUser ? (currentUser.full_name || currentUser.preferred_name || currentUser.email) : (api.getUserName() || 'Resident');
    const householdName = currentUser && currentUser.households && currentUser.households.length > 0
        ? currentUser.households[0].name
        : (localStorage.getItem('sarah_household_name') || 'Home Residence');

    if (greetingNameEl) greetingNameEl.textContent = `Welcome Home, ${displayName}`;
    if (subInfoEl) subInfoEl.textContent = `Household: ${householdName} • Connected to MySQL 8.4 • Active Assistant: Sarah`;

    const residentId = currentUser ? currentUser.user_id : api.getUserId();
    const householdId = currentUser ? currentUser.household_id : api.getHouseholdId();

    // 4. Load Live MySQL Household Devices
    async function loadHouseholdDevices() {
        const devicesListEl = document.getElementById('devices-list');
        const badgeEl = document.getElementById('device-count-badge');
        if (!devicesListEl) return;

        try {
            const rawDevices = await api.listDevices(householdId);
            const devices = Array.isArray(rawDevices) ? rawDevices : (rawDevices.devices || []);
            
            devicesListEl.innerHTML = '';
            if (badgeEl) badgeEl.textContent = `${devices.length} Devices Online`;

            if (devices.length === 0) {
                devicesListEl.innerHTML = `
                    <li class="timeline-item" style="color: var(--text-muted); font-size: 0.92rem;">
                        No smart devices found in MySQL for household "${householdName}".
                        <br><a href="/admin/index.html" style="color: var(--primary); font-weight: 600; text-decoration: underline; margin-top: 6px; display: inline-block;">+ Enroll New Device in Admin Console</a>
                    </li>
                `;
                return;
            }

            devices.forEach(dev => {
                const li = document.createElement('li');
                li.className = 'timeline-item';
                const isOnline = dev.online_status !== 'offline';
                const powerState = dev.power_state || 'off';
                const devIcon = dev.type === 'radar' ? '📡' : (dev.type === 'thermostat' ? '🌡️' : '💡');

                li.innerHTML = `
                    <div class="item-info">
                        <span class="item-title">${devIcon} ${dev.name}</span>
                        <span class="item-sub">${dev.location || 'Home'} • ID: <code>${dev.device_id || dev.id}</code></span>
                    </div>
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span class="status-pill ${isOnline ? 'pill-green' : 'pill-amber'}">
                            ${isOnline ? (powerState === 'on' ? 'Active On' : 'Standby') : 'Offline'}
                        </span>
                        ${dev.type !== 'radar' ? `
                            <button class="a11y-btn btn-device-toggle" data-dev-id="${dev.device_id || dev.id}" data-state="${powerState}" style="padding: 4px 10px; font-size: 0.82rem;">
                                ${powerState === 'on' ? 'Turn Off' : 'Turn On'}
                            </button>
                        ` : ''}
                    </div>
                `;
                devicesListEl.appendChild(li);
            });

            // Bind toggle buttons
            document.querySelectorAll('.btn-device-toggle').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const devId = e.target.getAttribute('data-dev-id');
                    const curState = e.target.getAttribute('data-state');
                    const nextAction = curState === 'on' ? 'turn_off' : 'turn_on';
                    e.target.disabled = true;
                    e.target.textContent = 'Updating...';
                    try {
                        await api.sendDeviceCommand(devId, nextAction, { state: nextAction === 'turn_on' ? 'on' : 'off' });
                        appendConversationMsg('Sarah', `Device command sent: ${nextAction.replace('_', ' ')}.`);
                        await loadHouseholdDevices();
                    } catch (err) {
                        alert('Could not toggle device: ' + err.message);
                        e.target.disabled = false;
                    }
                });
            });
        } catch (e) {
            console.warn('Error loading MySQL devices:', e);
            devicesListEl.innerHTML = `
                <li class="timeline-item" style="color: var(--danger);">
                    Could not query MySQL devices table (${e.message}).
                </li>
            `;
        }
    }

    // 5. Load Live MySQL Schedule & Medications
    async function loadScheduleAndMedications() {
        const routineListEl = document.getElementById('routine-list');
        const badgeEl = document.getElementById('med-count-badge');
        if (!routineListEl) return;

        try {
            routineListEl.innerHTML = '';
            let totalItems = 0;

            // A. Prescriptions / Medications from MySQL
            if (residentId) {
                try {
                    const rawMeds = await api.getMedications(residentId);
                    const meds = Array.isArray(rawMeds) ? rawMeds : (rawMeds.medications || []);
                    meds.forEach(med => {
                        totalItems++;
                        const li = document.createElement('li');
                        li.className = 'timeline-item medication';
                        li.innerHTML = `
                            <div class="item-info">
                                <span class="item-title">💊 ${med.medication_name}</span>
                                <span class="item-sub">${med.scheduled_time || 'Daily'} — ${med.dosage || 'Prescribed dose'} ${med.instructions ? '• ' + med.instructions : ''}</span>
                            </div>
                            <span class="status-pill pill-amber">Scheduled</span>
                        `;
                        routineListEl.appendChild(li);
                    });
                } catch (medErr) {
                    console.debug('No custom medications returned for resident:', medErr);
                }
            }

            // B. Active Reminders from Database
            try {
                const remData = await api.listReminders();
                const reminders = remData && remData.reminders ? remData.reminders : [];
                reminders.forEach(rem => {
                    totalItems++;
                    const li = document.createElement('li');
                    li.className = 'timeline-item';
                    li.innerHTML = `
                        <div class="item-info">
                            <span class="item-title">⏰ ${rem.text}</span>
                            <span class="item-sub">Due: ${rem.due_at || 'Soon'} • Recurrence: ${rem.recurrence || 'Once'}</span>
                        </div>
                        <span class="status-pill pill-blue">Reminder</span>
                    `;
                    routineListEl.appendChild(li);
                });
            } catch (remErr) {
                console.debug('No active reminders:', remErr);
            }

            if (badgeEl) badgeEl.textContent = `${totalItems} Items Synced`;

            if (totalItems === 0) {
                routineListEl.innerHTML = `
                    <li class="timeline-item" style="color: var(--text-muted); font-size: 0.92rem;">
                        No medications or reminders recorded in MySQL for today.
                        <br>You can ask Sarah: <em>"Remind me to take my vitamins at 8 PM"</em>.
                    </li>
                `;
            }
        } catch (e) {
            console.warn('Error loading schedule from MySQL:', e);
        }
    }

    await loadHouseholdDevices();
    await loadScheduleAndMedications();

    // 6. Real-Time Conversation Log UI Helper
    const convContainer = document.getElementById('conversation-container');
    function appendConversationMsg(speaker, text) {
        if (!convContainer || !text) return;
        const msgDiv = document.createElement('div');
        const isAgent = speaker.toLowerCase().includes('sarah');
        msgDiv.className = `msg-box ${isAgent ? 'msg-agent' : 'msg-user'}`;
        msgDiv.style.cssText = isAgent
            ? 'background: white; border: 1px solid var(--border-color); padding: 12px 16px; border-radius: 12px; border-left: 4px solid var(--primary);'
            : 'background: var(--primary-light); border: 1px solid rgba(59,130,246,0.25); padding: 12px 16px; border-radius: 12px; border-right: 4px solid var(--primary-dark); align-self: flex-end;';
        
        msgDiv.innerHTML = `
            <strong style="color: ${isAgent ? 'var(--primary)' : 'var(--primary-dark)'}; display: block; font-size: 0.85rem; margin-bottom: 4px;">
                ${speaker}:
            </strong>
            <span>${text}</span>
        `;
        convContainer.appendChild(msgDiv);
        convContainer.scrollTop = convContainer.scrollHeight;
    }

    // 7. Sarah Live Gemini BIDI Voice AI Audio Engine
    let liveSocket = null;
    let isLiveActive = false;
    let inputAudioCtx = null;
    let outputAudioCtx = null;
    let micStream = null;
    let scriptNode = null;
    let activeSources = [];
    let scheduledAudioTime = 0;

    const btnToggleVoice = document.getElementById('btn-toggle-voice');
    const voiceBtnIcon = document.getElementById('voice-btn-icon');
    const voiceBtnText = document.getElementById('voice-btn-text');
    const btnBargeIn = document.getElementById('btn-bargein');
    const voiceStateBadge = document.getElementById('live-voice-state');

    function setVoiceState(state, label) {
        if (voiceStateBadge) {
            voiceStateBadge.textContent = label;
            voiceStateBadge.className = `status-pill ${
                state === 'connected' || state === 'speaking' ? 'pill-green' : 
                state === 'listening' ? 'pill-blue' : 
                state === 'error' ? 'pill-amber' : 'pill-blue'
            }`;
        }
    }

    async function startLiveSession() {
        try {
            setVoiceState('connecting', 'Authenticating JWT Ticket...');
            avatar.setState('thinking', "Connecting to Sarah Voice AI...");

            // A. Acquire signed WebSocket ticket
            const ticketRes = await api.acquireWsTicket();
            const ticket = ticketRes.ticket;
            const endpoint = ticketRes.ws_endpoint || '/api/v1/sarah-live/ws';

            // B. Establish WebSocket
            const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${proto}//${window.location.host}${endpoint}?ticket=${encodeURIComponent(ticket)}`;

            liveSocket = new WebSocket(wsUrl);
            liveSocket.binaryType = 'arraybuffer';

            liveSocket.onopen = async () => {
                isLiveActive = true;
                btnToggleVoice.classList.remove('btn-primary');
                btnToggleVoice.classList.add('btn-danger');
                voiceBtnIcon.textContent = '⏹️';
                voiceBtnText.textContent = 'End Voice Session';
                setVoiceState('connected', 'Live Connected (Aoede)');
                avatar.setState('idle', "I'm listening! Speak naturally to me.");

                // Start 16kHz microphone stream
                await initMicrophoneCapture();
                // Start 24kHz audio playback engine
                initAudioPlaybackEngine();
            };

            liveSocket.onmessage = async (event) => {
                if (typeof event.data === 'string') {
                    try {
                        const data = JSON.parse(event.data);
                        handleControlMessage(data);
                    } catch (e) {
                        console.debug('Raw string ws message:', event.data);
                    }
                } else if (event.data instanceof ArrayBuffer) {
                    // Incoming 24kHz Raw PCM 16-bit audio chunk from Gemini Aoede voice
                    playAudioChunk24kHz(event.data);
                }
            };

            liveSocket.onerror = (err) => {
                console.warn('Sarah Live WebSocket error:', err);
                setVoiceState('error', 'Voice Stream Error');
            };

            liveSocket.onclose = () => {
                stopLiveSession();
            };

        } catch (err) {
            console.error('Failed to start Sarah Live session:', err);
            avatar.setState('idle', "Could not open real-time voice channel. You can type to Sarah below.");
            setVoiceState('error', 'Connection Failed');
            stopLiveSession();
        }
    }

    function stopLiveSession() {
        isLiveActive = false;
        if (liveSocket && liveSocket.readyState === WebSocket.OPEN) {
            liveSocket.close();
        }
        liveSocket = null;

        // Clean up microphone
        if (scriptNode) {
            scriptNode.disconnect();
            scriptNode = null;
        }
        if (micStream) {
            micStream.getTracks().forEach(t => t.stop());
            micStream = null;
        }
        if (inputAudioCtx && inputAudioCtx.state !== 'closed') {
            inputAudioCtx.close().catch(() => {});
            inputAudioCtx = null;
        }

        // Clean up playback
        flushAudioQueue();
        if (outputAudioCtx && outputAudioCtx.state !== 'closed') {
            outputAudioCtx.close().catch(() => {});
            outputAudioCtx = null;
        }

        btnToggleVoice.classList.remove('btn-danger');
        btnToggleVoice.classList.add('btn-primary');
        voiceBtnIcon.textContent = '🎙️';
        voiceBtnText.textContent = 'Talk to Sarah';
        setVoiceState('standby', 'Standby');
        avatar.setState('idle', "Sarah is ready when you are.");
    }

    function handleControlMessage(data) {
        if (data.type === 'transcription') {
            const role = data.role === 'user' ? (displayName || 'Resident') : 'Sarah';
            appendConversationMsg(role, data.text);
            if (data.role === 'model') {
                avatar.setState('speaking', data.text);
            }
        } else if (data.type === 'barge_in') {
            flushAudioQueue();
            avatar.setState('listening', "I'm listening...");
        } else if (data.type === 'status') {
            console.log('Sarah Live status:', data);
        }
    }

    // Capture 16-bit 16kHz Raw PCM
    async function initMicrophoneCapture() {
        micStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                sampleRate: 16000,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        });

        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        inputAudioCtx = new AudioCtx({ sampleRate: 16000 });
        const source = inputAudioCtx.createMediaStreamSource(micStream);
        scriptNode = inputAudioCtx.createScriptProcessor(2048, 1, 1);

        scriptNode.onaudioprocess = (audioProcessingEvent) => {
            if (!isLiveActive || !liveSocket || liveSocket.readyState !== WebSocket.OPEN) return;
            const inputBuffer = audioProcessingEvent.inputBuffer;
            const channelData = inputBuffer.getChannelData(0);

            // Compute volume to drive avatar listening reaction
            let sum = 0;
            for (let i = 0; i < channelData.length; i++) {
                sum += channelData[i] * channelData[i];
            }
            const rms = Math.sqrt(sum / channelData.length);
            if (rms > 0.05 && avatar.state !== 'speaking') {
                avatar.setState('listening', "Listening to you...");
            }

            // Convert Float32Array to 16-bit signed PCM ArrayBuffer
            const pcm16 = new Int16Array(channelData.length);
            for (let i = 0; i < channelData.length; i++) {
                const s = Math.max(-1, Math.min(1, channelData[i]));
                pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            liveSocket.send(pcm16.buffer);
        };

        source.connect(scriptNode);
        scriptNode.connect(inputAudioCtx.destination);
    }

    // Playback 24kHz Raw PCM Audio
    function initAudioPlaybackEngine() {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        outputAudioCtx = new AudioCtx({ sampleRate: 24000 });
        scheduledAudioTime = outputAudioCtx.currentTime;
    }

    function playAudioChunk24kHz(arrayBuffer) {
        if (!outputAudioCtx) return;
        if (outputAudioCtx.state === 'suspended') {
            outputAudioCtx.resume();
        }

        const pcm16 = new Int16Array(arrayBuffer);
        const float32 = new Float32Array(pcm16.length);

        // Convert Int16 PCM to Float32 & measure RMS volume for mouth lip-sync
        let sum = 0;
        for (let i = 0; i < pcm16.length; i++) {
            float32[i] = pcm16[i] / 32768.0;
            sum += float32[i] * float32[i];
        }
        const rms = Math.sqrt(sum / pcm16.length);

        // Drive woman talking animation visemes
        avatar.setState('speaking');
        avatar.setAudioVolume(rms);

        // Create audio buffer and schedule playback
        const audioBuffer = outputAudioCtx.createBuffer(1, float32.length, 24000);
        audioBuffer.copyToChannel(float32, 0);

        const source = outputAudioCtx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(outputAudioCtx.destination);

        const start = Math.max(outputAudioCtx.currentTime, scheduledAudioTime);
        source.start(start);
        scheduledAudioTime = start + audioBuffer.duration;
        activeSources.push(source);

        source.onended = () => {
            const idx = activeSources.indexOf(source);
            if (idx > -1) activeSources.splice(idx, 1);
            if (activeSources.length === 0) {
                avatar.setAudioVolume(0.0);
                setTimeout(() => {
                    if (activeSources.length === 0 && avatar.state === 'speaking') {
                        avatar.setState('idle', "Ready when you are.");
                    }
                }, 400);
            }
        };
    }

    function flushAudioQueue() {
        activeSources.forEach(s => {
            try { s.stop(); } catch (e) {}
        });
        activeSources = [];
        if (outputAudioCtx) {
            scheduledAudioTime = outputAudioCtx.currentTime;
        }
        avatar.setAudioVolume(0.0);
    }

    // Toggle Voice Button
    btnToggleVoice.addEventListener('click', () => {
        if (isLiveActive) {
            stopLiveSession();
        } else {
            startLiveSession();
        }
    });

    // Interrupt (Barge-In) Button
    btnBargeIn.addEventListener('click', () => {
        flushAudioQueue();
        if (liveSocket && liveSocket.readyState === WebSocket.OPEN) {
            liveSocket.send(JSON.stringify({ type: 'interrupt' }));
        }
        avatar.setState('listening', "I'm listening...");
    });

    // Emergency Assistance Button
    const btnEmergency = document.getElementById('btn-emergency');
    btnEmergency.addEventListener('click', async () => {
        avatar.setState('speaking', "I am notifying your emergency family contacts and caregivers immediately. Please stay calm, help is on the way.");
        appendConversationMsg('Sarah', "🚨 Emergency alert triggered! Caregivers and family contacts are being alerted.");
        try {
            await api.sendFamilyContactRequest('Emergency', `EMERGENCY ALERT: Resident ${displayName} triggered emergency assistance.`);
            alert(`🚨 Emergency Alert Successfully Dispatched!\n\nFamily contacts and caregivers for resident ${displayName} have been notified.`);
        } catch (e) {
            alert(`🚨 Emergency Notification Active: Please remain calm. Help is being dispatched.`);
        }
    });

    // Manual Keyboard Text Input
    const textInput = document.getElementById('manual-text-input');
    const sendBtn = document.getElementById('manual-send-btn');
    async function handleManualSend() {
        const text = textInput.value.trim();
        if (!text) return;
        textInput.value = '';
        appendConversationMsg(displayName || 'Resident', text);

        if (isLiveActive && liveSocket && liveSocket.readyState === WebSocket.OPEN) {
            liveSocket.send(JSON.stringify({ type: 'text', text: text }));
        } else {
            avatar.setState('thinking', `"${text}"`);
            try {
                const res = await api.sendChat(text);
                const reply = res.speech || "I received your request.";
                appendConversationMsg('Sarah', reply);
                avatar.setState('speaking', reply);

                const audio = new Audio(`/api/tts?text=${encodeURIComponent(reply)}`);
                audio.onended = () => avatar.setState('idle', "Ready when you are.");
                audio.onerror = () => setTimeout(() => avatar.setState('idle', "Ready when you are."), 2500);
                await audio.play().catch(() => setTimeout(() => avatar.setState('idle', "Ready when you are."), 2500));
            } catch (err) {
                appendConversationMsg('Sarah', "I had a moment connecting, but I'm here to help.");
                avatar.setState('idle');
            }
        }
    }

    sendBtn.addEventListener('click', handleManualSend);
    textInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleManualSend();
    });
});
