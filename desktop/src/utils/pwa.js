/**
 * #217 PWA Install Prompt — Vanilla JS
 *
 * 3번째 방문 시 PWA 설치 배너를 표시합니다.
 * React 없이 순수 JS로 동작 (CDN / 직접 <script> 로드 가능).
 *
 * Usage:
 *   import { initPwaPrompt } from './pwa.js';
 *   // 앱 진입점(main.js)에서 한 번만 호출:
 *   initPwaPrompt();
 *
 *   // 콜백으로 커스텀 배너 연동:
 *   initPwaPrompt(() => document.getElementById('install-banner').hidden = false);
 *
 *   // 수동 설치 트리거 (버튼 클릭 등):
 *   import { triggerInstallPrompt } from './pwa.js';
 *   installBtn.addEventListener('click', () => triggerInstallPrompt());
 */

'use strict';

// ── Constants ──────────────────────────────────────────────────────────────
const VISIT_COUNT_KEY     = 'pwa_visit_count';
const PROMPTED_KEY        = 'pwa_install_prompted';
const ACCEPTED_KEY        = 'pwa_install_accepted';
const PROMPT_THRESHOLD    = 3;   // N번째 방문부터 배너 표시
const BANNER_ID           = 'agenthq-pwa-banner';

// ── Module state ───────────────────────────────────────────────────────────
let _deferredPrompt   = null;   // BeforeInstallPromptEvent
let _onBannerReady    = null;   // callback

// ── Visit counter ──────────────────────────────────────────────────────────

/** 방문 횟수를 읽어옵니다 */
export function getVisitCount() {
  return parseInt(localStorage.getItem(VISIT_COUNT_KEY) || '0', 10);
}

/** 방문 횟수를 1 증가시키고 새 값을 반환합니다 */
export function incrementVisitCount() {
  const next = getVisitCount() + 1;
  localStorage.setItem(VISIT_COUNT_KEY, String(next));
  return next;
}

// ── State queries ──────────────────────────────────────────────────────────

/** 설치 프롬프트를 이미 표시한 적이 있는지 확인 */
export function hasBeenPrompted() {
  return !!localStorage.getItem(PROMPTED_KEY);
}

/** 이미 설치(수락)했는지 또는 standalone 모드인지 확인 */
export function isInstalled() {
  if (localStorage.getItem(ACCEPTED_KEY)) return true;
  if (typeof window.matchMedia === 'function' &&
      window.matchMedia('(display-mode: standalone)').matches) return true;
  if (typeof navigator.standalone === 'boolean' && navigator.standalone) return true;
  return false;
}

/** 지금 설치 배너를 표시해야 하는지 판단 */
export function shouldShowInstallBanner() {
  if (isInstalled())    return false;
  if (hasBeenPrompted()) return false;
  return getVisitCount() >= PROMPT_THRESHOLD;
}

/** beforeinstallprompt 이벤트가 캐치되어 있는지 확인 */
export function isInstallPromptAvailable() {
  return _deferredPrompt !== null;
}

// ── Main initializer ───────────────────────────────────────────────────────

/**
 * PWA 설치 프롬프트를 초기화합니다.
 * 앱 로드 시 한 번 호출하세요.
 *
 * @param {(() => void)|null} [onBannerReady]
 *   배너를 표시해야 할 때 호출되는 콜백.
 *   null(기본값)이면 내장 기본 배너 DOM이 자동으로 삽입됩니다.
 *
 * @example
 * // 기본 내장 배너 사용
 * initPwaPrompt();
 *
 * // 커스텀 배너
 * initPwaPrompt(() => {
 *   document.getElementById('my-banner').hidden = false;
 * });
 */
export function initPwaPrompt(onBannerReady) {
  if (isInstalled()) return;

  _onBannerReady = onBannerReady ?? null;

  // 방문 횟수 증가 (페이지 로드마다 1회)
  const visitCount = incrementVisitCount();

  // beforeinstallprompt 이벤트 캐치
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    _deferredPrompt = e;

    if (visitCount >= PROMPT_THRESHOLD && !hasBeenPrompted()) {
      _showBanner();
    }
  });

  // appinstalled 이벤트 → 배너 제거
  window.addEventListener('appinstalled', () => {
    localStorage.setItem(ACCEPTED_KEY, 'true');
    _removeBanner();
  });

  // 이미 threshold에 도달했지만 이벤트가 아직 안 왔을 수 있으므로
  // 500ms 후 한 번 더 확인
  if (visitCount >= PROMPT_THRESHOLD && !hasBeenPrompted()) {
    setTimeout(() => {
      if (_deferredPrompt && !hasBeenPrompted()) {
        _showBanner();
      }
    }, 500);
  }
}

// ── Install action ─────────────────────────────────────────────────────────

/**
 * 브라우저 기본 설치 다이얼로그를 호출합니다.
 * beforeinstallprompt 이벤트가 캐치된 경우에만 동작합니다.
 *
 * @returns {Promise<'accepted'|'dismissed'|'unavailable'>}
 *
 * @example
 * document.getElementById('install-btn').addEventListener('click', async () => {
 *   const result = await triggerInstallPrompt();
 *   console.log(result); // 'accepted' | 'dismissed' | 'unavailable'
 * });
 */
export async function triggerInstallPrompt() {
  localStorage.setItem(PROMPTED_KEY, 'true');
  _removeBanner();

  if (!_deferredPrompt) return 'unavailable';

  await _deferredPrompt.prompt();
  const { outcome } = await _deferredPrompt.userChoice;

  if (outcome === 'accepted') {
    localStorage.setItem(ACCEPTED_KEY, 'true');
  }

  _deferredPrompt = null;
  return outcome;
}

/** 배너 닫기 (설치 없이 무시) */
export function dismissInstallBanner() {
  localStorage.setItem(PROMPTED_KEY, 'true');
  _removeBanner();
}

// ── Built-in banner DOM ────────────────────────────────────────────────────

function _showBanner() {
  if (_onBannerReady) {
    _onBannerReady();
    return;
  }
  _mountDefaultBanner();
}

function _removeBanner() {
  document.getElementById(BANNER_ID)?.remove();
}

/**
 * 기본 설치 배너를 DOM에 삽입합니다.
 * 커스텀 콜백을 initPwaPrompt에 전달하면 이 함수는 호출되지 않습니다.
 */
function _mountDefaultBanner() {
  if (document.getElementById(BANNER_ID)) return;

  const banner = document.createElement('div');
  banner.id = BANNER_ID;
  Object.assign(banner.style, {
    position:        'fixed',
    bottom:          '24px',
    left:            '50%',
    transform:       'translateX(-50%)',
    display:         'flex',
    alignItems:      'center',
    gap:             '12px',
    backgroundColor: '#1e1e2e',
    border:          '1px solid rgba(255,255,255,0.12)',
    borderRadius:    '14px',
    padding:         '12px 20px',
    zIndex:          '9998',
    boxShadow:       '0 8px 32px rgba(0,0,0,0.4)',
    color:           '#fff',
    fontFamily:      'system-ui, -apple-system, sans-serif',
    maxWidth:        '90vw',
    whiteSpace:      'nowrap',
  });

  banner.innerHTML = `
    <span style="font-size:28px">📥</span>
    <div style="display:flex;flex-direction:column;gap:2px;flex:1;font-size:14px">
      <strong>AgentHQ 앱 설치</strong>
      <span style="font-size:12px;color:rgba(255,255,255,.55)">오프라인에서도 빠르게 사용하세요</span>
    </div>
    <div style="display:flex;gap:8px;align-items:center">
      <button id="_pwa-install-btn" style="
        padding:7px 18px;border-radius:8px;border:none;
        background:#7c3aed;color:#fff;font-weight:600;font-size:13px;cursor:pointer">
        설치
      </button>
      <button id="_pwa-dismiss-btn" style="
        background:none;border:none;color:rgba(255,255,255,.4);
        font-size:16px;cursor:pointer;padding:4px 6px;border-radius:6px">
        ✕
      </button>
    </div>
  `;

  document.body.appendChild(banner);

  const installBtn  = banner.querySelector('#_pwa-install-btn');
  const dismissBtn  = banner.querySelector('#_pwa-dismiss-btn');

  installBtn.addEventListener('click', async () => {
    installBtn.textContent = '설치 중…';
    installBtn.disabled    = true;
    await triggerInstallPrompt();
  });

  dismissBtn.addEventListener('click', () => {
    dismissInstallBanner();
  });
}

// ── showInstallBanner (스프린트 플랜 스니펫 호환 alias) ─────────────────────

/**
 * 배너를 강제로 표시합니다.
 * sprint-plan.md 스니펫과의 호환을 위해 제공됩니다.
 * 내부적으로 _showBanner()와 동일합니다.
 */
export function showInstallBanner() {
  _showBanner();
}
