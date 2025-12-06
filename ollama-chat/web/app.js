const apiBase = '';
let chatId = null;
let ws = null;
let theme = localStorage.getItem('theme') || 'dark';
let memoryState = JSON.parse(localStorage.getItem('memoryState') || '[]');

document.body.classList.toggle('light', theme === 'light');

const historyEl = document.getElementById('history');
const chatsEl = document.getElementById('chat-list');
const inputEl = document.getElementById('input');
const sendBtn = document.getElementById('send-btn');
const typingEl = document.getElementById('typing');
const themeToggle = document.getElementById('theme-toggle');

function renderMessage(role, content, emoji=null) {
  const msg = document.createElement('div');
  msg.className = `message ${role}`;
  msg.innerHTML = marked.parse(content || '');
  if (emoji) {
    const span = document.createElement('span');
    span.textContent = ` ${emoji}`;
    msg.appendChild(span);
  }
  historyEl.appendChild(msg);
  historyEl.scrollTop = historyEl.scrollHeight;
}

function setTyping(show) {
  typingEl.style.display = show ? 'flex' : 'none';
}

async function fetchChats() {
  const res = await fetch(`${apiBase}/list_chats`);
  const data = await res.json();
  chatsEl.innerHTML = '';
  data.chats.forEach(c => {
    const item = document.createElement('div');
    item.className = 'chat-item' + (c.id === chatId ? ' active' : '');
    item.textContent = c.title;
    item.onclick = () => loadChat(c.id);
    chatsEl.appendChild(item);
  });
}

async function newChat() {
  const res = await fetch(`${apiBase}/new_chat`, { method: 'POST' });
  const data = await res.json();
  chatId = data.chat_id;
   localStorage.setItem('chatId', chatId);
  historyEl.innerHTML = '';
  await fetchChats();
}

async function loadChat(id) {
  chatId = id;
  localStorage.setItem('chatId', chatId);
  const res = await fetch(`${apiBase}/history/${id}`);
  const data = await res.json();
  historyEl.innerHTML = '';
  data.messages.forEach(m => renderMessage(m.role, m.content));
  await fetchChats();
}

function ensureWS() {
  if (ws && ws.readyState === WebSocket.OPEN) return;
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onmessage = (ev) => {
    const payload = JSON.parse(ev.data);
    if (payload.chunk) {
      const last = historyEl.querySelector('.message.assistant:last-child');
      if (last) {
        last.innerHTML += payload.chunk;
      } else {
        renderMessage('assistant', payload.chunk);
      }
      historyEl.scrollTop = historyEl.scrollHeight;
    }
    if (payload.done) {
      setTyping(false);
      if (payload.emotion) {
        const last = historyEl.querySelector('.message.assistant:last-child');
        if (last) {
          const span = document.createElement('span');
          span.textContent = ` ${emotionToEmoji(payload.emotion)}`;
          last.appendChild(span);
        }
      }
    }
  };
  ws.onclose = () => setTimeout(ensureWS, 1000);
}

function emotionToEmoji(emotion) {
  return {
    happy: '😊',
    sad: '😢',
    neutral: '😐',
    angry: '😠'
  }[emotion] || '';
}

async function sendMessage() {
  if (!chatId) await newChat();
  const text = inputEl.value.trim();
  if (!text) return;
  memoryState.push({ role: 'user', content: text, ts: Date.now() });
  localStorage.setItem('memoryState', JSON.stringify(memoryState.slice(-50)));
  renderMessage('user', text);
  inputEl.value = '';
  setTyping(true);
  ensureWS();
  ws.send(JSON.stringify({ chat_id: chatId, message: text }));
}

sendBtn.onclick = sendMessage;
inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

themeToggle.onclick = () => {
  theme = theme === 'light' ? 'dark' : 'light';
  localStorage.setItem('theme', theme);
  document.body.classList.toggle('light', theme === 'light');
};

async function init() {
  const saved = localStorage.getItem('chatId');
  if (saved) {
    await loadChat(parseInt(saved));
  } else {
    await newChat();
  }
  await fetchChats();
}

init();
