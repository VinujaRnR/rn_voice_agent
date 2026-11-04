/**
 * Sarah Avatar — Accessible, Human-Like 2D Canvas Assistant Avatar
 * Supports Idle, Listening, Thinking, and Speaking states with facial animation,
 * speech mouth oscillation, real-time captioning, and reduced-motion compliance.
 */

class SarahAvatar {
    constructor(canvasElement, options = {}) {
        this.canvas = canvasElement;
        this.ctx = canvasElement.getContext('2d');
        this.captionElement = options.captionElement || null;
        this.reducedMotion = options.reducedMotion || false;
        
        // State: 'idle' | 'listening' | 'thinking' | 'speaking'
        this.state = 'idle';
        this.captionText = '';
        this.mouthOpen = 0.0;
        this.blinkProgress = 0.0;
        this.isBlinking = false;
        this.lastBlinkTime = performance.now();
        this.nextBlinkInterval = 3000 + Math.random() * 4000;
        
        this.animFrameId = null;
        this.time = 0;
        
        this._bindEvents();
        this.start();
    }

    _bindEvents() {
        if (window.matchMedia) {
            const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
            if (mq.matches) {
                this.reducedMotion = true;
            }
            mq.addEventListener('change', (e) => {
                this.reducedMotion = e.matches;
            });
        }
    }

    setState(newState, caption = '') {
        this.state = newState;
        if (caption) {
            this.setCaption(caption);
        }
        if (newState !== 'speaking') {
            this.mouthOpen = 0.0;
        }
    }

    setCaption(text) {
        this.captionText = text || '';
        if (this.captionElement) {
            this.captionElement.textContent = this.captionText;
            this.captionElement.style.display = this.captionText ? 'block' : 'none';
        }
    }

    setReducedMotion(enabled) {
        this.reducedMotion = !!enabled;
    }

    start() {
        if (!this.animFrameId) {
            const loop = (timestamp) => {
                this.render(timestamp);
                this.animFrameId = requestAnimationFrame(loop);
            };
            this.animFrameId = requestAnimationFrame(loop);
        }
    }

    stop() {
        if (this.animFrameId) {
            cancelAnimationFrame(this.animFrameId);
            this.animFrameId = null;
        }
    }

    render(timestamp) {
        this.time = timestamp * 0.001;
        const width = this.canvas.width;
        const height = this.canvas.height;
        const ctx = this.ctx;

        ctx.clearRect(0, 0, width, height);

        // Responsive scaling
        const cx = width / 2;
        const cy = height / 2 + 10;
        const radius = Math.min(width, height) * 0.36;

        // 1. Aura / State Glow
        ctx.save();
        let glowColor = 'rgba(74, 144, 226, 0.25)'; // Idle soft blue
        let auraPulse = 0;

        if (this.state === 'listening') {
            glowColor = 'rgba(46, 204, 113, 0.45)'; // Listening green
            auraPulse = this.reducedMotion ? 5 : Math.sin(this.time * 6) * 10;
        } else if (this.state === 'thinking') {
            glowColor = 'rgba(155, 89, 182, 0.45)'; // Thinking violet
            auraPulse = this.reducedMotion ? 5 : Math.sin(this.time * 8) * 8;
        } else if (this.state === 'speaking') {
            glowColor = 'rgba(235, 104, 158, 0.45)'; // Speaking warm pink
            auraPulse = this.reducedMotion ? 6 : Math.sin(this.time * 12) * 12;
        } else {
            auraPulse = this.reducedMotion ? 2 : Math.sin(this.time * 2) * 4;
        }

        const auraGradient = ctx.createRadialGradient(cx, cy, radius * 0.7, cx, cy, radius * 1.35 + auraPulse);
        auraGradient.addColorStop(0, glowColor);
        auraGradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
        ctx.fillStyle = auraGradient;
        ctx.beginPath();
        ctx.arc(cx, cy, radius * 1.35 + auraPulse, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        // 2. Head & Hair Base
        ctx.save();
        // Hair back
        ctx.fillStyle = '#4a2c20'; // Warm brunette
        ctx.beginPath();
        ctx.ellipse(cx, cy - 10, radius * 1.15, radius * 1.25, 0, 0, Math.PI * 2);
        ctx.fill();

        // Face Skin Tone
        ctx.fillStyle = '#ffdfc4';
        ctx.beginPath();
        ctx.ellipse(cx, cy, radius * 0.88, radius * 1.05, 0, 0, Math.PI * 2);
        ctx.fill();

        // Hair Fringe / Front
        ctx.fillStyle = '#5c3826';
        ctx.beginPath();
        ctx.moveTo(cx - radius * 0.85, cy - radius * 0.3);
        ctx.quadraticCurveTo(cx - radius * 0.3, cy - radius * 0.9, cx, cy - radius * 0.6);
        ctx.quadraticCurveTo(cx + radius * 0.4, cy - radius * 0.9, cx + radius * 0.85, cy - radius * 0.3);
        ctx.quadraticCurveTo(cx, cy - radius * 1.25, cx - radius * 0.85, cy - radius * 0.3);
        ctx.fill();

        // 3. Cheeks / Blush
        ctx.fillStyle = 'rgba(255, 160, 160, 0.35)';
        ctx.beginPath();
        ctx.arc(cx - radius * 0.52, cy + radius * 0.15, radius * 0.18, 0, Math.PI * 2);
        ctx.arc(cx + radius * 0.52, cy + radius * 0.15, radius * 0.18, 0, Math.PI * 2);
        ctx.fill();

        // 4. Eyes & Blinking
        if (!this.reducedMotion && performance.now() - this.lastBlinkTime > this.nextBlinkInterval) {
            this.isBlinking = true;
            this.lastBlinkTime = performance.now();
            this.nextBlinkInterval = 3000 + Math.random() * 4000;
        }

        const eyeXOffset = radius * 0.36;
        const eyeY = cy - radius * 0.05;
        const eyeRadiusX = radius * 0.14;
        const eyeRadiusY = radius * 0.18;

        if (this.isBlinking) {
            // Closed eye arc
            ctx.strokeStyle = '#3d2314';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.arc(cx - eyeXOffset, eyeY, eyeRadiusX, 0, Math.PI);
            ctx.stroke();
            ctx.beginPath();
            ctx.arc(cx + eyeXOffset, eyeY, eyeRadiusX, 0, Math.PI);
            ctx.stroke();
            if (performance.now() - this.lastBlinkTime > 180) {
                this.isBlinking = false;
            }
        } else {
            // Open Eyes
            ctx.fillStyle = '#ffffff';
            ctx.beginPath();
            ctx.ellipse(cx - eyeXOffset, eyeY, eyeRadiusX, eyeRadiusY, 0, 0, Math.PI * 2);
            ctx.ellipse(cx + eyeXOffset, eyeY, eyeRadiusX, eyeRadiusY, 0, 0, Math.PI * 2);
            ctx.fill();

            // Irises (warm hazel-green)
            let lookOffset = 0;
            if (this.state === 'listening') {
                lookOffset = Math.sin(this.time * 3) * 3;
            }
            ctx.fillStyle = '#2c5e3b';
            ctx.beginPath();
            ctx.arc(cx - eyeXOffset + lookOffset, eyeY, eyeRadiusX * 0.75, 0, Math.PI * 2);
            ctx.arc(cx + eyeXOffset + lookOffset, eyeY, eyeRadiusX * 0.75, 0, Math.PI * 2);
            ctx.fill();

            // Pupils
            ctx.fillStyle = '#111111';
            ctx.beginPath();
            ctx.arc(cx - eyeXOffset + lookOffset, eyeY, eyeRadiusX * 0.45, 0, Math.PI * 2);
            ctx.arc(cx + eyeXOffset + lookOffset, eyeY, eyeRadiusX * 0.45, 0, Math.PI * 2);
            ctx.fill();

            // Eye Highlights
            ctx.fillStyle = '#ffffff';
            ctx.beginPath();
            ctx.arc(cx - eyeXOffset + lookOffset - 2, eyeY - 3, 2.5, 0, Math.PI * 2);
            ctx.arc(cx + eyeXOffset + lookOffset - 2, eyeY - 3, 2.5, 0, Math.PI * 2);
            ctx.fill();
        }

        // Eyebrows
        ctx.strokeStyle = '#4a2c20';
        ctx.lineWidth = 2.5;
        let browLift = 0;
        if (this.state === 'listening' || this.state === 'speaking') {
            browLift = -3;
        } else if (this.state === 'thinking') {
            browLift = 2;
        }
        ctx.beginPath();
        ctx.arc(cx - eyeXOffset, eyeY - eyeRadiusY - 5 + browLift, eyeRadiusX * 1.1, Math.PI * 1.15, Math.PI * 1.85);
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(cx + eyeXOffset, eyeY - eyeRadiusY - 5 + browLift, eyeRadiusX * 1.1, Math.PI * 1.15, Math.PI * 1.85);
        ctx.stroke();

        // 5. Friendly Nose
        ctx.strokeStyle = '#e0a98b';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(cx, cy + radius * 0.18, 5, 0, Math.PI * 0.9);
        ctx.stroke();

        // 6. Mouth & Lip Sync
        ctx.save();
        const mouthY = cy + radius * 0.48;

        if (this.state === 'speaking') {
            // Oscillating mouth for natural speaking
            if (!this.reducedMotion) {
                this.mouthOpen = 0.2 + (Math.sin(this.time * 16) * 0.5 + 0.5) * 0.7;
            } else {
                this.mouthOpen = 0.5;
            }
            const openHeight = radius * 0.18 * this.mouthOpen;

            // Mouth cavity
            ctx.fillStyle = '#8a2b3b';
            ctx.beginPath();
            ctx.ellipse(cx, mouthY, radius * 0.22, Math.max(3, openHeight), 0, 0, Math.PI * 2);
            ctx.fill();

            // Teeth / Smile
            ctx.fillStyle = '#ffffff';
            ctx.beginPath();
            ctx.rect(cx - radius * 0.12, mouthY - openHeight * 0.8, radius * 0.24, Math.max(2, openHeight * 0.4));
            ctx.fill();

            // Lips
            ctx.strokeStyle = '#d65a6f';
            ctx.lineWidth = 2.5;
            ctx.beginPath();
            ctx.ellipse(cx, mouthY, radius * 0.23, Math.max(3, openHeight + 1), 0, 0, Math.PI * 2);
            ctx.stroke();
        } else {
            // Calm gentle smile
            ctx.strokeStyle = '#c44b60';
            ctx.lineWidth = 2.8;
            ctx.beginPath();
            ctx.arc(cx, mouthY - 4, radius * 0.2, 0.25 * Math.PI, 0.75 * Math.PI);
            ctx.stroke();
        }
        ctx.restore();

        // 7. State Status Badge
        ctx.save();
        const badgeY = height - 20;
        ctx.font = '600 13px system-ui, -apple-system, sans-serif';
        ctx.textAlign = 'center';
        let stateText = 'Sarah is Ready';
        let stateBg = '#4a90e2';

        if (this.state === 'listening') {
            stateText = 'Sarah is Listening...';
            stateBg = '#27ae60';
        } else if (this.state === 'thinking') {
            stateText = 'Sarah is Thinking...';
            stateBg = '#8e44ad';
        } else if (this.state === 'speaking') {
            stateText = 'Sarah is Speaking';
            stateBg = '#e84393';
        }

        ctx.fillStyle = stateBg;
        ctx.beginPath();
        const textWidth = ctx.measureText(stateText).width + 24;
        ctx.roundRect(cx - textWidth / 2, badgeY - 14, textWidth, 24, 12);
        ctx.fill();

        ctx.fillStyle = '#ffffff';
        ctx.fillText(stateText, cx, badgeY + 3);
        ctx.restore();
    }
}

// Export for module or browser window
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { SarahAvatar };
} else {
    window.SarahAvatar = SarahAvatar;
}
