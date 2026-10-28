/**
 * Web Speech STT Implementation with 'Sarah' Phonetic Wake-Word Detection
 * File: frontend/speech.js
 */

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const statusIndicator = document.getElementById('status-indicator');
  const statusPanel = document.querySelector('.status-panel');
  const micBtn = document.getElementById('mic-btn');
  const micHint = document.getElementById('mic-hint');
  const transcriptEl = document.getElementById('transcript');
  const transcriptState = document.getElementById('transcript-state');
  const conversationHistory = document.getElementById('conversation-history');
  const chatForm = document.getElementById('chat-form');
  const textInput = document.getElementById('text-input');
  const clearBtn = document.getElementById('clear-btn');
  const connectionBadge = document.getElementById('connection-badge');
  const connectionText = document.getElementById('connection-text');
  const wakeToggle = document.getElementById('wake-toggle');
  const quickChips = document.querySelectorAll('.chip');
  const wakeBadge = document.getElementById('wake-badge');
  const wakeIcon = document.getElementById('wake-icon');
  const wakeLabel = document.getElementById('wake-label');
  const wakeTimerPill = document.getElementById('wake-timer-pill');
  const accentSelect = document.getElementById('accent-select');

  // Selected Regional Accent (defaults to Sri Lanka en-LK for local speech accuracy)
  let currentAccent = localStorage.getItem('sarah_accent') || 'en-LK';
  if (accentSelect) {
    accentSelect.value = currentAccent;
  }

  // Session ID
  const sessionId = 'session_' + Math.random().toString(36).substring(2, 9);
  let isListening = false;
  let shouldStayListening = true; // For continuous wake-word mode
  let finalTranscriptReceived = false;

  // 5-Minute Inactivity / Silence State Machine
  let isSarahAwake = false;
  let remainingSilenceSeconds = 0;
  let silenceInterval = null;

  function formatTime(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  }

  function wakeSarah() {
    isSarahAwake = true;
    remainingSilenceSeconds = 300; // 5 minutes
    if (wakeBadge) {
      wakeBadge.className = 'wake-word-badge awake';
    }
    if (wakeIcon) wakeIcon.textContent = '⚡';
    if (wakeLabel) wakeLabel.innerHTML = 'Active: <strong>Sarah</strong>';
    if (wakeTimerPill) {
      wakeTimerPill.style.display = 'inline-block';
      wakeTimerPill.textContent = '5:00';
    }

    if (silenceInterval) clearInterval(silenceInterval);
    silenceInterval = setInterval(() => {
      remainingSilenceSeconds--;
      if (wakeTimerPill) {
        wakeTimerPill.textContent = formatTime(remainingSilenceSeconds);
      }
      if (remainingSilenceSeconds <= 0) {
        sleepSarah(true);
      }
    }, 1000);
  }

  function resetSilenceTimer() {
    if (isSarahAwake) {
      remainingSilenceSeconds = 300;
      if (wakeTimerPill) {
        wakeTimerPill.textContent = '5:00';
      }
    }
  }

  function sleepSarah(announce = false) {
    isSarahAwake = false;
    remainingSilenceSeconds = 0;
    if (silenceInterval) {
      clearInterval(silenceInterval);
      silenceInterval = null;
    }
    if (wakeBadge) {
      wakeBadge.className = 'wake-word-badge asleep';
    }
    if (wakeIcon) wakeIcon.textContent = '💤';
    if (wakeLabel) wakeLabel.innerHTML = 'Standby: Greet <strong>"Sarah"</strong>';
    if (wakeTimerPill) {
      wakeTimerPill.style.display = 'none';
    }
    setAssistantStatus('Ready to listen');

    if (announce) {
      appendMessage('Sarah', '5 minutes of silence reached. Sarah has gone to sleep. Greet me with "Sarah" to trigger again.');
      if (tts) {
        setAssistantStatus('Speaking');
        tts.speak(
          '5 minutes of silence reached. I am now in sleep mode. Greet me with Sarah to wake me up.',
          () => setAssistantStatus('Speaking'),
          () => setAssistantStatus('Ready to listen')
        );
      }
    }
  }

  // Allow clicking wake badge to test/toggle wake/sleep manually
  if (wakeBadge) {
    wakeBadge.addEventListener('click', () => {
      if (isSarahAwake) {
        sleepSarah(false);
        appendMessage('Sarah', 'Sarah is now in sleep mode. Greet me with "Sarah" to wake me up.');
      } else {
        wakeSarah();
        appendMessage('Sarah', "Hello! I'm Sarah. I'm listening, what can I do for you?");
        if (tts) tts.speak("Hello! I'm Sarah. I'm listening, what can I do for you?");
      }
    });
  }

  // Soundex helper for phonetic matching of any pronunciation of 'Sarah'
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

  // Regex pattern matching phonetic variants of Sarah (and backward compatibility for Alexa/Jarvis)
  const WAKE_REGEX = /^(?:(?:hey|hi|ok|okay|hello)\s+)?(?:sierra|serrah|sarrah|serra|sarra|sarha|sahra|saira|serah|zarah|syrah|surah|sarah|sara|sera|zara|cera|ceira|zahra|zera|sayrah|sorah|sura|seira|sora|alexa|jarvis)(?:\b|[\s,:;!?-])\s*/i;

  // Initialize TTS helper if available
  const tts = window.TTSHandler ? new window.TTSHandler() : null;

  // Assistant status manager: Listening, Thinking, Speaking, Executing, Ready to listen
  function setAssistantStatus(status) {
    statusIndicator.textContent = status;
    statusPanel.className = 'status-panel';

    if (status.toLowerCase().includes('listen')) {
      statusPanel.classList.add('listening');
      transcriptState.textContent = 'Listening';
      transcriptState.className = 'transcript-badge active';
      micBtn.classList.add('active');
      micHint.textContent = 'Listening... Say "Sarah" or your request';
    } else if (status.toLowerCase().includes('think')) {
      statusPanel.classList.add('thinking');
      transcriptState.textContent = 'Processing';
      transcriptState.className = 'transcript-badge active';
      micBtn.classList.remove('active');
      micHint.textContent = 'Thinking...';
    } else if (status.toLowerCase().includes('speak')) {
      statusPanel.classList.add('speaking');
      transcriptState.textContent = 'Speaking';
      transcriptState.className = 'transcript-badge';
      micBtn.classList.remove('active');
      micHint.textContent = 'Sarah speaking...';
    } else if (status.toLowerCase().includes('execut')) {
      statusPanel.classList.add('executing');
      transcriptState.textContent = 'Executing';
      transcriptState.className = 'transcript-badge';
      micBtn.classList.remove('active');
      micHint.textContent = 'Executing command...';
    } else {
      // Ready to listen / Idle
      transcriptState.textContent = isSarahAwake ? 'Active' : 'Standby';
      transcriptState.className = isSarahAwake ? 'transcript-badge active' : 'transcript-badge';
      micBtn.classList.remove('active');
      if (isSarahAwake) {
        micHint.textContent = `Sarah is listening for any command (${formatTime(remainingSilenceSeconds)} left)`;
      } else {
        micHint.textContent = 'Greet "Sarah" to wake me up (any pronunciation)';
      }
    }
  }

  // Conversation history helper
  function appendMessage(sender, text, isError = false) {
    const card = document.createElement('div');
    card.className = `message-card ${sender === 'User' ? 'user' : 'assistant'}${isError ? ' error' : ''}`;

    const tag = document.createElement('div');
    tag.className = 'sender-tag';
    tag.textContent = sender;

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = text;

    card.appendChild(tag);
    card.appendChild(bubble);
    conversationHistory.appendChild(card);
    conversationHistory.scrollTop = conversationHistory.scrollHeight;
  }

  // Clear conversation history
  clearBtn.addEventListener('click', () => {
    conversationHistory.innerHTML = '';
  });

  function handleFastAPIResponse(data) {
    if (!data) return;
    if (window.App && typeof window.App.handleAssistantResponse === 'function') {
      window.App.handleAssistantResponse(data);
      return;
    }
    let displayText = data.speech;
    if (data.mode === 'device_command' && data.command) {
      const paramStr = Object.entries(data.command.parameters || {})
        .map(([k, v]) => `${k}=${v}`)
        .join(', ');
      const devName = data.command.device_id === '98a316e6b658' ? 'Testing Farm Lights' : data.command.device_id;
      displayText = data.speech || `Okay, setting ${data.command.action} on '${devName}'${paramStr ? ' (' + paramStr + ')' : ''}.`;
      setAssistantStatus('Executing');
      setTimeout(() => setAssistantStatus('Ready to listen'), 2500);
    } else if (data.mode === 'clarify') {
      const missing = data.missing_fields && data.missing_fields.length > 0 
        ? ` (Need: ${data.missing_fields.join(', ')})` 
        : '';
      displayText = `${data.speech || 'Which device should I control?'}${missing}`;
    }

    appendMessage('Sarah', displayText || 'Command received.');

    // Play audio response if TTS available and speech text exists
    const speechToPlay = data.speech || displayText;
    if (tts && speechToPlay) {
      setAssistantStatus('Speaking');
      tts.speak(
        speechToPlay,
        () => setAssistantStatus('Speaking'),
        () => {
          setAssistantStatus('Ready to listen');
          // Resume wake-word listening if continuous
          if (wakeToggle.checked && !isListening && !isMediaRecording) {
            startRecognition();
          }
        }
      );
    } else if (data.mode !== 'device_command') {
      setAssistantStatus('Ready to listen');
    }
  }

  // Call POST /api/chat with user text and session ID
  async function sendToFastAPI(userText) {
    setAssistantStatus('Thinking');
    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          text: userText,
          message: userText,
          session_id: sessionId
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      handleFastAPIResponse(data);
    } catch (err) {
      console.error('API Error:', err);
      appendMessage('Sarah', `Error contacting backend: ${err.message}`, true);
      setAssistantStatus('Ready to listen');
    }
  }

  // Send recorded audio to STT service (Gemini Audio / Faster-Whisper)
  async function sendAudioToFasterWhisper(audioBlob) {
    setAssistantStatus('Thinking');
    transcriptEl.textContent = 'Transcribing with Gemini Audio...';
    try {
      const formData = new FormData();
      formData.append('file', audioBlob, 'recording.webm');
      formData.append('session_id', sessionId);

      const response = await fetch('/api/chat/audio', {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      const transcribed = data.transcript;
      if (transcribed) {
        transcriptEl.textContent = transcribed;
        const parsed = extractCommandWithWakeWord(transcribed);

        if (!isSarahAwake) {
          // Asleep mode
          if (parsed.hasWakeWord) {
            wakeSarah();
            appendMessage('User', transcribed);
            handleFastAPIResponse(data.response);
          } else {
            transcriptEl.textContent = `Heard: "${transcribed}" (Sarah is asleep. Greet "Sarah" to wake)`;
            appendMessage('User', transcribed);
            appendMessage('Sarah', "I'm in sleep mode. Please say 'Sarah' to wake me up.");
            if (tts) tts.speak("I'm in sleep mode. Please say Sarah to wake me up.");
            setAssistantStatus('Ready to listen');
          }
        } else {
          // Awake mode -> any command works and resets silence timer!
          resetSilenceTimer();
          const clean = transcribed.toLowerCase().trim();
          if (['go to sleep', 'sleep', 'turn off', 'power down', 'good night'].includes(clean)) {
            sleepSarah(false);
          }
          appendMessage('User', transcribed);
          handleFastAPIResponse(data.response);
        }
      }
    } catch (err) {
      console.error('Faster-Whisper STT Error:', err);
      appendMessage('Sarah', `Faster-Whisper STT Error: ${err.message}`, true);
      setAssistantStatus('Ready to listen');
    }
  }

  // Extract command with phonetic wake-word detection for Sarah
  function extractCommandWithWakeWord(transcript) {
    const raw = transcript.trim();
    if (!raw) return { hasWakeWord: false, command: '' };

    // 1. Regex check on phonetic spellings
    const match = raw.match(WAKE_REGEX);
    if (match) {
      const remainder = raw.substring(match[0].length).replace(/^[,:;!-]+/, '').trim();
      return {
        hasWakeWord: true,
        command: remainder || 'Sarah'
      };
    }

    // 2. Soundex check on first word (or second word if prefixed by 'hey' / 'hi')
    const tokens = raw.split(/\s+/);
    if (tokens.length > 0) {
      const first = tokens[0].replace(/[^a-zA-Z]/g, '');
      if (isPhoneticSarah(first)) {
        const remainder = tokens.slice(1).join(' ').replace(/^[,:;!-]+/, '').trim();
        return {
          hasWakeWord: true,
          command: remainder || 'Sarah'
        };
      }
      if (['hey', 'hi', 'ok', 'okay', 'hello'].includes(first.toLowerCase()) && tokens.length > 1) {
        const second = tokens[1].replace(/[^a-zA-Z]/g, '');
        if (isPhoneticSarah(second)) {
          const remainder = tokens.slice(2).join(' ').replace(/^[,:;!-]+/, '').trim();
          return {
            hasWakeWord: true,
            command: remainder || 'Sarah'
          };
        }
      }
    }

    return {
      hasWakeWord: false,
      command: raw
    };
  }

  function normalizeClientTranscript(text) {
    if (!text) return '';
    let res = text.trim();
    res = res.replace(/^(?:(?:hey|hi|ok|okay|hello)\s+)?\b(sierra|serrah|sarrah|serra|sarra|sarha|sahra|saira|serah|zarah|syrah|surah|sara|sera|zara|cera|zahra|zera|sayrah|sorah|sura|seira|sora)\b/i, 'Sarah');
    res = res.replace(/\btesting\s+(?:farm|fan|form|firm|palm|fram|from|farms)\s+lights?\b/gi, 'testing farm lights');
    res = res.replace(/\b(?:farm|fan|form|firm|palm|fram)\s+lights?\b/gi, 'farm lights');
    res = res.replace(/\b(?:room|rum|rome)\s+lights?\b/gi, 'room lights');
    res = res.replace(/\bkitchen\s+(?:lights?|likes?|line)\b/gi, 'kitchen lights');
    res = res.replace(/\b(?:columbo|columba|calombo|calumba)\b/gi, 'Colombo');
    res = res.replace(/\b(?:tern|tunnel|tune|ten|danone)\s+on\b/gi, 'turn on');
    res = res.replace(/\b(?:tern|tune|turned)\s+off\b/gi, 'turn off');
    res = res.replace(/\bturn\s+of\b/gi, 'turn off');
    return res.trim();
  }

  // Web Speech API Initialization
  const SpeechRecognition =
    window.SpeechRecognition ||
    window.webkitSpeechRecognition;

  let recognition = null;

  function initRecognition() {
    if (!SpeechRecognition) return null;

    const rec = new SpeechRecognition();
    rec.lang = currentAccent || 'en-LK';
    rec.continuous = true;
    rec.interimResults = true;

    // Event: onstart
    rec.onstart = () => {
      isListening = true;
      finalTranscriptReceived = false;
      setAssistantStatus('Listening');
    };

    // Event: onresult
    rec.onresult = (event) => {
      // Prevent microphone recognition from running/transcribing while TTS is speaking
      if (window.isSpeaking && window.isSpeaking()) {
        console.log('[Microphone Recognition]: Discarding speech while TTS is speaking');
        return;
      }

      let interimTranscript = '';
      let finalTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const part = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += part;
        } else {
          interimTranscript += part;
        }
      }

      finalTranscript = normalizeClientTranscript(finalTranscript);
      const text = (finalTranscript || interimTranscript).trim();
      if (text) {
        transcriptEl.textContent = text;
      }

      // Check for wake-word activation or final speech
      if (finalTranscript) {
        const parsed = extractCommandWithWakeWord(finalTranscript);

        if (!isSarahAwake) {
          // Sarah is ASLEEP: Must first trigger by greeting Sarah
          if (parsed.hasWakeWord) {
            wakeSarah();
            const commandToSend = parsed.command;
            appendMessage('User', finalTranscript.trim());
            sendToFastAPI(commandToSend || 'Sarah');
          } else {
            transcriptEl.textContent = `Heard: "${finalTranscript}" (Sarah is asleep. Greet "Sarah" to wake)`;
            return;
          }
        } else {
          // Sarah is AWAKE: Any command allowed and resets the 5-minute silence timer!
          resetSilenceTimer();
          const clean = finalTranscript.trim();
          if (['go to sleep', 'sleep', 'turn off', 'power down', 'good night'].includes(clean.toLowerCase())) {
            sleepSarah(false);
            appendMessage('User', clean);
            sendToFastAPI(clean);
          } else {
            const commandToSend = parsed.hasWakeWord ? (parsed.command || 'Sarah') : clean;
            appendMessage('User', clean);
            sendToFastAPI(commandToSend);
          }
        }
      }
    };

    // Event: onend
    rec.onend = () => {
      isListening = false;
      // Do not auto-restart if paused for TTS playback
      if (isPausedForTTS) {
        return;
      }
      // Auto-restart if continuous wake word is toggled on
      if (wakeToggle.checked && shouldStayListening) {
        setTimeout(() => {
          if (!isPausedForTTS) {
            try {
              rec.start();
            } catch (e) {
              // ignore rapid start errors
            }
          }
        }, 300);
      } else {
        setAssistantStatus('Ready to listen');
      }
    };

    // Event: onerror
    rec.onerror = (event) => {
      console.warn('Speech recognition event:', event.error);
      if (event.error === 'not-allowed') {
        transcriptEl.textContent = 'Microphone permission blocked. Please allow microphone access.';
        shouldStayListening = false;
        setAssistantStatus('Ready to listen');
      } else if (event.error !== 'no-speech') {
        transcriptEl.textContent = `Recognition note: ${event.error}`;
      }
    };

    return rec;
  }

  recognition = initRecognition();

  let isPausedForTTS = false;

  function pauseRecognition() {
    isPausedForTTS = true;
    if (recognition && isListening) {
      try {
        recognition.stop();
      } catch (e) {}
    }
  }

  function resumeRecognition() {
    isPausedForTTS = false;
    if (wakeToggle && wakeToggle.checked && recognition && !isListening) {
      try {
        shouldStayListening = true;
        recognition.start();
      } catch (e) {}
    }
  }

  function startRecognition() {
    if (!recognition) return;
    try {
      shouldStayListening = true;
      recognition.start();
    } catch (e) {
      console.log('Recognition already started or error:', e);
    }
  }

  function stopRecognition() {
    if (!recognition) return;
    shouldStayListening = false;
    try {
      recognition.stop();
    } catch (e) {
      console.log('Error stopping recognition:', e);
    }
    setAssistantStatus('Ready to listen');
  }

  // Expose SpeechController globally
  window.SpeechController = {
    startRecognition,
    stopRecognition,
    pauseRecognition,
    resumeRecognition,
    isListening: () => isListening,
    wakeSarah,
    sleepSarah
  };

  let mediaRecorder = null;
  let audioChunks = [];
  let isMediaRecording = false;

  async function startAudioRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      startRecognition();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
      };
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        const blob = new Blob(audioChunks, { type: 'audio/webm' });
        if (blob.size > 500) {
          await sendAudioToFasterWhisper(blob);
        } else {
          setAssistantStatus('Ready to listen');
        }
      };
      mediaRecorder.start();
      isMediaRecording = true;
      setAssistantStatus('Listening');
      micHint.textContent = 'Recording with Faster-Whisper... Click mic when finished';
    } catch (err) {
      console.warn('Microphone stream error, fallback to Web Speech:', err);
      startRecognition();
    }
  }

  function stopAudioRecording() {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
      isMediaRecording = false;
      micHint.textContent = 'Transcribing with Faster-Whisper...';
    }
  }

  // Toggle microphone button click
  micBtn.addEventListener('click', () => {
    if (isMediaRecording) {
      stopAudioRecording();
    } else if (isListening) {
      stopRecognition();
    } else {
      startAudioRecording();
    }
  });

  // Toggle Continuous Wake Word Mode
  wakeToggle.addEventListener('change', () => {
    if (wakeToggle.checked) {
      micHint.textContent = 'Continuous listening for "Sarah"...';
      startRecognition();
    } else {
      stopRecognition();
      micHint.textContent = 'Press microphone to speak';
    }
  });

  // Handle Accent Selection Change
  if (accentSelect) {
    accentSelect.addEventListener('change', () => {
      currentAccent = accentSelect.value;
      localStorage.setItem('sarah_accent', currentAccent);
      appendMessage('Sarah', `Acoustic model switched to ${accentSelect.options[accentSelect.selectedIndex].text}.`);
      if (recognition) {
        recognition.lang = currentAccent;
        if (isListening) {
          stopRecognition();
          setTimeout(() => startRecognition(), 300);
        }
      }
    });
  }

  // Handle Quick Chips click
  quickChips.forEach(chip => {
    chip.addEventListener('click', () => {
      const cmd = chip.getAttribute('data-cmd');
      if (cmd) {
        if (!isSarahAwake) {
          wakeSarah();
        } else {
          resetSilenceTimer();
        }
        transcriptEl.textContent = cmd;
        appendMessage('User', cmd);
        sendToFastAPI(cmd);
      }
    });
  });

  // Handle Text Input Form
  chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = textInput.value.trim();
    if (!text) return;

    if (!isSarahAwake) {
      wakeSarah();
    } else {
      resetSilenceTimer();
    }

    // Display transcript and save in conversation
    transcriptEl.textContent = text;
    appendMessage('User', text);
    textInput.value = '';

    // Send to backend
    sendToFastAPI(text);
  });

  // Check Backend Health
  async function checkHealth() {
    try {
      const res = await fetch('/health');
      if (res.ok) {
        const data = await res.json();
        connectionBadge.classList.add('connected');
        connectionText.textContent = `${data.service} (${data.status})`;
      } else {
        throw new Error(`HTTP ${res.status}`);
      }
    } catch (err) {
      connectionBadge.classList.remove('connected');
      connectionText.textContent = 'Backend Offline';
    }
  }

  checkHealth();
  setInterval(checkHealth, 8000);

  // Auto-start wake word detection if permission previously granted
  if (wakeToggle.checked) {
    startRecognition();
  }
});
