/**
 * Zara Live Studio - Client Audio & WebSocket Manager
 * Implements:
 * - Short-lived JWT ticket authentication
 * - Raw PCM 16-bit 16kHz microphone streaming (Client -> WebSocket)
 * - Raw PCM 16-bit 24kHz audio playback (WebSocket -> AudioContext)
 * - Real-time dual input & output transcription streaming
 * - Instant barge-in / interruption buffer flushing
 * - Reactive canvas waveform visualizer
 */

class ZaraLiveStudio {
  constructor() {
    this.socket = null;
    this.isConnected = false;
    this.isSessionActive = false;

    // Audio Contexts
    this.inputContext = null;
    this.outputContext = null;
    this.microphoneStream = null;
    this.scriptProcessor = null;

    // Playback Scheduling (24 kHz PCM)
    this.scheduledTime = 0;
    this.activeAudioSources = [];

    // UI Elements
    this.btnToggle = document.getElementById('btn-toggle-session');
    this.btnText = document.getElementById('btn-text');
    this.btnIcon = document.getElementById('btn-icon');
    this.btnInterrupt = document.getElementById('btn-interrupt');
    this.statusPill = document.getElementById('status-pill');
    this.statusLabel = document.getElementById('status-label');
    this.statusHint = document.getElementById('status-hint');
    this.avatarOrb = document.getElementById('avatar-orb');
    this.orbIcon = document.getElementById('orb-icon');
    this.inputTranscript = document.getElementById('input-transcript');
    this.outputTranscript = document.getElementById('output-transcript');
    this.canvas = document.getElementById('visualizer-canvas');
    this.canvasCtx = this.canvas ? this.canvas.getContext('2d') : null;

    // Visualizer Metrics
    this.inputVolume = 0;
    this.outputVolume = 0;

    this._bindEvents();
    this._startVisualizerLoop();
  }

  _bindEvents() {
    if (this.btnToggle) {
      this.btnToggle.addEventListener('click', () => {
        if (this.isSessionActive) {
          this.stopSession();
        } else {
          this.startSession();
        }
      });
    }

    if (this.btnInterrupt) {
      this.btnInterrupt.addEventListener('click', () => {
        this.triggerBargeIn();
      });
    }
  }

  setStatus(state, label, hint = '') {
    if (!this.statusPill) return;
    this.statusPill.className = `status-pill ${state}`;
    if (this.statusLabel) this.statusLabel.textContent = label;
    if (this.statusHint && hint) this.statusHint.textContent = hint;

    if (this.avatarOrb) {
      this.avatarOrb.className = `avatar-orb ${state}`;
    }
    if (this.orbIcon) {
      if (state === 'speaking') this.orbIcon.textContent = '🔊';
      else if (state === 'listening') this.orbIcon.textContent = '🎙️';
      else if (state === 'error') this.orbIcon.textContent = '⚠️';
      else this.orbIcon.textContent = '✨';
    }
  }

  async acquireTicket() {
    const token = localStorage.getItem('sarah_access_token');
    const headers = { 'Content-Type': 'application/json' };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
    const res = await fetch('/api/v1/auth/ws-ticket', {
      method: 'POST',
      headers: headers
    });
    if (!res.ok) {
      throw new Error(`Failed to obtain WebSocket ticket (HTTP ${res.status})`);
    }
    const data = await res.json();
    return data.ticket;
  }

  async startSession() {
    try {
      this.setStatus('connecting', 'Authenticating with short-lived JWT...', 'Acquiring ticket from security middleware');
      this.btnToggle.disabled = true;

      // 1. Acquire Ticket
      const ticket = await this.acquireTicket();

      // 2. Open WebSocket
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${proto}//${window.location.host}/api/v1/zara-live/ws?ticket=${encodeURIComponent(ticket)}`;

      this.socket = new WebSocket(wsUrl);
      this.socket.binaryType = 'arraybuffer';

      this.socket.onopen = async () => {
        this.isConnected = true;
        this.isSessionActive = true;
        this.btnToggle.disabled = false;
        this.btnToggle.className = 'action-btn btn-stop';
        this.btnText.textContent = 'Stop Session';
        this.btnIcon.textContent = '⏹️';
        if (this.btnInterrupt) this.btnInterrupt.disabled = false;

        this.setStatus('connected', 'Connected to Gemini Live (Aoede)', 'Bidirectional raw audio channel established');
        await this.startMicrophoneCapture();
      };

      this.socket.onmessage = (event) => {
        if (typeof event.data === 'string') {
          // JSON control or transcript message
          try {
            const data = JSON.parse(event.data);
            this.handleServerMessage(data);
          } catch (e) {
            console.warn('JSON parse error from server:', e);
          }
        } else if (event.data instanceof ArrayBuffer) {
          // Binary Raw PCM 16-bit 24kHz audio from Aoede voice
          this.handleIncomingAudio(event.data);
        }
      };

      this.socket.onerror = (err) => {
        console.error('WebSocket Error:', err);
        this.setStatus('error', 'Connection Error', 'Check server connection or API credentials');
      };

      this.socket.onclose = (ev) => {
        console.log('WebSocket closed:', ev.code, ev.reason);
        this.cleanup();
        this.setStatus('idle', 'Session Ended', 'Press Start to begin a new live conversation');
      };

    } catch (err) {
      console.error('Start session error:', err);
      this.setStatus('error', 'Failed to Start', err.message);
      this.cleanup();
    }
  }

  async startMicrophoneCapture() {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this.inputContext = new AudioCtx({ sampleRate: 16000 });
      this.outputContext = new AudioCtx({ sampleRate: 24000 });
      this.scheduledTime = this.outputContext.currentTime;

      // Resume context if suspended by browser autoplay policy
      if (this.inputContext.state === 'suspended') await this.inputContext.resume();
      if (this.outputContext.state === 'suspended') await this.outputContext.resume();

      this.microphoneStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });

      const micSource = this.inputContext.createMediaStreamSource(this.microphoneStream);

      // ScriptProcessorNode converts Float32 to 16-bit PCM at 16,000 Hz
      const bufferSize = 2048;
      this.scriptProcessor = this.inputContext.createScriptProcessor(bufferSize, 1, 1);

      this.scriptProcessor.onaudioprocess = (e) => {
        if (!this.isConnected || !this.socket || this.socket.readyState !== WebSocket.OPEN) return;

        const inputData = e.inputBuffer.getChannelData(0);
        let sum = 0;

        // Convert Float32Array [-1.0, 1.0] to Int16Array [-32768, 32767]
        const pcm16 = new Int16Array(inputData.length);
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
          sum += s * s;
        }

        // Measure input volume for visualizer
        this.inputVolume = Math.sqrt(sum / inputData.length);

        // Stream raw binary PCM chunk over WebSocket
        this.socket.send(pcm16.buffer);
      };

      micSource.connect(this.scriptProcessor);
      this.scriptProcessor.connect(this.inputContext.destination);

      this.setStatus('listening', 'Zara is listening...', 'Speak naturally in any language');
    } catch (micErr) {
      console.error('Microphone access error:', micErr);
      this.setStatus('error', 'Microphone Access Denied', 'Please allow microphone permissions');
    }
  }

  handleIncomingAudio(arrayBuffer) {
    if (!this.outputContext) return;

    // Convert Int16 PCM 24kHz to Float32 for Web Audio playback
    const int16Array = new Int16Array(arrayBuffer);
    const float32Array = new Float32Array(int16Array.length);
    let sum = 0;

    for (let i = 0; i < int16Array.length; i++) {
      const val = int16Array[i] / 32768.0;
      float32Array[i] = val;
      sum += val * val;
    }

    this.outputVolume = Math.sqrt(sum / int16Array.length);

    const audioBuffer = this.outputContext.createBuffer(1, float32Array.length, 24000);
    audioBuffer.getChannelData(0).set(float32Array);

    const source = this.outputContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.outputContext.destination);

    // Schedule seamlessly without gaps
    const now = this.outputContext.currentTime;
    if (this.scheduledTime < now) {
      this.scheduledTime = now + 0.02; // Small 20ms buffer margin
    }

    source.start(this.scheduledTime);
    this.scheduledTime += audioBuffer.duration;

    this.activeAudioSources.push(source);
    source.onended = () => {
      const idx = this.activeAudioSources.indexOf(source);
      if (idx !== -1) this.activeAudioSources.splice(idx, 1);
      if (this.activeAudioSources.length === 0) {
        this.outputVolume = 0;
        if (this.isSessionActive) {
          this.setStatus('listening', 'Zara is listening...', 'Speak naturally in any language');
        }
      }
    };

    this.setStatus('speaking', 'Zara is speaking (Aoede)...', 'Real-time 24 kHz raw audio output');
  }

  handleServerMessage(data) {
    if (!data) return;

    if (data.type === 'input_transcription') {
      if (this.inputTranscript) {
        this.inputTranscript.className = 'transcript-body active';
        this.inputTranscript.textContent = data.text || '...';
      }
    } else if (data.type === 'output_transcription') {
      if (this.outputTranscript) {
        this.outputTranscript.className = 'transcript-body active';
        this.outputTranscript.textContent = data.text || '...';
      }
    } else if (data.type === 'interrupted') {
      this.flushAudioQueue();
      this.setStatus('listening', 'Barge-in: Zara interrupted', 'Listening to you...');
    } else if (data.type === 'turn_complete') {
      if (this.activeAudioSources.length === 0) {
        this.setStatus('listening', 'Zara is listening...', 'Speak anytime');
      }
    } else if (data.type === 'status') {
      console.log('Zara Live Handshake Status:', data);
    }
  }

  triggerBargeIn() {
    this.flushAudioQueue();
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: 'interrupt' }));
    }
    this.setStatus('listening', 'Interrupted', 'Listening for your instructions...');
  }

  flushAudioQueue() {
    for (const source of this.activeAudioSources) {
      try {
        source.stop();
        source.disconnect();
      } catch (e) {}
    }
    this.activeAudioSources = [];
    if (this.outputContext) {
      this.scheduledTime = this.outputContext.currentTime;
    }
    this.outputVolume = 0;
  }

  stopSession() {
    this.cleanup();
    this.setStatus('idle', 'Standby: Press Start to Connect', 'Direct duplex microphone & voice streaming over WebSocket');
  }

  cleanup() {
    this.isSessionActive = false;
    this.isConnected = false;

    this.flushAudioQueue();

    if (this.scriptProcessor) {
      this.scriptProcessor.disconnect();
      this.scriptProcessor = null;
    }

    if (this.microphoneStream) {
      this.microphoneStream.getTracks().forEach(t => t.stop());
      this.microphoneStream = null;
    }

    if (this.inputContext) {
      this.inputContext.close().catch(() => {});
      this.inputContext = null;
    }

    if (this.outputContext) {
      this.outputContext.close().catch(() => {});
      this.outputContext = null;
    }

    if (this.socket) {
      try { this.socket.close(); } catch (e) {}
      this.socket = null;
    }

    if (this.btnToggle) {
      this.btnToggle.disabled = false;
      this.btnToggle.className = 'action-btn btn-start';
      this.btnText.textContent = 'Start Live Voice Session';
      this.btnIcon.textContent = '🎙️';
    }

    if (this.btnInterrupt) {
      this.btnInterrupt.disabled = true;
    }
  }

  _startVisualizerLoop() {
    if (!this.canvasCtx || !this.canvas) return;

    const render = () => {
      const width = this.canvas.width;
      const height = this.canvas.height;
      const centerX = width / 2;
      const centerY = height / 2;

      this.canvasCtx.clearRect(0, 0, width, height);

      const activeVol = Math.max(this.inputVolume * 1.5, this.outputVolume * 2.0);
      const isSpeaking = this.outputVolume > 0.02;
      const isListening = this.inputVolume > 0.02;

      if (this.isSessionActive && (isSpeaking || isListening)) {
        const numPoints = 36;
        const baseRadius = 75;
        const maxAmplitude = 25 * activeVol;

        this.canvasCtx.beginPath();
        for (let i = 0; i <= numPoints; i++) {
          const angle = (i / numPoints) * Math.PI * 2;
          const wobble = Math.sin(angle * 6 + Date.now() * 0.008) * maxAmplitude;
          const r = baseRadius + wobble;
          const x = centerX + Math.cos(angle) * r;
          const y = centerY + Math.sin(angle) * r;

          if (i === 0) {
            this.canvasCtx.moveTo(x, y);
          } else {
            this.canvasCtx.lineTo(x, y);
          }
        }
        this.canvasCtx.closePath();

        const color = isSpeaking
          ? 'rgba(168, 85, 247, 0.65)' // Purple for Zara Aoede
          : 'rgba(0, 242, 254, 0.65)';  // Cyan for User 16kHz
        this.canvasCtx.strokeStyle = color;
        this.canvasCtx.lineWidth = 3;
        this.canvasCtx.shadowColor = color;
        this.canvasCtx.shadowBlur = 15;
        this.canvasCtx.stroke();
      }

      requestAnimationFrame(render);
    };

    render();
  }
}

// Auto-initialize studio on page load
document.addEventListener('DOMContentLoaded', () => {
  window.zaraStudio = new ZaraLiveStudio();
});

