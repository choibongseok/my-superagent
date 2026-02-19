/**
 * #218 First Task Celebration
 *
 * 첫 번째 Task 완료 시 confetti 애니메이션과 공유 버튼을 표시합니다.
 * localStorage를 사용하여 첫 Task 여부를 체크합니다.
 */
import { useEffect, useRef, useState } from 'react';

// ── Canvas-confetti를 CDN 없이 직접 구현한 경량 confetti ──────────────────
interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  color: string;
  size: number;
  rotation: number;
  rotationSpeed: number;
  opacity: number;
}

function launchConfetti(canvas: HTMLCanvasElement, durationMs = 3000): void {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const colors = [
    '#ff6b6b',
    '#ffa502',
    '#2ed573',
    '#1e90ff',
    '#a29bfe',
    '#fd79a8',
    '#fdcb6e',
  ];
  const particles: Particle[] = [];

  // 초기 파티클 생성
  for (let i = 0; i < 120; i++) {
    particles.push({
      x: Math.random() * canvas.width,
      y: -20,
      vx: (Math.random() - 0.5) * 6,
      vy: Math.random() * 4 + 2,
      color: colors[Math.floor(Math.random() * colors.length)],
      size: Math.random() * 8 + 4,
      rotation: Math.random() * 360,
      rotationSpeed: (Math.random() - 0.5) * 10,
      opacity: 1,
    });
  }

  const start = performance.now();

  function animate(now: number) {
    const elapsed = now - start;
    if (elapsed > durationMs) {
      ctx!.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }

    ctx!.clearRect(0, 0, canvas.width, canvas.height);

    for (const p of particles) {
      p.x += p.vx;
      p.y += p.vy;
      p.vy += 0.1; // 중력
      p.rotation += p.rotationSpeed;
      p.opacity = Math.max(0, 1 - elapsed / durationMs);

      ctx!.save();
      ctx!.globalAlpha = p.opacity;
      ctx!.translate(p.x, p.y);
      ctx!.rotate((p.rotation * Math.PI) / 180);
      ctx!.fillStyle = p.color;
      ctx!.fillRect(-p.size / 2, -p.size / 2, p.size, p.size * 0.5);
      ctx!.restore();
    }

    requestAnimationFrame(animate);
  }

  requestAnimationFrame(animate);
}

// ── Storage helpers ────────────────────────────────────────────────────────
const FIRST_TASK_KEY = 'first_task_done';
const CELEBRATION_SHOWN_KEY = 'celebration_shown';

export function markFirstTaskDone(): void {
  if (!localStorage.getItem(FIRST_TASK_KEY)) {
    localStorage.setItem(FIRST_TASK_KEY, 'true');
  }
}

export function shouldShowCelebration(): boolean {
  return (
    !!localStorage.getItem(FIRST_TASK_KEY) &&
    !localStorage.getItem(CELEBRATION_SHOWN_KEY)
  );
}

export function markCelebrationShown(): void {
  localStorage.setItem(CELEBRATION_SHOWN_KEY, 'true');
}

/** 테스트용: celebration 상태를 초기화합니다 */
export function resetCelebrationState(): void {
  localStorage.removeItem(FIRST_TASK_KEY);
  localStorage.removeItem(CELEBRATION_SHOWN_KEY);
}

// ── React 컴포넌트 ─────────────────────────────────────────────────────────

interface CelebrationModalProps {
  taskId?: string;
  onClose: () => void;
  shareBaseUrl?: string;
}

/**
 * 첫 Task 완료 축하 모달
 *
 * @example
 * // Task 완료 직후 호출
 * markFirstTaskDone();
 * // shouldShowCelebration() === true 이면 이 컴포넌트를 렌더
 */
export function CelebrationModal({
  taskId,
  onClose,
  shareBaseUrl = window.location.origin,
}: CelebrationModalProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [copied, setCopied] = useState(false);

  // 마운트 시 confetti 실행
  useEffect(() => {
    if (canvasRef.current) {
      launchConfetti(canvasRef.current, 3500);
    }
    markCelebrationShown();
  }, []);

  const shareUrl = taskId ? `${shareBaseUrl}/r/${taskId}` : shareBaseUrl;

  async function handleCopyLink() {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // fallback for non-https
      const input = document.createElement('input');
      input.value = shareUrl;
      document.body.appendChild(input);
      input.select();
      document.execCommand('copy');
      document.body.removeChild(input);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }

  return (
    <div style={styles.overlay}>
      {/* Confetti canvas — 화면 전체를 덮음 */}
      <canvas
        ref={canvasRef}
        width={window.innerWidth}
        height={window.innerHeight}
        style={styles.canvas}
      />

      {/* 모달 카드 */}
      <div style={styles.card}>
        <div style={styles.emoji}>🎉</div>
        <h2 style={styles.title}>첫 번째 Task 완료!</h2>
        <p style={styles.subtitle}>
          AgentHQ로 만든 첫 결과물이에요.
          <br />
          지인에게 공유해 보세요!
        </p>

        <div style={styles.actions}>
          <button style={styles.copyButton} onClick={handleCopyLink}>
            {copied ? '✅ 복사됨!' : '🔗 링크 복사'}
          </button>

          {taskId && (
            <a
              href={shareUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={styles.openButton}
            >
              새 탭에서 열기 ↗
            </a>
          )}
        </div>

        <button style={styles.closeButton} onClick={onClose}>
          닫기
        </button>
      </div>
    </div>
  );
}

// ── Hook — 사용 편의를 위한 wrapper ───────────────────────────────────────

interface UseCelebrationResult {
  visible: boolean;
  show: (taskId?: string) => void;
  hide: () => void;
  taskId: string | undefined;
}

/**
 * 첫 Task 완료 축하 모달을 관리하는 훅
 *
 * @example
 * const { visible, show, hide, taskId } = useCelebration();
 *
 * // Task 완료 콜백에서:
 * markFirstTaskDone();
 * if (shouldShowCelebration()) show(completedTaskId);
 *
 * // JSX에서:
 * {visible && <CelebrationModal taskId={taskId} onClose={hide} />}
 */
export function useCelebration(): UseCelebrationResult {
  const [visible, setVisible] = useState(false);
  const [taskId, setTaskId] = useState<string | undefined>(undefined);

  function show(id?: string) {
    setTaskId(id);
    setVisible(true);
  }

  function hide() {
    setVisible(false);
  }

  return { visible, show, hide, taskId };
}

// ── Inline styles ──────────────────────────────────────────────────────────
const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed',
    inset: 0,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 9999,
    backgroundColor: 'rgba(0,0,0,0.45)',
  },
  canvas: {
    position: 'absolute',
    inset: 0,
    pointerEvents: 'none',
  },
  card: {
    position: 'relative',
    backgroundColor: '#1e1e2e',
    border: '1px solid rgba(255,255,255,0.12)',
    borderRadius: 20,
    padding: '40px 48px',
    textAlign: 'center',
    maxWidth: 420,
    width: '90%',
    boxShadow: '0 24px 60px rgba(0,0,0,0.5)',
    color: '#fff',
    fontFamily: 'system-ui, -apple-system, sans-serif',
  },
  emoji: { fontSize: 56, marginBottom: 12 },
  title: { margin: '0 0 10px', fontSize: 26, fontWeight: 700 },
  subtitle: {
    margin: '0 0 28px',
    fontSize: 15,
    color: 'rgba(255,255,255,0.7)',
    lineHeight: 1.6,
  },
  actions: {
    display: 'flex',
    gap: 12,
    justifyContent: 'center',
    flexWrap: 'wrap',
    marginBottom: 24,
  },
  copyButton: {
    padding: '10px 22px',
    borderRadius: 10,
    border: 'none',
    backgroundColor: '#7c3aed',
    color: '#fff',
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
  },
  openButton: {
    padding: '10px 22px',
    borderRadius: 10,
    border: '1px solid rgba(255,255,255,0.2)',
    backgroundColor: 'transparent',
    color: '#fff',
    fontSize: 14,
    fontWeight: 600,
    textDecoration: 'none',
  },
  closeButton: {
    background: 'none',
    border: 'none',
    color: 'rgba(255,255,255,0.4)',
    fontSize: 13,
    cursor: 'pointer',
    textDecoration: 'underline',
  },
};
