/**
 * Text-to-Speech handler using Web Speech Synthesis API
 * Phase 4 — Step 9: Web Speech TTS
 * File: frontend/tts.js
 */

function speak(text, onStart, onEnd, onError) {
  const synth = window.speechSynthesis;

  if (!synth) {
    console.error("Speech synthesis unsupported");
    if (onEnd) onEnd();
    return;
  }

  // Cancel any ongoing speech synthesis before speaking new utterance
  synth.cancel();

  if (!text || typeof text !== 'string' || !text.trim()) {
    if (onEnd) onEnd();
    return;
  }

  const utterance = new SpeechSynthesisUtterance(text.trim());

  // Configure speech attributes according to specification
  utterance.lang = "en-US";
  utterance.rate = 1.0;
  utterance.pitch = 1.0;
  utterance.volume = 1.0;

  // Use natural high-quality English voice if available in the browser
  const voices = synth.getVoices();
  const matchedVoice = voices.find(v => v.lang === 'en-US' && (v.name.includes('Natural') || v.name.includes('Google'))) ||
                       voices.find(v => v.lang.startsWith('en') && (v.name.includes('Natural') || v.name.includes('Google'))) ||
                       voices.find(v => v.lang === 'en-US') ||
                       voices.find(v => v.lang.startsWith('en'));
  if (matchedVoice) {
    utterance.voice = matchedVoice;
  }

  utterance.onstart = () => {
    if (onStart) onStart();
  };

  utterance.onend = () => {
    if (onEnd) onEnd();
  };

  utterance.onerror = (event) => {
    console.warn("Speech synthesis error or canceled:", event);
    if (onError) onError(event);
    if (onEnd) onEnd();
  };

  synth.speak(utterance);
}

function stopSpeaking() {
  const synth = window.speechSynthesis;
  if (synth && synth.speaking) {
    synth.cancel();
  }
}

function isSpeaking() {
  const synth = window.speechSynthesis;
  return synth ? synth.speaking : false;
}

// Window exports for global access
window.speak = speak;
window.stopSpeaking = stopSpeaking;
window.isSpeaking = isSpeaking;
window.TTS = {
  speak,
  stop: stopSpeaking,
  isSpeaking
};

// Object-oriented wrapper for compatibility
class TTSHandler {
  speak(text, onStart, onEnd, onError) {
    speak(text, onStart, onEnd, onError);
  }
  stop() {
    stopSpeaking();
  }
  isSpeaking() {
    return isSpeaking();
  }
}
window.TTSHandler = TTSHandler;
