/*
 * Client-side logic for the habit tracker.
 *
 * This script handles user authentication, renders the daily habit
 * checklist, calculates completion percentages, saves habit entries,
 * and retrieves progress charts.  It communicates with the Flask
 * backend via fetch() calls.
 */

// Base URL of the backend API.  Replace this with your Render
// deployment URL (e.g. https://your-backend.onrender.com) when deploying.
const API_BASE_URL = 'http://localhost:5000';

// DOM elements
const authContainer = document.getElementById('auth-container');
const trackerContainer = document.getElementById('tracker-container');

// Forms and messages
const loginForm = document.getElementById('login-form');
const registerForm = document.getElementById('register-form');
const loginButton = document.getElementById('login-button');
const registerButton = document.getElementById('register-button');
const loginMessage = document.getElementById('login-message');
const registerMessage = document.getElementById('register-message');
const showRegisterLink = document.getElementById('show-register');
const showLoginLink = document.getElementById('show-login');

// Tracker elements
const currentDateEl = document.getElementById('current-date');
const dailyQuoteEl = document.getElementById('daily-quote');
const habitsForm = document.getElementById('habits-form');
const progressPercentageEl = document.getElementById('progress-percentage');
const saveButton = document.getElementById('save-button');
const saveMessage = document.getElementById('save-message');
const logoutButton = document.getElementById('logout-button');
const loadWeeklyButton = document.getElementById('load-weekly');
const loadMonthlyButton = document.getElementById('load-monthly');
const progressChartCanvas = document.getElementById('progress-chart');

let progressChart; // Chart.js instance

// Utility: format date to YYYY-MM-DD
function formatDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

// Show login or registration forms
function showLoginForm() {
  loginForm.style.display = 'block';
  registerForm.style.display = 'none';
  loginMessage.textContent = '';
  registerMessage.textContent = '';
}

function showRegisterForm() {
  loginForm.style.display = 'none';
  registerForm.style.display = 'block';
  loginMessage.textContent = '';
  registerMessage.textContent = '';
}

// Token storage
function setToken(token) {
  localStorage.setItem('habit_token', token);
}

function getToken() {
  return localStorage.getItem('habit_token');
}

function removeToken() {
  localStorage.removeItem('habit_token');
}

// Initialize event listeners for authentication
function initAuthListeners() {
  // Toggle between login and register
  showRegisterLink.addEventListener('click', (e) => {
    e.preventDefault();
    showRegisterForm();
  });
  showLoginLink.addEventListener('click', (e) => {
    e.preventDefault();
    showLoginForm();
  });

  // Register
  registerButton.addEventListener('click', async () => {
    const username = document.getElementById('register-username').value.trim();
    const password = document.getElementById('register-password').value;
    registerMessage.textContent = '';
    if (!username || !password) {
      registerMessage.textContent = 'Please enter a username and password.';
      return;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await response.json();
      if (response.ok) {
        registerMessage.style.color = '#27ae60';
        registerMessage.textContent = 'Registration successful. You can now log in.';
        showLoginForm();
      } else {
        registerMessage.style.color = '#e74c3c';
        registerMessage.textContent = data.error || 'Registration failed.';
      }
    } catch (error) {
      registerMessage.style.color = '#e74c3c';
      registerMessage.textContent = 'An error occurred. Please try again later.';
    }
  });

  // Login
  loginButton.addEventListener('click', async () => {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    loginMessage.textContent = '';
    if (!username || !password) {
      loginMessage.textContent = 'Please enter your username and password.';
      return;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await response.json();
      if (response.ok) {
        setToken(data.access_token);
        loginMessage.style.color = '#27ae60';
        loginMessage.textContent = 'Login successful!';
        showTracker();
      } else {
        loginMessage.style.color = '#e74c3c';
        loginMessage.textContent = data.error || 'Login failed.';
      }
    } catch (error) {
      loginMessage.style.color = '#e74c3c';
      loginMessage.textContent = 'An error occurred. Please try again later.';
    }
  });
}

// Initialize tracker page
function initTracker() {
  const today = new Date();
  currentDateEl.textContent = today.toLocaleDateString(undefined, {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  });
  fetchQuote();
  fetchHabits(formatDate(today));
  saveButton.addEventListener('click', () => {
    saveHabits(formatDate(today));
  });
  logoutButton.addEventListener('click', () => {
    removeToken();
    if (progressChart) {
      progressChart.destroy();
    }
    trackerContainer.style.display = 'none';
    authContainer.style.display = 'block';
    showLoginForm();
  });
  loadWeeklyButton.addEventListener('click', () => {
    loadProgress('weekly');
  });
  loadMonthlyButton.addEventListener('click', () => {
    loadProgress('monthly');
  });
}

// Show tracker and hide auth container
function showTracker() {
  authContainer.style.display = 'none';
  trackerContainer.style.display = 'block';
  initTracker();
}

// Fetch a random quote
async function fetchQuote() {
  try {
    const response = await fetch(`${API_BASE_URL}/quote`);
    const data = await response.json();
    if (data.quote) {
      dailyQuoteEl.innerHTML = `“${data.quote}” — <em>${data.author}</em>`;
    } else {
      dailyQuoteEl.textContent = '';
    }
  } catch (error) {
    dailyQuoteEl.textContent = '';
  }
}

// Fetch habits for a given date.  The token is optional; if present it
// sends the Authorization header so the backend can reflect completed
// habits.
async function fetchHabits(dateStr) {
  const token = getToken();
  const headers = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  try {
    const response = await fetch(`${API_BASE_URL}/habits?date=${dateStr}`, { headers });
    const data = await response.json();
    if (response.ok) {
      renderHabits(data.habits || []);
    } else {
      console.error(data.error);
      renderHabits([]);
    }
  } catch (error) {
    console.error('Failed to fetch habits', error);
    renderHabits([]);
  }
}

// Render habits as checkboxes
function renderHabits(habits) {
  habitsForm.innerHTML = '';
  if (!habits || habits.length === 0) {
    const msg = document.createElement('p');
    msg.textContent = 'No habits available.';
    habitsForm.appendChild(msg);
    progressPercentageEl.textContent = '0%';
    return;
  }
  habits.forEach((habit) => {
    const wrapper = document.createElement('div');
    wrapper.className = 'habit-item';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = `habit-${habit.id}`;
    checkbox.checked = habit.completed;
    checkbox.addEventListener('change', updateProgress);
    const label = document.createElement('label');
    label.htmlFor = `habit-${habit.id}`;
    label.textContent = habit.name;
    wrapper.appendChild(checkbox);
    wrapper.appendChild(label);
    habitsForm.appendChild(wrapper);
  });
  updateProgress();
}

// Update progress percentage
function updateProgress() {
  const checkboxes = habitsForm.querySelectorAll('input[type="checkbox"]');
  let completed = 0;
  checkboxes.forEach((cb) => {
    if (cb.checked) completed += 1;
  });
  const total = checkboxes.length;
  const percentage = total > 0 ? Math.round((completed / total) * 100) : 0;
  progressPercentageEl.textContent = `${percentage}%`;
}

// Save habit completions
async function saveHabits(dateStr) {
  const token = getToken();
  if (!token) return;
  const completions = {};
  const checkboxes = habitsForm.querySelectorAll('input[type="checkbox"]');
  checkboxes.forEach((cb) => {
    const habitId = cb.id.replace('habit-', '');
    completions[habitId] = cb.checked;
  });
  saveMessage.textContent = '';
  try {
    const response = await fetch(`${API_BASE_URL}/habits`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify({ date: dateStr, completions }),
    });
    const data = await response.json();
    if (response.ok) {
      saveMessage.style.color = '#27ae60';
      saveMessage.textContent = `Habits saved! Completion: ${data.percentage.toFixed(0)}%`;
    } else {
      saveMessage.style.color = '#e74c3c';
      saveMessage.textContent = data.error || 'Failed to save.';
    }
  } catch (error) {
    saveMessage.style.color = '#e74c3c';
    saveMessage.textContent = 'An error occurred while saving.';
  }
}

// Load progress and draw chart
async function loadProgress(period) {
  const token = getToken();
  if (!token) return;
  try {
    const response = await fetch(`${API_BASE_URL}/progress?period=${period}`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    const data = await response.json();
    if (response.ok) {
      drawChart(data.habits, period);
    } else {
      console.error(data.error);
    }
  } catch (error) {
    console.error('Failed to load progress', error);
  }
}

// Draw bar chart using Chart.js
function drawChart(habits, period) {
  const labels = habits.map((h) => h.name);
  const values = habits.map((h) => h.percentage);
  const backgroundColors = values.map((val) => `rgba(${Math.floor(100 + val * 1.5)}, ${Math.floor(200 - val)}, ${Math.floor(150 + val * 0.5)}, 0.6)`);
  if (progressChart) {
    progressChart.destroy();
  }
  progressChart = new Chart(progressChartCanvas, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: `${period.charAt(0).toUpperCase() + period.slice(1)} Completion (%)`,
          data: values,
          backgroundColor: backgroundColors,
        },
      ],
    },
    options: {
      responsive: true,
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
        },
      },
    },
  });
}

// On page load, initialize
document.addEventListener('DOMContentLoaded', () => {
  initAuthListeners();
  const token = getToken();
  if (token) {
    showTracker();
  } else {
    showLoginForm();
  }
});
