let currentChat = null;
let chats = [];
const messagesEl = document.getElementById('messages');
const chatListEl = document.getElementById('chatList');
const memoryPanel = document.getElementById('memoryPanel');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('send');
const newChatBtn = document.getElementById('newChat');
const allowSearchEl = document.getElementById('allowSearch');
const modelEl = document.getElementById('model');
const themeSelect = document.getElementById('themeSelect');

function applyTheme(theme) {
  const root = document.documentElement;
  root.classList.remove('light', 'amoled');
  if (theme !== 'dark') root.classList.add(theme);
  localStorage.setItem('theme', theme);
  themeSelect.value = theme;
}

async function api(path, options={}) {
  const res = await fetch(path, {headers: {'Content-Type': 'application/json'}, ...options});
  return res.json();
}

function renderMessages(msgs) {
  messagesEl.innerHTML = '';
  msgs.forEach(m => {
    const div = document.createElement('div');
    div.className = `message ${m.role}`;
    div.innerHTML = `<div class="role">${m.role}</div><div class="content">${marked.parse(m.content)}</div>`;
    messagesEl.appendChild(div);
  });
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addMessage(role, content) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.innerHTML = `<div class="role">${role}</div><div class="content">${marked.parse(content)}</div>`;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function loadMemory() {
  const data = await api('/api/memory');
  memoryPanel.innerHTML = data.map(m => `<div><strong>${m.key}</strong>: ${m.content}</div>`).join('');
}

async function loadChat(chatId) {
  const msgs = await api(`/api/history/${chatId}`);
  renderMessages(msgs);
}

async function createChat() {
  const data = await api('/api/new_chat');
  currentChat = data.chat_id;
  chats.unshift({id: currentChat, title: 'New Chat'});
  renderChatList();
  await loadChat(currentChat);
}

function renderChatList() {
  chatListEl.innerHTML = '';
  chats.forEach(c => {
    const li = document.createElement('li');
    li.textContent = c.title || `Chat ${c.id}`;
    li.classList.toggle('active', c.id === currentChat);
    li.onclick = async () => { currentChat = c.id; renderChatList(); await loadChat(c.id); };
    chatListEl.appendChild(li);
  });
}

async function sendMessage() {
  const content = inputEl.value.trim();
  if (!content) return;
  if (!currentChat) await createChat();
  addMessage('user', content);
  inputEl.value = '';
  const ws = new WebSocket(`${location.origin.replace('http', 'ws')}/ws/chat`);
  ws.onopen = () => {
    ws.send(JSON.stringify({chat_id: currentChat, message: content, model: modelEl.value, allow_search: allowSearchEl.checked}));
  };
  let buffer = '';
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'token') {
      buffer += data.token;
      if (!document.getElementById('streaming')) {
        const div = document.createElement('div');
        div.id = 'streaming';
        div.className = 'message assistant';
        div.innerHTML = '<div class="role">assistant</div><div class="content"></div>';
        messagesEl.appendChild(div);
      }
      document.querySelector('#streaming .content').innerHTML = marked.parse(buffer);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
    if (data.type === 'done') {
      const streaming = document.getElementById('streaming');
      if (streaming) streaming.id = '';
      ws.close();
    }
  };
}

sendBtn.onclick = sendMessage;
inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
newChatBtn.onclick = createChat;
themeSelect.onchange = (e) => applyTheme(e.target.value);

(async function init(){
  applyTheme(localStorage.getItem('theme') || 'dark');
  await createChat();
  await loadMemory();
})();
