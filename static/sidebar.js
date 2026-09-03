document.addEventListener("DOMContentLoaded", () => {
    // 1. Create Sidebar Element
    const sidebar = document.createElement("aside");
    sidebar.id = "appSidebar";
    sidebar.className = "fixed top-0 left-0 h-full w-64 glass z-50 transform -translate-x-full transition-transform duration-300 ease-in-out flex flex-col justify-between p-6 bg-gray-900/95 border-r border-gray-800 shadow-2xl";

    const currentPath = window.location.pathname;

    sidebar.innerHTML = `
        <div class="flex flex-col h-full justify-between">
            <div>
                <div class="flex items-center justify-between mb-8">
                    <div class="flex items-center space-x-3">
                        <div class="w-3 h-3 rounded-full bg-indigo-500 animate-ping"></div>
                        <span class="font-bold text-gray-200 text-lg tracking-wide">Menu</span>
                    </div>
                    <button id="closeSidebar" class="text-gray-400 hover:text-white text-2xl font-bold">&times;</button>
                </div>

                <nav class="space-y-3">
                    <a href="/app" class="flex items-center space-x-3 px-4 py-3 rounded-xl transition ${currentPath === '/app' || currentPath === '/index' ? 'bg-indigo-600/30 text-indigo-400 border border-indigo-500/30 font-semibold' : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'}">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 00-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"></path></svg>
                        <span>Main Page</span>
                    </a>
                    <a href="/analytics" class="flex items-center space-x-3 px-4 py-3 rounded-xl transition ${currentPath === '/analytics' ? 'bg-indigo-600/30 text-indigo-400 border border-indigo-500/30 font-semibold' : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'}">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
                        <span>Analytics</span>
                    </a>
                    <a href="/chatbot" class="flex items-center space-x-3 px-4 py-3 rounded-xl transition ${currentPath === '/chatbot' ? 'bg-indigo-600/30 text-indigo-400 border border-indigo-500/30 font-semibold' : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'}">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16h6m5-4a8 8 0 11-16 0c0 1.2.27 2.34.76 3.36L4 20l4.64-.76A8 8 0 0020 12z"></path></svg>
                        <span>Chatbot</span>
                    </a>
                </nav>
            </div>

            <div>
                <div id="themeSettingsSlot" class="mb-5"></div>
                <div class="text-xs text-gray-500 border-t border-gray-800/80 pt-4">
                    Tutor Lamp Dashboard
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(sidebar);
    window.dispatchEvent(new CustomEvent("tutorLampSidebarReady"));

    // Toggle events
    const openBtn = document.getElementById("openSidebar");
    const closeBtn = document.getElementById("closeSidebar");

    if (openBtn) openBtn.addEventListener("click", () => sidebar.classList.remove("-translate-x-full"));
    if (closeBtn) closeBtn.addEventListener("click", () => sidebar.classList.add("-translate-x-full"));
});