/**
 * #217 PWA Install Prompt
 *
 * 3번째 방문 시 PWA 설치 프롬프트를 표시합니다.
 * beforeinstallprompt 이벤트를 캐치하고 localStorage로 방문 횟수를 추적합니다.
 */

// ── Types ─────────────────────────────────────────────────────────────────

interface BeforeInstallPromptEvent extends Event {
  readonly platforms: string[];
  readonly userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>;
  prompt(): Promise<void>;
}

export type InstallOutcome = 'accepted' | 'dismissed' | 'unavailable';

// ── Constants ──────────────────────────────────────────────────────────────

const VISIT_COUNT_KEY = 'pwa_visit_count';
const INSTALL_PROMPTED_KEY = 'pwa_install_prompted';
const INSTALL_ACCEPTED_KEY = 'pwa_install_accepted';
const PROMPT_THRESHOLD = 3; // N번째 방문부터 프롬프트 표시

// ── State ─────────────────────────────────────────────────────────────────

let _deferredPrompt: BeforeInstallPromptEvent | null = null;
let _onBannerReadyCallback: (() => void) | null = null;

// ── Core helpers ──────────────────────────────────────────────────────────

/** 방문 횟수를 읽어옵니다 */
export function getVisitCount(): number {
  return parseInt(localStorage.getItem(VISIT_COUNT_KEY) || '0', 10);
}

/** 방문 횟수를 1 증가시키고 새 값을 반환합니다 */
export function incrementVisitCount(): number {
  const next = getVisitCount() + 1;
  localStorage.setItem(VISIT_COUNT_KEY, String(next));
  return next;
}

/** 이미 설치 프롬프트를 표시한 적 있는지 확인합니다 */
export function hasBeenPrompted(): boolean {
  return !!localStorage.getItem(INSTALL_PROMPTED_KEY);
}

/** 사용자가 설치를 수락했는지 확인합니다 */
export function isInstalled(): boolean {
  // 1) 사용자가 직접 수락한 경우
  if (localStorage.getItem(INSTALL_ACCEPTED_KEY)) return true;
  // 2) standalone 모드로 실행 중인 경우
  if (window.matchMedia?.('(display-mode: standalone)').matches) return true;
  // 3) iOS Safari standalone
  if ((navigator as any).standalone === true) return true;
  return false;
}

/** 지금 설치 배너를 표시해야 하는지 판단합니다 */
export function shouldShowInstallBanner(): boolean {
  if (isInstalled()) return false;
  if (hasBeenPrompted()) return false;
  return getVisitCount() >= PROMPT_THRESHOLD;
}

// ── Main initializer (앱 진입점에서 1회 호출) ─────────────────────────────

/**
 * PWA 설치 프롬프트를 초기화합니다.
 * 앱 최초 로드 시 한 번 호출하세요.
 *
 * @param onBannerReady  배너를 표시해야 할 때 호출되는 콜백
 *
 * @example
 * // main.tsx 또는 App.tsx에서
 * initPwaPrompt(() => setShowInstallBanner(true));
 */
export function initPwaPrompt(onBannerReady?: () => void): void {
  if (isInstalled()) return;

  // 방문 횟수 증가
  const count = incrementVisitCount();
  _onBannerReadyCallback = onBannerReady ?? null;

  // beforeinstallprompt 이벤트 캐치
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    _deferredPrompt = e as BeforeInstallPromptEvent;

    if (count >= PROMPT_THRESHOLD && !hasBeenPrompted()) {
      _onBannerReadyCallback?.();
    }
  });

  // 이미 PROMPT_THRESHOLD에 도달했고 이벤트가 이미 발생했을 수 있으므로
  // 일정 시간 대기 후 배너를 확인
  if (count >= PROMPT_THRESHOLD && !hasBeenPrompted()) {
    // 이벤트가 동기적으로 발생하지 않을 수 있어 약간 지연
    setTimeout(() => {
      if (_deferredPrompt && _onBannerReadyCallback) {
        _onBannerReadyCallback();
      }
    }, 500);
  }
}

// ── Install action ────────────────────────────────────────────────────────

/**
 * 브라우저 기본 설치 다이얼로그를 호출합니다.
 * beforeinstallprompt 이벤트가 캐치된 경우에만 동작합니다.
 *
 * @returns 설치 결과 ('accepted' | 'dismissed' | 'unavailable')
 */
export async function triggerInstallPrompt(): Promise<InstallOutcome> {
  localStorage.setItem(INSTALL_PROMPTED_KEY, 'true');

  if (!_deferredPrompt) return 'unavailable';

  await _deferredPrompt.prompt();
  const { outcome } = await _deferredPrompt.userChoice;

  if (outcome === 'accepted') {
    localStorage.setItem(INSTALL_ACCEPTED_KEY, 'true');
  }

  _deferredPrompt = null;
  return outcome;
}

/** 프롬프트 이벤트가 준비됐는지 확인합니다 */
export function isInstallPromptAvailable(): boolean {
  return _deferredPrompt !== null;
}

// ── React hook ────────────────────────────────────────────────────────────

import { useEffect, useState } from 'react';

interface UsePwaInstallResult {
  /** 배너를 표시해야 하면 true */
  showBanner: boolean;
  /** 이미 설치되었으면 true */
  installed: boolean;
  /** 브라우저 설치 다이얼로그 호출 */
  install: () => Promise<InstallOutcome>;
  /** 배너를 수동으로 닫음 */
  dismissBanner: () => void;
}

/**
 * PWA 설치 프롬프트를 관리하는 훅
 *
 * @example
 * const { showBanner, install, dismissBanner } = usePwaInstall();
 *
 * {showBanner && (
 *   <InstallBanner onInstall={install} onDismiss={dismissBanner} />
 * )}
 */
export function usePwaInstall(): UsePwaInstallResult {
  const [showBanner, setShowBanner] = useState(false);
  const [installed, setInstalled] = useState(isInstalled);

  useEffect(() => {
    initPwaPrompt(() => setShowBanner(true));

    // appinstalled 이벤트 감지
    const handleInstalled = () => {
      setInstalled(true);
      setShowBanner(false);
    };
    window.addEventListener('appinstalled', handleInstalled);
    return () => window.removeEventListener('appinstalled', handleInstalled);
  }, []);

  async function install(): Promise<InstallOutcome> {
    const outcome = await triggerInstallPrompt();
    if (outcome === 'accepted') {
      setInstalled(true);
      setShowBanner(false);
    }
    return outcome;
  }

  function dismissBanner() {
    localStorage.setItem(INSTALL_PROMPTED_KEY, 'true');
    setShowBanner(false);
  }

  return { showBanner, installed, install, dismissBanner };
}

// ── Optional: InstallBanner 컴포넌트 (기본 UI) ───────────────────────────

import React from 'react';

interface InstallBannerProps {
  onInstall: () => Promise<InstallOutcome>;
  onDismiss: () => void;
}

/**
 * 간단한 PWA 설치 배너 UI
 *
 * @example
 * const { showBanner, install, dismissBanner } = usePwaInstall();
 * {showBanner && <InstallBanner onInstall={install} onDismiss={dismissBanner} />}
 */
export function InstallBanner({ onInstall, onDismiss }: InstallBannerProps) {
  const [loading, setLoading] = useState(false);

  async function handleInstall() {
    setLoading(true);
    await onInstall();
    setLoading(false);
  }

  return (
    <div style={bannerStyles.wrapper}>
      <span style={bannerStyles.icon}>📥</span>
      <div style={bannerStyles.text}>
        <strong>AgentHQ 앱 설치</strong>
        <span style={bannerStyles.sub}>오프라인에서도 빠르게 사용하세요</span>
      </div>
      <div style={bannerStyles.buttons}>
        <button
          style={bannerStyles.install}
          onClick={handleInstall}
          disabled={loading}
        >
          {loading ? '설치 중…' : '설치'}
        </button>
        <button style={bannerStyles.dismiss} onClick={onDismiss}>
          ✕
        </button>
      </div>
    </div>
  );
}

const bannerStyles: Record<string, React.CSSProperties> = {
  wrapper: {
    position: 'fixed',
    bottom: 24,
    left: '50%',
    transform: 'translateX(-50%)',
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#1e1e2e',
    border: '1px solid rgba(255,255,255,0.12)',
    borderRadius: 14,
    padding: '12px 20px',
    zIndex: 9998,
    boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
    color: '#fff',
    fontFamily: 'system-ui, -apple-system, sans-serif',
    maxWidth: '90vw',
  },
  icon: { fontSize: 28 },
  text: {
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
    flex: 1,
    fontSize: 14,
  },
  sub: { fontSize: 12, color: 'rgba(255,255,255,0.55)' },
  buttons: { display: 'flex', gap: 8, alignItems: 'center' },
  install: {
    padding: '7px 18px',
    borderRadius: 8,
    border: 'none',
    backgroundColor: '#7c3aed',
    color: '#fff',
    fontWeight: 600,
    fontSize: 13,
    cursor: 'pointer',
  },
  dismiss: {
    background: 'none',
    border: 'none',
    color: 'rgba(255,255,255,0.4)',
    fontSize: 16,
    cursor: 'pointer',
    padding: '4px 6px',
    borderRadius: 6,
  },
};
