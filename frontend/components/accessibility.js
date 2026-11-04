/**
 * Accessibility Controls Component for Elderly Care Interfaces
 * Supports Font Scaling (Normal / Large / Extra Large), High Contrast Mode,
 * and Reduced Motion toggle.
 */

class AccessibilityManager {
    constructor() {
        this.fontSizeLevels = ['font-normal', 'font-large', 'font-xlarge'];
        this.currentFontLevel = parseInt(localStorage.getItem('sarah_font_level') || '0', 10);
        this.highContrast = localStorage.getItem('sarah_high_contrast') === 'true';
        this.reducedMotion = localStorage.getItem('sarah_reduced_motion') === 'true';

        this.applySettings();
    }

    applySettings() {
        const root = document.documentElement;
        // Font sizing
        this.fontSizeLevels.forEach(cls => root.classList.remove(cls));
        root.classList.add(this.fontSizeLevels[this.currentFontLevel] || 'font-normal');

        // Contrast
        if (this.highContrast) {
            root.classList.add('high-contrast');
        } else {
            root.classList.remove('high-contrast');
        }

        // Reduced motion
        if (this.reducedMotion) {
            root.classList.add('reduced-motion');
        } else {
            root.classList.remove('reduced-motion');
        }
    }

    increaseFontSize() {
        if (this.currentFontLevel < this.fontSizeLevels.length - 1) {
            this.currentFontLevel++;
            localStorage.setItem('sarah_font_level', this.currentFontLevel.toString());
            this.applySettings();
        }
    }

    decreaseFontSize() {
        if (this.currentFontLevel > 0) {
            this.currentFontLevel--;
            localStorage.setItem('sarah_font_level', this.currentFontLevel.toString());
            this.applySettings();
        }
    }

    toggleContrast() {
        this.highContrast = !this.highContrast;
        localStorage.setItem('sarah_high_contrast', this.highContrast.toString());
        this.applySettings();
        return this.highContrast;
    }

    toggleReducedMotion() {
        this.reducedMotion = !this.reducedMotion;
        localStorage.setItem('sarah_reduced_motion', this.reducedMotion.toString());
        this.applySettings();
        return this.reducedMotion;
    }

    renderControls(containerElement) {
        if (!containerElement) return;
        containerElement.innerHTML = `
            <div class="accessibility-toolbar" role="region" aria-label="Accessibility Options">
                <span class="a11y-label">Accessibility:</span>
                <button type="button" class="a11y-btn" id="btn-font-dec" aria-label="Decrease text size">A-</button>
                <button type="button" class="a11y-btn" id="btn-font-inc" aria-label="Increase text size">A+</button>
                <button type="button" class="a11y-btn ${this.highContrast ? 'active' : ''}" id="btn-contrast" aria-label="Toggle high contrast">👁️ High Contrast</button>
                <button type="button" class="a11y-btn ${this.reducedMotion ? 'active' : ''}" id="btn-motion" aria-label="Toggle reduced motion">🛑 Calm Motion</button>
            </div>
        `;

        document.getElementById('btn-font-dec').addEventListener('click', () => this.decreaseFontSize());
        document.getElementById('btn-font-inc').addEventListener('click', () => this.increaseFontSize());
        document.getElementById('btn-contrast').addEventListener('click', (e) => {
            const active = this.toggleContrast();
            e.target.classList.toggle('active', active);
        });
        document.getElementById('btn-motion').addEventListener('click', (e) => {
            const active = this.toggleReducedMotion();
            e.target.classList.toggle('active', active);
            if (window.avatar) {
                window.avatar.setReducedMotion(active);
            }
        });
    }
}

const a11y = new AccessibilityManager();
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { a11y, AccessibilityManager };
} else {
    window.a11y = a11y;
}
