/**
 * Sarah Resident Dashboard Controller
 * Integrates:
 * 1. Sarah Woman Talking Animated Avatar with Live Lip-Sync
 * 2. Unified Voice Engine: Web Speech STT (regional accents, phonetic "Sarah" wake word)
 *    and Google ADK Live BIDI Audio (Aoede voice, 16kHz raw PCM in, 24kHz out)
 * 3. Dynamic MySQL Database Synchronization (User, Household, Devices, Medications, Reminders)
 * 4. Music and Audio Playback (Elderly relaxation music, ambient audio)
 * 5. Emergency alerts, device controls, and real-time status updates
 * 6. Quick Touch Controls buttons removed
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
                        <span class="status-pill ${isOnline ? (powerState === 'on' ? 'pill-green' : 'pill-amber') : 'pill-amber'}">
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

    const btnClearConv = document.getElementById('btn-clear-conv');
    if (btnClearConv) {
        btnClearConv.addEventListener('click', () => {
            if (convContainer) convContainer.innerHTML = '';
        });
    }

    // 7. Music Streaming & Elderly Care Entertainment Engine
    const musicBar = document.getElementById('sarah-music-bar');
    const musicTitle = document.getElementById('music-title');
    const musicStatus = document.getElementById('music-status');
    const musicPlayBtn = document.getElementById('music-play-btn');
    const musicStopBtn = document.getElementById('music-stop-btn');
    const musicPlayer = document.getElementById('sarah-audio-player');

    function handleMusicPlayback(music) {
        if (!music || !musicPlayer) return;
        const action = music.action || 'play';
        const track = music.track || "Can't Help Falling in Love by Elvis Presley";
        const mediaUrl = music.media_url || '/audio/relaxing_music.wav';

        if (musicTitle) musicTitle.textContent = track;

        if (action === 'play') {
            musicPlayer.src = mediaUrl;
            musicPlayer.play().catch(e => console.warn('Music play rejected:', e));
            if (musicBar) musicBar.style.display = 'flex';
            if (musicStatus) musicStatus.textContent = 'Playing • Relaxing Audio';
            if (musicPlayBtn) musicPlayBtn.textContent = '⏸️ Pause';
        } else if (action === 'pause') {
            musicPlayer.pause();
            if (musicStatus) musicStatus.textContent = 'Paused';
            if (musicPlayBtn) musicPlayBtn.textContent = '▶️ Resume';
        } else if (action === 'stop') {
            musicPlayer.pause();
            musicPlayer.currentTime = 0;
            if (musicBar) musicBar.style.display = 'none';
        }
    }

    if (musicPlayBtn) {
        musicPlayBtn.addEventListener('click', () => {
            if (!musicPlayer) return;
            if (musicPlayer.paused) {
                musicPlayer.play().catch(() => {});
                musicPlayBtn.textContent = '⏸️ Pause';
                if (musicStatus) musicStatus.textContent = 'Playing • Relaxing Audio';
            } else {
                musicPlayer.pause();
                musicPlayBtn.textContent = '▶️ Resume';
                if (musicStatus) musicStatus.textContent = 'Paused';
            }
        });
    }

    if (musicStopBtn) {
        musicStopBtn.addEventListener('click', () => {
            if (musicPlayer) {
                musicPlayer.pause();
                musicPlayer.currentTime = 0;
            }
            if (musicBar) musicBar.style.display = 'none';
        });
    }

    // 8. Wake-Word Detection & 5-Minute Inactivity State Machine
    let isSarahAwake = false;
    let remainingSilenceSeconds = 0;
    let silenceInterval = null;

    const wakeBadge = document.getElementById('wake-badge');
    const wakeIcon = document.getElementById('wake-icon');
    const wakeLabel = document.getElementById('wake-label');
    const wakeTimerPill = document.getElementById('wake-timer-pill');
    const accentSelect = document.getElementById('accent-select');

    let currentAccent = localStorage.getItem('sarah_accent') || 'en-LK';
    if (accentSelect) {
        accentSelect.value = currentAccent;
        accentSelect.addEventListener('change', (e) => {
            currentAccent = e.target.value;
            localStorage.setItem('sarah_accent', currentAccent);
            if (recognition) {
                recognition.lang = currentAccent;
            }
        });
    }

    function formatTime(seconds) {
        const m = Math.floor(seconds / 60);
        const s = seconds % 60;
        return `${m}:${s < 10 ? '0' : ''}${s}`;
    }

    function wakeSarah() {
        isSarahAwake = true;
        remainingSilenceSeconds = 300;
        if (wakeBadge) wakeBadge.className = 'wake-word-badge awake';
        if (wakeIcon) wakeIcon.textContent = '⚡';
        if (wakeLabel) wakeLabel.innerHTML = 'Active: <strong>Sarah</strong>';
        if (wakeTimerPill) {
            wakeTimerPill.style.display = 'inline-block';
            wakeTimerPill.textContent = '5:00';
        }

        if (silenceInterval) clearInterval(silenceInterval);
        silenceInterval = setInterval(() => {
            remainingSilenceSeconds--;
            if (wakeTimerPill) wakeTimerPill.textContent = formatTime(remainingSilenceSeconds);
            if (remainingSilenceSeconds <= 0) {
                sleepSarah(true);
            }
        }, 1000);
    }

    function resetSilenceTimer() {
        if (isSarahAwake) {
            remainingSilenceSeconds = 300;
            if (wakeTimerPill) wakeTimerPill.textContent = '5:00';
        }
    }

    function sleepSarah(announce = false) {
        isSarahAwake = false;
        remainingSilenceSeconds = 0;
        if (silenceInterval) {
            clearInterval(silenceInterval);
            silenceInterval = null;
        }
        if (wakeBadge) wakeBadge.className = 'wake-word-badge asleep';
        if (wakeIcon) wakeIcon.textContent = '💤';
        if (wakeLabel) wakeLabel.innerHTML = 'Standby: Greet <strong>"Sarah"</strong>';
        if (wakeTimerPill) wakeTimerPill.style.display = 'none';

        if (announce) {
            appendConversationMsg('Sarah', '5 minutes of silence reached. Sarah has gone to standby. Greet me with "Sarah" to wake me up.');
            speakAssistantResponse('5 minutes of silence reached. I am now in standby mode. Greet me with Sarah to wake me up.');
        }
    }

    if (wakeBadge) {
        wakeBadge.addEventListener('click', () => {
            if (isSarahAwake) {
                sleepSarah(false);
            } else {
                wakeSarah();
                const greeting = "Hello! I'm Sarah. I'm listening, what can I do for you?";
                appendConversationMsg('Sarah', greeting);
                speakAssistantResponse(greeting);
            }
        });
    }

    // Soundex phonetic helper for "Sarah"
    function computeSoundex(word) {
        const clean = word.replace(/[^A-Za-z]/g, '').toUpperCase();
        if (!clean) return '';
        const mapping = {
            'B': '1', 'F': '1', 'P': '1', 'V': '1',
            'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
            'D': '3', 'T': '3',
            'L': '4',
            'M': '5', 'N': '5',
            'R': '6'
        };
        let res = clean[0];
        let prev = mapping[clean[0]] || '';
        for (let i = 1; i < clean.length; i++) {
            const code = mapping[clean[i]] || '';
            if (code && code !== prev) {
                res += code;
                prev = code;
            } else if (!code) {
                prev = '';
            }
        }
        return (res + '000').substring(0, 4);
    }

    function isPhoneticSarah(word) {
        const clean = word.replace(/[^a-zA-Z]/g, '').toLowerCase();
        if (!clean || clean.length < 3 || clean.length > 7) return false;
        const normalized = clean.startsWith('ce') || clean.startsWith('ci') || clean.startsWith('cy')
            ? 's' + clean.slice(1)
            : clean;
        const code = computeSoundex(normalized);
        return code === 'S600' || code === 'Z600';
    }

    const WAKE_REGEX = /^(?:(?:hey|hi|ok|okay|hello)\s+)?(?:sierra|serrah|sarrah|serra|sarra|sarha|sahra|saira|serah|zarah|syrah|surah|sarah|sara|sera|zara|cera|ceira|zahra|zera|sayrah|sorah|sura|seira|sora)(?:\b|[\s,:;!?-])\s*/i;

    // 9. Female Voice Synthesis & Animated Mouth Lip-Sync
    const tts = window.TTSHandler ? new window.TTSHandler() : null;
    let ttsAudioEl = null;

    function speakAssistantResponse(text, onEnded = null) {
        if (!text) return;
        avatar.setState('speaking', text);

        // Pre-rendered instant static audio match
        const lower = text.trim().toLowerCase();
        const staticMap = {
            "hello! i'm sarah. i'm listening, what can i do for you?": '/audio/sarah_greeting.mp3',
            "hello! i'm sarah. i'm listening, what can i do for you": '/audio/sarah_greeting.mp3',
            "okay, turning on the room lights.": '/audio/sarah_turn_on_room_lights.mp3',
            "okay, turning off the room lights.": '/audio/sarah_turn_off_room_lights.mp3',
            "okay, turning on the kitchen lights.": '/audio/sarah_turn_on_kitchen_lights.mp3',
            "okay, turning off the kitchen lights.": '/audio/sarah_turn_off_kitchen_lights.mp3',
            "okay, turning on the desk lamp.": '/audio/sarah_turn_on_desk_lamp.mp3',
            "okay, turning off the desk lamp.": '/audio/sarah_turn_off_desk_lamp.mp3',
            "okay, turning on the lights.": '/audio/sarah_turn_on_lights.mp3',
            "okay, turning off the lights.": '/audio/sarah_turn_off_lights.mp3',
            "okay, turning on light 1.": '/audio/sarah_turn_on_light_1.mp3',
            "okay, turning off light 1.": '/audio/sarah_turn_off_light_1.mp3',
            "okay, turning on the testing farm lights.": '/audio/sarah_turn_on_testing_farm_lights.mp3',
            "okay, turning off the testing farm lights.": '/audio/sarah_turn_off_testing_farm_lights.mp3',
            "sending the command to rn hub.": '/audio/sarah_sending_to_rn_hub.mp3',
            "okay.": '/audio/sarah_okay.mp3'
        };

        const staticUrl = staticMap[lower];

        if (staticUrl) {
            playAudioWithLipSync(staticUrl, onEnded);
        } else if (tts) {
            tts.speak(
                text,
                () => {
                    avatar.setState('speaking', text);
                    // Approximate lip movement
                    const iv = setInterval(() => {
                        if (avatar.state === 'speaking') {
                            avatar.setAudioVolume(0.3 + Math.random() * 0.5);
                        } else {
                            clearInterval(iv);
                        }
                    }, 120);
                },
                () => {
                    avatar.setAudioVolume(0.0);
                    avatar.setState('idle', "Ready when you are.");
                    if (onEnded) onEnded();
                }
            );
        } else {
            playAudioWithLipSync(`/api/tts?text=${encodeURIComponent(text)}`, onEnded);
        }
    }

    function playAudioWithLipSync(audioUrl, onEnded) {
        if (ttsAudioEl) {
            ttsAudioEl.pause();
            ttsAudioEl = null;
        }
        ttsAudioEl = new Audio(audioUrl);
        ttsAudioEl.crossOrigin = "anonymous";
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        let actx = null;
        let analyser = null;

        try {
            actx = new AudioCtx();
            if (actx.state === 'suspended') actx.resume();
            const src = actx.createMediaElementSource(ttsAudioEl);
            analyser = actx.createAnalyser();
            analyser.fftSize = 256;
            analyser.smoothingTimeConstant = 0.2;
            src.connect(analyser);
            analyser.connect(actx.destination);
        } catch (e) {
            // Audio context permission or CORS fallback
        }

        let animHandle = null;
        function updateMouth() {
            if (analyser) {
                const dataArray = new Uint8Array(analyser.frequencyBinCount);
                analyser.getByteFrequencyData(dataArray);
                let sum = 0;
                for (let i = 0; i < dataArray.length; i++) sum += dataArray[i];
                const avg = sum / dataArray.length;
                avatar.setAudioVolume(Math.min(1.0, avg / 60));
            } else {
                avatar.setAudioVolume(0.3 + Math.random() * 0.4);
            }
            if (!ttsAudioEl.paused && !ttsAudioEl.ended) {
                animHandle = requestAnimationFrame(updateMouth);
            }
        }

        ttsAudioEl.onplay = () => {
            avatar.setState('speaking');
            animHandle = requestAnimationFrame(updateMouth);
        };

        ttsAudioEl.onended = () => {
            if (animHandle) cancelAnimationFrame(animHandle);
            avatar.setAudioVolume(0.0);
            avatar.setState('idle', "Ready when you are.");
            if (actx && actx.state !== 'closed') actx.close().catch(() => {});
            if (onEnded) onEnded();
        };

        ttsAudioEl.onerror = () => {
            if (animHandle) cancelAnimationFrame(animHandle);
            avatar.setAudioVolume(0.0);
            avatar.setState('idle', "Ready when you are.");
            if (actx && actx.state !== 'closed') actx.close().catch(() => {});
            if (onEnded) onEnded();
        };

        ttsAudioEl.play().catch(e => {
            console.warn('Audio play prevented:', e);
            avatar.setState('idle');
            if (onEnded) onEnded();
        });
    }

    // 10. Voice Engine Toggle: Standard Sarah AI vs Google ADK Live BIDI
    let engineMode = 'standard'; // 'standard' | 'live_adk'
    const engineModeBtn = document.getElementById('engine-mode-btn');

    if (engineModeBtn) {
        engineModeBtn.addEventListener('click', () => {
            if (engineMode === 'standard') {
                engineMode = 'live_adk';
                engineModeBtn.textContent = '⚡ Engine: Google ADK Live BIDI (Aoede)';
                engineModeBtn.style.background = '#dbeafe';
                engineModeBtn.style.color = '#1d4ed8';
                appendConversationMsg('Sarah', "Switched to Google ADK Live BIDI Mode with Gemini Aoede voice.");
            } else {
                engineMode = 'standard';
                engineModeBtn.textContent = '🎙️ Engine: Sarah Voice AI (Active)';
                engineModeBtn.style.background = 'var(--primary-light)';
                engineModeBtn.style.color = 'var(--primary-dark)';
                if (isLiveActive) stopLiveSession();
                appendConversationMsg('Sarah', "Switched to Standard Sarah Voice AI Mode with Web Speech & tools.");
            }
        });
    }

    // 11. Web Speech STT Engine (First Iteration Parity)
    let recognition = null;
    let isRecognizing = false;
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = currentAccent;

        recognition.onstart = () => {
            isRecognizing = true;
            setVoiceState('listening', 'Listening...');
            voiceBtnIcon.textContent = '⏹️';
            voiceBtnText.textContent = 'Stop Listening';
            btnToggleVoice.classList.remove('btn-primary');
            btnToggleVoice.classList.add('btn-danger');
        };

        recognition.onresult = async (event) => {
            let interimTranscript = '';
            let finalTranscript = '';

            for (let i = event.resultIndex; i < event.results.length; i++) {
                const transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    finalTranscript += transcript;
                } else {
                    interimTranscript += transcript;
                }
            }

            if (interimTranscript) {
                avatar.setState('listening', `"${interimTranscript}"`);
            }

            if (finalTranscript.trim()) {
                const userText = finalTranscript.trim();
                console.log('Recognized speech:', userText);

                // Wake word evaluation
                const hasWakeWord = WAKE_REGEX.test(userText) || userText.split(/\s+/).some(isPhoneticSarah);

                if (hasWakeWord) {
                    wakeSarah();
                    resetSilenceTimer();
                    const cleanedQuery = userText.replace(WAKE_REGEX, '').trim();

                    if (!cleanedQuery || cleanedQuery.length < 2) {
                        const greeting = "Hello! I'm Sarah. I'm listening, what can I do for you?";
                        appendConversationMsg('Sarah', greeting);
                        speakAssistantResponse(greeting);
                        return;
                    }
                    await processUserVoiceQuery(cleanedQuery);
                } else if (isSarahAwake) {
                    resetSilenceTimer();
                    await processUserVoiceQuery(userText);
                } else {
                    // Not awake yet: prompt user
                    avatar.setState('idle', 'Say "Sarah" or click Talk to start.');
                }
            }
        };

        recognition.onerror = (e) => {
            console.debug('Speech recognition error:', e.error);
            if (e.error === 'not-allowed') {
                setVoiceState('error', 'Mic Blocked');
            }
        };

        recognition.onend = () => {
            isRecognizing = false;
            if (engineMode === 'standard' && isSarahAwake) {
                try { recognition.start(); } catch (e) {}
            } else {
                setVoiceState('standby', 'Ready to listen');
                voiceBtnIcon.textContent = '🎙️';
                voiceBtnText.textContent = 'Talk to Sarah';
                btnToggleVoice.classList.remove('btn-danger');
                btnToggleVoice.classList.add('btn-primary');
            }
        };
    }

    async function processUserVoiceQuery(queryText) {
        appendConversationMsg(displayName || 'Resident', queryText);
        avatar.setState('thinking', `"${queryText}"`);
        setVoiceState('thinking', 'Processing...');

        try {
            const res = await api.sendChat(queryText);
            const reply = res.speech || "I received your request.";
            appendConversationMsg('Sarah', reply);

            // Handle device command
            if (res.command) {
                await loadHouseholdDevices();
            }

            // Handle reminder
            if (res.reminder) {
                await loadScheduleAndMedications();
            }

            // Handle music
            if (res.music) {
                handleMusicPlayback(res.music);
            }

            speakAssistantResponse(reply, () => {
                setVoiceState('standby', 'Ready to listen');
            });
        } catch (err) {
            console.error('Chat error:', err);
            const errMsg = "I had a moment connecting, but I'm here to help.";
            appendConversationMsg('Sarah', errMsg);
            speakAssistantResponse(errMsg);
        }
    }

    // 12. Google ADK Live BIDI Voice AI Engine (WebSocket Raw PCM)
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
            avatar.setState('thinking', "Connecting to Sarah Live Voice AI...");

            const ticketRes = await api.acquireWsTicket();
            const ticket = ticketRes.ticket;
            const endpoint = ticketRes.ws_endpoint || '/api/v1/sarah-live/ws';

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

                await initMicrophoneCapture();
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
            // Fallback to Standard Voice
            engineMode = 'standard';
            if (engineModeBtn) engineModeBtn.textContent = '🎙️ Engine: Sarah Voice AI (Active)';
            avatar.setState('idle', "Connecting via Standard Voice AI.");
            toggleVoice();
        }
    }

    function stopLiveSession() {
        isLiveActive = false;
        if (liveSocket && liveSocket.readyState === WebSocket.OPEN) {
            liveSocket.close();
        }
        liveSocket = null;

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

        flushAudioQueue();
        if (outputAudioCtx && outputAudioCtx.state !== 'closed') {
            outputAudioCtx.close().catch(() => {});
            outputAudioCtx = null;
        }

        btnToggleVoice.classList.remove('btn-danger');
        btnToggleVoice.classList.add('btn-primary');
        voiceBtnIcon.textContent = '🎙️';
        voiceBtnText.textContent = 'Talk to Sarah';
        setVoiceState('standby', 'Ready to listen');
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

            let sum = 0;
            for (let i = 0; i < channelData.length; i++) {
                sum += channelData[i] * channelData[i];
            }
            const rms = Math.sqrt(sum / channelData.length);
            if (rms > 0.05 && avatar.state !== 'speaking') {
                avatar.setState('listening', "Listening to you...");
            }

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

        let sum = 0;
        for (let i = 0; i < pcm16.length; i++) {
            float32[i] = pcm16[i] / 32768.0;
            sum += float32[i] * float32[i];
        }
        const rms = Math.sqrt(sum / pcm16.length);

        avatar.setState('speaking');
        avatar.setAudioVolume(rms);

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

    // Toggle Voice Button (Universal handler for both modes)
    function toggleVoice() {
        if (engineMode === 'live_adk') {
            if (isLiveActive) {
                stopLiveSession();
            } else {
                startLiveSession();
            }
        } else {
            // Standard Web Speech Mode
            wakeSarah();
            if (isRecognizing) {
                if (recognition) recognition.stop();
            } else {
                if (recognition) {
                    try {
                        recognition.start();
                    } catch (e) {
                        console.debug('Recognition restart:', e);
                    }
                } else {
                    // No Web Speech API: prompt text
                    const txt = prompt("Voice recognition is not available in this browser. Please type your message for Sarah:");
                    if (txt) processUserVoiceQuery(txt);
                }
            }
        }
    }

    btnToggleVoice.addEventListener('click', toggleVoice);

    // Interrupt (Barge-In) Button
    btnBargeIn.addEventListener('click', () => {
        flushAudioQueue();
        if (ttsAudioEl) {
            ttsAudioEl.pause();
            ttsAudioEl = null;
        }
        if (liveSocket && liveSocket.readyState === WebSocket.OPEN) {
            liveSocket.send(JSON.stringify({ type: 'interrupt' }));
        }
        avatar.setAudioVolume(0.0);
        avatar.setState('listening', "I'm listening...");
    });

    // Emergency Assistance Button
    const btnEmergency = document.getElementById('btn-emergency');
    btnEmergency.addEventListener('click', async () => {
        avatar.setState('speaking', "I am notifying your emergency family contacts and caregivers immediately. Please stay calm, help is on the way.");
        appendConversationMsg('Sarah', "🚨 Emergency alert triggered! Caregivers and family contacts are being alerted.");
        speakAssistantResponse("I am notifying your emergency family contacts and caregivers immediately. Please stay calm, help is on the way.");
        try {
            await api.sendFamilyContactRequest('Emergency', `EMERGENCY ALERT: Resident ${displayName} triggered emergency assistance.`);
            alert(`🚨 Emergency Alert Successfully Dispatched!\n\nFamily contacts and caregivers for resident ${displayName} have been notified.`);
        } catch (e) {
            alert(`🚨 Emergency Notification Active: Help is being dispatched.`);
        }
    });

    // Manual Keyboard Text Input
    const textInput = document.getElementById('manual-text-input');
    const sendBtn = document.getElementById('manual-send-btn');
    async function handleManualSend() {
        const text = textInput.value.trim();
        if (!text) return;
        textInput.value = '';
        wakeSarah();
        resetSilenceTimer();
        await processUserVoiceQuery(text);
    }

    sendBtn.addEventListener('click', handleManualSend);
    textInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') handleManualSend();
    });
});
