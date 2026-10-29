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
    this.sessionId = 'session_' + Math.random().toString(36).substring(2, 9);
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

    this._bindEvents();
  }

  _bindEvents() {
    // Clear conversation history button
    if (this.clearBtn) {
      this.clearBtn.addEventListener('click', () => {
        if (this.conversationHistory) {
          this.conversationHistory.innerHTML = '';
        }
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

  appendMessage(sender, text, isError = false) {
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
    this.conversationHistory.appendChild(card);
    this.conversationHistory.scrollTop = this.conversationHistory.scrollHeight;
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
