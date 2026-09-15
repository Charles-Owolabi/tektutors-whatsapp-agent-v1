let currentPhone = null;
let pollTimer = null;
let conversationAiStates = {};
window.soundEnabled = true;
window.friendlyLogMode = true;
window.currentLeadView = 'kanban';
window.campaignsData = [];
window.selectedCampaignId = null;
window.leadsData = [];
window.appointmentsData = [];
window.emailTemplates = [];
window.currentEmailCategory = 'all';

const TAB_METADATA = {
    handoff: {
        title: '<i class="fa-solid fa-headset" style="color: #ff8c3a;"></i> Live Handoff Console',
        desc: 'Monitor active student WhatsApp conversations, take over manually, or inspect AI drafts in real-time.'
    },
    simulator: {
        title: '<i class="fa-brands fa-whatsapp" style="color: #25D366;"></i> WhatsApp AI Simulator',
        desc: 'Test real-time conversational flows, 1-click consultative chips, syllabus delivery & instant qualification.'
    },
    leads: {
        title: '<i class="fa-solid fa-users" style="color: #3b82f6;"></i> Student CRM & Pipeline',
        desc: 'Track prospect engagement, automated lead scoring, qualification stages, and 1-click WhatsApp follow-ups.'
    },
    appointments: {
        title: '<i class="fa-solid fa-calendar-check" style="color: #8b5cf6;"></i> 1-on-1 Consultation Bookings',
        desc: 'Manage scheduled academic consultations, phone calls, and advisor meeting links.'
    },
    analytics: {
        title: '<i class="fa-solid fa-chart-pie" style="color: #10b981;"></i> Sales Funnel & Cost ROI',
        desc: 'Track lead conversion rates, revenue pipeline, tuition projections, and 99.4% Groq token savings.'
    },
    campaigns: {
        title: '<i class="fa-solid fa-bullhorn" style="color: #f59e0b;"></i> WhatsApp Broadcast Campaigns',
        desc: 'Launch personalized cohort announcements, weekend workshop alerts, and deadline reminders.'
    },
    emails: {
        title: '<i class="fa-solid fa-envelope" style="color: #38bdf8;"></i> Email Marketing & Syllabi Hub',
        desc: 'Preview, compose, and auto-dispatch branded syllabus PDFs, follow-up sequences, and promotional offers.'
    },
    courses: {
        title: '<i class="fa-solid fa-graduation-cap" style="color: #6366f1;"></i> Academy Course Catalog',
        desc: 'Manage tuition pricing, curriculum modules, prerequisites, career outcomes, and simulator test pitches.'
    },
    faqs: {
        title: '<i class="fa-solid fa-circle-question" style="color: #ec4899;"></i> Dynamic FAQ Knowledge Base',
        desc: 'Maintain instant answers for laptops, weekend schedules, USD tuition, certificates, and job mentorship.'
    },
    settings: {
        title: '<i class="fa-solid fa-sliders" style="color: #e2e8f0;"></i> System Settings & AI Guardrails',
        desc: 'Tune AI personality, model temperature, WhatsApp phone number, and academy operating parameters.'
    }
};

document.addEventListener('DOMContentLoaded', () => {
    setupTabNavigation();
    fetchConversations();
    fetchLeads();
    fetchCourses();
    fetchFAQs();
    fetchSettings();
    fetchCRMStats();
    fetchEmailStats();
    fetchEmailTemplates();

    // Start auto polling for conversations every 4 seconds
    pollTimer = setInterval(fetchConversations, 4000);

    // Check saved state of quick start strip
    if (localStorage.getItem('hideQuickStart') === 'true') {
        const strip = document.getElementById('quick-start-strip');
        if (strip) strip.style.display = 'none';
    }

    // Interactive event listeners
    const refreshBtn = document.getElementById('refresh-chats-btn');
    if (refreshBtn) refreshBtn.addEventListener('click', fetchConversations);

    const aiToggle = document.getElementById('ai-active-toggle');
    if (aiToggle) aiToggle.addEventListener('change', handleHandoffToggle);

    const sendHumanBtn = document.getElementById('send-human-btn');
    if (sendHumanBtn) sendHumanBtn.addEventListener('click', sendHumanMessage);

    const humanInput = document.getElementById('human-message-input');
    if (humanInput) {
        humanInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') sendHumanMessage();
        });
    }

    // Global keyboard shortcuts for fast UX
    document.addEventListener('keydown', (e) => {
        // Search shortcut: '/' or 'Ctrl+K' / 'Cmd+K'
        if ((e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) ||
            ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k')) {
            e.preventDefault();
            const searchInput = document.getElementById('global-search-input');
            if (searchInput) {
                searchInput.focus();
                searchInput.select();
            }
        }

        // Close on Escape
        if (e.key === 'Escape') {
            const searchInput = document.getElementById('global-search-input');
            if (document.activeElement === searchInput) {
                searchInput.blur();
                searchInput.value = '';
                handleGlobalSearch('');
            }
            closeHelpModal();
            closeCourseModal();
            closeFaqModal();
            closeEmailComposer();
            document.querySelector('.sidebar')?.classList.remove('mobile-open');
            document.getElementById('sidebar-backdrop')?.classList.remove('active');
        }
    });

    // Close any open modal on outside backdrop click
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                overlay.style.display = 'none';
            }
        });
    });
});

function setupTabNavigation() {
    const navButtons = document.querySelectorAll('.nav-btn');
    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            switchToTab(btn.dataset.tab);
        });
    });
}

function switchToTab(tabName) {
    const navButtons = document.querySelectorAll('.nav-btn');
    const tabPanes = document.querySelectorAll('.tab-pane');

    navButtons.forEach(b => b.classList.toggle('active', b.dataset.tab === tabName));
    tabPanes.forEach(p => p.classList.toggle('active', p.id === `tab-${tabName}`));

    // Update dynamic executive header title & subtitle
    const meta = TAB_METADATA[tabName];
    const headerTitle = document.getElementById('header-view-title');
    const headerDesc = document.getElementById('header-view-desc');
    if (meta) {
        if (headerTitle) headerTitle.innerHTML = meta.title;
        if (headerDesc) headerDesc.innerText = meta.desc;
    }

    // Auto-close mobile navigation drawer if open
    document.querySelector('.sidebar')?.classList.remove('mobile-open');
    document.getElementById('sidebar-backdrop')?.classList.remove('active');

    // Smooth scroll main container to top
    const mainContent = document.querySelector('.main-content');
    if (mainContent) mainContent.scrollTop = 0;

    // Trigger tab specific data loaders
    if (tabName === 'analytics') fetchFunnelAnalytics();
    if (tabName === 'campaigns') fetchCampaigns();
    if (tabName === 'emails') loadEmailHub();
    if (tabName === 'appointments') fetchAppointments();
    if (tabName === 'leads') fetchLeads();
    if (tabName === 'courses') fetchCourses();
    if (tabName === 'faqs') fetchFAQs();
    if (tabName === 'settings') fetchSettings();
}

function dismissQuickStart() {
    const strip = document.getElementById('quick-start-strip');
    if (strip) {
        strip.style.opacity = '0';
        strip.style.transform = 'translateY(-10px)';
        strip.style.transition = 'all 0.25s ease';
        setTimeout(() => {
            strip.style.display = 'none';
        }, 250);
    }
    localStorage.setItem('hideQuickStart', 'true');
    showToast('Quick Action Hub hidden. Click Guide anytime to restore.', 'info');
}

function restoreQuickStart() {
    const strip = document.getElementById('quick-start-strip');
    if (strip) {
        strip.style.display = 'block';
        strip.style.opacity = '1';
        strip.style.transform = 'translateY(0)';
    }
    localStorage.removeItem('hideQuickStart');
}

function toggleMobileSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');
    if (!sidebar) return;
    const isOpen = sidebar.classList.toggle('mobile-open');
    if (backdrop) {
        backdrop.classList.toggle('active', isOpen);
    }
}

function handleGlobalSearch(query) {
    const q = (query || '').toLowerCase().trim();
    const activePane = document.querySelector('.tab-pane.active');
    const activeTabId = activePane ? activePane.id.replace('tab-', '') : 'handoff';

    // 1. Direct tab shortcuts
    const navShortcuts = {
        'leads': 'leads',
        'lead': 'leads',
        'crm': 'leads',
        'sim': 'simulator',
        'simulator': 'simulator',
        'chat': 'simulator',
        'whatsapp': 'simulator',
        'email': 'emails',
        'emails': 'emails',
        'campaign': 'campaigns',
        'campaigns': 'campaigns',
        'broadcast': 'campaigns',
        'course': 'courses',
        'courses': 'courses',
        'faq': 'faqs',
        'faqs': 'faqs',
        'analytics': 'analytics',
        'roi': 'analytics',
        'cost': 'analytics',
        'appointments': 'appointments',
        'appointment': 'appointments',
        'call': 'appointments',
        'settings': 'settings',
        'setting': 'settings'
    };

    if (navShortcuts[q]) {
        switchToTab(navShortcuts[q]);
        return;
    }

    // 2. Real-time active tab filtering
    if (activeTabId === 'leads') {
        const leadInput = document.getElementById('lead-search-input');
        if (leadInput) {
            leadInput.value = query;
            filterLeadsLocally();
        }
    } else if (activeTabId === 'courses') {
        const cards = document.querySelectorAll('#courses-container .course-card');
        cards.forEach(card => {
            const txt = card.innerText.toLowerCase();
            card.style.display = txt.includes(q) ? 'block' : 'none';
        });
    } else if (activeTabId === 'faqs') {
        const rows = document.querySelectorAll('#faqs-table-body tr');
        rows.forEach(row => {
            const txt = row.innerText.toLowerCase();
            row.style.display = txt.includes(q) ? '' : 'none';
        });
    } else if (activeTabId === 'handoff') {
        const items = document.querySelectorAll('#conversations-container .conv-item');
        items.forEach(item => {
            const txt = item.innerText.toLowerCase();
            item.style.display = txt.includes(q) ? 'block' : 'none';
        });
    } else if (activeTabId === 'appointments') {
        const rows = document.querySelectorAll('#appointments-table-body tr');
        rows.forEach(row => {
            const txt = row.innerText.toLowerCase();
            row.style.display = txt.includes(q) ? '' : 'none';
        });
    } else if (activeTabId === 'emails') {
        const rows = document.querySelectorAll('#email-history-table-body tr');
        rows.forEach(row => {
            const txt = row.innerText.toLowerCase();
            row.style.display = txt.includes(q) ? '' : 'none';
        });
    }
}

async function seedSampleData() {
    try {
        const res = await fetch('/api/demo/seed', { method: 'POST' });
        const data = await res.json();
        showToast(data.message || 'Sample data loaded successfully!');
        await fetchConversations();
        await fetchLeads();
        await fetchCRMStats();
        await fetchFunnelAnalytics();
    } catch (err) {
        console.error('Error seeding demo data:', err);
    }
}

// --- FLOATING TOAST NOTIFICATIONS ---
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast-notification ${type}`;
    const icon = type === 'success' ? 'fa-circle-check' : 'fa-circle-info';
    toast.innerHTML = `<i class="fa-solid ${icon}" style="color: ${type === 'success' ? '#10b981' : '#3b82f6'};"></i> <span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3200);
}

// --- INTERACTIVE HELP MODAL ---
function openHelpModal() {
    document.getElementById('help-modal').style.display = 'flex';
}
function closeHelpModal() {
    document.getElementById('help-modal').style.display = 'none';
}

// --- TAB 1: LIVE HANDOFF ---
async function fetchConversations() {
    try {
        const res = await fetch('/api/conversations');
        const data = await res.json();
        const container = document.getElementById('conversations-container');
        const activeCount = document.getElementById('active-chats-count');

        if (!data.conversations || data.conversations.length === 0) {
            container.innerHTML = `
                <div class="empty-state" style="padding: 1.5rem 1rem; text-align: center;">
                    <i class="fa-brands fa-whatsapp fa-2x" style="color: #25D366; margin-bottom: 0.5rem;"></i>
                    <p style="font-size: 0.8rem; margin-bottom: 0.75rem;">No active WhatsApp conversations yet.</p>
                    <button class="btn btn-primary" style="font-size: 0.75rem; padding: 0.4rem 0.8rem; width: 100%; margin-bottom: 0.4rem;" onclick="switchToTab('simulator')">
                        <i class="fa-solid fa-play"></i> Start Test Chat
                    </button>
                    <button class="btn btn-secondary" style="font-size: 0.75rem; padding: 0.4rem 0.8rem; width: 100%;" onclick="seedSampleData()">
                        <i class="fa-solid fa-wand-magic-sparkles"></i> Load Sample Data
                    </button>
                </div>
            `;
            activeCount.innerText = '0';
            return;
        }

        activeCount.innerText = data.conversations.length;
        container.innerHTML = '';

        // Auto-select first chat if none selected to make app immediately active and effortless
        if (!currentPhone && data.conversations.length > 0) {
            selectConversation(data.conversations[0].phone, data.conversations[0].customer_name);
        }

        data.conversations.forEach(c => {
            // Check takeover transition
            if (c.phone in conversationAiStates && conversationAiStates[c.phone] === true && c.ai_active === false) {
                playTakeoverChime();
                showToast(`🚨 Attention: Human takeover requested for ${c.customer_name || c.phone}`, 'info');
            }
            conversationAiStates[c.phone] = c.ai_active;

            const item = document.createElement('div');
            const isPulsing = !c.ai_active ? 'pulse-alert' : '';
            item.className = `conv-item ${c.phone === currentPhone ? 'active' : ''} ${isPulsing}`;
            item.onclick = () => selectConversation(c.phone, c.customer_name);

            const aiStatusPill = c.ai_active 
                ? '<span class="pill pill-ai">🤖 AI Active</span>' 
                : '<span class="pill pill-human">👤 Human Takeover</span>';

            const leadPill = `<span class="pill pill-${c.lead_status}">${c.lead_status}</span>`;

            item.innerHTML = `
                <div class="conv-header">
                    <span class="conv-title">${escapeHtml(c.customer_name)} (${c.phone})</span>
                    <span class="conv-time">${c.last_message_at.split(' ')[1] || ''}</span>
                </div>
                <div class="conv-preview">${escapeHtml(c.last_message)}</div>
                <div class="conv-tags">
                    ${aiStatusPill}
                    ${leadPill}
                </div>
            `;
            container.appendChild(item);
        });
    } catch (err) {
        console.error('Error fetching conversations:', err);
    }
}

async function selectConversation(phone, name) {
    currentPhone = phone;
    document.getElementById('current-chat-name').innerText = name || 'Customer';
    document.getElementById('current-chat-phone').innerText = `Phone: +${phone}`;
    document.getElementById('handoff-controls-bar').style.display = 'flex';
    document.getElementById('human-input-area').style.display = 'flex';

    await loadMessages(phone);
    await loadCopilotSuggestions(phone);
    loadCustomer360Profile(phone);
    fetchConversations();
}

async function loadMessages(phone) {
    try {
        const res = await fetch(`/api/conversations/${phone}/messages`);
        const data = await res.json();
        const container = document.getElementById('messages-container');
        const aiToggle = document.getElementById('ai-active-toggle');
        const banner = document.getElementById('override-banner');
        const aiBanner = document.getElementById('ai-active-banner');

        aiToggle.checked = data.ai_active;
        if (banner) banner.style.display = data.ai_active ? 'none' : 'flex';
        if (aiBanner) aiBanner.style.display = data.ai_active ? 'flex' : 'none';

        // Co-Pilot Draft box show/hide
        const copilotContainer = document.getElementById('copilot-draft-container');
        const copilotText = document.getElementById('copilot-draft-text');
        
        if (!data.ai_active && data.ai_draft_reply) {
            copilotText.innerText = data.ai_draft_reply;
            copilotContainer.style.display = 'block';
        } else {
            copilotContainer.style.display = 'none';
        }

        if (!data.messages || data.messages.length === 0) {
            container.innerHTML = '<div class="empty-state">No messages in thread yet.</div>';
            return;
        }

        container.innerHTML = '';
        data.messages.forEach(m => {
            const row = document.createElement('div');
            row.className = `msg-row ${m.sender}`;

            let senderLabel = m.sender === 'user' ? 'Customer' : (m.sender === 'assistant' ? '🤖 Tara (AI Agent)' : '👤 Human Advisor');
            let toolBadge = m.tool_calls_log ? `<span style="font-size:0.65rem; color:#a7f3d0; margin-left:6px;">[Tools: ${m.tool_calls_log}]</span>` : '';

            row.innerHTML = `
                <div class="msg-content">
                    <div class="msg-sender">${senderLabel} ${toolBadge}</div>
                    <div class="msg-text">${formatWhatsAppText(m.body)}</div>
                    <div class="msg-timestamp">${m.timestamp}</div>
                </div>
            `;
            container.appendChild(row);
        });

        container.scrollTop = container.scrollHeight;
    } catch (err) {
        console.error('Error loading messages:', err);
    }
}

async function takeOverConversation() {
    const aiToggle = document.getElementById('ai-active-toggle');
    if (aiToggle) {
        aiToggle.checked = false;
        await handleHandoffToggle({ target: { checked: false } });
    }
}

async function resumeAiConversation() {
    const aiToggle = document.getElementById('ai-active-toggle');
    if (aiToggle) {
        aiToggle.checked = true;
        await handleHandoffToggle({ target: { checked: true } });
    }
}

async function handleHandoffToggle(e) {
    if (!currentPhone) return;
    const aiActive = e.target.checked;
    try {
        const res = await fetch('/api/handoff/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                phone: currentPhone,
                ai_active: aiActive,
                reason: aiActive ? 'Admin resumed AI agent.' : 'Admin intervened via dashboard.'
            })
        });
        if (res.ok) {
            showToast(aiActive ? '🤖 AI Auto-Reply Resumed' : '👤 Human Control Active - AI Paused');
            loadMessages(currentPhone);
            fetchConversations();
        }
    } catch (err) {
        console.error('Error toggling handoff:', err);
    }
}

async function sendHumanMessage() {
    const input = document.getElementById('human-message-input');
    const message = input.value.trim();
    if (!message || !currentPhone) return;

    try {
        const res = await fetch('/api/handoff/send-message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone: currentPhone, message: message })
        });

        if (res.ok) {
            input.value = '';
            showToast('Message sent to WhatsApp user');
            await loadMessages(currentPhone);
            fetchConversations();
        } else {
            alert('Failed to send message.');
        }
    } catch (err) {
        console.error('Error sending human message:', err);
    }
}

// --- CUSTOMER 360° PROFILE DRAWER CONTROLS ---
function toggleCustomer360Drawer() {
    const grid = document.querySelector('.handoff-grid');
    const panel = document.getElementById('chat-profile-panel');
    if (!panel) return;
    if (panel.style.display === 'none' || panel.style.display === '') {
        panel.style.display = 'flex';
        grid.classList.add('with-profile');
        if (currentPhone) loadCustomer360Profile(currentPhone);
    } else {
        panel.style.display = 'none';
        grid.classList.remove('with-profile');
    }
}

function loadCustomer360Profile(phone) {
    const panel = document.getElementById('chat-profile-panel');
    if (!panel || panel.style.display === 'none') return;

    const clean = phone.replace('+', '');
    const lead = (window.leadsData || []).find(l => l.phone.replace('+', '') === clean);

    if (lead) {
        window.activeProfileLeadId = lead.id;
        let score = 40;
        if (lead.status === 'hot') score = 95;
        else if (lead.status === 'qualified') score = 75;
        else if (lead.status === 'enrolled') score = 100;
        if (lead.budget_ready) score = Math.min(100, score + 15);

        document.getElementById('profile-stage-badge').innerText = lead.status.toUpperCase();
        document.getElementById('profile-stage-badge').className = `badge badge-${lead.status}`;
        document.getElementById('profile-lead-score').innerHTML = `🔥 ${score}<span style="font-size: 0.8rem; color: var(--text-muted);">/100</span>`;
        document.getElementById('profile-course-interest').innerText = lead.course_interest || 'General Tech';
        document.getElementById('profile-skill-level').innerText = lead.skill_level || 'Beginner';
        document.getElementById('profile-phone-text').innerText = `+${lead.phone}`;
        document.getElementById('profile-email-text').innerText = lead.email || 'Not provided yet';
        document.getElementById('profile-stage-select').value = lead.status;
        document.getElementById('profile-notes-input').value = lead.notes || '';

        refreshLeadSummary(lead.id);
    } else {
        document.getElementById('profile-course-interest').innerText = 'Exploring';
        document.getElementById('profile-phone-text').innerText = `+${phone}`;
        document.getElementById('profile-email-text').innerText = 'Not provided';
        document.getElementById('profile-ai-dossier-text').innerText = 'New prospect. Ongoing qualification.';
    }
}

async function refreshLeadSummary(leadId) {
    const id = leadId || window.activeProfileLeadId;
    if (!id) return;
    try {
        const res = await fetch(`/api/crm/lead/${id}/summary`);
        if (res.ok) {
            const data = await res.json();
            document.getElementById('profile-ai-dossier-text').innerText = data.summary;
        }
    } catch (err) {
        console.error('Error fetching lead summary:', err);
    }
}

async function updateProfileStage() {
    const leadId = window.activeProfileLeadId;
    const newStage = document.getElementById('profile-stage-select').value;
    if (!leadId) return;
    await updateLeadStage(leadId, newStage);
}

async function saveProfileNotes() {
    const leadId = window.activeProfileLeadId;
    const notes = document.getElementById('profile-notes-input').value.trim();
    if (!leadId) return;
    try {
        const res = await fetch(`/api/crm/lead/${leadId}/notes`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ notes: notes })
        });
        if (res.ok) {
            showToast('Advisor notes saved successfully!');
            fetchLeads();
        }
    } catch (err) {
        console.error('Error saving notes:', err);
    }
}

// --- TAB 2: SIMULATOR CONTROLS ---
async function sendSimMessage() {
    const phoneInput = document.getElementById('sim-phone-input');
    const userInput = document.getElementById('sim-user-input');
    const phone = phoneInput.value.trim();
    const text = userInput.value.trim();

    if (!text) return;
    userInput.value = '';

    appendSimBubble('user', text);
    logToolExecution(`Customer asked: "${text}"`, 'user');

    const messagesBody = document.getElementById('sim-messages-body');
    const typingIndicator = document.createElement('div');
    typingIndicator.id = 'sim-typing-indicator';
    typingIndicator.className = 'msg-bubble assistant-bubble typing-bubble';
    typingIndicator.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
    messagesBody.appendChild(typingIndicator);
    messagesBody.scrollTop = messagesBody.scrollHeight;

    const startTime = performance.now();

    try {
        const res = await fetch('/api/simulator/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ phone: phone, message: text })
        });
        const data = await res.json();
        const latencyMs = Math.round(performance.now() - startTime);

        const indicator = document.getElementById('sim-typing-indicator');
        if (indicator) indicator.remove();

        if (data.ai_response) {
            appendSimBubble('assistant', data.ai_response.body, latencyMs);
            playMessageChime();

            if (data.ai_response.tool_logs && data.ai_response.tool_logs.length > 0) {
                data.ai_response.tool_logs.forEach(t => {
                    const desc = window.friendlyLogMode ? toolExplanations(t) : `[EXECUTED_TOOL: ${t}]`;
                    logToolExecution(desc, 'success');
                });
            }
        }
        fetchConversations();
        fetchLeads();
        fetchCRMStats();
    } catch (err) {
        const indicator = document.getElementById('sim-typing-indicator');
        if (indicator) indicator.remove();
        console.error('Simulator error:', err);
    }
}

function toolExplanations(toolName) {
    const map = {
        'search_tektutors_courses': '🔍 Looked up Course Catalog & Fees in Database',
        'get_course_faq_answer': '💡 Checked FAQ Answers on Installments & Schedule',
        'qualify_and_capture_lead': '🎯 Captured Lead Contact into CRM',
        'schedule_advisor_call': '📅 Scheduled Admissions Discovery Call',
        'escalate_to_human_advisor': '🚨 Connected Student with Real Advisor'
    };
    return map[toolName] || toolName;
}

function sendSimPrompt(promptText) {
    document.getElementById('sim-user-input').value = promptText;
    sendSimMessage();
}

function logToolExecution(msg, level = 'info') {
    const container = document.getElementById('tools-log-container');
    const item = document.createElement('div');
    item.className = `log-item ${level}`;
    const time = new Date().toLocaleTimeString();
    item.innerText = `[${time}] ${msg}`;
    container.appendChild(item);
    container.scrollTop = container.scrollHeight;
}

function toggleLogMode() {
    window.friendlyLogMode = !window.friendlyLogMode;
    const btn = document.getElementById('btn-log-mode');
    if (window.friendlyLogMode) {
        btn.innerHTML = '<i class="fa-solid fa-code"></i> Toggle Tech Logs';
        showToast('Switched to Plain English Activity View', 'info');
    } else {
        btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Toggle Plain English';
        showToast('Switched to Raw Developer Logs View', 'info');
    }
}

function formatWhatsAppText(rawText) {
    if (!rawText) return '';
    // Normalize literal escaped newlines
    let text = rawText.replace(/\\n/g, '\n');
    let formatted = escapeHtml(text);

    // Markdown table parser for WhatsApp simulator
    if (formatted.includes('|') && formatted.includes('\n')) {
        const lines = formatted.split('\n');
        const tableLines = lines.filter(l => l.trim().startsWith('|') && l.trim().endsWith('|'));
        if (tableLines.length >= 2) {
            let tableHtml = '<div style="overflow-x:auto; margin:0.4rem 0;"><table style="width:100%; border-collapse:collapse; font-size:0.75rem;">';
            tableLines.forEach((tLine, idx) => {
                if (tLine.includes('---')) return;
                const cols = tLine.split('|').map(c => c.trim()).filter((c, i, a) => i !== 0 && i !== a.length - 1);
                const isHeader = idx === 0;
                tableHtml += '<tr>' + cols.map(c => `<${isHeader ? 'th' : 'td'} style="border:1px solid rgba(255,255,255,0.15); padding:4px 8px; ${isHeader ? 'background:rgba(255,255,255,0.08); font-weight:600;' : ''}">${c}</${isHeader ? 'th' : 'td'}>`).join('') + '</tr>';
            });
            tableHtml += '</table></div>';
            const tableBlock = tableLines.join('\n');
            formatted = formatted.replace(tableBlock, tableHtml);
        }
    }

    formatted = formatted.replace(/\*([^\*]+)\*/g, '<strong>$1</strong>');
    formatted = formatted.replace(/_([^_]+)_/g, '<em>$1</em>');
    formatted = formatted.replace(/~([^~]+)~/g, '<del>$1</del>');
    formatted = formatted.replace(/```([^`]+)```/g, '<code>$1</code>');
    formatted = formatted.replace(/\n/g, '<br>');
    return formatted;
}

function extractInteractiveActions(text) {
    const actions = [];
    const lower = text.toLowerCase();

    // If numbered course tracks or outline selection is presented
    if (lower.includes('reply with a number') || lower.includes('reply with the number') || lower.includes('which skill track') || lower.includes('training tracks') || lower.includes('featured training tracks')) {
        actions.push({ label: '1️⃣ Track 1: Data Analytics', prompt: '1' });
        actions.push({ label: '2️⃣ Track 2: Excel Analysis', prompt: '2' });
        actions.push({ label: '3️⃣ Track 3: SQL Database', prompt: '3' });
        actions.push({ label: '4️⃣ Track 4: Power BI', prompt: '4' });
        actions.push({ label: '5️⃣ Track 5: Python & AI', prompt: '5' });
        actions.push({ label: '6️⃣ Explore Other Courses', prompt: '6' });
        return actions;
    }

    // If other specialized courses/tracks are presented
    if (lower.includes('other available courses') || lower.includes('specialized tracks') || lower.includes('which of these courses interests you')) {
        actions.push({ label: '📅 Book 1-on-1 Call', prompt: 'Yes, please book me a 1-on-1 call with an Admissions Advisor.' });
        actions.push({ label: '💳 View Payment Plans', prompt: 'Tell me more about the month-to-month payment plan.' });
        actions.push({ label: '📚 Send Full Syllabus', prompt: 'Please share the complete course syllabus breakdown.' });
        return actions;
    }

    const isPaymentResponse = lower.includes('flexible tuition & payment plans') || lower.includes('flexible month-to-month plan') || lower.includes('upfront full-payment plan');
    const isCallResponse = lower.includes('book your 1-on-1 admissions discovery call') || lower.includes('to lock in your call slot');
    const isSyllabusResponse = lower.includes('syllabus breakdown') || lower.includes('module 1: foundations') || lower.includes('core syllabus architecture');

    if (!isCallResponse && (lower.includes('discovery call') || lower.includes('schedule') || lower.includes('book a call') || lower.includes('advisor') || isPaymentResponse || isSyllabusResponse)) {
        actions.push({ label: '📅 Book 1-on-1 Call', prompt: 'Yes, please book me a 1-on-1 call with an Admissions Advisor.' });
    }
    if (!isPaymentResponse && (lower.includes('installment') || lower.includes('payment') || lower.includes('month-to-month') || lower.includes('fee') || isCallResponse || isSyllabusResponse)) {
        actions.push({ label: '💳 View Payment Plans', prompt: 'Tell me more about the month-to-month payment plan.' });
    }
    if (!isSyllabusResponse && (lower.includes('syllabus') || lower.includes('curriculum') || lower.includes('learn') || lower.includes('prerequisites') || isPaymentResponse || isCallResponse)) {
        actions.push({ label: '📚 Send Full Syllabus', prompt: 'Please share the complete course syllabus breakdown.' });
    }

    if (actions.length < 3) {
        actions.push({ label: '1️⃣ Track 1: Data Analytics', prompt: '1' });
    }
    return actions.slice(0, 3);
}

function appendSimBubble(sender, text, latencyMs = null) {
    const body = document.getElementById('sim-messages-body');
    const bubble = document.createElement('div');
    bubble.className = `msg-bubble ${sender === 'user' ? 'user-bubble' : 'assistant-bubble'}`;
    const timeStr = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});

    if (sender === 'user') {
        bubble.innerHTML = `
            <div class="msg-text">${formatWhatsAppText(text)}</div>
            <span class="msg-time">${timeStr} <span class="wa-checkmarks blue">✓✓</span></span>
        `;
    } else {
        let buttonsHtml = '';
        const actions = extractInteractiveActions(text);
        if (actions.length > 0) {
            buttonsHtml = `<div class="wa-interactive-buttons">` + 
                actions.map((act) => `<button class="wa-btn-action" onclick="sendSimPrompt('${escapeHtml(act.prompt)}')">${act.label}</button>`).join('') +
                `</div>`;
        }
        const speedBadge = latencyMs ? `<span class="sim-speed-pill" title="Sub-second response time"><i class="fa-solid fa-bolt"></i> ${latencyMs}ms</span>` : '';
        bubble.innerHTML = `
            <div class="msg-text">${formatWhatsAppText(text)}</div>
            ${buttonsHtml}
            <span class="msg-time">${timeStr} ${speedBadge}</span>
        `;
    }

    body.appendChild(bubble);
    body.scrollTop = body.scrollHeight;
}

async function runInteractiveDemo() {
    switchToTab('simulator');
    showToast('✨ Starting 10-Second Interactive Tour...', 'info');
    
    // Check if we need demo data
    if (!window.leadsData || window.leadsData.length === 0) {
        await seedSampleData();
    }
    
    const phoneInput = document.getElementById('sim-phone-input');
    const userInput = document.getElementById('sim-user-input');
    if (phoneInput) phoneInput.value = '2348012345678';
    
    const demoPrompt = "Hi Tara! I have zero coding experience. Can I join Data Analytics and how much is tuition?";
    if (userInput) {
        userInput.value = "";
        let i = 0;
        const typingTimer = setInterval(() => {
            if (i < demoPrompt.length) {
                userInput.value += demoPrompt.charAt(i);
                i++;
            } else {
                clearInterval(typingTimer);
                setTimeout(() => {
                    sendSimMessage();
                    showToast('Tara AI is analyzing the inquiry & calculating fees...', 'info');
                }, 300);
            }
        }, 15);
    }
}

function loadSimPersona(personaKey) {
    const phoneInput = document.getElementById('sim-phone-input');
    const userInput = document.getElementById('sim-user-input');
    
    if (personaKey === 'blessing') {
        if (phoneInput) phoneInput.value = '2348012345678';
        if (userInput) userInput.value = "Hi Tara! I have no coding background. Can I join Data Analytics and how much is it?";
        showToast("Loaded Blessing (Beginner) persona");
        sendSimMessage();
    } else if (personaKey === 'emeka') {
        if (phoneInput) phoneInput.value = '2348098765432';
        if (userInput) userInput.value = "Good day! What are the installment payment options for Full-Stack Python?";
        showToast("Loaded Emeka (Installments) persona");
        sendSimMessage();
    } else if (personaKey === 'alex') {
        if (phoneInput) phoneInput.value = '2348033322114';
        if (userInput) userInput.value = "My name is Alex, email alex@example.com. I want to book a 15-minute admissions call for tomorrow.";
        showToast("Loaded Alex (Admissions Booking) persona");
        sendSimMessage();
    }
}

function simulateVoiceNote() {
    const body = document.getElementById('sim-messages-body');
    const bubble = document.createElement('div');
    bubble.className = 'msg-bubble assistant-bubble wa-audio-bubble';
    const timeStr = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
    
    // Generate 24 animated wave bars
    const waveBarsHtml = Array.from({length: 24}).map((_, idx) => {
        const heights = [6, 12, 18, 10, 16, 22, 14, 8, 16, 20, 12, 6, 14, 18, 10, 22, 16, 8, 12, 18, 14, 8, 6, 10];
        const h = heights[idx % heights.length];
        return `<span class="audio-wave-bar" style="height: ${h}px;"></span>`;
    }).join('');

    bubble.innerHTML = `
        <div class="audio-player-mock">
            <button class="audio-play-btn" onclick="toggleAudioMock(this)"><i class="fa-solid fa-play"></i></button>
            <div class="audio-waveform">
                <div class="audio-wave-bars">
                    ${waveBarsHtml}
                </div>
                <div class="audio-meta">
                    <span class="audio-time">0:18</span>
                    <span class="audio-label"><i class="fa-solid fa-microphone" style="color: #25D366;"></i> Voice Note from Tara</span>
                </div>
            </div>
            <div class="audio-avatar"><i class="fa-solid fa-graduation-cap"></i></div>
        </div>
        <span class="msg-time">${timeStr} <span class="wa-checkmarks blue">✓✓</span></span>
    `;
    body.appendChild(bubble);
    body.scrollTop = body.scrollHeight;
    logToolExecution("Simulated inbound WhatsApp Voice Note audio message.", "info");
    
    const playBtn = bubble.querySelector('.audio-play-btn');
    if (playBtn) toggleAudioMock(playBtn);
}

function toggleAudioMock(btn) {
    const icon = btn.querySelector('i');
    const player = btn.closest('.audio-player-mock');
    const speechText = "Hello there! Welcome to TekTutors. Our practical Data Analytics and AI bootcamps feature live weekend classes with 1-on-1 industry mentors. You can also pay month-to-month at one hundred thousand Naira per month. Let me know which course you'd like to explore!";
    
    if (icon.classList.contains('fa-play')) {
        icon.classList.remove('fa-play');
        icon.classList.add('fa-pause');
        if (player) player.classList.add('is-playing');
        speakVoiceNote(speechText, () => {
            icon.classList.remove('fa-pause');
            icon.classList.add('fa-play');
            if (player) player.classList.remove('is-playing');
        });
    } else {
        if (window.speechSynthesis) window.speechSynthesis.cancel();
        icon.classList.remove('fa-pause');
        icon.classList.add('fa-play');
        if (player) player.classList.remove('is-playing');
    }
}

function speakVoiceNote(text, onEnd) {
    if (!window.speechSynthesis) {
        if (onEnd) onEnd();
        return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    utterance.pitch = 1.05;
    const voices = window.speechSynthesis.getVoices();
    const naturalVoice = voices.find(v => v.lang.startsWith('en') && (v.name.includes('Female') || v.name.includes('Natural') || v.name.includes('Samantha')));
    if (naturalVoice) utterance.voice = naturalVoice;

    utterance.onend = () => { if (onEnd) onEnd(); };
    utterance.onerror = () => { if (onEnd) onEnd(); };
    window.speechSynthesis.speak(utterance);
}

function toggleAudioChimes() {
    window.soundEnabled = !window.soundEnabled;
    const btn = document.getElementById('sound-toggle-btn');
    if (btn) {
        btn.innerHTML = window.soundEnabled ? '<i class="fa-solid fa-volume-high"></i>' : '<i class="fa-solid fa-volume-xmark"></i>';
        showToast(window.soundEnabled ? 'Audio Chimes Enabled' : 'Audio Chimes Muted', 'info');
    }
}

function playMessageChime() {
    if (!window.soundEnabled) return;
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.frequency.setValueAtTime(523.25, audioCtx.currentTime); // C5
        osc.frequency.exponentialRampToValueAtTime(783.99, audioCtx.currentTime + 0.08); // G5
        gain.gain.setValueAtTime(0.12, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.22);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.22);
    } catch (e) {}
}

function playTakeoverChime() {
    if (!window.soundEnabled) return;
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const playTone = (freq, start, dur) => {
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            osc.type = 'sine';
            osc.frequency.value = freq;
            gain.gain.setValueAtTime(0, start);
            gain.gain.linearRampToValueAtTime(0.2, start + 0.05);
            gain.gain.exponentialRampToValueAtTime(0.0001, start + dur);
            osc.start(start);
            osc.stop(start + dur);
        };
        playTone(587.33, audioCtx.currentTime, 0.3);
        playTone(880.00, audioCtx.currentTime + 0.12, 0.35);
    } catch (e) {}
}

// --- TAB 3: LEADS CRM & VISUAL KANBAN ---
function setLeadView(view) {
    window.currentLeadView = view;
    document.getElementById('btn-view-kanban').classList.toggle('active', view === 'kanban');
    document.getElementById('btn-view-table').classList.toggle('active', view === 'table');
    document.getElementById('leads-kanban-container').style.display = view === 'kanban' ? 'flex' : 'none';
    document.getElementById('leads-table-container').style.display = view === 'table' ? 'block' : 'none';
    renderLeads();
}

async function fetchLeads() {
    try {
        const filter = document.getElementById('lead-status-filter').value;
        const res = await fetch(`/api/leads?status=${filter}`);
        const data = await res.json();
        window.leadsData = data.leads || [];

        const hotBadge = document.getElementById('hot-leads-count');
        const hotCount = (window.leadsData).filter(l => l.status === 'hot').length;
        if (hotBadge) hotBadge.innerText = hotCount;

        renderLeads();
        fetchCRMStats();
    } catch (err) {
        console.error('Error fetching leads:', err);
    }
}

function renderLeads() {
    filterLeadsLocally();
}

function filterLeadsLocally() {
    const query = (document.getElementById('lead-search-input')?.value || '').toLowerCase().trim();
    let leads = window.leadsData || [];
    if (query) {
        leads = leads.filter(l => {
            return (l.name && l.name.toLowerCase().includes(query)) ||
                   (l.phone && l.phone.includes(query)) ||
                   (l.course_interest && l.course_interest.toLowerCase().includes(query)) ||
                   (l.email && l.email.toLowerCase().includes(query)) ||
                   (l.status && l.status.toLowerCase().includes(query));
        });
    }
    renderKanbanBoard(leads);
    renderTableLeads(leads);
}

function openChatForLead(phone, name) {
    switchToTab('handoff');
    selectConversation(phone, name);
    showToast(`Opened WhatsApp chat for ${name || phone}`, 'info');
}

function renderKanbanBoard(leads) {
    const container = document.getElementById('leads-kanban-container');
    if (!container) return;

    const stages = [
        { id: 'new', name: '🆕 New Leads', color: '#3b82f6' },
        { id: 'qualified', name: '✅ Qualified', color: '#10b981' },
        { id: 'hot', name: '🔥 Hot Prospects', color: '#ef4444' },
        { id: 'call_booked', name: '📅 Call Booked', color: '#8b5cf6' },
        { id: 'enrolled', name: '🎉 Enrolled / Won', color: '#f59e0b' }
    ];

    container.innerHTML = '';

    stages.forEach(st => {
        const matchingLeads = leads.filter(l => {
            if (st.id === 'call_booked') return l.status === 'call_booked' || (l.notes && l.notes.includes('Call Scheduled'));
            return l.status === st.id;
        });

        const col = document.createElement('div');
        col.className = 'kanban-column';
        col.innerHTML = `
            <div class="kanban-header" style="border-top: 3px solid ${st.color};">
                <span>${st.name}</span>
                <span class="badge" style="background: rgba(255,255,255,0.08);">${matchingLeads.length}</span>
            </div>
            <div class="kanban-cards-list">
                ${matchingLeads.map(l => createKanbanCardHtml(l)).join('')}
                ${matchingLeads.length === 0 ? '<div style="font-size: 0.72rem; color: var(--text-muted); text-align: center; padding: 1.5rem 0;">No leads in stage</div>' : ''}
            </div>
        `;
        container.appendChild(col);
    });
}

function createKanbanCardHtml(lead) {
    let scoreBadge = '';
    if (lead.status === 'hot' || lead.budget_ready) {
        scoreBadge = '<span class="lead-score hot">🔥 95</span>';
    } else if (lead.status === 'qualified' || (lead.email && lead.email.includes('@'))) {
        scoreBadge = '<span class="lead-score warm">⚡ 75</span>';
    } else {
        scoreBadge = '<span class="lead-score cold">❄️ 40</span>';
    }

    return `
        <div class="kanban-card">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                <div class="kanban-card-title">${escapeHtml(lead.name || 'Student')}</div>
                ${scoreBadge}
            </div>
            <div class="kanban-card-course"><i class="fa-solid fa-graduation-cap"></i> ${escapeHtml(lead.course_interest || 'General Tech')}</div>
            <div class="kanban-card-meta" style="display: flex; justify-content: space-between; align-items: center; margin-top: 0.5rem;">
                <div style="display: flex; gap: 0.3rem;">
                    <button class="btn btn-secondary" style="font-size: 0.7rem; padding: 0.2rem 0.5rem; background: rgba(37,211,102,0.15); color: #25D366; border: 1px solid rgba(37,211,102,0.3);" onclick="openChatForLead('${lead.phone}', '${escapeHtml(lead.name || '')}')"><i class="fa-solid fa-comments"></i> Chat</button>
                    <button class="btn btn-secondary" style="font-size: 0.7rem; padding: 0.2rem 0.5rem; background: rgba(56,189,248,0.15); color: #38bdf8; border: 1px solid rgba(56,189,248,0.3);" onclick="openEmailComposerForLead(${lead.id}, '${escapeHtml(lead.name || '')}', '${escapeHtml(lead.email || '')}', '${escapeHtml(lead.course_interest || '')}')" title="Compose Custom Email"><i class="fa-solid fa-envelope"></i></button>
                    <button class="btn btn-secondary" style="font-size: 0.7rem; padding: 0.2rem 0.5rem; background: rgba(235,103,17,0.15); color: #ff8c3a; border: 1px solid rgba(235,103,17,0.3);" onclick="promptQuickConversionEmail(${lead.id}, '${escapeHtml(lead.name || '')}', '${escapeHtml(lead.email || '')}')" title="1-Click Conversion Follow-Up"><i class="fa-solid fa-bolt"></i></button>
                </div>
                <select class="kanban-stage-select" onchange="updateLeadStage(${lead.id}, this.value)">
                    <option value="new" ${lead.status === 'new' ? 'selected' : ''}>New</option>
                    <option value="qualified" ${lead.status === 'qualified' ? 'selected' : ''}>Qualified</option>
                    <option value="hot" ${lead.status === 'hot' ? 'selected' : ''}>Hot</option>
                    <option value="enrolled" ${lead.status === 'enrolled' ? 'selected' : ''}>Enrolled</option>
                    <option value="cold" ${lead.status === 'cold' ? 'selected' : ''}>Cold</option>
                </select>
            </div>
        </div>
    `;
}

function renderTableLeads(leads) {
    const tbody = document.getElementById('leads-table-body');
    if (!tbody) return;
    if (leads.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center">No leads found matching search.</td></tr>';
        return;
    }
    tbody.innerHTML = '';
    leads.forEach(l => {
        let scoreBadge = l.status === 'hot' ? '<span class="lead-score hot">🔥 95</span>' : (l.status === 'qualified' ? '<span class="lead-score warm">⚡ 75</span>' : '<span class="lead-score cold">❄️ 40</span>');
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>#${l.id}</td>
            <td><strong>${escapeHtml(l.name || 'Prospect')}</strong></td>
            <td>+${l.phone}</td>
            <td>${escapeHtml(l.email || '—')}</td>
            <td>${escapeHtml(l.course_interest || 'Tech')}</td>
            <td><span class="pill pill-${l.status}">${l.status}</span></td>
            <td>${scoreBadge}</td>
            <td style="max-width: 220px; font-size: 0.75rem; color: var(--text-muted);">${escapeHtml(l.notes || '—')}</td>
            <td>
                <div style="display: flex; gap: 0.35rem; align-items: center;">
                    <button class="btn btn-sm btn-secondary" style="font-size: 0.7rem; padding: 0.2rem 0.45rem; background: rgba(37,211,102,0.15); color: #25D366; border: 1px solid rgba(37,211,102,0.3);" onclick="openChatForLead('${l.phone}', '${escapeHtml(l.name || '')}')" title="Open WhatsApp Chat"><i class="fa-solid fa-comments"></i></button>
                    <button class="btn btn-sm btn-secondary" style="font-size: 0.7rem; padding: 0.2rem 0.45rem; background: rgba(56,189,248,0.15); color: #38bdf8; border: 1px solid rgba(56,189,248,0.3);" onclick="openEmailComposerForLead(${l.id}, '${escapeHtml(l.name || '')}', '${escapeHtml(l.email || '')}', '${escapeHtml(l.course_interest || '')}')" title="Compose Custom Email"><i class="fa-solid fa-envelope"></i></button>
                    <button class="btn btn-sm btn-secondary" style="font-size: 0.7rem; padding: 0.2rem 0.45rem; background: rgba(235,103,17,0.15); color: #ff8c3a; border: 1px solid rgba(235,103,17,0.3);" onclick="promptQuickConversionEmail(${l.id}, '${escapeHtml(l.name || '')}', '${escapeHtml(l.email || '')}')" title="1-Click Conversion Follow-Up"><i class="fa-solid fa-bolt"></i></button>
                    <select class="kanban-stage-select" onchange="updateLeadStage(${l.id}, this.value)">
                        <option value="new" ${l.status === 'new' ? 'selected' : ''}>New</option>
                        <option value="qualified" ${l.status === 'qualified' ? 'selected' : ''}>Qualified</option>
                        <option value="hot" ${l.status === 'hot' ? 'selected' : ''}>Hot</option>
                        <option value="enrolled" ${l.status === 'enrolled' ? 'selected' : ''}>Enrolled</option>
                    </select>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

async function updateLeadStage(leadId, newStage) {
    try {
        const res = await fetch(`/api/crm/lead/${leadId}/status`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ status: newStage })
        });
        if (res.ok) {
            showToast(`Lead moved to ${newStage.toUpperCase()} stage!`);
            fetchLeads();
            fetchCRMStats();
        }
    } catch (err) {
        console.error('Error updating stage:', err);
    }
}

// --- TAB 4: BROADCASTS & CAMPAIGNS ---
async function fetchCampaigns() {
    try {
        const res = await fetch('/api/campaigns');
        const data = await res.json();
        window.campaignsData = data.campaigns || [];
        renderCampaignTemplates();
        if (window.campaignsData.length > 0 && !window.selectedCampaignId) {
            selectCampaign(window.campaignsData[0].id);
        }
    } catch (err) {
        console.error('Error fetching campaigns:', err);
    }
}

window.currentCampaignCategory = 'all';

function filterCampaignCategory(category) {
    window.currentCampaignCategory = category;
    document.querySelectorAll('.campaign-cat-btn').forEach(btn => {
        if (btn.getAttribute('data-cat') === category) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    const filtered = (window.campaignsData || []).filter(c => 
        category === 'all' || c.category === category
    );

    if (filtered.length > 0 && !filtered.some(c => c.id === window.selectedCampaignId)) {
        window.selectedCampaignId = filtered[0].id;
        selectCampaign(filtered[0].id);
    } else {
        renderCampaignTemplates();
    }
}

function renderCampaignTemplates() {
    const grid = document.getElementById('campaign-templates-grid');
    if (!grid) return;
    grid.innerHTML = '';

    const currentCat = window.currentCampaignCategory || 'all';
    const templates = (window.campaignsData || []).filter(c => 
        currentCat === 'all' || c.category === currentCat
    );

    if (templates.length === 0) {
        grid.innerHTML = `<div style="grid-column: 1 / -1; text-align: center; padding: 2rem; color: var(--text-muted);">No templates found for this category.</div>`;
        return;
    }

    templates.forEach(c => {
        const isSelected = c.id === window.selectedCampaignId ? 'selected' : '';
        const card = document.createElement('div');
        card.className = `campaign-card ${isSelected}`;
        card.onclick = () => selectCampaign(c.id);

        card.innerHTML = `
            <div>
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
                    <span class="badge" style="background: rgba(235,103,17,0.15); color: #ff8c3a; font-size: 0.68rem;">${escapeHtml(c.category)}</span>
                    <span style="font-size: 0.72rem; color: #10b981; font-weight: 600;">CTR: ${c.stats.click_rate}</span>
                </div>
                <h4 style="font-size: 0.95rem; margin-bottom: 0.35rem; color: #fff;">${escapeHtml(c.title)}</h4>
                <p style="font-size: 0.78rem; color: var(--text-muted); line-height: 1.35;">${escapeHtml(c.description)}</p>
            </div>
            <div style="margin-top: 0.75rem; padding-top: 0.5rem; border-top: 1px solid var(--border-color); font-size: 0.72rem; color: var(--text-muted); display: flex; justify-content: space-between;">
                <span>Audience: <strong>${c.target_audience.toUpperCase()}</strong></span>
                <span style="color: #ff8c3a;">Select & Preview →</span>
            </div>
        `;
        grid.appendChild(card);
    });
}

function selectCampaign(id) {
    window.selectedCampaignId = id;
    renderCampaignTemplates();
    const campaign = window.campaignsData.find(c => c.id === id);
    if (!campaign) return;

    document.getElementById('campaign-selected-badge').innerText = campaign.category;
    document.getElementById('broadcast-audience-select').value = campaign.target_audience || 'all';
    updateBroadcastPreview();
}

function updateBroadcastPreview() {
    const campaign = window.campaignsData.find(c => c.id === window.selectedCampaignId);
    if (!campaign) return;

    const sampleName = 'Alex';
    const sampleCourse = 'Data Analytics';
    let text = campaign.template_body.replace('{{name}}', sampleName).replace('{{course}}', sampleCourse);

    document.getElementById('broadcast-preview-message').innerHTML = formatWhatsAppText(text);

    const actionsContainer = document.getElementById('broadcast-preview-actions');
    actionsContainer.innerHTML = (campaign.suggested_actions || []).map(act => `
        <div style="background: #111b21; border: 1px solid #202c33; color: #00a884; font-size: 0.75rem; padding: 0.4rem; border-radius: 6px; text-align: center; font-weight: 600;">
            🔘 [ ${escapeHtml(act)} ]
        </div>
    `).join('');
}

async function dispatchBroadcastCampaign() {
    if (!window.selectedCampaignId) return;
    const btn = document.getElementById('btn-dispatch-campaign');
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Dispatching Broadcast...';

    const audience = document.getElementById('broadcast-audience-select').value;

    try {
        const res = await fetch('/api/campaigns/send', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                campaign_id: window.selectedCampaignId,
                target_audience: audience
            })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(`🚀 Broadcast sent successfully to ${data.recipients_count} leads!`);
            fetchConversations();
        } else {
            alert('Failed to dispatch campaign.');
        }
    } catch (err) {
        console.error('Error sending broadcast:', err);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-rocket"></i> Launch WhatsApp Broadcast';
    }
}

async function sendTestBroadcast() {
    if (!window.selectedCampaignId) {
        showToast('Please select a campaign template first', 'info');
        return;
    }
    const testPhone = (document.getElementById('broadcast-test-phone')?.value || '2348012345678').trim();
    showToast(`Sending test template preview to +${testPhone}...`, 'info');
    try {
        const res = await fetch('/api/campaigns/send', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                campaign_id: window.selectedCampaignId,
                target_phone: testPhone
            })
        });
        const data = await res.json();
        if (res.ok) {
            showToast(`✅ Test broadcast dispatched to +${testPhone}! Check Simulator or WhatsApp.`);
            fetchConversations();
        } else {
            showToast('Failed to send test broadcast', 'info');
        }
    } catch (err) {
        console.error('Error sending test broadcast:', err);
    }
}

// --- TAB 5: APPOINTMENTS & CONSULTATIONS ---
async function fetchAppointments() {
    try {
        const res = await fetch('/api/appointments');
        const data = await res.json();
        window.appointmentsData = data.appointments || [];

        const countBadge = document.getElementById('appointments-count');
        if (countBadge) countBadge.innerText = window.appointmentsData.length;

        const tbody = document.getElementById('appointments-table-body');
        if (!tbody) return;

        if (window.appointmentsData.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center">No admissions consultations scheduled yet. Students can schedule calls automatically in chat!</td></tr>';
            return;
        }

        tbody.innerHTML = '';
        window.appointmentsData.forEach(a => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>#${a.id}</td>
                <td><strong>${escapeHtml(a.name)}</strong></td>
                <td>+${a.phone}</td>
                <td><span class="pill pill-ai">${escapeHtml(a.service_or_course)}</span></td>
                <td><strong style="color: #38bdf8;"><i class="fa-regular fa-clock"></i> ${escapeHtml(a.preferred_time)}</strong></td>
                <td><span class="pill ${a.status === 'scheduled' ? 'pill-ai' : (a.status === 'completed' ? 'pill-qualified' : 'pill-human')}">${a.status}</span></td>
                <td>${a.created_at}</td>
                <td>
                    <select class="kanban-stage-select" onchange="updateAppointmentStatus(${a.id}, this.value)">
                        <option value="scheduled" ${a.status === 'scheduled' ? 'selected' : ''}>Scheduled</option>
                        <option value="completed" ${a.status === 'completed' ? 'selected' : ''}>Completed</option>
                        <option value="cancelled" ${a.status === 'cancelled' ? 'selected' : ''}>Cancelled</option>
                    </select>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error('Error fetching appointments:', err);
    }
}

async function updateAppointmentStatus(id, status) {
    try {
        const res = await fetch(`/api/appointments/${id}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ status: status })
        });
        if (res.ok) {
            showToast(`Appointment status updated to ${status}`);
            fetchAppointments();
        }
    } catch (err) {
        console.error('Error updating appointment:', err);
    }
}

// --- TAB 6 & 7: COURSES & FAQS ---
async function fetchCourses() {
    try {
        const res = await fetch('/api/courses');
        const data = await res.json();
        const container = document.getElementById('courses-container');
        if (!data.courses || data.courses.length === 0) {
            container.innerHTML = '<div class="empty-state">No courses in database.</div>';
            return;
        }
        window.coursesData = {};
        container.innerHTML = '';
        data.courses.forEach(c => {
            window.coursesData[c.id] = c;
            const card = document.createElement('div');
            card.className = 'course-card';
            card.innerHTML = `
                <div class="card-header" style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <h3 style="font-size: 1.05rem; margin: 0;">${escapeHtml(c.title)}</h3>
                    <div class="card-actions" style="display: flex; gap: 0.35rem;">
                        <button class="btn-icon" onclick="openEditCourseModal(${c.id})"><i class="fa-solid fa-pen-to-square"></i></button>
                        <button class="btn-icon" style="color: var(--status-hot);" onclick="deleteCourse(${c.id})"><i class="fa-solid fa-trash"></i></button>
                    </div>
                </div>
                <div class="course-price">₦${c.price.toLocaleString()} per month <span style="font-size:0.8rem; color:var(--text-muted);">(${c.duration_weeks} Weeks)</span></div>
                <p style="font-size:0.85rem; color:var(--text-muted);">${escapeHtml(c.description)}</p>
                <div style="font-size:0.8rem; background:rgba(255,255,255,0.05); padding:0.6rem; border-radius:8px; display: flex; flex-direction: column; gap: 0.25rem;">
                    <div><strong>Syllabus:</strong> ${escapeHtml(c.syllabus)}</div>
                    <div><strong>Prerequisites:</strong> ${escapeHtml(c.prerequisites)}</div>
                    <div><strong>Outcomes:</strong> ${escapeHtml(c.career_outcomes)}</div>
                </div>
                <button class="btn btn-secondary btn-sm" style="margin-top: 0.65rem; width: 100%; font-size: 0.76rem; padding: 0.35rem 0.6rem; border-color: rgba(37,211,102,0.3); color: #25D366; background: rgba(37,211,102,0.08);" onclick="pitchCourseInSimulator('${escapeHtml(c.title)}')">
                    <i class="fa-brands fa-whatsapp"></i> Test Pitch in Simulator
                </button>
            `;
            container.appendChild(card);
        });
    } catch (err) {
        console.error('Error fetching courses:', err);
    }
}

async function fetchFAQs() {
    try {
        const res = await fetch('/api/faqs');
        const data = await res.json();
        const tbody = document.getElementById('faqs-table-body');
        if (!data.faqs || data.faqs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center">No FAQs recorded yet.</td></tr>';
            return;
        }
        window.faqsData = {};
        tbody.innerHTML = '';
        data.faqs.forEach(f => {
            window.faqsData[f.id] = f;
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td><span class="pill" style="background: rgba(235, 103, 17, 0.15); color: #ff8c3a;">${escapeHtml(f.category)}</span></td>
                <td><strong>${escapeHtml(f.question)}</strong></td>
                <td><p style="font-size:0.85rem; max-width: 400px; white-space: pre-wrap; margin: 0; color: var(--text-muted);">${escapeHtml(f.answer)}</p></td>
                <td>
                    <div style="display: flex; gap: 0.5rem;">
                        <button class="btn btn-secondary" style="padding: 0.35rem 0.6rem; font-size: 0.75rem;" onclick="openEditFaqModal(${f.id})"><i class="fa-solid fa-pen-to-square"></i> Edit</button>
                        <button class="btn btn-secondary" style="padding: 0.35rem 0.6rem; font-size: 0.75rem; color: var(--status-hot);" onclick="deleteFaq(${f.id})"><i class="fa-solid fa-trash"></i> Delete</button>
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error('Error fetching FAQs:', err);
    }
}

// Course and FAQ Modals
function openAddCourseModal() {
    document.getElementById('course-modal-title').innerText = 'Add New Course';
    document.getElementById('course-id').value = '';
    document.getElementById('course-form').reset();
    document.getElementById('course-modal').style.display = 'flex';
}
function openEditCourseModal(id) {
    const c = window.coursesData[id];
    if (!c) return;
    document.getElementById('course-modal-title').innerText = 'Edit Course';
    document.getElementById('course-id').value = c.id;
    document.getElementById('course-title').value = c.title;
    document.getElementById('course-slug').value = c.slug;
    document.getElementById('course-price').value = c.price;
    document.getElementById('course-duration').value = c.duration_weeks;
    document.getElementById('course-description').value = c.description;
    document.getElementById('course-syllabus').value = c.syllabus;
    document.getElementById('course-prerequisites').value = c.prerequisites;
    document.getElementById('course-outcomes').value = c.career_outcomes;
    document.getElementById('course-active').checked = c.is_active;
    document.getElementById('course-modal').style.display = 'flex';
}
function closeCourseModal() { document.getElementById('course-modal').style.display = 'none'; }
async function saveCourse(e) {
    e.preventDefault();
    const id = document.getElementById('course-id').value;
    const courseData = {
        title: document.getElementById('course-title').value,
        slug: document.getElementById('course-slug').value,
        price: parseFloat(document.getElementById('course-price').value),
        duration_weeks: parseInt(document.getElementById('course-duration').value),
        description: document.getElementById('course-description').value,
        syllabus: document.getElementById('course-syllabus').value,
        prerequisites: document.getElementById('course-prerequisites').value,
        career_outcomes: document.getElementById('course-outcomes').value,
        is_active: document.getElementById('course-active').checked
    };
    try {
        const method = id ? 'PUT' : 'POST';
        const url = id ? `/api/courses/${id}` : '/api/courses';
        const res = await fetch(url, {
            method: method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(courseData)
        });
        if (res.ok) {
            closeCourseModal();
            fetchCourses();
            showToast('Course catalog updated successfully!');
        }
    } catch (err) { console.error(err); }
}
async function deleteCourse(id) {
    if (!confirm('Are you sure you want to delete this course?')) return;
    try {
        const res = await fetch(`/api/courses/${id}`, { method: 'DELETE' });
        if (res.ok) { fetchCourses(); showToast('Course deleted'); }
    } catch (err) { console.error(err); }
}

function openAddFaqModal() {
    document.getElementById('faq-modal-title').innerText = 'Add New FAQ';
    document.getElementById('faq-id').value = '';
    document.getElementById('faq-form').reset();
    document.getElementById('faq-modal').style.display = 'flex';
}
function openEditFaqModal(id) {
    const f = window.faqsData[id];
    if (!f) return;
    document.getElementById('faq-modal-title').innerText = 'Edit FAQ';
    document.getElementById('faq-id').value = f.id;
    document.getElementById('faq-category').value = f.category;
    document.getElementById('faq-question').value = f.question;
    document.getElementById('faq-answer').value = f.answer;
    document.getElementById('faq-modal').style.display = 'flex';
}
function closeFaqModal() { document.getElementById('faq-modal').style.display = 'none'; }
async function saveFaq(e) {
    e.preventDefault();
    const id = document.getElementById('faq-id').value;
    const faqData = {
        category: document.getElementById('faq-category').value,
        question: document.getElementById('faq-question').value,
        answer: document.getElementById('faq-answer').value
    };
    try {
        const method = id ? 'PUT' : 'POST';
        const url = id ? `/api/faqs/${id}` : '/api/faqs';
        const res = await fetch(url, {
            method: method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(faqData)
        });
        if (res.ok) {
            closeFaqModal();
            fetchFAQs();
            showToast('FAQ knowledge base updated!');
        }
    } catch (err) { console.error(err); }
}
async function deleteFaq(id) {
    if (!confirm('Are you sure you want to delete this FAQ?')) return;
    try {
        const res = await fetch(`/api/faqs/${id}`, { method: 'DELETE' });
        if (res.ok) { fetchFAQs(); showToast('FAQ deleted'); }
    } catch (err) { console.error(err); }
}

// --- TAB 8: SYSTEM SETTINGS ---
function selectPersonaTone(tone) {
    document.querySelectorAll('.persona-card').forEach(c => {
        c.classList.toggle('active', c.dataset.tone === tone);
    });
    document.getElementById('settings-persona-tone').value = tone;
    showToast(`AI Tone set to ${tone.toUpperCase()}`);
}

async function fetchSettings() {
    try {
        const res = await fetch('/api/settings');
        const data = await res.json();
        document.getElementById('settings-agent-name').value = data.agent_name || 'Tara';
        document.getElementById('settings-system-prompt').value = data.system_prompt || '';
        document.getElementById('settings-ai-enabled').checked = data.global_ai_enabled;

        const tone = data.persona_tone || 'consultative';
        selectPersonaTone(tone);

        if (document.getElementById('settings-business-hours')) {
            document.getElementById('settings-business-hours').value = data.business_hours || '9:00 AM - 6:00 PM (Mon-Sat)';
        }
        if (document.getElementById('settings-away-message')) {
            document.getElementById('settings-away-message').value = data.away_message || 'Thanks for contacting TekTutors! We are outside business hours, but our AI advisor is here 24/7.';
        }
        if (document.getElementById('settings-currency')) {
            document.getElementById('settings-currency').value = data.currency || 'NGN';
        }
        if (document.getElementById('settings-currency-symbol')) {
            document.getElementById('settings-currency-symbol').value = data.currency_symbol || '₦';
        }
        if (document.getElementById('settings-webhook-url')) {
            document.getElementById('settings-webhook-url').value = data.outbound_webhook_url || '';
        }
        if (document.getElementById('settings-webhook-secret')) {
            document.getElementById('settings-webhook-secret').value = data.outbound_webhook_secret || '';
        }
    } catch (err) {
        console.error('Error fetching settings:', err);
    }
}

function onCurrencyChange() {
    const sel = document.getElementById('settings-currency');
    const symbolInput = document.getElementById('settings-currency-symbol');
    if (!sel || !symbolInput) return;
    const map = { 'NGN': '₦', 'USD': '$', 'GBP': '£', 'EUR': '€' };
    symbolInput.value = map[sel.value] || '₦';
}

async function testWebhookPing() {
    const urlInput = document.getElementById('settings-webhook-url');
    const url = urlInput ? urlInput.value.trim() : '';
    if (!url) {
        showToast('Please enter a webhook endpoint URL first', 'warning');
        return;
    }
    showToast('Sending HMAC signed test ping to CRM webhook...', 'info');
    try {
        const res = await fetch('/api/settings/webhook-test', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ url: url })
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('✅ ' + data.message, 'success');
        } else {
            showToast('⚠️ ' + data.message, 'warning');
        }
    } catch (err) {
        showToast('Webhook endpoint unreachable', 'warning');
    }
}

function pitchCourseInSimulator(title) {
    switchToTab('simulator');
    sendSimPrompt(`Tell me about the ${title} training track and how to register`);
    showToast(`Pitching "${title}" in WhatsApp Simulator...`, 'info');
}

async function saveSettings(e) {
    e.preventDefault();
    const configData = {
        agent_name: document.getElementById('settings-agent-name').value,
        system_prompt: document.getElementById('settings-system-prompt').value,
        global_ai_enabled: document.getElementById('settings-ai-enabled').checked,
        persona_tone: document.getElementById('settings-persona-tone').value,
        business_hours: document.getElementById('settings-business-hours').value,
        away_message: document.getElementById('settings-away-message').value,
        currency: document.getElementById('settings-currency') ? document.getElementById('settings-currency').value : 'NGN',
        currency_symbol: document.getElementById('settings-currency-symbol') ? document.getElementById('settings-currency-symbol').value : '₦',
        outbound_webhook_url: document.getElementById('settings-webhook-url') ? document.getElementById('settings-webhook-url').value.trim() : null,
        outbound_webhook_secret: document.getElementById('settings-webhook-secret') ? document.getElementById('settings-webhook-secret').value.trim() : null
    };
    try {
        const res = await fetch('/api/settings', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(configData)
        });
        if (res.ok) {
            showToast('AI Settings & Integrations updated successfully!');
            fetchSettings();
            fetchCRMStats();
            fetchFunnelAnalytics();
        } else {
            alert('Failed to update system settings.');
        }
    } catch (err) {
        console.error('Failed to save settings:', err);
    }
}

async function fetchFunnelAnalytics() {
    try {
        const res = await fetch('/api/analytics/funnel');
        const data = await res.json();
        if (!data) return;

        if (document.getElementById('funnel-mrr')) document.getElementById('funnel-mrr').innerText = data.roi_metrics.projected_mrr;
        if (document.getElementById('funnel-cac')) document.getElementById('funnel-cac').innerText = data.roi_metrics.cac_cost_saved;
        if (document.getElementById('funnel-time')) document.getElementById('funnel-time').innerText = data.roi_metrics.human_advisor_time_freed;
        if (document.getElementById('funnel-speed')) document.getElementById('funnel-speed').innerText = data.roi_metrics.first_response_latency;
        if (document.getElementById('funnel-resolution')) document.getElementById('funnel-resolution').innerText = data.roi_metrics.self_service_resolution_rate;

        if (data.cost_optimization) {
            if (document.getElementById('funnel-tokens-saved')) document.getElementById('funnel-tokens-saved').innerText = data.cost_optimization.tokens_saved;
            if (document.getElementById('funnel-fast-path-rate')) document.getElementById('funnel-fast-path-rate').innerText = data.cost_optimization.fast_path_rate;
        }

        const enrolledStage = data.funnel.find(f => f.stage.includes('Enrolled'));
        if (document.getElementById('funnel-enrolled-count') && enrolledStage) {
            document.getElementById('funnel-enrolled-count').innerText = enrolledStage.count;
        }

        const stagesContainer = document.getElementById('funnel-stages-container');
        if (stagesContainer && data.funnel) {
            stagesContainer.innerHTML = '';
            const colors = ['#38bdf8', '#ff8c3a', '#f59e0b', '#25D366', '#10b981'];
            data.funnel.forEach((f, idx) => {
                const stageDiv = document.createElement('div');
                stageDiv.className = 'funnel-stage-item';
                const col = colors[idx % colors.length];
                stageDiv.innerHTML = `
                    <div class="funnel-stage-meta">
                        <span><strong>${escapeHtml(f.stage)}</strong> <small style="color:var(--text-muted);">(${escapeHtml(f.description)})</small></span>
                        <span><strong style="color:${col}; font-size:0.95rem;">${f.count}</strong> <span style="font-size:0.75rem; color:var(--text-muted);">(${f.percentage}%)</span></span>
                    </div>
                    <div class="funnel-progress-track">
                        <div class="funnel-progress-fill" style="width: ${Math.max(f.percentage, 4)}%; background: ${col};"></div>
                    </div>
                `;
                stagesContainer.appendChild(stageDiv);
            });
        }

        const channelsContainer = document.getElementById('funnel-channels-container');
        if (channelsContainer && data.channels) {
            channelsContainer.innerHTML = '';
            const channelColors = ['#25D366', '#ec4899', '#38bdf8', '#c084fc'];
            data.channels.forEach((ch, idx) => {
                const chDiv = document.createElement('div');
                chDiv.className = 'channel-item';
                const col = channelColors[idx % channelColors.length];
                chDiv.innerHTML = `
                    <div class="channel-meta">
                        <span><strong>${escapeHtml(ch.channel)}</strong></span>
                        <span><strong style="color:${col};">${ch.share}%</strong> <small style="color:var(--text-muted);">(${ch.leads} leads)</small></span>
                    </div>
                    <div class="channel-track">
                        <div class="channel-fill" style="width: ${ch.share}%; background: ${col};"></div>
                    </div>
                `;
                channelsContainer.appendChild(chDiv);
            });
        }
    } catch (err) {
        console.error('Error fetching funnel analytics:', err);
    }
}

// --- STATS & EXPORT ---
async function fetchCRMStats() {
    try {
        const res = await fetch('/api/crm/stats');
        const data = await res.json();
        if (document.getElementById('kpi-pipeline')) document.getElementById('kpi-pipeline').innerText = data.pipeline_value;
        if (document.getElementById('kpi-conversion')) document.getElementById('kpi-conversion').innerText = data.conversion_rate;
        if (document.getElementById('kpi-leads')) document.getElementById('kpi-leads').innerText = data.total_leads;
        if (document.getElementById('kpi-hot')) document.getElementById('kpi-hot').innerText = data.hot_leads;
        if (document.getElementById('kpi-automation')) document.getElementById('kpi-automation').innerText = data.automation_rate || '94.2%';
        if (document.getElementById('kpi-hours')) document.getElementById('kpi-hours').innerText = data.hours_saved || '18.5 hrs';
    } catch (err) {
        console.error('Error fetching CRM stats:', err);
    }
}

function exportLeads() {
    window.location.href = '/api/crm/export';
}

// Co-pilot suggestions
async function loadCopilotSuggestions(phone) {
    const container = document.getElementById('copilot-dynamic-suggestions');
    if (!container) return;
    try {
        const res = await fetch('/api/copilot/suggest', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ phone: phone })
        });
        const data = await res.json();
        container.innerHTML = '';
        if (data.suggestions && data.suggestions.length > 0) {
            data.suggestions.forEach(s => {
                const btn = document.createElement('button');
                btn.className = 'chip copilot-chip';
                btn.title = 'Click to insert into advisor reply box';
                btn.innerHTML = `${escapeHtml(s.title)}`;
                btn.onclick = () => { document.getElementById('human-message-input').value = s.text; };
                container.appendChild(btn);
            });
        }
    } catch (err) {
        console.error('Error loading copilot suggestions:', err);
    }
}

function useCopilotSuggestion() {
    const draftText = document.getElementById('copilot-draft-text').innerText;
    if (draftText && draftText !== 'Generating suggested response...') {
        document.getElementById('human-message-input').value = draftText;
    }
}

function applyTemplate(text) {
    document.getElementById('human-message-input').value = text;
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

// =========================================================================
// EMAIL HUB & MARKETING CAMPAIGN CLIENT LOGIC
// =========================================================================
window.emailTemplates = [];
window.currentEmailCategory = 'all';
window.emailPreviewDebounceTimer = null;

async function loadEmailHub() {
    await Promise.all([
        fetchEmailStats(),
        fetchEmailTemplates(),
        fetchEmailLogs()
    ]);
}

async function fetchEmailStats() {
    try {
        const res = await fetch('/api/emails/stats');
        if (!res.ok) return;
        const stats = await res.json();
        const totalEl = document.getElementById('email-kpi-total');
        const followEl = document.getElementById('email-kpi-followup');
        const mktEl = document.getElementById('email-kpi-marketing');
        const rateEl = document.getElementById('email-kpi-rate');

        if (totalEl) totalEl.innerText = stats.total_dispatched || 0;
        if (followEl) followEl.innerText = stats.follow_up_count || 0;
        if (mktEl) mktEl.innerText = (stats.marketing_count || 0) + (stats.promotional_count || 0);
        if (rateEl) rateEl.innerText = `${stats.delivery_rate || 100}%`;
    } catch (err) {
        console.error('Error loading email stats:', err);
    }
}

async function fetchEmailTemplates() {
    try {
        const res = await fetch('/api/emails/templates');
        if (!res.ok) return;
        window.emailTemplates = await res.json();
        renderEmailTemplates();
    } catch (err) {
        console.error('Error fetching email templates:', err);
    }
}

function renderEmailTemplates() {
    const grid = document.getElementById('email-templates-grid');
    if (!grid) return;

    const activeCat = window.currentEmailCategory || 'all';
    const templates = window.emailTemplates || [];
    const filtered = (activeCat === 'all')
        ? templates
        : templates.filter(t => t.category === activeCat);

    // Sync composer dropdown
    const select = document.getElementById('composer-template-select');
    if (select && templates.length > 0) {
        const curVal = select.value;
        select.innerHTML = '<option value="">-- Choose High-Converting Campaign Template --</option>' +
            templates.map(t => `<option value="${t.id}">${escapeHtml(t.badge || t.category)}: ${escapeHtml(t.title)}</option>`).join('');
        if (curVal) select.value = curVal;
    }

    if (!filtered || filtered.length === 0) {
        grid.innerHTML = '<div class="empty-state" style="grid-column: 1/-1;">No templates found for this category.</div>';
        return;
    }

    grid.innerHTML = filtered.map(t => {
        const badgeClass = `email-badge-${t.category}`;
        const previewExcerpt = t.body ? t.body.substring(0, 115).replace(/[*#•]/g, '') + '...' : '';
        return `
            <div class="email-template-card">
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.6rem;">
                        <span class="email-badge ${badgeClass}">${escapeHtml(t.badge || t.category)}</span>
                        <span style="font-size: 0.7rem; color: var(--text-muted);"><i class="fa-solid fa-code-branch"></i> Automated</span>
                    </div>
                    <h4 style="font-size: 0.95rem; color: #fff; margin-bottom: 0.4rem; font-weight: 600;">${escapeHtml(t.title)}</h4>
                    <div style="font-size: 0.76rem; color: #38bdf8; font-weight: 500; margin-bottom: 0.5rem;">
                        <i class="fa-solid fa-envelope"></i> ${escapeHtml(t.subject)}
                    </div>
                    <p style="font-size: 0.74rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 1rem;">
                        ${escapeHtml(previewExcerpt)}
                    </p>
                </div>
                <div style="display: flex; gap: 0.4rem; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 0.75rem;">
                    <button class="btn btn-sm btn-secondary" style="flex: 1; font-size: 0.72rem; padding: 0.35rem;" onclick="previewTemplateInModal('${t.id}')">
                        <i class="fa-solid fa-eye"></i> Preview
                    </button>
                    <button class="btn btn-sm btn-secondary" style="flex: 1.1; font-size: 0.72rem; padding: 0.35rem; background: rgba(56,189,248,0.15); color: #38bdf8; border: 1px solid rgba(56,189,248,0.3);" onclick="openEmailComposer(null, '${t.id}', 'single')">
                        <i class="fa-solid fa-user"></i> 1-on-1 Send
                    </button>
                    <button class="btn btn-sm btn-primary" style="flex: 1.2; font-size: 0.72rem; padding: 0.35rem;" onclick="openEmailComposer(null, '${t.id}', 'broadcast')">
                        <i class="fa-solid fa-bullhorn"></i> Broadcast
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function filterEmailTemplates(category) {
    window.currentEmailCategory = category;
    document.querySelectorAll('.email-cat-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.cat === category);
    });
    renderEmailTemplates();
}

async function fetchEmailLogs() {
    try {
        const res = await fetch('/api/emails/logs?limit=40');
        if (!res.ok) return;
        const logs = await res.json();
        const tbody = document.getElementById('email-logs-table-body');
        if (!tbody) return;

        if (!logs || logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center">No emails dispatched yet.</td></tr>';
            return;
        }

        tbody.innerHTML = logs.map(l => {
            const statusPill = l.status === 'delivered' || l.status === 'sent'
                ? `<span class="pill-delivered"><i class="fa-solid fa-check"></i> ${l.status.toUpperCase()}</span>`
                : `<span class="pill-failed"><i class="fa-solid fa-triangle-exclamation"></i> FAILED</span>`;
            const badgeClass = `email-badge-${l.campaign_type}`;

            return `
                <tr>
                    <td>#${l.id}</td>
                    <td><strong>${escapeHtml(l.recipient_email)}</strong></td>
                    <td>${escapeHtml(l.recipient_name || 'Student')}</td>
                    <td><span class="email-badge ${badgeClass}">${l.campaign_type}</span></td>
                    <td style="max-width: 250px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(l.subject)}</td>
                    <td>${statusPill}</td>
                    <td style="font-size: 0.75rem; color: var(--text-muted);">${l.sent_at || ''}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary" style="font-size: 0.68rem; padding: 0.18rem 0.45rem; background: rgba(56,189,248,0.15); color: #38bdf8; border: 1px solid rgba(56,189,248,0.3);" onclick="viewEmailLogDetail(${l.id})" title="Inspect Dispatched Email">
                            <i class="fa-solid fa-eye"></i> View
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    } catch (err) {
        console.error('Error loading email logs:', err);
    }
}

function setComposerMode(mode) {
    const singleFields = document.getElementById('composer-single-fields');
    const broadcastFields = document.getElementById('composer-broadcast-fields');
    const modalTitle = document.getElementById('email-modal-title');
    const submitBtn = document.getElementById('btn-submit-email');
    const btnSingle = document.getElementById('btn-mode-single');
    const btnBroadcast = document.getElementById('btn-mode-broadcast');

    document.getElementById('composer-mode').value = mode;

    if (btnSingle) btnSingle.classList.toggle('active', mode === 'single');
    if (btnBroadcast) btnBroadcast.classList.toggle('active', mode === 'broadcast');

    if (mode === 'broadcast') {
        if (singleFields) singleFields.style.display = 'none';
        if (broadcastFields) broadcastFields.style.display = 'block';
        if (modalTitle) modalTitle.innerHTML = '<i class="fa-solid fa-bullhorn" style="color: #c084fc;"></i> Broadcast Campaign Dispatcher';
        if (submitBtn) submitBtn.innerHTML = '<i class="fa-solid fa-rocket"></i> Launch Broadcast Campaign';
    } else {
        if (singleFields) singleFields.style.display = 'block';
        if (broadcastFields) broadcastFields.style.display = 'none';
        if (modalTitle) modalTitle.innerHTML = '<i class="fa-solid fa-paper-plane" style="color: #38bdf8;"></i> Compose &amp; Dispatch Email';
        if (submitBtn) submitBtn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Send Email Now';
    }
    updateEmailLivePreview();
}

function onComposerTemplateSelected(templateId) {
    if (!templateId) return;
    const t = (window.emailTemplates || []).find(tpl => tpl.id === templateId);
    if (!t) return;

    document.getElementById('composer-subject').value = t.subject || '';
    document.getElementById('composer-body').value = t.body || '';
    document.getElementById('composer-campaign-type').value = t.category || 'follow_up';
    if (t.cta_text) document.getElementById('composer-cta-text').value = t.cta_text;
    if (t.cta_url) document.getElementById('composer-cta-url').value = t.cta_url;
    updateEmailLivePreview();
}

function openEmailComposer(leadId = null, templateId = null, mode = 'single') {
    const modal = document.getElementById('email-composer-modal');
    if (!modal) return;

    document.getElementById('composer-lead-id').value = leadId || '';

    // Ensure templates dropdown is populated
    const select = document.getElementById('composer-template-select');
    if (select && select.options.length <= 1 && (window.emailTemplates || []).length > 0) {
        select.innerHTML = '<option value="">-- Choose High-Converting Campaign Template --</option>' +
            window.emailTemplates.map(t => `<option value="${t.id}">${escapeHtml(t.badge || t.category)}: ${escapeHtml(t.title)}</option>`).join('');
    }

    setComposerMode(mode);

    if (templateId) {
        if (select) select.value = templateId;
        onComposerTemplateSelected(templateId);
    } else if (!document.getElementById('composer-subject').value) {
        document.getElementById('composer-subject').value = "Great connecting with you! Next steps for TekTutors Academy";
        document.getElementById('composer-body').value = "Hi {{name}},\n\nThank you for exploring our 1-on-1 mentorship programs in **{{course}}**.\n\nWe would love to help you build an employer-ready technical portfolio with flexible month-to-month tuition (₦100,000/month).\n\nFeel free to complete your enrollment or reply to this email anytime!";
        document.getElementById('composer-campaign-type').value = 'follow_up';
    }

    modal.style.display = 'flex';
    updateEmailLivePreview();
}

function openEmailComposerForLead(leadId, leadName, leadEmail, leadCourse) {
    openEmailComposer(leadId, 'consultation_booking_confirmation', 'single');
    const emailInput = document.getElementById('composer-recipient-email');
    const nameInput = document.getElementById('composer-recipient-name');
    const courseSelect = document.getElementById('composer-course-name');

    if (emailInput && leadEmail && leadEmail !== '—') emailInput.value = leadEmail;
    if (nameInput && leadName) nameInput.value = leadName;
    if (courseSelect && leadCourse) {
        for (let opt of courseSelect.options) {
            if (opt.value.toLowerCase().includes(leadCourse.toLowerCase()) || leadCourse.toLowerCase().includes(opt.value.toLowerCase())) {
                courseSelect.value = opt.value;
                break;
            }
        }
    }
    updateEmailLivePreview();
}

function useEmailTemplate(templateId) {
    openEmailComposer(null, templateId, 'single');
}

function previewTemplateInModal(templateId) {
    openEmailComposer(null, templateId, 'single');
}

function closeEmailComposer() {
    const modal = document.getElementById('email-composer-modal');
    if (modal) modal.style.display = 'none';
}

function updateEmailLivePreviewDebounced() {
    clearTimeout(window.emailPreviewDebounceTimer);
    window.emailPreviewDebounceTimer = setTimeout(updateEmailLivePreview, 250);
}

async function updateEmailLivePreview() {
    const iframe = document.getElementById('composer-preview-iframe');
    if (!iframe) return;

    const subject = document.getElementById('composer-subject')?.value || "TekTutors Academy";
    let body = document.getElementById('composer-body')?.value || "";
    const ctaText = document.getElementById('composer-cta-text')?.value || "Enroll Now";
    const ctaUrl = document.getElementById('composer-cta-url')?.value || "https://tektutors.com.ng/registration";
    const recipientName = document.getElementById('composer-recipient-name')?.value || "Alex";
    const courseName = document.getElementById('composer-course-name')?.value || "Data Analytics & BI Accelerator";

    body = body.replace(/\{\{name\}\}/g, recipientName)
               .replace(/\{\{course\}\}/g, courseName)
               .replace(/\{\{registration_url\}\}/g, ctaUrl);

    try {
        const res = await fetch('/api/emails/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                subject: subject.replace(/\{\{name\}\}/g, recipientName).replace(/\{\{course\}\}/g, courseName),
                body: body,
                cta_text: ctaText,
                cta_url: ctaUrl,
                recipient_name: recipientName
            })
        });
        if (res.ok) {
            const data = await res.json();
            const doc = iframe.contentWindow.document;
            doc.open();
            doc.write(data.html);
            doc.close();
        }
    } catch (err) {
        console.error('Error rendering email preview:', err);
    }
}

async function sendTestEmailFromComposer() {
    const testEmailInput = document.getElementById('composer-test-email');
    const toEmail = testEmailInput?.value?.trim();
    if (!toEmail || !toEmail.includes('@')) {
        showToast('Please enter a valid test recipient email address.', 'error');
        return;
    }

    const subject = document.getElementById('composer-subject')?.value || "TekTutors Test";
    const body = document.getElementById('composer-body')?.value || "";
    const ctaText = document.getElementById('composer-cta-text')?.value || "Explore Courses";
    const ctaUrl = document.getElementById('composer-cta-url')?.value || "https://tektutors.com.ng/registration";
    const courseName = document.getElementById('composer-course-name')?.value || "Data Analytics & BI Accelerator";
    const campaignType = document.getElementById('composer-campaign-type')?.value || "test";

    showToast(`Dispatching test preview to ${toEmail}...`, 'info');

    try {
        const res = await fetch('/api/emails/send-test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                recipient_email: toEmail,
                recipient_name: "Admissions Tester",
                subject: subject,
                body: body,
                cta_text: ctaText,
                cta_url: ctaUrl,
                course_name: courseName,
                campaign_type: campaignType
            })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast(`✅ Test email successfully sent to ${toEmail}!`);
            fetchEmailStats();
            fetchEmailLogs();
        } else {
            showToast(data.detail || 'Failed to dispatch test email', 'error');
        }
    } catch (err) {
        console.error('Error dispatching test email:', err);
        showToast('Network error while dispatching test email', 'error');
    }
}

async function submitEmailDispatch() {
    const mode = document.getElementById('composer-mode')?.value || 'single';
    const campaignType = document.getElementById('composer-campaign-type')?.value || 'follow_up';
    const subject = document.getElementById('composer-subject')?.value;
    const body = document.getElementById('composer-body')?.value;
    const ctaText = document.getElementById('composer-cta-text')?.value;
    const ctaUrl = document.getElementById('composer-cta-url')?.value;
    const submitBtn = document.getElementById('btn-submit-email');

    if (!subject || !body) {
        showToast('Please enter both subject and email body.', 'error');
        return;
    }

    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Dispatching...';
    }

    try {
        if (mode === 'broadcast') {
            const targetAudience = document.getElementById('composer-target-audience')?.value || 'all';
            const res = await fetch('/api/emails/send-broadcast', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    target_audience: targetAudience,
                    campaign_type: campaignType,
                    subject: subject,
                    body: body,
                    cta_text: ctaText,
                    cta_url: ctaUrl
                })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                showToast(`🚀 ${data.message}`);
                closeEmailComposer();
                loadEmailHub();
            } else {
                showToast(data.detail || data.message || 'Failed to dispatch broadcast', 'error');
            }
        } else {
            const recipientEmail = document.getElementById('composer-recipient-email')?.value;
            const recipientName = document.getElementById('composer-recipient-name')?.value || 'Student';
            const leadIdVal = document.getElementById('composer-lead-id')?.value;
            const leadId = leadIdVal ? parseInt(leadIdVal) : null;

            if (!recipientEmail) {
                showToast('Please provide a recipient email address.', 'error');
                if (submitBtn) {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Send Email Now';
                }
                return;
            }

            const res = await fetch('/api/emails/send-single', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    recipient_email: recipientEmail,
                    recipient_name: recipientName,
                    subject: subject,
                    body: body,
                    campaign_type: campaignType,
                    lead_id: leadId,
                    cta_text: ctaText,
                    cta_url: ctaUrl
                })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                showToast(`📧 Email dispatched to ${recipientEmail}`);
                closeEmailComposer();
                loadEmailHub();
            } else {
                showToast(data.detail || 'Failed to send email', 'error');
            }
        }
    } catch (err) {
        console.error('Error submitting email dispatch:', err);
        showToast('Network error while dispatching email', 'error');
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = mode === 'broadcast' ? '<i class="fa-solid fa-rocket"></i> Launch Broadcast Campaign' : '<i class="fa-solid fa-paper-plane"></i> Send Email Now';
        }
    }
}

async function viewEmailLogDetail(logId) {
    try {
        const res = await fetch(`/api/emails/logs/${logId}`);
        if (!res.ok) {
            showToast('Could not load email details', 'error');
            return;
        }
        const log = await res.json();
        const modal = document.getElementById('email-log-detail-modal');
        if (!modal) return;

        document.getElementById('log-detail-recipient').innerText = `${log.recipient_name || 'Student'} <${log.recipient_email}>`;
        document.getElementById('log-detail-subject').innerText = log.subject;
        document.getElementById('log-detail-sent-at').innerText = log.sent_at || 'Just now';

        const statusEl = document.getElementById('log-detail-status');
        if (statusEl) {
            statusEl.innerHTML = log.status === 'delivered' || log.status === 'sent'
                ? `<span class="pill-delivered"><i class="fa-solid fa-check"></i> ${log.status.toUpperCase()}</span>`
                : `<span class="pill-failed"><i class="fa-solid fa-triangle-exclamation"></i> FAILED</span>`;
        }

        const errBox = document.getElementById('log-detail-error');
        if (errBox) {
            if (log.error_message) {
                errBox.innerText = `Error: ${log.error_message}`;
                errBox.style.display = 'block';
            } else {
                errBox.style.display = 'none';
            }
        }

        const iframe = document.getElementById('log-detail-iframe');
        if (iframe) {
            const doc = iframe.contentWindow.document;
            doc.open();
            doc.write(log.body_html || '<p>No content preview available.</p>');
            doc.close();
        }

        modal.style.display = 'flex';
    } catch (err) {
        console.error('Error loading email log detail:', err);
        showToast('Failed to load email log', 'error');
    }
}

function closeEmailLogDetail() {
    const modal = document.getElementById('email-log-detail-modal');
    if (modal) modal.style.display = 'none';
}

function promptQuickConversionEmail(leadId, name, email) {
    if (!email || email === '—' || !email.includes('@')) {
        showToast(`Lead "${name || 'Student'}" has no email on file. Please capture their email address first.`, 'error');
        return;
    }

    const modal = document.getElementById('conversion-followup-modal');
    if (!modal) return;

    document.getElementById('conversion-target-lead-id').value = leadId;
    document.getElementById('conversion-target-name').innerText = name || 'Student';
    document.getElementById('conversion-target-email').innerText = email;

    modal.style.display = 'flex';
}

function closeConversionFollowup() {
    const modal = document.getElementById('conversion-followup-modal');
    if (modal) modal.style.display = 'none';
}

async function executeConversionFollowup(triggerEvent) {
    const leadId = document.getElementById('conversion-target-lead-id')?.value;
    if (!leadId) return;

    showToast(`🚀 Dispatching '${triggerEvent}' conversion follow-up email...`, 'info');
    closeConversionFollowup();

    try {
        const res = await fetch('/api/emails/trigger-engagement', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                lead_id: parseInt(leadId),
                trigger_event: triggerEvent
            })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            showToast(`✅ ${data.message}`);
            fetchEmailStats();
            fetchEmailLogs();
        } else {
            showToast(data.detail || data.message || 'Failed to dispatch conversion follow-up', 'error');
        }
    } catch (err) {
        console.error('Error executing conversion follow-up:', err);
        showToast('Network error while dispatching follow-up', 'error');
    }
}

