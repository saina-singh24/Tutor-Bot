(() => {
    const storageKeys = { theme: 'tutor-lamp-theme', accent: 'tutor-lamp-accent' };
    const defaultAccent = '#9b7cff';
    const root = document.documentElement;

    function hexToRgb(hex) {
        const value = hex.replace('#', '');
        return {
            r: parseInt(value.slice(0, 2), 16),
            g: parseInt(value.slice(2, 4), 16),
            b: parseInt(value.slice(4, 6), 16)
        };
    }

    function getContrastColor(hex) {
        const { r, g, b } = hexToRgb(hex);
        const luminance = [r, g, b].map(channel => {
            const normalized = channel / 255;
            return normalized <= 0.03928 ? normalized / 12.92 : Math.pow((normalized + 0.055) / 1.055, 2.4);
        });
        const relativeLuminance = 0.2126 * luminance[0] + 0.7152 * luminance[1] + 0.0722 * luminance[2];
        const whiteContrast = 1.05 / (relativeLuminance + 0.05);
        const darkContrast = (relativeLuminance + 0.05) / 0.05;
        return darkContrast >= whiteContrast ? '#101813' : '#ffffff';
    }

    function setAccent(accent) {
        if (!/^#[0-9a-f]{6}$/i.test(accent)) return;
        root.style.setProperty('--user-accent', accent);
        root.style.setProperty('--user-accent-text', getContrastColor(accent));
        root.style.setProperty('--user-accent-soft', `${accent}26`);
        root.style.setProperty('--user-accent-glow', `${accent}59`);
        localStorage.setItem(storageKeys.accent, accent);
        window.dispatchEvent(new CustomEvent('tutorLampThemeChange'));
        const picker = document.getElementById('accentPicker');
        if (picker) picker.value = accent;
        const swatch = document.getElementById('accentSwatch');
        if (swatch) swatch.style.backgroundColor = accent;
    }

    function setTheme(theme) {
        const nextTheme = theme === 'light' ? 'light' : 'dark';
        root.dataset.theme = nextTheme;
        root.style.colorScheme = nextTheme;
        localStorage.setItem(storageKeys.theme, nextTheme);
        const toggle = document.getElementById('themeToggle');
        if (toggle) {
            toggle.setAttribute('aria-pressed', String(nextTheme === 'dark'));
            toggle.querySelector('.theme-icon').textContent = nextTheme === 'dark' ? '☀' : '☾';
            toggle.querySelector('.theme-label').textContent = nextTheme === 'dark' ? 'Light mode' : 'Dark mode';
        }
    }

    function addThemeStyles() {
        const style = document.createElement('style');
        style.textContent = `
            :root { --user-accent: ${defaultAccent}; --user-accent-text: #101813; --user-accent-soft: #c8f06b26; }
            [data-theme="light"] body { background: #f5f7f5 !important; color: #17231d !important; }
            [data-theme="dark"] body { background: #090d16 !important; color: #f3f4f6 !important; }
            body .glass { background: linear-gradient(145deg, rgba(255,255,255,.10), rgba(255,255,255,.035)) !important; border: 1px solid rgba(255,255,255,.14) !important; box-shadow: inset 0 1px rgba(255,255,255,.10), 0 18px 42px rgba(0,0,0,.22); backdrop-filter: blur(18px) saturate(125%); }
            [data-theme="light"] body .glass { background: rgba(255,255,255,.92) !important; border-color: rgba(23,35,29,.16) !important; }
            [data-theme="light"] body input { background: #ffffff !important; color: #17231d !important; border-color: #aab8af !important; }
            [data-theme="light"] body input::placeholder { color: #65756c !important; }
            [data-theme="light"] body .text-gray-200, [data-theme="light"] body .text-gray-300 { color: #26372e !important; }
            [data-theme="light"] body .text-gray-400, [data-theme="light"] body .text-gray-500 { color: #53645a !important; }
            [data-theme="light"] body .bg-gray-800\/60, [data-theme="light"] body .bg-gray-800\/40 { background: #e8eee9 !important; border-color: #c4d0c7 !important; }
            [data-theme="light"] body .bg-gray-900 { background: #ffffff !important; }
            [data-theme="light"] body .bg-black { background: #dce5df !important; }
            [data-theme="dark"] body .glass { background: linear-gradient(145deg, rgba(255,255,255,.10), rgba(255,255,255,.035)) !important; }
            .text-indigo-400, .text-indigo-300, .text-indigo-200 { color: var(--user-accent) !important; }
            .bg-indigo-600 { background-color: var(--user-accent) !important; color: var(--user-accent-text) !important; }
            .bg-indigo-900, .bg-indigo-950 { background-color: var(--user-accent-soft) !important; }
            .border-indigo-500\/30, .border-indigo-500\/40, .border-indigo-500\/20 { border-color: var(--user-accent) !important; opacity: .8; }
            .pulse-glow { box-shadow: 0 0 20px var(--user-accent-soft) !important; }
            button:focus-visible, a:focus-visible, input:focus-visible { outline: 3px solid var(--user-accent) !important; outline-offset: 3px; }
            [data-theme="light"] body #chatLog .text-gray-200 { color: #26372e !important; }
            [data-theme="light"] body .bg-red-950\/30 { background: #ffe5df !important; }
            [data-theme="light"] body .bg-green-950\/20 { background: #e1f4e8 !important; }
            [data-theme="dark"] body .page { --ink: #f5f3ff; --muted: #a8a4b8; --paper: #08080b; --cream: #13131a; --line: rgba(245,243,255,.14); }
            [data-theme="dark"] body .lamp-card, [data-theme="dark"] body .feature:nth-child(3) { background: #191722; color: #f5f3ff; }
            [data-theme="dark"] body .roadmap-item { background: rgba(25,23,34,.76); }
            [data-theme="dark"] body .primary { border-color: #f5f3ff; }
            .theme-controls { position: fixed; z-index: 100; right: 20px; bottom: 20px; display: flex; align-items: center; gap: 8px; padding: 8px; color: #f5f3ff; background: #191722; border: 1px solid rgba(255,255,255,.2); border-radius: 14px; box-shadow: 0 10px 30px rgba(0,0,0,.2); font: 600 12px 'DM Sans', sans-serif; }
            #themeSettingsSlot .theme-controls { position: static; right: auto; bottom: auto; display: block; padding: 0; color: inherit; background: transparent; border: 0; border-radius: 0; box-shadow: none; }
            #themeSettingsSlot #themeToggle { width: 100%; justify-content: space-between; padding: 10px 0; color: inherit; }
            #themeSettingsSlot .accent-setting { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding-top: 10px; border-top: 1px solid rgba(128,145,134,.25); }
            #themeSettingsSlot .accent-label { flex-shrink: 0; }
            .theme-controls button { border: 0; cursor: pointer; color: inherit; background: transparent; }
            #themeToggle { display: flex; align-items: center; gap: 7px; padding: 7px 9px; border-radius: 9px; }
            #themeToggle:hover { background: rgba(255,255,255,.12); }
            .theme-icon { font-size: 16px; line-height: 1; }
            .accent-label { width: 25px; height: 25px; display: block; overflow: hidden; cursor: pointer; border: 2px solid rgba(255,255,255,.75); border-radius: 50%; }
            #accentPicker { width: 40px; height: 40px; opacity: 0; cursor: pointer; transform: translate(-8px, -8px); }
            [data-theme="light"] .theme-controls { color: #17231d; background: #ffffff; border-color: rgba(23,35,29,.2); }
            @media (max-width: 520px) { .theme-controls { right: 12px; bottom: 12px; } .theme-label { display: none; } }
        `;
        document.head.appendChild(style);
    }

    function addControls() {
        if (document.querySelector('.theme-controls')) return;
        const controls = document.createElement('div');
        controls.className = 'theme-controls';
        controls.innerHTML = `
            <button id="themeToggle" type="button" aria-pressed="false" aria-label="Switch theme">
                <span class="theme-icon" aria-hidden="true">☾</span><span class="theme-label">Dark mode</span>
            </button>
            <div class="accent-setting"><span>Primary color</span><label class="accent-label" id="accentSwatch" title="Choose primary color" aria-label="Choose primary color"><input id="accentPicker" type="color" value="${defaultAccent}" aria-label="Choose primary color"></label></div>
        `;
        document.body.appendChild(controls);
        document.getElementById('themeToggle').addEventListener('click', () => setTheme(root.dataset.theme === 'dark' ? 'light' : 'dark'));
        document.getElementById('accentPicker').addEventListener('input', event => setAccent(event.target.value));
        setTheme(root.dataset.theme);
        setAccent(root.style.getPropertyValue('--user-accent') || localStorage.getItem(storageKeys.accent) || defaultAccent);
    }

    function moveControlsToSidebar() {
        const slot = document.getElementById('themeSettingsSlot');
        const controls = document.querySelector('.theme-controls');
        if (slot && controls) slot.appendChild(controls);
    }

    addThemeStyles();
    setTheme(localStorage.getItem(storageKeys.theme) || 'dark');
    setAccent(localStorage.getItem(storageKeys.accent) || defaultAccent);
    document.addEventListener('DOMContentLoaded', addControls);
    window.addEventListener('tutorLampSidebarReady', moveControlsToSidebar);
})();
