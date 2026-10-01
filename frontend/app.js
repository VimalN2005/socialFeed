// ScaleFeed Single Page Application Frontend
let currentFeedMode = 'ranked'; // 'ranked' or 'timeline'
let currentCursor = null;
let activeSocket = null;
let currentTab = 'login';

// Initialize Lucide icons
document.addEventListener('DOMContentLoaded', () => {
  lucide.createIcons();
  checkAuthSession();
  fetchFeed();
});

function getApiBase() {
  return window.location.origin;
}

function getAuthToken() {
  return localStorage.getItem('access_token');
}

function getCurrentUser() {
  try {
    return JSON.parse(localStorage.getItem('user_profile'));
  } catch {
    return null;
  }
}

// ------------------- Authentication -------------------
function checkAuthSession() {
  const token = getAuthToken();
  const user = getCurrentUser();
  const userControls = document.getElementById('user-controls');
  const postBox = document.getElementById('post-box');

  if (token && user) {
    userControls.innerHTML = `
      <div class="flex items-center gap-2">
        <span class="text-xs font-semibold text-gray-300">@${user.username}</span>
        <button onclick="logout()" class="px-2.5 py-1 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white text-xs transition">Logout</button>
      </div>
    `;
    postBox.classList.remove('hidden');
    document.getElementById('author-avatar').innerText = user.username.charAt(0);
    initNotificationWebSocket(user.id);
  } else {
    userControls.innerHTML = `
      <button onclick="openAuthModal()" class="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-sm transition">Sign In</button>
    `;
    postBox.classList.add('hidden');
    updateWsStatus(false, 'Sign in for alerts');
  }
}

function openAuthModal() {
  document.getElementById('auth-modal').classList.remove('hidden');
}

function closeAuthModal() {
  document.getElementById('auth-modal').classList.add('hidden');
}

function setAuthTab(tab) {
  currentTab = tab;
  const loginBtn = document.getElementById('auth-tab-login');
  const regBtn = document.getElementById('auth-tab-register');
  const emailField = document.getElementById('email-field');
  const submitBtn = document.getElementById('auth-submit-btn');

  if (tab === 'login') {
    loginBtn.className = 'flex-1 py-1.5 rounded-md text-xs font-bold bg-indigo-600 text-white';
    regBtn.className = 'flex-1 py-1.5 rounded-md text-xs font-bold text-gray-400 hover:text-white';
    emailField.classList.add('hidden');
    submitBtn.innerText = 'Sign In';
  } else {
    regBtn.className = 'flex-1 py-1.5 rounded-md text-xs font-bold bg-indigo-600 text-white';
    loginBtn.className = 'flex-1 py-1.5 rounded-md text-xs font-bold text-gray-400 hover:text-white';
    emailField.classList.remove('hidden');
    submitBtn.innerText = 'Create Account';
  }
}

async function handleAuthSubmit(e) {
  e.preventDefault();
  const username = document.getElementById('auth-username').value.trim();
  const password = document.getElementById('auth-password').value;
  const email = document.getElementById('auth-email').value.trim();

  try {
    if (currentTab === 'login') {
      const res = await fetch(`${getApiBase()}/api/v1/auth/token/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      const data = await res.json();
      if (res.ok) {
        localStorage.setItem('access_token', data.access);
        localStorage.setItem('refresh_token', data.refresh);
        // Fetch user profile
        const profRes = await fetch(`${getApiBase()}/api/v1/users/me/`, {
          headers: { 'Authorization': `Bearer ${data.access}` }
        });
        const prof = await profRes.json();
        localStorage.setItem('user_profile', JSON.stringify(prof));
        closeAuthModal();
        checkAuthSession();
        fetchFeed();
        showToast('Welcome back, @' + username, 'Signed in successfully');
      } else {
        alert(data.detail || 'Login failed. Check credentials.');
      }
    } else {
      const res = await fetch(`${getApiBase()}/api/v1/users/register/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password })
      });
      const data = await res.json();
      if (res.ok) {
        localStorage.setItem('access_token', data.tokens.access);
        localStorage.setItem('refresh_token', data.tokens.refresh);
        localStorage.setItem('user_profile', JSON.stringify(data.user));
        closeAuthModal();
        checkAuthSession();
        fetchFeed();
        showToast('Account Created!', 'Welcome to ScaleFeed @' + username);
      } else {
        alert(JSON.stringify(data));
      }
    }
  } catch (err) {
    alert('Network error: ' + err.message);
  }
}

function logout() {
  localStorage.clear();
  if (activeSocket) activeSocket.close();
  checkAuthSession();
  fetchFeed();
}

// ------------------- Real-time WebSockets -------------------
function initNotificationWebSocket(userId) {
  if (activeSocket) activeSocket.close();

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  // Use port 8001 directly in local dev or current host through reverse proxy
  const host = window.location.port === '8000' ? `${window.location.hostname}:8001` : window.location.host;
  const wsUrl = `${protocol}//${host}/ws/notifications/${userId}`;

  try {
    activeSocket = new WebSocket(wsUrl);

    activeSocket.onopen = () => {
      updateWsStatus(true, 'Live Connected');
    };

    activeSocket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.event === 'post_liked') {
          showToast('New Like! ❤️', payload.message || 'Someone liked your post');
        } else if (payload.event === 'new_follower') {
          showToast('New Follower! 👤', payload.message);
        }
      } catch (e) {
        console.log('WS msg:', event.data);
      }
    };

    activeSocket.onclose = () => {
      updateWsStatus(false, 'Disconnected');
    };

    activeSocket.onerror = () => {
      updateWsStatus(false, 'Offline');
    };
  } catch (e) {
    updateWsStatus(false, 'Mock Mode');
  }
}

function updateWsStatus(connected, text) {
  const badge = document.getElementById('ws-badge');
  const label = document.getElementById('ws-status');
  label.innerText = text;
  if (connected) {
    badge.className = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20';
  } else {
    badge.className = 'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20';
  }
}

// ------------------- Toast Alerts -------------------
function showToast(title, message) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = 'glass-card toast-anim rounded-xl p-3.5 border-l-4 border-indigo-500 shadow-2xl flex items-center justify-between pointer-events-auto';
  toast.innerHTML = `
    <div>
      <h4 class="text-xs font-bold text-indigo-400">${title}</h4>
      <p class="text-xs text-gray-200 mt-0.5">${message}</p>
    </div>
    <button onclick="this.parentElement.remove()" class="text-gray-400 hover:text-white ml-3 text-xs">✕</button>
  `;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4500);
}

// ------------------- Feed Switcher & Fetcher -------------------
function switchFeedMode(mode) {
  currentFeedMode = mode;
  const rankedTab = document.getElementById('tab-ranked');
  const timelineTab = document.getElementById('tab-timeline');

  if (mode === 'ranked') {
    rankedTab.className = 'flex-1 py-2 text-sm font-semibold rounded-lg bg-indigo-600 text-white shadow transition flex items-center justify-center gap-1.5';
    timelineTab.className = 'flex-1 py-2 text-sm font-semibold rounded-lg text-gray-400 hover:text-white transition flex items-center justify-center gap-1.5';
  } else {
    timelineTab.className = 'flex-1 py-2 text-sm font-semibold rounded-lg bg-indigo-600 text-white shadow transition flex items-center justify-center gap-1.5';
    rankedTab.className = 'flex-1 py-2 text-sm font-semibold rounded-lg text-gray-400 hover:text-white transition flex items-center justify-center gap-1.5';
  }
  currentCursor = null;
  fetchFeed();
}

async function fetchFeed() {
  const token = getAuthToken();
  const container = document.getElementById('feed-container');

  let endpoint = currentFeedMode === 'ranked'
    ? `${getApiBase()}/api/v1/feed/ranked/?top_k=20`
    : `${getApiBase()}/api/v1/feed/timeline/`;

  if (currentCursor) {
    endpoint += (endpoint.includes('?') ? '&' : '?') + `cursor=${encodeURIComponent(currentCursor)}`;
  }

  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  try {
    const res = await fetch(endpoint, { headers });
    const data = await res.json();
    const posts = data.results || [];

    if (!currentCursor) container.innerHTML = '';

    if (posts.length === 0) {
      container.innerHTML = `
        <div class="glass-card rounded-2xl p-8 text-center text-gray-400">
          <i data-lucide="sparkles" class="w-8 h-8 mx-auto mb-2 text-indigo-400"></i>
          <p class="font-semibold text-sm">No posts in feed yet.</p>
          <p class="text-xs text-gray-500 mt-1">Be the first to publish a post above!</p>
        </div>
      `;
      lucide.createIcons();
      return;
    }

    posts.forEach(post => {
      container.appendChild(createPostCard(post));
    });

    if (data.next) {
      const url = new URL(data.next);
      currentCursor = url.searchParams.get('cursor');
      document.getElementById('load-more-btn').classList.remove('hidden');
    } else {
      document.getElementById('load-more-btn').classList.add('hidden');
    }

    lucide.createIcons();
  } catch (err) {
    container.innerHTML = `<div class="glass-card p-4 rounded-xl text-center text-red-400 text-xs">Error loading feed: ${err.message}</div>`;
  }
}

function createPostCard(post) {
  const card = document.createElement('div');
  card.className = 'glass-card rounded-2xl p-4 shadow-lg hover:border-gray-700/80 transition';

  const userInitial = post.user?.username ? post.user.username.charAt(0).toUpperCase() : 'U';
  const timeFormatted = new Date(post.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  const isCelebBadge = post.user?.is_celebrity ? '<span class="text-xs px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 font-bold ml-1.5">★ Star</span>' : '';
  const scoreBadge = post.ranking_score ? `<span class="text-xs text-indigo-400 font-mono bg-indigo-500/10 px-2 py-0.5 rounded-full">Score: ${post.ranking_score.toFixed(2)}</span>` : '';

  card.innerHTML = `
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2.5">
        <div class="w-9 h-9 rounded-full bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center font-bold text-white text-xs">${userInitial}</div>
        <div>
          <div class="flex items-center">
            <span class="font-bold text-sm text-gray-200">@${post.user?.username || 'anonymous'}</span>
            ${isCelebBadge}
          </div>
          <span class="text-xs text-gray-500">${timeFormatted}</span>
        </div>
      </div>
      ${scoreBadge}
    </div>

    <p class="text-sm text-gray-200 mb-3 whitespace-pre-line">${escapeHtml(post.caption)}</p>

    ${post.media_url ? `<div class="mb-3 rounded-xl overflow-hidden max-h-80 bg-black/40"><img src="${post.media_url}" class="w-full object-cover" onerror="this.remove()"></div>` : ''}

    <div class="flex items-center gap-4 pt-2 border-t border-gray-800/80 text-gray-400 text-xs">
      <button onclick="toggleLike('${post.id}', this)" class="flex items-center gap-1.5 hover:text-rose-400 transition font-semibold">
        <i data-lucide="heart" class="w-4 h-4 ${post.is_liked ? 'text-rose-500 fill-rose-500' : ''}"></i>
        <span class="like-count">${post.likes_count}</span>
      </button>
      <div class="flex items-center gap-1.5 text-gray-500 font-semibold">
        <i data-lucide="message-circle" class="w-4 h-4"></i>
        <span>${post.comments_count}</span>
      </div>
    </div>
  `;
  return card;
}

// ------------------- Post Actions -------------------
async function toggleLike(postId, btn) {
  const token = getAuthToken();
  if (!token) return openAuthModal();

  try {
    const res = await fetch(`${getApiBase()}/api/v1/posts/${postId}/like/`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await res.json();
    if (res.ok) {
      const heartIcon = btn.querySelector('svg') || btn.querySelector('i');
      const countSpan = btn.querySelector('.like-count');
      countSpan.innerText = data.likes_count;
      if (data.liked) {
        btn.classList.add('text-rose-500');
        showToast('Liked!', 'Post like registered');
      } else {
        btn.classList.remove('text-rose-500');
      }
    }
  } catch (e) {
    console.error('Like error', e);
  }
}

async function requestAiAnalysis() {
  const caption = document.getElementById('post-caption').value.trim();
  if (!caption) return alert('Please enter a caption first to analyze!');

  const token = getAuthToken();
  try {
    const res = await fetch(`${getApiBase()}/api/v1/posts/ai-analyze/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ caption })
    });
    const data = await res.json();
    if (res.ok) {
      const preview = document.getElementById('ai-preview');
      preview.classList.remove('hidden');
      document.getElementById('ai-sentiment-badge').innerText = `${data.sentiment} (${data.sentiment_score})`;
      document.getElementById('ai-headline').innerText = `"${data.generated_headline}"`;

      const tagsList = document.getElementById('ai-tags-list');
      tagsList.innerHTML = '';
      data.suggested_hashtags.forEach(tag => {
        const span = document.createElement('span');
        span.className = 'px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-semibold cursor-pointer hover:bg-indigo-500/30';
        span.innerText = tag;
        span.onclick = () => {
          document.getElementById('post-caption').value += ` ${tag}`;
        };
        tagsList.appendChild(span);
      });
      lucide.createIcons();
    }
  } catch (err) {
    alert('AI Analysis error: ' + err.message);
  }
}

async function publishNewPost() {
  const caption = document.getElementById('post-caption').value.trim();
  const mediaUrl = document.getElementById('post-media-url').value.trim();
  const token = getAuthToken();

  if (!caption) return alert('Please write a caption.');
  if (!token) return openAuthModal();

  const publishBtn = document.getElementById('publish-btn');
  publishBtn.disabled = true;
  publishBtn.innerText = 'Publishing...';

  try {
    const res = await fetch(`${getApiBase()}/api/v1/posts/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ caption, media_url: mediaUrl })
    });
    const data = await res.json();
    if (res.ok) {
      document.getElementById('post-caption').value = '';
      document.getElementById('post-media-url').value = '';
      document.getElementById('ai-preview').classList.add('hidden');
      showToast('Published! 🚀', 'Your post is now live across follower timelines');
      fetchFeed();
    } else {
      alert(JSON.stringify(data));
    }
  } catch (err) {
    alert('Publishing error: ' + err.message);
  } finally {
    publishBtn.disabled = false;
    publishBtn.innerHTML = '<span>Publish</span> <i data-lucide="send" class="w-4 h-4"></i>';
    lucide.createIcons();
  }
}

function escapeHtml(text) {
  if (!text) return '';
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
