/**
 * Text-to-Speech handler: Strictly Enforced Female Voice Playback
 * Enforces exclusively female voice playback for Sarah assistant persona.
 * Priority 1: Instant Pre-Rendered High-Fidelity Static Audio (/audio/*.mp3)
 * Priority 2: High-Definition Neural Female TTS (/api/tts)
 * Priority 3: Strictly Verified Female-Only Browser Web Speech
 * Absolute Rule: Under NO circumstances will an unverified or male voice play.
 * File: frontend/tts.js
 */

// Positive list of verified female voice identifiers
const FEMALE_VOICE_NAMES = [
  'jenny', 'aria', 'samantha', 'victoria', 'karen', 'serena', 'ava',
  'allison', 'susan', 'zoe', 'natasha', 'sonia', 'libby', 'mia', 'clara',
  'stephanie', 'linda', 'sarah', 'zira', 'female', 'woman', 'girl',
  'neerja', 'heera', 'hazel', 'catherine', 'fiona', 'tessa', 'moira',
  'google uk english female'
];

// Blocklist of male voices and ambiguous default systems
const MALE_VOICE_INDICATORS = [
  'google us english', 'google us', 'guy', 'david', 'mark', 'ryan',
  'george', 'brian', 'alex', 'daniel', 'fred', 'tom', 'oliver', 'lee',
  'rishi', 'aaron', 'steffan', 'christopher', 'eric', 'william', 'richard',
  'sean', 'paul', 'frank', 'sam', 'mike', 'arthur', 'roger', 'thomas',
  'andrew', 'wayne', 'tony', 'james', 'charles', 'john', 'robert',
  'michael', 'edward', 'henry', 'peter', 'walter', 'harold', 'victor',
  'ralph', 'albert', 'jack', 'joseph', 'donald', 'kenneth', 'kevin',
  'jason', 'matthew', 'gary', 'timothy', 'larry', 'jeffrey', 'scott',
  'stephen', 'raymond', 'gregory', 'joshua', 'jerry', 'dennis', 'patrick',
  'douglas', 'carl', 'joe', 'juan', 'jonathan', 'justin', 'terry',
  'gerald', 'keith', 'samuel', 'willie', 'lawrence', 'nicholas', 'roy',
  'benjamin', 'bruce', 'brandon', 'adam', 'harry', 'billy', 'steve',
  'louis', 'jeremy', 'randy', 'howard', 'eugene', 'carlos', 'russell',
  'bobby', 'martin', 'ernest', 'phillip', 'todd', 'jesse', 'craig',
  'alan', 'shawn', 'clarence', 'philip', 'chris', 'johnny', 'earl',
  'jimmy', 'antonio', 'prabhat', 'ravi', 'male', 'man', 'boy', 'espeak',
  'speech-dispatcher', 'system', 'default', 'desktop'
];

// Instant, crystal-clear static female audio recordings for core system prompts and device commands
const PRE_RENDERED_AUDIO = {
  // Core System & Wake Prompts
  "hello! i'm sarah. i'm listening, what can i do for you?": '/audio/sarah_greeting.mp3',
  "hello! i'm sarah. i'm listening, what can i do for you": '/audio/sarah_greeting.mp3',
  "hello! i am sarah. i am listening, what can i do for you?": '/audio/sarah_greeting.mp3',
  "5 minutes of silence reached. i am now in sleep mode. greet me with sarah to wake me up.": '/audio/sarah_sleep.mp3',
  "i'm in sleep mode. please say 'sarah' to wake me up.": '/audio/sarah_wake_prompt.mp3',
  "i'm in sleep mode. please say sarah to wake me up.": '/audio/sarah_wake_prompt.mp3',

  // Device On/Off Confirmations (Instant Local MP3s)
  "okay, turning on the room lights.": '/audio/sarah_turn_on_room_lights.mp3',
  "okay, turning on the room lights": '/audio/sarah_turn_on_room_lights.mp3',
  "okay, turning off the room lights.": '/audio/sarah_turn_off_room_lights.mp3',
  "okay, turning off the room lights": '/audio/sarah_turn_off_room_lights.mp3',

  "okay, turning on the kitchen lights.": '/audio/sarah_turn_on_kitchen_lights.mp3',
  "okay, turning on the kitchen lights": '/audio/sarah_turn_on_kitchen_lights.mp3',
  "okay, turning off the kitchen lights.": '/audio/sarah_turn_off_kitchen_lights.mp3',
  "okay, turning off the kitchen lights": '/audio/sarah_turn_off_kitchen_lights.mp3',

  "okay, turning on the desk lamp.": '/audio/sarah_turn_on_desk_lamp.mp3',
  "okay, turning on the desk lamp": '/audio/sarah_turn_on_desk_lamp.mp3',
  "okay, turning off the desk lamp.": '/audio/sarah_turn_off_desk_lamp.mp3',
  "okay, turning off the desk lamp": '/audio/sarah_turn_off_desk_lamp.mp3',

  "okay, turning on the lights.": '/audio/sarah_turn_on_lights.mp3',
  "okay, turning on the lights": '/audio/sarah_turn_on_lights.mp3',
  "okay, turning off the lights.": '/audio/sarah_turn_off_lights.mp3',
  "okay, turning off the lights": '/audio/sarah_turn_off_lights.mp3',

  "okay, turning on light 1.": '/audio/sarah_turn_on_light_1.mp3',
  "okay, turning on light 1": '/audio/sarah_turn_on_light_1.mp3',
  "okay, turning off light 1.": '/audio/sarah_turn_off_light_1.mp3',
  "okay, turning off light 1": '/audio/sarah_turn_off_light_1.mp3',

  "okay, turning on the farm lights.": '/audio/sarah_turn_on_farm_lights.mp3',
  "okay, turning on the farm lights": '/audio/sarah_turn_on_farm_lights.mp3',
  "okay, turning off the farm lights.": '/audio/sarah_turn_off_farm_lights.mp3',
  "okay, turning off the farm lights": '/audio/sarah_turn_off_farm_lights.mp3',

  "okay, turning on the testing farm lights.": '/audio/sarah_turn_on_testing_farm_lights.mp3',
  "okay, turning on the testing farm lights": '/audio/sarah_turn_on_testing_farm_lights.mp3',
  "okay, turning off the testing farm lights.": '/audio/sarah_turn_off_testing_farm_lights.mp3',
  "okay, turning off the testing farm lights": '/audio/sarah_turn_off_testing_farm_lights.mp3',

  "sending the command to rn hub.": '/audio/sarah_sending_to_rn_hub.mp3',
  "sending the command to rn hub": '/audio/sarah_sending_to_rn_hub.mp3',

  "okay.": '/audio/sarah_okay.mp3',
  "okay": '/audio/sarah_okay.mp3'
};

let cachedVoices = [];
let currentAudio = null;
let currentWatchdog = null;
let isSpeechActive = false;

function clearWatchdog() {
  if (currentWatchdog) {
    clearTimeout(currentWatchdog);
    currentWatchdog = null;
  }
}

function loadVoices() {
  if (typeof window !== 'undefined' && window.speechSynthesis) {
    const list = window.speechSynthesis.getVoices();
    if (list && list.length > 0) {
      cachedVoices = list;
    }
  }
}

if (typeof window !== 'undefined' && window.speechSynthesis) {
  loadVoices();
  window.speechSynthesis.onvoiceschanged = () => {
    loadVoices();
  };
}

function isMaleVoice(voice) {
  if (!voice) return true;
  const lower = ((voice.name || '') + ' ' + (voice.voiceURI || '')).toLowerCase();
  return MALE_VOICE_INDICATORS.some(m => {
    const regex = new RegExp(`(^|[^a-z])${m}([^a-z]|$)`, 'i');
    return regex.test(lower);
  });
}

function isFemaleVoice(voice) {
  if (!voice) return false;
  if (isMaleVoice(voice)) return false;
  const lower = ((voice.name || '') + ' ' + (voice.voiceURI || '')).toLowerCase();
  return FEMALE_VOICE_NAMES.some(f => lower.includes(f));
}

function getBestFemaleVoice() {
  const synth = typeof window !== 'undefined' ? window.speechSynthesis : null;
  if (!synth) return null;

  const voices = synth.getVoices().length > 0 ? synth.getVoices() : cachedVoices;
  if (!voices || voices.length === 0) return null;

  // 1. Natural / Online Female English voices
  const naturalFemale = voices.find(v => (
    v.lang && v.lang.startsWith('en') &&
    isFemaleVoice(v) &&
    (v.name.includes('Natural') || v.name.includes('Online') || v.name.includes('Neural'))
  ));
  if (naturalFemale) return naturalFemale;

  // 2. High-priority named female voices
  const preferredFemaleOrder = [
    'jenny', 'aria', 'samantha', 'victoria', 'zira', 'karen', 'natasha',
    'sonia', 'libby', 'ava', 'allison', 'serena', 'clara', 'google uk english female'
  ];
  for (const name of preferredFemaleOrder) {
    const matched = voices.find(v => (
      v.lang && v.lang.startsWith('en') &&
      v.name.toLowerCase().includes(name) &&
      isFemaleVoice(v)
    ));
    if (matched) return matched;
  }

  // 3. Any English voice verified as female
  const anyEnFemale = voices.find(v => v.lang && v.lang.startsWith('en') && isFemaleVoice(v));
  if (anyEnFemale) return anyEnFemale;

  // 4. Any voice verified as female in any language
  const anyFemale = voices.find(v => isFemaleVoice(v));
  if (anyFemale) return anyFemale;

  return null;
}

/**
 * Strict fallback to browser Web Speech API.
 * If NO verified female voice is available, it REFUSES to play to prevent male voice.
 */
function speakWebSpeechFallback(text, onStart, onEnd, onError) {
  const synth = window.speechSynthesis;
  if (!synth) {
    if (onEnd) onEnd();
    return;
  }

  const femaleVoice = getBestFemaleVoice();
  if (!femaleVoice) {
    console.warn("[TTS] No verified female voice installed in browser speech synthesis. Suppressing fallback to prevent male voice.");
    if (onEnd) onEnd();
    return;
  }

  const utterance = new SpeechSynthesisUtterance(text.trim());
  // Retain utterance on window to prevent Chromium garbage-collection dropping onend event
  window._currentUtterance = utterance;
  utterance.voice = femaleVoice;
  utterance.pitch = 1.1;
  utterance.rate = 1.0;
  utterance.volume = 1.0;

  utterance.onstart = () => {
    isSpeechActive = true;
    if (onStart) onStart();
  };

  utterance.onend = () => {
    window._currentUtterance = null;
    isSpeechActive = false;
    clearWatchdog();
    if (onEnd) onEnd();
  };

  utterance.onerror = (e) => {
    console.warn("[TTS] Web Speech fallback error:", e);
    window._currentUtterance = null;
    isSpeechActive = false;
    clearWatchdog();
    if (onError) onError(e);
    if (onEnd) onEnd();
  };

  // 4-second safety watchdog for fallback speech
  clearWatchdog();
  const words = text.trim().split(/\s+/).length;
  currentWatchdog = setTimeout(() => {
    if (window._currentUtterance === utterance) {
      console.warn("[TTS] Web Speech fallback watchdog triggered, forcing release");
      window._currentUtterance = null;
      isSpeechActive = false;
      try { synth.cancel(); } catch (e) {}
      if (onEnd) onEnd();
    }
  }, Math.max(3000, words * 450 + 1500));

  synth.speak(utterance);
}

/**
 * Speaks text strictly using Sarah's female voice.
 */
function speak(text, onStart, onEnd, onError) {
  stopSpeaking();

  if (!text || typeof text !== 'string' || !text.trim()) {
    if (onEnd) onEnd();
    return;
  }

  const cleanText = text.trim();
  const normalizedKey = cleanText.toLowerCase().replace(/['"’]/g, "'");
  const strippedKey = normalizedKey.replace(/[.!?]+$/, '').trim();

  isSpeechActive = true;

  let finished = false;
  const safeEnd = () => {
    if (finished) return;
    finished = true;
    clearWatchdog();
    isSpeechActive = false;
    currentAudio = null;
    window._currentUtterance = null;
    if (onEnd) onEnd();
  };

  const safeStart = () => {
    isSpeechActive = true;
    if (onStart) onStart();
  };

  // Tier 1: Instant Pre-Rendered High-Definition Female Audio
  let staticAudioUrl = PRE_RENDERED_AUDIO[normalizedKey] || PRE_RENDERED_AUDIO[strippedKey];
  if (!staticAudioUrl) {
    const match = Object.keys(PRE_RENDERED_AUDIO).find(k => k === strippedKey || k.replace(/[.!?]+$/, '') === strippedKey);
    if (match) staticAudioUrl = PRE_RENDERED_AUDIO[match];
  }

  if (staticAudioUrl) {
    try {
      const audio = new Audio(staticAudioUrl);
      currentAudio = audio;

      // Watchdog timer: on/off and core confirmation static audios are <= 2s
      currentWatchdog = setTimeout(() => {
        console.warn("[TTS] Pre-rendered audio watchdog reached, releasing lock");
        safeEnd();
      }, 2500);

      audio.onplay = () => {
        safeStart();
      };

      audio.onended = () => {
        safeEnd();
      };

      audio.onerror = (err) => {
        console.warn("[TTS] Static audio error, falling back:", err);
        clearWatchdog();
        currentAudio = null;
        speakWebSpeechFallback(cleanText, onStart, onEnd, onError);
      };

      const playPromise = audio.play();
      if (playPromise !== undefined) {
        playPromise.catch(err => {
          console.warn("[TTS] Static audio autoplay restricted, falling back:", err);
          clearWatchdog();
          currentAudio = null;
          speakWebSpeechFallback(cleanText, onStart, onEnd, onError);
        });
      }
      return;
    } catch (err) {
      console.error("[TTS] Static audio exception:", err);
      clearWatchdog();
      currentAudio = null;
    }
  }

  // Tier 2: Dynamic Neural Female TTS (/api/tts)
  const url = `/api/tts?text=${encodeURIComponent(cleanText)}&voice=jenny`;

  try {
    const audio = new Audio(url);
    currentAudio = audio;

    const words = cleanText.split(/\s+/).length;
    const maxWaitMs = Math.max(3500, words * 450 + 2000);
    currentWatchdog = setTimeout(() => {
      console.warn(`[TTS] Neural TTS watchdog reached after ${maxWaitMs}ms, releasing lock`);
      safeEnd();
    }, maxWaitMs);

    audio.onplay = () => {
      safeStart();
    };

    audio.onended = () => {
      safeEnd();
    };

    audio.onerror = (err) => {
      console.warn("[TTS] Neural TTS audio error, falling back to Web Speech:", err);
      clearWatchdog();
      currentAudio = null;
      speakWebSpeechFallback(cleanText, onStart, onEnd, onError);
    };

    const playPromise = audio.play();
    if (playPromise !== undefined) {
      playPromise.catch(err => {
        console.warn("[TTS] Audio playback restricted, falling back:", err);
        clearWatchdog();
        currentAudio = null;
        speakWebSpeechFallback(cleanText, onStart, onEnd, onError);
      });
    }
  } catch (err) {
    console.error("[TTS] Audio creation exception:", err);
    clearWatchdog();
    speakWebSpeechFallback(cleanText, onStart, onEnd, onError);
  }
}

function stopSpeaking() {
  clearWatchdog();
  isSpeechActive = false;
  if (currentAudio) {
    try {
      currentAudio.pause();
      currentAudio.currentTime = 0;
    } catch (e) {}
    currentAudio = null;
  }
  const synth = window.speechSynthesis;
  if (synth) {
    try {
      synth.cancel();
    } catch (e) {}
  }
  window._currentUtterance = null;
}

function isSpeaking() {
  const audioPlaying = Boolean(currentAudio && !currentAudio.paused && !currentAudio.ended);
  const synthSpeaking = Boolean(window.speechSynthesis && window.speechSynthesis.speaking && window._currentUtterance);
  return Boolean(isSpeechActive || audioPlaying || synthSpeaking);
}

// Window exports
window.speak = speak;
window.stopSpeaking = stopSpeaking;
window.isSpeaking = isSpeaking;
window.TTS = {
  speak,
  stop: stopSpeaking,
  isSpeaking,
  getFemaleVoice: getBestFemaleVoice,
  isFemaleVoice,
  isMaleVoice
};

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
