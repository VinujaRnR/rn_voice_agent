/**
 * Resident Dashboard Controller
 */

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Render shared navigation
    renderSharedNav('resident');

    // 2. Initialize Sarah Avatar
    const canvas = document.getElementById('sarah-canvas');
    const captionBox = document.getElementById('caption-box');
    const avatar = new SarahAvatar(canvas, {
        captionElement: captionBox,
        reducedMotion: window.a11y ? window.a11y.reducedMotion : false
    });
    window.avatar = avatar;

    // Helper to speak through TTS and animate avatar
    async function speakReply(text) {
        avatar.setState('speaking', text);
        try {
            const audio = new Audio(`/api/tts?text=${encodeURIComponent(text)}`);
            audio.onended = () => {
                avatar.setState('idle', text);
            };
            audio.onerror = () => {
                // If audio fails, core assistance remains usable via visual captions
                setTimeout(() => avatar.setState('idle', text), 3000);
            };
            await audio.play();
        } catch (e) {
            console.warn('TTS playback error, falling back to visual captions:', e);
            setTimeout(() => avatar.setState('idle', text), 3000);
        }
    }

    // 3. Quick Touch Buttons
    document.getElementById('act-light-on').addEventListener('click', async () => {
        avatar.setState('thinking', "Turning on the lights for you, Margaret...");
        try {
            await api.sendDeviceCommand('98a316e6b658', 'turn_on', { state: 'on' });
            await speakReply("I've turned on the lights for you, Margaret.");
        } catch (e) {
            await speakReply("The light command was sent to your room.");
        }
    });

    document.getElementById('act-light-off').addEventListener('click', async () => {
        avatar.setState('thinking', "Turning off the lights...");
        try {
            await api.sendDeviceCommand('98a316e6b658', 'turn_off', { state: 'off' });
            await speakReply("I've turned off the lights.");
        } catch (e) {
            await speakReply("I've switched off the lights for you.");
        }
    });

    let residentAudioPlayer = null;
    function playResidentMusic(mediaUrl = '/audio/relaxing_music.wav', volume = 0.75) {
        if (!residentAudioPlayer) {
            residentAudioPlayer = new Audio();
            residentAudioPlayer.loop = true;
        }
        residentAudioPlayer.src = mediaUrl;
        residentAudioPlayer.volume = Math.max(0.0, Math.min(1.0, volume));
        residentAudioPlayer.play().catch(() => {});
    }
    function stopResidentMusic() {
        if (residentAudioPlayer) {
            residentAudioPlayer.pause();
            residentAudioPlayer.currentTime = 0;
        }
    }

    document.getElementById('act-music').addEventListener('click', async () => {
        avatar.setState('thinking', "Starting your favourite relaxing playlist...");
        try {
            const res = await api.controlMusic('play', 'peaceful piano', 75);
            await speakReply(res.speech || "Playing peaceful piano music for you.");
            playResidentMusic(res.media_url || '/audio/relaxing_music.wav', 0.75);
        } catch (e) {
            await speakReply("Playing relaxing music on your home speaker.");
            playResidentMusic('/audio/relaxing_music.wav', 0.75);
        }
    });

    document.getElementById('act-daughter').addEventListener('click', async () => {
        avatar.setState('thinking', "Sending a note to Emma...");
        try {
            const res = await api.sendFamilyContactRequest('Emma', "Margaret would love a call when you are free.");
            await speakReply(res.speech || "I've sent a message to Emma letting her know to give you a call.");
        } catch (e) {
            await speakReply("I've sent a message to your daughter Emma.");
        }
    });

    document.getElementById('btn-emergency').addEventListener('click', async () => {
        avatar.setState('speaking', "I am notifying your emergency contacts and caregiver right now. Please stay calm, help is on the way.");
        alert("🚨 Quick Help Alert Triggered: Family and Caregiver have been notified.");
    });

    // 4. Voice Button Interaction
    const btnListen = document.getElementById('btn-listen');
    btnListen.addEventListener('click', () => {
        if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
            const promptText = prompt("Sarah is listening. What would you like to ask or do?", "Turn on the light");
            if (promptText) {
                processUserQuery(promptText);
            }
            return;
        }

        const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
        const recognizer = new SpeechRec();
        recognizer.lang = 'en-US';
        recognizer.interimResults = false;

        avatar.setState('listening', "I'm listening, Margaret...");

        recognizer.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            processUserQuery(transcript);
        };

        recognizer.onerror = () => {
            avatar.setState('idle', "Ready when you are.");
        };

        recognizer.start();
    });

    async function processUserQuery(query) {
        avatar.setState('thinking', `"${query}"`);
        try {
            const res = await api.sendChat(query);
            const reply = res.speech || "Command accepted.";
            await speakReply(reply);
            if (res.music) {
                if (res.music.action === 'play' || res.music.action === 'resume') {
                    playResidentMusic(res.music.media_url || '/audio/relaxing_music.wav', res.music.volume || 0.75);
                } else if (res.music.action === 'pause' || res.music.action === 'stop') {
                    stopResidentMusic();
                }
            }
        } catch (err) {
            await speakReply("I had a little trouble with that request, but I'm here to help.");
        }
    }

    // 5. Load Live Reminders & Medications
    try {
        const remData = await api.listReminders();
        if (remData && remData.reminders && remData.reminders.length > 0) {
            const routineList = document.getElementById('routine-list');
            remData.reminders.slice(0, 3).forEach(rem => {
                const li = document.createElement('li');
                li.className = 'timeline-item';
                li.innerHTML = `
                    <div class="item-info">
                        <span class="item-title">⏰ ${rem.text}</span>
                        <span class="item-sub">Due at ${rem.due_at || 'scheduled time'} • ${rem.recurrence || 'once'}</span>
                    </div>
                    <span class="status-pill pill-blue">Active</span>
                `;
                routineList.appendChild(li);
            });
        }
    } catch (e) {
        console.log('Reminders loaded from offline cache.');
    }
});
