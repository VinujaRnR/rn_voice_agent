/**
 * Sarah Avatar — Photorealistic Human-Like Female Voice AI
 * Powered by high-resolution photographic rendering, real-time zero-delay mouth viseme tracking,
 * natural eye blinking, idle breathing micro-motion, and dynamic state-reactive aura.
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
        this.targetMouthOpen = 0.0;
        this.audioVolume = 0.0;
        
        // Natural human blinking state machine
        this.blinkProgress = 0.0;
        this.isBlinking = false;
        this.blinkStartTime = 0;
        this.lastBlinkTime = performance.now();
        this.nextBlinkInterval = 3200 + Math.random() * 3000;
        
        this.animFrameId = null;
        this.time = 0;

        // Offscreen cached lower lip/chin patch for ultra-smooth 60fps zero-delay rendering
        this.lowerLipCanvas = document.createElement('canvas');
        this.lowerLipCtx = this.lowerLipCanvas.getContext('2d');
        
        // Load photorealistic avatar portrait
        const domImg = document.getElementById('sarah-photo-source');
        if (domImg) {
            this.photo = domImg;
        } else {
            this.photo = new Image();
            this.photo.src = '/avatar/sarah_photo.jpg?v=20261105_real_v7';
        }

        this.isPhotoLoaded = false;
        const onPhotoReady = () => {
            this.isPhotoLoaded = true;
            this._prepareOffscreenAssets();
        };

        if (this.photo.complete && this.photo.naturalWidth > 0) {
            onPhotoReady();
        } else {
            this.photo.addEventListener('load', onPhotoReady);
            this.photo.addEventListener('error', (e) => {
                console.error('Failed to load Sarah photo:', e);
            });
            if (!this.photo.src || !this.photo.src.includes('sarah_photo.jpg')) {
                this.photo.src = '/avatar/sarah_photo.jpg?v=20261105_real_v7';
            }
        }
        
        this._bindEvents();
        this.start();
    }

    _prepareOffscreenAssets() {
        if (!this.isPhotoLoaded || !this.photo || !this.photo.naturalWidth) return;
        if (!this.lowerLipCanvas) {
            this.lowerLipCanvas = document.createElement('canvas');
            this.lowerLipCtx = this.lowerLipCanvas.getContext('2d');
        }
        // The lower lip & chin patch in source coordinates (1024x1024):
        // x: 390 to 635 (w: 245), y: 618 to 800 (h: 182)
        const sx = 390;
        const sy = 618;
        const sw = 245;
        const sh = 182;
        
        this.lowerLipCanvas.width = sw;
        this.lowerLipCanvas.height = sh;
        
        const ctx = this.lowerLipCtx;
        ctx.clearRect(0, 0, sw, sh);
        
        // Draw lower lip & chin crop
        ctx.drawImage(this.photo, sx, sy, sw, sh, 0, 0, sw, sh);
        
        // Create soft feather mask for seamless skin blending
        ctx.globalCompositeOperation = 'destination-in';
        const grad = ctx.createLinearGradient(0, 0, 0, sh);
        grad.addColorStop(0.0, 'rgba(0,0,0,1.0)');
        grad.addColorStop(0.65, 'rgba(0,0,0,1.0)');
        grad.addColorStop(0.92, 'rgba(0,0,0,0.5)');
        grad.addColorStop(1.0, 'rgba(0,0,0,0.0)');
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, sw, sh);
        
        ctx.globalCompositeOperation = 'source-over';
    }

    setAudioVolume(vol) {
        this.audioVolume = Math.max(0, Math.min(1.0, vol || 0));
        if (this.state === 'speaking') {
            // Rapid response for speech phonemes
            this.targetMouthOpen = Math.min(1.0, this.audioVolume * 1.8 + 0.1);
        } else {
            this.targetMouthOpen = 0.0;
        }
    }

    _bindEvents() {
        if (window.matchMedia) {
            const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
            if (mq.matches) this.reducedMotion = true;
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
            this.targetMouthOpen = 0.0;
            this.audioVolume = 0.0;
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

        const cx = width / 2;
        const cy = height / 2;
        const radius = Math.min(width, height) * 0.45;

        // 1. Dynamic State Glow & Aura
        ctx.save();
        let glowColor = 'rgba(59, 130, 246, 0.35)'; // Azure for idle
        let auraPulse = 0;

        if (this.state === 'listening') {
            glowColor = 'rgba(34, 197, 94, 0.45)'; // Emerald Green
            auraPulse = this.reducedMotion ? 4 : Math.sin(this.time * 6) * 8;
        } else if (this.state === 'thinking') {
            glowColor = 'rgba(168, 85, 247, 0.45)'; // Amethyst Violet
            auraPulse = this.reducedMotion ? 4 : Math.sin(this.time * 7) * 7;
        } else if (this.state === 'speaking') {
            glowColor = 'rgba(244, 63, 94, 0.50)'; // Warm Rose
            auraPulse = this.reducedMotion ? 5 : (Math.sin(this.time * 10) * 8 + this.audioVolume * 10);
        } else {
            auraPulse = this.reducedMotion ? 2 : Math.sin(this.time * 2) * 4;
        }

        const auraGradient = ctx.createRadialGradient(cx, cy, radius * 0.85, cx, cy, radius * 1.08 + auraPulse);
        auraGradient.addColorStop(0, glowColor);
        auraGradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
        ctx.fillStyle = auraGradient;
        ctx.beginPath();
        ctx.arc(cx, cy, radius * 1.08 + auraPulse, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();

        // If photo assets aren't decoded yet, allow underlying <img> to display naturally
        if (!this.isPhotoLoaded) {
            return;
        }

        // 2. Idle Breathing & Living Micro-motion
        let breatheY = 0;
        let breatheX = 0;
        if (!this.reducedMotion) {
            breatheY = Math.sin(this.time * 1.6) * 1.2;
            breatheX = Math.cos(this.time * 1.2) * 0.6;
        }

        // 3. Mouth Opening Viseme Calculation (Zero Delay with Voice)
        if (this.state === 'speaking') {
            // Syllable articulation modulation so lips naturally articulate phonemes like human speech
            const syllableMod = 0.55 + 0.45 * (Math.sin(this.time * 24) * Math.cos(this.time * 15));
            let openTarget = 0.0;
            if (this.audioVolume > 0.02) {
                openTarget = (this.audioVolume * 0.85 + 0.15) * (this.reducedMotion ? 0.7 : syllableMod);
            } else {
                openTarget = 0.35 + 0.25 * Math.sin(this.time * 18);
            }
            // Fast zero-delay interpolation
            this.mouthOpen += (openTarget - this.mouthOpen) * 0.42;
        } else {
            // Smoothly close mouth to calm smile
            this.mouthOpen += (0.0 - this.mouthOpen) * 0.35;
        }

        // 4. Natural Eye Blinking State Machine
        const now = performance.now();
        if (!this.reducedMotion && !this.isBlinking && (now - this.lastBlinkTime > this.nextBlinkInterval)) {
            this.isBlinking = true;
            this.blinkStartTime = now;
            this.nextBlinkInterval = 3200 + Math.random() * 3500;
        }

        if (this.isBlinking) {
            const elapsed = now - this.blinkStartTime;
            const blinkDuration = 160; // ms
            if (elapsed < blinkDuration) {
                // Symmetrical blink curve (0 -> 1 -> 0)
                this.blinkProgress = Math.sin((elapsed / blinkDuration) * Math.PI);
            } else {
                this.isBlinking = false;
                this.blinkProgress = 0.0;
                this.lastBlinkTime = now;
            }
        }

        // 5. Draw Sarah Photorealistic Face in Circular Portrait
        ctx.save();
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        ctx.clip();

        // Draw base 1024x1024 photo scaled into portrait
        // The face center is roughly at (512, 480) in the 1024x1024 image
        const drawSize = radius * 2.25;
        const drawX = cx - drawSize / 2 + breatheX;
        const drawY = cy - drawSize * 0.47 + breatheY;
        const scale = drawSize / 1024.0;
        const mapX = (sx) => drawX + sx * scale;
        const mapY = (sy) => drawY + sy * scale;

        ctx.drawImage(this.photo, drawX, drawY, drawSize, drawSize);

        // 6. Draw Mouth Opening (if mouthOpen > 0.02)
        if (this.mouthOpen > 0.02) {
            const openPixels = this.mouthOpen * 22; // max ~22px in 1024 space

            // Coordinates in source image space (1024x1024):
            // Upper lip seam: (425, 618) through (512, 619) to (620, 618)
            const pLeft = { x: mapX(425), y: mapY(618) };
            const pRight = { x: mapX(620), y: mapY(618) };
            const pUpperMid = { x: mapX(512), y: mapY(619) };
            const pLowerMid = { x: mapX(512), y: mapY(619 + openPixels) };

            // A. Dark Oral Cavity Interior
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(pLeft.x, pLeft.y);
            ctx.quadraticCurveTo(pUpperMid.x, pUpperMid.y, pRight.x, pRight.y);
            ctx.quadraticCurveTo(pLowerMid.x, pLowerMid.y, pLeft.x, pLeft.y);
            ctx.closePath();

            const cavityGrad = ctx.createLinearGradient(0, pUpperMid.y, 0, pLowerMid.y);
            cavityGrad.addColorStop(0.0, '#1c0809');
            cavityGrad.addColorStop(0.4, '#2d0f13');
            cavityGrad.addColorStop(1.0, '#3f1519');
            ctx.fillStyle = cavityGrad;
            ctx.fill();

            // B. Upper Teeth Row peeking from beneath upper lip
            const teethDrop = Math.min(openPixels * 0.42, 8.5) * scale;
            ctx.beginPath();
            ctx.moveTo(mapX(455), mapY(618));
            ctx.quadraticCurveTo(pUpperMid.x, mapY(619), mapX(575), mapY(618));
            ctx.quadraticCurveTo(pUpperMid.x, mapY(619) + teethDrop, mapX(455), mapY(618));
            ctx.closePath();

            const teethGrad = ctx.createLinearGradient(0, mapY(618), 0, mapY(618) + teethDrop);
            teethGrad.addColorStop(0.0, 'rgba(215, 208, 198, 0.95)');
            teethGrad.addColorStop(0.35, 'rgba(252, 250, 246, 0.98)');
            teethGrad.addColorStop(1.0, 'rgba(238, 230, 220, 0.95)');
            ctx.fillStyle = teethGrad;
            ctx.fill();

            // C. Subtle Tongue Arch at bottom
            if (openPixels > 7) {
                const tongueH = (openPixels * 0.35) * scale;
                ctx.beginPath();
                ctx.moveTo(mapX(460), pLowerMid.y);
                ctx.quadraticCurveTo(pLowerMid.x, pLowerMid.y - tongueH, mapX(570), pLowerMid.y);
                ctx.quadraticCurveTo(pLowerMid.x, pLowerMid.y, mapX(460), pLowerMid.y);
                ctx.fillStyle = 'rgba(180, 85, 96, 0.85)';
                ctx.fill();
            }
            ctx.restore();

            // D. Lower Lip & Jaw Movement (Photorealistic texture translation)
            const sx = 390;
            const sy = 618;
            const sw = 245;
            const sh = 182;
            const dropY = openPixels * 0.88 * scale;

            ctx.save();
            // Clip lower lip path so cheeks and mouth corners stay anchored
            ctx.beginPath();
            ctx.moveTo(pLeft.x, pLeft.y);
            ctx.quadraticCurveTo(pLowerMid.x, pLowerMid.y + 4 * scale, pRight.x, pRight.y);
            ctx.lineTo(mapX(635), mapY(800));
            ctx.lineTo(mapX(390), mapY(800));
            ctx.closePath();
            ctx.clip();

            // Render translated lower lip & chin patch
            ctx.drawImage(
                this.lowerLipCanvas,
                mapX(sx),
                mapY(sy) + dropY,
                sw * scale,
                sh * scale
            );
            ctx.restore();
        }

        // 7. Natural Human Eye Blinking (Smooth Eyelid Fold)
        if (this.blinkProgress > 0.01) {
            ctx.save();
            const b = this.blinkProgress;

            // Left Eye: center (349, 344), w: ~110px, h: ~38px in 1024 space
            const lx = mapX(349);
            const ly = mapY(344);
            const lW = 55 * scale;
            const lH = 20 * scale * b;

            // Right Eye: center (655, 334), w: ~110px, h: ~38px in 1024 space
            const rx = mapX(655);
            const ry = mapY(334);
            const rW = 55 * scale;
            const rH = 20 * scale * b;

            // Left Eyelid
            ctx.beginPath();
            ctx.ellipse(lx, ly - 3 * scale + lH * 0.5, lW, lH, 0.05, 0, Math.PI * 2);
            const leftLidGrad = ctx.createLinearGradient(0, ly - lH, 0, ly + lH);
            leftLidGrad.addColorStop(0.0, 'rgba(215, 175, 155, 0.95)');
            leftLidGrad.addColorStop(0.7, 'rgba(202, 160, 140, 0.98)');
            leftLidGrad.addColorStop(1.0, 'rgba(165, 120, 100, 0.98)');
            ctx.fillStyle = leftLidGrad;
            ctx.fill();

            // Left Eyelash line
            ctx.strokeStyle = 'rgba(52, 32, 24, 0.92)';
            ctx.lineWidth = 2.2 * scale;
            ctx.beginPath();
            ctx.ellipse(lx, ly + lH * 0.6, lW * 0.95, lH * 0.35, 0.05, 0, Math.PI);
            ctx.stroke();

            // Right Eyelid
            ctx.beginPath();
            ctx.ellipse(rx, ry - 3 * scale + rH * 0.5, rW, rH, -0.05, 0, Math.PI * 2);
            const rightLidGrad = ctx.createLinearGradient(0, ry - rH, 0, ry + rH);
            rightLidGrad.addColorStop(0.0, 'rgba(215, 175, 155, 0.95)');
            rightLidGrad.addColorStop(0.7, 'rgba(202, 160, 140, 0.98)');
            rightLidGrad.addColorStop(1.0, 'rgba(165, 120, 100, 0.98)');
            ctx.fillStyle = rightLidGrad;
            ctx.fill();

            // Right Eyelash line
            ctx.strokeStyle = 'rgba(52, 32, 24, 0.92)';
            ctx.lineWidth = 2.2 * scale;
            ctx.beginPath();
            ctx.ellipse(rx, ry + rH * 0.6, rW * 0.95, rH * 0.35, -0.05, 0, Math.PI);
            ctx.stroke();

            ctx.restore();
        }

        ctx.restore(); // End Circular Clip

        // 8. Elegant Outer Border & State Ring
        ctx.save();
        ctx.beginPath();
        ctx.arc(cx, cy, radius, 0, Math.PI * 2);
        let strokeColor = '#3b82f6';
        if (this.state === 'listening') strokeColor = '#22c55e';
        else if (this.state === 'thinking') strokeColor = '#a855f7';
        else if (this.state === 'speaking') strokeColor = '#f43f5e';

        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = 3.5;
        ctx.stroke();

        // Inner soft white rim
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.65)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(cx, cy, radius - 2, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();

        // 9. Status Pill Badge at Bottom
        ctx.save();
        const badgeY = height - 16;
        ctx.font = '600 12px Outfit, system-ui, -apple-system, sans-serif';
        ctx.textAlign = 'center';
        let stateText = 'Sarah is Ready';
        let stateBg = '#3b82f6';

        if (this.state === 'listening') {
            stateText = 'Sarah is Listening...';
            stateBg = '#16a34a';
        } else if (this.state === 'thinking') {
            stateText = 'Sarah is Thinking...';
            stateBg = '#9333ea';
        } else if (this.state === 'speaking') {
            stateText = 'Sarah is Speaking';
            stateBg = '#e11d48';
        }

        ctx.fillStyle = stateBg;
        ctx.beginPath();
        const textWidth = ctx.measureText(stateText).width + 22;
        ctx.roundRect(cx - textWidth / 2, badgeY - 14, textWidth, 22, 11);
        ctx.fill();

        ctx.fillStyle = '#ffffff';
        ctx.fillText(stateText, cx, badgeY + 2);
        ctx.restore();
    }
}

// Export for module or browser window
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { SarahAvatar };
} else {
    window.SarahAvatar = SarahAvatar;
}
