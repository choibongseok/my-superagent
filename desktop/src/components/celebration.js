/**
 * #218 First Task Celebration — Vanilla JS
 *
 * 첫 번째 Task 완료 시 confetti 애니메이션 + 공유 버튼을 표시합니다.
 * share.py (#200) 공유 링크와 연동됩니다.
 * React 없이 순수 JS로 동작 (CDN / 직접 <script> 로드 가능).
 *
 * Usage:
 *   import { checkFirstTaskCelebration } from './celebration.js';
 *   // Task 완료 콜백에서:
 *   checkFirstTaskCelebration(taskId);
 *
 *   // 또는 share_token 기반 URL 직접 지정:
 *   checkFirstTaskCelebration(null, 'https://your-app.com/r/abc-token');
 */

'use strict';

// ── Constants ──────────────────────────────────────────────────────────────
const FIRST_TASK_KEY       = 'first_task_done';
const CELEBRATION_KEY      = 'celebration_shown';
const SHARE_BASE_URL_KEY   = 'share_base_url';

// ── Confetti ───────────────────────────────────────────────────────────────

/**
 * 경량 confetti 애니메이션 (canvas 기반, 의존성 없음)
 * @param {HTMLCanvasElement} canvas
 * @param {number} durationMs
 */
function launchConfetti(canvas, durationMs = 3500) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const COLORS = [
    '#ff6b6b', '#ffa502', '#2ed573',
    '#1e90ff', '#a29bfe', '#fd79a8', '#fdcb6e',
  ];

  const particles = Array.from({ length: 130 }, () => ({
    x:             Math.random() * canvas.width,
    y:             -20,
    vx:            (Math.random() - 0.5) * 6,
    vy:            Math.random() * 4 + 2,
    color:         COLORS[Math.floor(Math.random() * COLORS.length)],
    size:          Math.random() * 8 + 4,
    rotation:      Math.random() * 360,
    rotSpeed:      (Math.random() - 0.5) * 10,
    opacity:       1,
  }));

  const start = performance.now();

  function animate(now) {
    const elapsed = now - start;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (elapsed > durationMs) return;

    for (const p of particles) {
      p.x  += p.vx;
      p.y  += p.vy;
      p.vy += 0.1;          // gravity
      p.rotation += p.rotSpeed;
      p.opacity = Math.max(0, 1 - elapsed / durationMs);

      ctx.save();
      ctx.globalAlpha = p.opacity;
      ctx.translate(p.x, p.y);
      ctx.rotate((p.rotation * Math.PI) / 180);
      ctx.fillStyle = p.color;
      ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.5);
      ctx.restore();
    }

    requestAnimationFrame(animate);
  }

  requestAnimationFrame(animate);
}

// ── Share URL helpers ──────────────────────────────────────────────────────

/**
 * share.py (#200) /r/{token} 형식의 공유 URL 반환
 * @param {string|null} taskId  task_id 또는 share_token
 * @param {string} [base]       기본 오리진 (기본값: 현재 origin)
 * @returns {string}
 */
function buildShareUrl(taskId, base) {
  const origin = base || localStorage.getItem(SHARE_BASE_URL_KEY) || window.location.origin;
  return taskId ? `${origin}/r/${taskId}` : origin;
}

// ── Storage helpers ────────────────────────────────────────────────────────

/** 첫 Task 완료 여부를 localStorage에 기록 */
export function markFirstTaskDone() {
  if (!localStorage.getItem(FIRST_TASK_KEY)) {
    localStorage.setItem(FIRST_TASK_KEY, 'true');
  }
}

/** 축하 모달을 아직 보여줘야 하는지 확인 */
export function shouldShowCelebration() {
  return (
    !!localStorage.getItem(FIRST_TASK_KEY) &&
    !localStorage.getItem(CELEBRATION_KEY)
  );
}

/** 축하 모달이 이미 표시됐음을 기록 */
export function markCelebrationShown() {
  localStorage.setItem(CELEBRATION_KEY, 'true');
}

/** 테스트용: celebration 상태 초기화 */
export function resetCelebrationState() {
  localStorage.removeItem(FIRST_TASK_KEY);
  localStorage.removeItem(CELEBRATION_KEY);
}

// ── Modal DOM builder ──────────────────────────────────────────────────────

const MODAL_ID = 'agenthq-celebration-modal';

/**
 * DOM에 축하 모달 + confetti 오버레이를 삽입합니다.
 * @param {string|null} taskId   share_token / task id (null이면 링크 버튼 숨김)
 * @param {string}      [base]   share base URL
 * @returns {() => void}  cleanup 함수 (모달 제거)
 */
function mountCelebrationModal(taskId, base) {
  // 중복 방지
  if (document.getElementById(MODAL_ID)) return () => {};

  const shareUrl = buildShareUrl(taskId, base);

  // --- overlay ---
  const overlay = document.createElement('div');
  overlay.id = MODAL_ID;
  Object.assign(overlay.style, {
    position:        'fixed',
    inset:           '0',
    display:         'flex',
    alignItems:      'center',
    justifyContent:  'center',
    zIndex:          '9999',
    backgroundColor: 'rgba(0,0,0,0.45)',
    fontFamily:      'system-ui, -apple-system, sans-serif',
  });

  // --- confetti canvas ---
  const canvas = document.createElement('canvas');
  canvas.width  = window.innerWidth;
  canvas.height = window.innerHeight;
  Object.assign(canvas.style, {
    position:      'absolute',
    inset:         '0',
    pointerEvents: 'none',
  });
  overlay.appendChild(canvas);

  // --- card ---
  const card = document.createElement('div');
  Object.assign(card.style, {
    position:        'relative',
    backgroundColor: '#1e1e2e',
    border:          '1px solid rgba(255,255,255,0.12)',
    borderRadius:    '20px',
    padding:         '40px 48px',
    textAlign:       'center',
    maxWidth:        '420px',
    width:           '90%',
    boxShadow:       '0 24px 60px rgba(0,0,0,0.5)',
    color:           '#fff',
  });

  card.innerHTML = `
    <div style="font-size:56px;margin-bottom:12px">🎉</div>
    <h2 style="margin:0 0 10px;font-size:26px;font-weight:700">첫 번째 Task 완료!</h2>
    <p style="margin:0 0 28px;font-size:15px;color:rgba(255,255,255,.7);line-height:1.6">
      AgentHQ로 만든 첫 결과물이에요.<br>지인에게 공유해 보세요!
    </p>
    <div id="_cel-actions" style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-bottom:24px">
      <button id="_cel-copy" style="
        padding:10px 22px;border-radius:10px;border:none;
        background:#7c3aed;color:#fff;font-size:14px;font-weight:600;cursor:pointer">
        🔗 링크 복사
      </button>
      ${taskId ? `
      <a href="${shareUrl}" target="_blank" rel="noopener noreferrer" style="
        padding:10px 22px;border-radius:10px;
        border:1px solid rgba(255,255,255,.2);background:transparent;
        color:#fff;font-size:14px;font-weight:600;text-decoration:none">
        새 탭에서 열기 ↗
      </a>` : ''}
    </div>
    <button id="_cel-close" style="
      background:none;border:none;color:rgba(255,255,255,.4);
      font-size:13px;cursor:pointer;text-decoration:underline">
      닫기
    </button>
  `;

  overlay.appendChild(card);
  document.body.appendChild(overlay);

  // --- confetti ---
  launchConfetti(canvas);
  markCelebrationShown();

  // --- events ---
  const copyBtn  = card.querySelector('#_cel-copy');
  const closeBtn = card.querySelector('#_cel-close');

  function cleanup() {
    overlay.remove();
  }

  closeBtn.addEventListener('click', cleanup);

  copyBtn.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
    } catch {
      // fallback
      const inp = document.createElement('input');
      inp.value = shareUrl;
      document.body.appendChild(inp);
      inp.select();
      document.execCommand('copy');
      inp.remove();
    }
    copyBtn.textContent = '✅ 복사됨!';
    setTimeout(() => { copyBtn.textContent = '🔗 링크 복사'; }, 2000);
  });

  return cleanup;
}

// ── Primary API ────────────────────────────────────────────────────────────

/**
 * Task 완료 직후 호출하는 메인 함수.
 * 첫 번째 Task인 경우에만 confetti + 공유 모달을 표시합니다.
 *
 * @param {string|null} taskId     완료된 task의 id 또는 share_token
 * @param {string}      [shareUrl] 공유 링크를 직접 지정할 경우 (선택)
 *
 * @example
 * // Task 완료 콜백에서:
 * import { checkFirstTaskCelebration } from './celebration.js';
 * checkFirstTaskCelebration(task.share_token);
 *
 * // 또는 직접 URL 지정:
 * checkFirstTaskCelebration(null, 'https://app.example.com/r/abc123');
 */
export function checkFirstTaskCelebration(taskId, shareUrl) {
  markFirstTaskDone();

  if (!shouldShowCelebration()) return;

  // shareUrl이 전달된 경우 base 추출
  let base;
  if (shareUrl) {
    try {
      const parsed = new URL(shareUrl);
      base = parsed.origin;
      // share_token이 URL 안에 있으면 taskId로 사용
      if (!taskId) {
        const parts = parsed.pathname.split('/');
        taskId = parts[parts.length - 1] || null;
      }
    } catch {
      base = shareUrl;
    }
  }

  mountCelebrationModal(taskId, base);
}

// ── triggerConfetti (standalone, 모달 없이 confetti만) ────────────────────

/**
 * 모달 없이 confetti 애니메이션만 실행합니다.
 * @param {number} [durationMs=3500]
 */
export function triggerConfetti(durationMs = 3500) {
  const canvas = document.createElement('canvas');
  canvas.width  = window.innerWidth;
  canvas.height = window.innerHeight;
  Object.assign(canvas.style, {
    position:      'fixed',
    inset:         '0',
    zIndex:        '9998',
    pointerEvents: 'none',
  });
  document.body.appendChild(canvas);
  launchConfetti(canvas, durationMs);
  setTimeout(() => canvas.remove(), durationMs + 200);
}
