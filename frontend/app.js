/**
 * Phase 4 — Text-to-speech and conversational loop
 * Step 9 — Implement Web Speech TTS & Conversational State Machine
 * File: frontend/app.js
 */

// Formal Assistant and Command Execution States
const AssistantState = {
  READY: 'ready',
  LISTENING: 'listening',       // Speech recognition active
  THINKING: 'thinking',         // Gemini processing request
  CLARIFYING: 'clarifying',     // Waiting for the user clarification
  SPEAKING: 'speaking',         // Playing browser Web Speech TTS
  // Command execution states
  WAITING_FOR_HUB: 'waiting_for_hub', // Command dispatched to RN Hub
  COMPLETED: 'completed',             // Command successfully executed
  FAILED: 'failed',                   // Command rejected or execution failed
  UNKNOWN: 'unknown'                  // Ambiguous or unverified status
};

class AssistantApp {
  constructor() {
    this.currentState = AssistantState.READY;
    let savedSession = null;
    try {
      savedSession = localStorage.getItem('sarah_active_session_id');
    } catch (e) {}
    this.sessionId = savedSession || ('session_' + Math.random().toString(36).substring(2, 9));
    try {
      localStorage.setItem('sarah_active_session_id', this.sessionId);
    } catch (e) {}
    this.isTTSSpeaking = false;
    this.resumeTimeout = null;

    // Cache DOM Elements
    this.statusPanel = document.querySelector('.status-panel');
    this.statusIndicator = document.getElementById('status-indicator');
    this.transcriptEl = document.getElementById('transcript');
    this.transcriptState = document.getElementById('transcript-state');
    this.conversationHistory = document.getElementById('conversation-history');
    this.micBtn = document.getElementById('mic-btn');
    this.micHint = document.getElementById('mic-hint');
    this.chatForm = document.getElementById('chat-form');
    this.textInput = document.getElementById('text-input');
    this.clearBtn = document.getElementById('clear-btn');
    this.wakeToggle = document.getElementById('wake-toggle');

    // Reminder Banner Elements
    this.reminderBanner = document.getElementById('reminder-alert-banner');
    this.reminderBannerText = document.getElementById('reminder-banner-text');
    this.reminderBannerClose = document.getElementById('reminder-banner-close');

    // Track active processed reminder alerts persisted in localStorage
    try {
      const stored = localStorage.getItem('sarah_processed_reminders');
      this.processedReminderIds = new Set(stored ? JSON.parse(stored) : []);
    } catch (e) {
      this.processedReminderIds = new Set();
    }

    this._bindEvents();
    this.startReminderPoller();
    this.loadPreviousConversations();
  }

  _bindEvents() {
    // Dismiss reminder banner
    if (this.reminderBannerClose) {
      this.reminderBannerClose.addEventListener('click', () => {
        if (this.reminderBanner) {
          this.reminderBanner.style.display = 'none';
        }
      });
    }
    // Clear conversation history button
    if (this.clearBtn) {
      this.clearBtn.addEventListener('click', async () => {
        try {
          await fetch('/api/chat/clear', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: this.sessionId, clear_all: true })
          });
        } catch (e) {
          console.warn('Note clearing history on server:', e);
        }
        try {
          localStorage.removeItem('sarah_active_session_id');
          this.sessionId = 'session_' + Math.random().toString(36).substring(2, 9);
          localStorage.setItem('sarah_active_session_id', this.sessionId);
        } catch (e) {}
        if (this.conversationHistory) {
          this.conversationHistory.innerHTML = '';
          this.appendMessage('Sarah', "I've cleared the entire conversation history.");
        }
        this.speakAssistantResponse("I've cleared the entire conversation history.", () => {
          this.returnToListeningOrReady();
        });
      });
    }

    // Text form fallback
    if (this.chatForm) {
      this.chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const text = this.textInput.value.trim();
        if (text) {
          this.textInput.value = '';
          this.handleUserInput(text);
        }
      });
    }

    // Quick chips
    const chips = document.querySelectorAll('.chip');
    chips.forEach(chip => {
      chip.addEventListener('click', () => {
        const cmd = chip.getAttribute('data-cmd');
        if (cmd) {
          this.handleUserInput(cmd);
        }
      });
    });

    // Populate device count badge in navigation bar
    fetch('/api/devices')
      .then(res => res.json())
      .then(data => {
        const badge = document.getElementById('nav-badge-count');
        if (badge && data.total_devices) {
          badge.textContent = `${data.total_devices} Devices`;
        }
      })
      .catch(() => {});
  }

  /**
   * Central state manager: updates visual status panel, orb styling, and badges
   */
  setState(state, customLabel = null) {
    this.currentState = state;

    if (this.statusPanel) {
      // Remove all prior state classes
      Object.values(AssistantState).forEach(s => {
        this.statusPanel.classList.remove(s);
      });
      this.statusPanel.classList.add(state);
    }

    // Update status text label
    if (this.statusIndicator) {
      let label = customLabel;
      if (!label) {
        switch (state) {
          case AssistantState.LISTENING:
            label = 'Listening...';
            break;
          case AssistantState.THINKING:
            label = 'Thinking...';
            break;
          case AssistantState.CLARIFYING:
            label = 'Clarifying (Waiting for user)';
            break;
          case AssistantState.SPEAKING:
            label = 'Speaking...';
            break;
          case AssistantState.WAITING_FOR_HUB:
            label = 'Dispatching to RN Hub...';
            break;
          case AssistantState.COMPLETED:
            label = 'Command Completed';
            break;
          case AssistantState.FAILED:
            label = 'Command Failed';
            break;
          case AssistantState.UNKNOWN:
            label = 'Execution Status Unknown';
            break;
          case AssistantState.READY:
          default:
            label = 'Ready to listen';
            break;
        }
      }
      this.statusIndicator.textContent = label;
    }

    // Update transcript header badge
    if (this.transcriptState) {
      this.transcriptState.textContent = state.replace(/_/g, ' ').toUpperCase();
      this.transcriptState.className = `transcript-badge ${state}`;
    }

    console.log(`[Assistant State]: ${state}`);
  }

  getState() {
    return this.currentState;
  }

  appendMessage(sender, text, isError = false, hash = null) {
    if (!this.conversationHistory) return;
    const card = document.createElement('div');
    card.className = `message-card ${sender.toLowerCase()} ${isError ? 'error-card' : ''}`;

    const tag = document.createElement('div');
    tag.className = 'sender-tag';
    tag.textContent = sender;

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.textContent = text;

    card.appendChild(tag);
    card.appendChild(bubble);

    if (hash) {
      const hashBadge = document.createElement('span');
      hashBadge.className = 'hash-badge';
      hashBadge.textContent = `#${hash.substring(0, 8)}`;
      hashBadge.title = `Cryptographic SHA-256 Hash: ${hash}\nStored permanently for future reference.`;
      card.appendChild(hashBadge);
    }

    this.conversationHistory.appendChild(card);
    this.conversationHistory.scrollTop = this.conversationHistory.scrollHeight;
    return card;
  }

  /**
   * Load stored previous conversations with their SHA-256 hashes for future reference
   */
  async loadPreviousConversations() {
    try {
      // 1. Try loading recent messages for this active session first
      let messagesToRender = [];
      let isCrossSession = false;

      try {
        const histRes = await fetch(`/api/chat/history?session_id=${encodeURIComponent(this.sessionId)}&limit=15`);
        if (histRes.ok) {
          const hData = await histRes.json();
          if (hData.messages && hData.messages.length > 0) {
            messagesToRender = hData.messages;
          }
        }
      } catch (he) {}

      // 2. If current session is empty, load recent cross-session references
      if (messagesToRender.length === 0) {
        const res = await fetch('/api/chat/references?limit=8');
        if (res.ok) {
          const data = await res.json();
          if (data.references && data.references.length > 0) {
            messagesToRender = [...data.references].reverse();
            isCrossSession = true;
          }
        }
      }

      if (messagesToRender.length > 0 && this.conversationHistory) {
        // Clear starter mock messages
        this.conversationHistory.innerHTML = '';
        // Show reference divider
        const divider = document.createElement('div');
        divider.style.cssText = 'text-align: center; margin: 8px 0; font-size: 0.75rem; color: #64748b; font-weight: 500;';
        divider.textContent = isCrossSession
          ? '— Previous Conversation References (Hashed) —'
          : '— Recent Conversation History —';
        this.conversationHistory.appendChild(divider);

        // Render in chronological order
        for (const item of messagesToRender) {
          const sender = item.role === 'user' ? 'User' : 'Sarah';
          this.appendMessage(sender, item.content, false, item.content_hash);
        }
      }
    } catch (e) {
      console.debug('Note loading past conversations:', e);
    }
  }

  /**
   * Proactive Voice Assistant Reminder Poller:
   * Polls backend every 2 seconds for scheduled reminders that have reached their due time.
   * Proactively announces through TTS and displays a prominent visual banner.
   */
  startReminderPoller() {
    if (this._reminderInterval) clearInterval(this._reminderInterval);

    this._reminderInterval = setInterval(async () => {
      try {
        const res = await fetch('/api/reminders/due');
        if (!res.ok) return;
        const data = await res.json();

        // Merge candidates from both triggered and recent_history
        const rawCandidates = [...(data.triggered || []), ...(data.recent_history || [])];
        const uniqueCandidates = [];
        const seenInBatch = new Set();
        for (const rem of rawCandidates) {
          if (!rem || !rem.id || seenInBatch.has(rem.id)) continue;
          seenInBatch.add(rem.id);
          uniqueCandidates.push(rem);
        }

        const now = Date.now();
        const dueReminders = uniqueCandidates.filter(rem => {
          // 1. Skip if already alerted by this client session
          if (this.processedReminderIds.has(rem.id)) return false;

          // 2. Skip if acknowledged on backend
          if (rem.status === 'acknowledged' || rem.acknowledged) return false;

          // 3. Freshness check: only alert if due/triggered within the last 120 seconds
          // Prevents replaying old reminders on page refresh
          let trigTime = null;
          if (typeof rem.triggered_timestamp === 'number') {
            trigTime = rem.triggered_timestamp * 1000;
          } else if (typeof rem.due_timestamp === 'number') {
            trigTime = rem.due_timestamp * 1000;
          } else if (rem.due_at_timestamp) {
            trigTime = Number(rem.due_at_timestamp) * 1000;
          } else if (rem.triggered_at) {
            const parsed = new Date(rem.triggered_at).getTime();
            if (!isNaN(parsed)) trigTime = parsed;
          } else if (rem.due_at_iso) {
            const parsed = new Date(rem.due_at_iso).getTime();
            if (!isNaN(parsed)) trigTime = parsed;
          }

          if (trigTime !== null) {
            const ageMs = now - trigTime;
            // Must have fired within the last 120 seconds, and not in the distant future
            if (ageMs > 120000 || ageMs < -15000) {
              return false;
            }
          }

          return true;
        });

        if (dueReminders.length > 0) {
          const newlyDeliveredIds = [];
          for (const rem of dueReminders) {
            this.processedReminderIds.add(rem.id);
            newlyDeliveredIds.push(rem.id);

            const alertText = `Reminder alert: It's time to ${rem.text}.`;

            // 1. Display notification banner
            if (this.reminderBanner && this.reminderBannerText) {
              this.reminderBannerText.textContent = `It's time to ${rem.text} (scheduled for ${rem.due_at})`;
              this.reminderBanner.style.display = 'flex';
            }

            // 2. Add message to conversation history
            this.appendMessage('Sarah', `🔔 ${alertText}`);

            // 3. Proactively speak reminder through TTS
            this.speakAssistantResponse(alertText, () => {
              this.returnToListeningOrReady();
            });
          }

          if (newlyDeliveredIds.length > 0) {
            try {
              // Maintain localStorage bounds (last 200 IDs)
              const idsArray = Array.from(this.processedReminderIds);
              if (idsArray.length > 200) {
                this.processedReminderIds = new Set(idsArray.slice(-100));
              }
              localStorage.setItem('sarah_processed_reminders', JSON.stringify(Array.from(this.processedReminderIds)));

              // Acknowledge to backend so it won't appear in subsequent polling
              fetch('/api/reminders/ack', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reminder_ids: newlyDeliveredIds })
              }).catch(() => {});
            } catch (e) {
              console.warn('Reminder acknowledge error:', e);
            }
          }
        }
      } catch (err) {
        // Poller error note
      }
    }, 2000);
  }

  /**
   * Main conversational loop: sends input to Gemini backend,
   * updates states (thinking, clarifying, speaking, command execution),
   * and triggers Web Speech TTS.
   */
  async handleUserInput(userText) {
    if (!userText || !userText.trim()) return;
    const cleanText = userText.trim();

    // 1. Display user query
    if (this.transcriptEl) {
      this.transcriptEl.textContent = cleanText;
    }
    this.appendMessage('User', cleanText);

    // 2. Set Thinking state
    this.setState(AssistantState.THINKING);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          text: cleanText,
          message: cleanText,
          session_id: this.sessionId
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error ${response.status}`);
      }

      const data = await response.json();
      await this.handleAssistantResponse(data);

      // Attach cryptographic SHA-256 hashes to recent message cards
      try {
        const histRes = await fetch(`/api/chat/history?session_id=${encodeURIComponent(this.sessionId)}&limit=4`);
        if (histRes.ok) {
          const histData = await histRes.json();
          if (histData.messages && histData.messages.length > 0) {
            const cards = this.conversationHistory.querySelectorAll('.message-card');
            const recentMsgs = histData.messages.slice(-cards.length);
            for (let i = 0; i < recentMsgs.length; i++) {
              const card = cards[cards.length - recentMsgs.length + i];
              const msg = recentMsgs[i];
              if (card && msg && msg.content_hash && !card.querySelector('.hash-badge')) {
                const b = document.createElement('span');
                b.className = 'hash-badge';
                b.textContent = `#${msg.content_hash.substring(0, 8)}`;
                b.title = `Cryptographic SHA-256 Hash: ${msg.content_hash}\nStored permanently for future reference.`;
                card.appendChild(b);
              }
            }
          }
        }
      } catch (he) {}
    } catch (err) {
      console.error('Chat error:', err);
      this.setState(AssistantState.FAILED, 'Connection Error');
      this.appendMessage('Sarah', `Error contacting assistant: ${err.message}`, true);
      setTimeout(() => this.setState(AssistantState.READY), 3000);
    }
  }

  /**
   * Handles Gemini structured response, command states, and TTS playback
   */
  async handleAssistantResponse(data) {
    if (!data) return;

    if (data.reasoning) {
      console.log('%c[Sarah Reasoning / Chain-of-Thought]:', 'color: #3b82f6; font-weight: bold;', data.reasoning);
    }

    let speechText = data.speech || '';
    let displayText = speechText;

    // Handle Device Command Execution states
    if (data.mode === 'device_command' && data.command) {
      const devId = data.command.device_id;
      const devName = devId === '98a316e6b658' ? 'Testing Farm Lights' : devId;
      const action = data.command.action;
      const params = Object.entries(data.command.parameters || {})
        .map(([k, v]) => `${k}=${v}`)
        .join(', ');

      displayText = speechText || `Sending ${action} command to ${devName}${params ? ' (' + params + ')' : ''}.`;
      speechText = speechText || `Turning ${data.command.parameters?.state || 'on'} the ${devName}.`;

      // Set command state: waiting_for_hub
      this.setState(AssistantState.WAITING_FOR_HUB);
      this.appendMessage('Sarah', displayText);

      // Speak initial dispatch confirmation through TTS
      this.speakAssistantResponse(speechText, () => {
        const cmdId = data.command.command_id;
        if (cmdId) {
          this.pollCommandOutcome(cmdId, devName);
        } else {
          this.setState(AssistantState.COMPLETED);
          setTimeout(() => {
            this.returnToListeningOrReady();
          }, 2200);
        }
      });
      return;
    }

    // Handle Clarifying state (waiting for user input)
    if (data.mode === 'clarify') {
      const missing = data.missing_fields && data.missing_fields.length > 0 
        ? ` (Need: ${data.missing_fields.join(', ')})` 
        : '';
      displayText = `${speechText || 'Which device would you like to control?'}${missing}`;
      speechText = speechText || 'Which device would you like to control?';

      this.appendMessage('Sarah', displayText);

      // Speak clarification and transition to clarifying state
      this.speakAssistantResponse(speechText, () => {
        this.setState(AssistantState.CLARIFYING);
        // Resume microphone recognition immediately so user can clarify
        this.resumeMicrophoneRecognition();
      });
      return;
    }

    // If response is clearing history, empty past messages from UI before showing Sarah's response
    if (displayText && displayText.toLowerCase().includes("cleared") && displayText.toLowerCase().includes("conversation")) {
      if (this.conversationHistory) {
        this.conversationHistory.innerHTML = '';
      }
      try {
        localStorage.removeItem('sarah_active_session_id');
        this.sessionId = 'session_' + Math.random().toString(36).substring(2, 9);
        localStorage.setItem('sarah_active_session_id', this.sessionId);
      } catch (e) {}
    }

    // Normal Answer mode (Milestone 1 Pass Condition)
    this.appendMessage('Sarah', displayText || 'I understood your request.');
    this.speakAssistantResponse(speechText || displayText, () => {
      this.returnToListeningOrReady();
    });
  }

  /**
   * Speaks text through Web Speech TTS, ensuring microphone recognition
   * is strictly paused while speaking so assistant does NOT transcribe its own voice.
   */
  speakAssistantResponse(text, onComplete) {
    if (!text || typeof window.speak !== 'function') {
      if (onComplete) onComplete();
      return;
    }

    // 1. Prevent microphone recognition from running while TTS is speaking
    this.pauseMicrophoneRecognition();
    this.isTTSSpeaking = true;
    this.setState(AssistantState.SPEAKING);

    // 2. Play speech through computer speakers via Web Speech TTS
    window.speak(
      text,
      // onStart callback
      () => {
        this.isTTSSpeaking = true;
        this.setState(AssistantState.SPEAKING);
      },
      // onEnd callback
      () => {
        this.isTTSSpeaking = false;
        // Small delay (250ms) to ensure residual audio playback doesn't trigger mic
        if (this.resumeTimeout) clearTimeout(this.resumeTimeout);
        this.resumeTimeout = setTimeout(() => {
          if (onComplete) onComplete();
        }, 250);
      },
      // onError callback
      (err) => {
        console.warn('TTS playback note:', err);
        this.isTTSSpeaking = false;
        if (onComplete) onComplete();
      }
    );
  }

  pauseMicrophoneRecognition() {
    if (window.SpeechController && typeof window.SpeechController.pauseRecognition === 'function') {
      window.SpeechController.pauseRecognition();
    }
  }

  resumeMicrophoneRecognition() {
    if (this.isTTSSpeaking) return; // Do not resume if still speaking
    if (window.SpeechController && typeof window.SpeechController.resumeRecognition === 'function') {
      window.SpeechController.resumeRecognition();
    }
  }

  async pollCommandOutcome(commandId, deviceName, retries = 5) {
    try {
      const res = await fetch(`/api/commands/${encodeURIComponent(commandId)}?wait=true&timeout=2.0`);
      if (res.ok) {
        const data = await res.json();
        if (data.state === 'completed') {
          this.setState(AssistantState.COMPLETED);
          const outcomeText = data.speech_outcome || `The ${deviceName} has been updated.`;
          this.appendMessage('Sarah', outcomeText);
          this.speakAssistantResponse(outcomeText, () => {
            setTimeout(() => this.returnToListeningOrReady(), 1500);
          });
          return;
        } else if (data.state === 'failed' || data.state === 'rejected') {
          this.setState(AssistantState.FAILED);
          const failText = data.speech_outcome || `Execution failed on ${deviceName}.`;
          this.appendMessage('Sarah', failText, true);
          this.speakAssistantResponse(failText, () => {
            setTimeout(() => this.returnToListeningOrReady(), 2000);
          });
          return;
        }
      }
    } catch (e) {
      console.warn('Poll command error:', e);
    }

    if (retries > 0) {
      setTimeout(() => this.pollCommandOutcome(commandId, deviceName, retries - 1), 1000);
    } else {
      this.setState(AssistantState.COMPLETED);
      setTimeout(() => this.returnToListeningOrReady(), 1500);
    }
  }

  returnToListeningOrReady() {
    if (this.wakeToggle && this.wakeToggle.checked) {
      this.setState(AssistantState.LISTENING);
      this.resumeMicrophoneRecognition();
    } else {
      this.setState(AssistantState.READY);
    }
  }
}

// Instantiate and expose globally
document.addEventListener('DOMContentLoaded', () => {
  window.appInstance = new AssistantApp();
  window.App = window.appInstance;
});
