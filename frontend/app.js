// =====================================================================
// 설정 / 상태
// =====================================================================
const API = (window.API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const PAGE_SIZE = 20;

const $ = (selector) => document.querySelector(selector);

let currentConversationId = null; // 지금 보고 있는 대화 id (null이면 새 대화)
let sending = false;              // 채팅 전송 중인지
let dataOffset = 0;               // 데이터 목록 페이지 위치

const EXAMPLE_QUESTIONS = [
  "요즘 휘발유 가격 추세가 어때?",
  "가장 비쌌던 날은 언제야?",
  "2025년 월별 평균 가격을 알려줘",
];

// =====================================================================
// 공통 도우미
// =====================================================================
const fmt = (n, digits = 1) =>
  Number(n).toLocaleString("ko-KR", { maximumFractionDigits: digits });

function showToast(message, isError = false) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.className = "toast" + (isError ? " error" : "");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.add("hidden"), 3000);
}

// 서버 호출 공통 함수: 에러 메시지 정리 + 느린 응답(콜드 스타트) 안내
async function api(path, options = {}) {
  const slowTimer = setTimeout(() => $("#notice").classList.remove("hidden"), 4000);
  try {
    let res;
    try {
      res = await fetch(API + path, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
    } catch (e) {
      throw new Error("서버에 연결할 수 없어요. 서버가 켜져 있는지 확인해 주세요.");
    }

    if (!res.ok) {
      let message = `요청에 실패했어요 (${res.status})`;
      try {
        const body = await res.json();
        if (typeof body.detail === "string") message = body.detail;
        else if (Array.isArray(body.detail)) message = body.detail.map((d) => d.msg).join(", ");
      } catch (_) { /* 본문이 JSON이 아니면 기본 메시지 사용 */ }
      throw new Error(message);
    }
    return await res.json();
  } finally {
    clearTimeout(slowTimer);
    $("#notice").classList.add("hidden");
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text; // textContent만 사용 -> XSS 방지
  return node;
}

// =====================================================================
// 다크 모드
// =====================================================================
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  $("#themeBtn").textContent = theme === "dark" ? "☀️" : "🌙";
}

function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem("theme"); } catch (_) {}
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(saved || (prefersDark ? "dark" : "light"));

  $("#themeBtn").addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem("theme", next); } catch (_) {}
  });
}

// =====================================================================
// 탭
// =====================================================================
function initTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => showTab(btn.dataset.tab));
  });
}

function showTab(name) {
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $("#tab-chat").classList.toggle("hidden", name !== "chat");
  $("#tab-data").classList.toggle("hidden", name !== "data");
}

// =====================================================================
// 데이터 요약
// =====================================================================
async function loadSummary() {
  try {
    const s = await api("/api/data/summary");
    const grid = $("#summaryGrid");
    grid.innerHTML = "";

    if (!s.count) {
      $("#summaryPeriod").textContent = "저장된 데이터가 없어요.";
      $("#summaryTrend").textContent = "";
      return;
    }

    const m = s.metrics;
    $("#summaryPeriod").textContent = `기간: ${s.period}  |  총 ${fmt(s.count, 0)}건`;

    const stats = [
      ["평균", `${fmt(m.average)}원`, ""],
      ["최고", `${fmt(m.max)}원`, m.max_date],
      ["최저", `${fmt(m.min)}원`, m.min_date],
      ["가장 최근", `${fmt(m.latest)}원`, m.latest_date],
      ["표준편차", fmt(m.std_dev), "가격 변동 정도"],
    ];
    stats.forEach(([label, value, sub]) => {
      const box = el("div", "stat");
      box.append(el("div", "label", label), el("div", "value", value), el("div", "sub", sub));
      grid.appendChild(box);
    });

    const trend = $("#summaryTrend");
    trend.textContent = `📈 최근 트렌드: ${s.trend}`;
    trend.className = "trend" + (s.trend.startsWith("상승") ? " up" : s.trend.startsWith("하락") ? " down" : "");
  } catch (e) {
    $("#summaryPeriod").textContent = "요약을 불러오지 못했어요: " + e.message;
  }
}

// =====================================================================
// 채팅
// =====================================================================
function scrollMessages() {
  const box = $("#messages");
  box.scrollTop = box.scrollHeight;
}

function addMessage(role, text, toolsUsed = []) {
  const row = el("div", `msg ${role}`);
  const wrap = el("div");
  wrap.appendChild(el("div", "bubble", text));
  if (toolsUsed.length) {
    wrap.appendChild(el("div", "tool-note", `🔧 추가 조회: ${[...new Set(toolsUsed)].join(", ")}`));
  }
  row.appendChild(wrap);
  $("#messages").appendChild(row);
  scrollMessages();
  return row;
}

function addLoading() {
  const row = el("div", "msg assistant");
  const bubble = el("div", "bubble");
  const dots = el("span", "dots");
  dots.innerHTML = "<span>●</span><span>●</span><span>●</span>"; // 고정 문자열이라 안전
  bubble.append(dots, document.createTextNode(" AI가 데이터를 확인하고 있어요..."));
  row.appendChild(bubble);
  $("#messages").appendChild(row);
  scrollMessages();
  return row;
}

function showWelcome() {
  const box = $("#messages");
  box.innerHTML = "";
  const welcome = el("div", "welcome");
  welcome.appendChild(el("div", "", "김해시 휘발유 가격 데이터에 대해 무엇이든 물어보세요 ⛽"));
  const chips = el("div", "chips");
  EXAMPLE_QUESTIONS.forEach((q) => {
    const chip = el("button", "chip", q);
    chip.addEventListener("click", () => sendMessage(q));
    chips.appendChild(chip);
  });
  welcome.appendChild(chips);
  box.appendChild(welcome);
}

function setSending(isSending) {
  sending = isSending;
  $("#sendBtn").disabled = isSending;
  $("#chatInput").disabled = isSending;
  $("#sendBtn").textContent = isSending ? "응답 중..." : "전송";
}

async function sendMessage(text) {
  text = (text || "").trim();
  if (!text || sending) return;

  showTab("chat");
  if ($("#messages .welcome")) $("#messages").innerHTML = "";
  addMessage("user", text);
  $("#chatInput").value = "";
  setSending(true);
  const loading = addLoading();

  try {
    const body = { message: text };
    if (currentConversationId) body.conversation_id = currentConversationId;

    const res = await api("/api/chat", { method: "POST", body: JSON.stringify(body) });
    loading.remove();
    addMessage("assistant", res.reply, res.tools_used || []);
    currentConversationId = res.conversation_id;
    await loadConversations();
  } catch (e) {
    loading.remove();
    addMessage("error", "⚠️ " + e.message);
  } finally {
    setSending(false);
    $("#chatInput").focus();
  }
}

function initChat() {
  $("#sendBtn").addEventListener("click", () => sendMessage($("#chatInput").value));
  $("#chatInput").addEventListener("keydown", (e) => {
    // 한글 입력 중 Enter(조합 확정)는 전송하지 않음
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      sendMessage($("#chatInput").value);
    }
  });
  $("#newChatBtn").addEventListener("click", newConversation);
}

// =====================================================================
// 대화 기록
// =====================================================================
function newConversation() {
  currentConversationId = null;
  showWelcome();
  showTab("chat");
  highlightActiveConversation();
}

function highlightActiveConversation() {
  document.querySelectorAll(".conv-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.id === currentConversationId);
  });
}

async function loadConversations() {
  try {
    const list = await api("/api/conversations");
    const ul = $("#convList");
    ul.innerHTML = "";

    if (!list.length) {
      ul.appendChild(el("li", "muted small", "아직 저장된 대화가 없어요."));
      return;
    }

    list.forEach((c) => {
      const li = el("li", "conv-item");
      li.dataset.id = c.id;

      const info = el("div", "conv-info");
      info.appendChild(el("div", "conv-title", c.title));
      const date = new Date(c.updated_at).toLocaleString("ko-KR", {
        month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit",
      });
      info.appendChild(el("div", "conv-meta", `${date} · 메시지 ${c.message_count}개`));

      const del = el("button", "conv-del", "✕");
      del.title = "대화 삭제";
      del.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteConversation(c);
      });

      li.append(info, del);
      li.addEventListener("click", () => openConversation(c.id));
      ul.appendChild(li);
    });
    highlightActiveConversation();
  } catch (e) {
    $("#convList").textContent = "목록을 불러오지 못했어요: " + e.message;
  }
}

async function openConversation(id) {
  try {
    const conv = await api(`/api/conversations/${encodeURIComponent(id)}`);
    currentConversationId = conv.id;
    $("#messages").innerHTML = "";
    conv.messages.forEach((m) => addMessage(m.role, m.content));
    showTab("chat");
    highlightActiveConversation();
  } catch (e) {
    showToast(e.message, true);
  }
}

async function deleteConversation(conv) {
  if (!confirm(`"${conv.title}" 대화를 삭제할까요?`)) return;
  try {
    await api(`/api/conversations/${encodeURIComponent(conv.id)}`, { method: "DELETE" });
    if (conv.id === currentConversationId) newConversation();
    showToast("대화를 삭제했어요.");
    await loadConversations();
  } catch (e) {
    showToast(e.message, true);
  }
}

// =====================================================================
// 데이터 관리 (CRUD)
// =====================================================================
function todayString() {
  return new Date().toLocaleDateString("sv-SE"); // YYYY-MM-DD (내 시간대 기준)
}

async function loadData() {
  try {
    const items = await api(`/api/data?order=desc&limit=${PAGE_SIZE}&offset=${dataOffset}`);
    const tbody = $("#dataBody");
    tbody.innerHTML = "";

    if (!items.length) {
      const tr = el("tr");
      const td = el("td", "empty", "데이터가 없어요.");
      td.colSpan = 4;
      tr.appendChild(td);
      tbody.appendChild(tr);
    } else {
      items.forEach((item) => tbody.appendChild(buildRow(item)));
    }

    $("#prevBtn").disabled = dataOffset === 0;
    $("#nextBtn").disabled = items.length < PAGE_SIZE;
    $("#pageInfo").textContent = items.length
      ? `${dataOffset + 1} ~ ${dataOffset + items.length}번째`
      : "";
  } catch (e) {
    showToast(e.message, true);
  }
}

function buildRow(item) {
  const tr = el("tr");
  tr.append(el("td", "", item.date), el("td", "", `${fmt(item.value)}원`), el("td", "", item.memo || ""));

  const actions = el("td", "actions");
  const editBtn = el("button", "", "수정");
  editBtn.addEventListener("click", () => tr.replaceWith(buildEditRow(item)));
  const delBtn = el("button", "danger", "삭제");
  delBtn.addEventListener("click", () => deleteData(item));
  actions.append(editBtn, delBtn);
  tr.appendChild(actions);
  return tr;
}

function buildEditRow(item) {
  const tr = el("tr");

  const dateInput = el("input");
  dateInput.type = "date";
  dateInput.value = item.date;

  const valueInput = el("input");
  valueInput.type = "number";
  valueInput.step = "0.1";
  valueInput.min = "0.1";
  valueInput.value = item.value;

  const memoInput = el("input");
  memoInput.type = "text";
  memoInput.maxLength = 100;
  memoInput.value = item.memo || "";

  [dateInput, valueInput, memoInput].forEach((input) => {
    const td = el("td");
    td.appendChild(input);
    tr.appendChild(td);
  });

  const actions = el("td", "actions");
  const saveBtn = el("button", "primary", "저장");
  saveBtn.addEventListener("click", async () => {
    const value = Number(valueInput.value);
    if (!dateInput.value || !(value > 0)) {
      showToast("날짜와 0보다 큰 가격을 입력해 주세요.", true);
      return;
    }
    try {
      await api(`/api/data/${encodeURIComponent(item.id)}`, {
        method: "PUT",
        body: JSON.stringify({ date: dateInput.value, value, memo: memoInput.value }),
      });
      showToast("수정했어요.");
      await Promise.all([loadData(), loadSummary()]);
    } catch (e) {
      showToast(e.message, true);
    }
  });
  const cancelBtn = el("button", "", "취소");
  cancelBtn.addEventListener("click", () => tr.replaceWith(buildRow(item)));
  actions.append(saveBtn, cancelBtn);
  tr.appendChild(actions);
  return tr;
}

async function deleteData(item) {
  if (!confirm(`${item.date} 데이터(${fmt(item.value)}원)를 삭제할까요?`)) return;
  try {
    await api(`/api/data/${encodeURIComponent(item.id)}`, { method: "DELETE" });
    showToast("삭제했어요.");
    await Promise.all([loadData(), loadSummary()]);
  } catch (e) {
    showToast(e.message, true);
  }
}

function initDataForm() {
  $("#addDate").value = todayString();

  $("#addForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const value = Number($("#addValue").value);
    if (!(value > 0)) {
      showToast("가격은 0보다 커야 해요.", true);
      return;
    }
    try {
      await api("/api/data", {
        method: "POST",
        body: JSON.stringify({ date: $("#addDate").value, value, memo: $("#addMemo").value }),
      });
      showToast("추가했어요.");
      $("#addValue").value = "";
      $("#addMemo").value = "";
      dataOffset = 0;
      await Promise.all([loadData(), loadSummary()]);
    } catch (err) {
      showToast(err.message, true); // 같은 날짜가 있으면 409 메시지가 표시됨
    }
  });

  $("#prevBtn").addEventListener("click", () => {
    dataOffset = Math.max(0, dataOffset - PAGE_SIZE);
    loadData();
  });
  $("#nextBtn").addEventListener("click", () => {
    dataOffset += PAGE_SIZE;
    loadData();
  });
}

// =====================================================================
// 시작
// =====================================================================
document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initTabs();
  initChat();
  initDataForm();
  showWelcome();

  loadSummary();
  loadConversations();
  loadData();
});
