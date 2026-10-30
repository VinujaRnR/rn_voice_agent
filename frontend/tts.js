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

// Instant, crystal-clear static female audio recordings for core system prompts
const PRE_RENDERED_AUDIO = {
  "hello! i'm sarah. i'm listening, what can i do for you?": '/audio/sarah_greeting.mp3',
  "hello! i'm sarah. i'm listening, what can i do for you": '/audio/sarah_greeting.mp3',
  "hello! i am sarah. i am listening, what can i do for you?": '/audio/sarah_greeting.mp3',
  "5 minutes of silence reached. i am now in sleep mode. greet me with sarah to wake me up.": '/audio/sarah_sleep.mp3',
  "i'm in sleep mode. please say 'sarah' to wake me up.": '/audio/sarah_wake_prompt.mp3',
  "i'm in sleep mode. please say sarah to wake me up.": '/audio/sarah_wake_prompt.mp3'
};

let cachedVoices = [];
let currentAudio = null;

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
  utterance.voice = femaleVoice;
  utterance.pitch = 1.1;
  utterance.rate = 1.0;
  utterance.volume = 1.0;

  utterance.onstart = () => {
    if (onStart) onStart();
  };

  utterance.onend = () => {
    if (onEnd) onEnd();
  };

  utterance.onerror = (e) => {
    console.warn("[TTS] Web Speech fallback error:", e);
    if (onError) onError(e);
    if (onEnd) onEnd();
  };

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

  // Tier 1: Instant Pre-Rendered High-Definition Female Audio
  const staticAudioUrl = PRE_RENDERED_AUDIO[normalizedKey];
  if (staticAudioUrl) {
    try {
      const audio = new Audio(staticAudioUrl);
      currentAudio = audio;

      audio.onplay = () => {
        if (onStart) onStart();
      };

      audio.onended = () => {
        currentAudio = null;
        if (onEnd) onEnd();
      };

      audio.onerror = (err) => {
        console.warn("[TTS] Static audio error, falling back:", err);
        currentAudio = null;
        speakWebSpeechFallback(cleanText, onStart, onEnd, onError);
      };

      const playPromise = audio.play();
      if (playPromise !== undefined) {
        playPromise.catch(err => {
          console.warn("[TTS] Static audio autoplay restricted, falling back:", err);
          currentAudio = null;
          speakWebSpeechFallback(cleanText, onStart, onEnd, onError);
        });
      }
      return;
    } catch (err) {
      console.error("[TTS] Static audio exception:", err);
    }
  }

  // Tier 2: Dynamic Neural Female TTS (/api/tts)
  const url = `/api/tts?text=${encodeURIComponent(cleanText)}&voice=jenny`;

  try {
    const audio = new Audio(url);
    currentAudio = audio;

    audio.onplay = () => {
      if (onStart) onStart();
    };

    audio.onended = () => {
      currentAudio = null;
      if (onEnd) onEnd();
    };

    audio.onerror = (err) => {
      console.warn("[TTS] Neural TTS audio error, falling back to Web Speech:", err);
      currentAudio = null;
      speakWebSpeechFallback(cleanText, onStart, onEnd, onError);
    };

    const playPromise = audio.play();
    if (playPromise !== undefined) {
      playPromise.catch(err => {
        console.warn("[TTS] Audio playback restricted, falling back:", err);
        currentAudio = null;
        speakWebSpeechFallback(cleanText, onStart, onEnd, onError);
      });
    }
  } catch (err) {
    console.error("[TTS] Audio creation exception:", err);
    speakWebSpeechFallback(cleanText, onStart, onEnd, onError);
  }
}

function stopSpeaking() {
  if (currentAudio) {
    try {
      currentAudio.pause();
      currentAudio.currentTime = 0;
    } catch (e) {}
    currentAudio = null;
  }
  const synth = window.speechSynthesis;
  if (synth && synth.speaking) {
    synth.cancel();
  }
}

function isSpeaking() {
  const audioPlaying = Boolean(currentAudio && !currentAudio.paused && !currentAudio.ended);
  const synthSpeaking = Boolean(window.speechSynthesis && window.speechSynthesis.speaking);
  return audioPlaying || synthSpeaking;
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
