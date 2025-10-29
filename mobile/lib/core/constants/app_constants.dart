/// Application-wide constants
class AppConstants {
  // App Info
  static const String appName = 'AgentHQ';
  static const String appVersion = '0.1.0';
  static const String appDescription = 'AI-powered workspace automation';

  // API Configuration
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );
  static const String apiVersion = 'v1';
  static const Duration connectTimeout = Duration(seconds: 30);
  static const Duration receiveTimeout = Duration(seconds: 30);
  static const Duration sendTimeout = Duration(seconds: 30);

  // Storage Keys
  static const String keyAccessToken = 'access_token';
  static const String keyRefreshToken = 'refresh_token';
  static const String keyUserId = 'user_id';
  static const String keyUserEmail = 'user_email';
  static const String keyUserName = 'user_name';
  static const String keyUserAvatar = 'user_avatar';
  static const String keyThemeMode = 'theme_mode';
  static const String keyLanguage = 'language';

  // Hive Boxes
  static const String boxAuth = 'auth_box';
  static const String boxTasks = 'tasks_box';
  static const String boxSettings = 'settings_box';
  static const String boxCache = 'cache_box';

  // Agent Types
  static const String agentDocs = 'docs';
  static const String agentSheets = 'sheets';
  static const String agentSlides = 'slides';
  static const String agentResearch = 'research';
  static const String agentCode = 'code';
  static const String agentImage = 'image';
  static const String agentVideo = 'video';
  static const String agentAudio = 'audio';
  static const String agentData = 'data';
  static const String agentChat = 'chat';
  static const String agentCustom = 'custom';

  // Agent Labels (Korean)
  static const Map<String, String> agentLabels = {
    agentDocs: 'AI 문서',
    agentSheets: 'AI 시트',
    agentSlides: 'AI 슬라이드',
    agentResearch: 'AI 리서치',
    agentCode: 'AI 코드',
    agentImage: 'AI 이미지',
    agentVideo: 'AI 비디오',
    agentAudio: 'AI 오디오',
    agentData: 'AI 데이터',
    agentChat: 'AI 채팅',
    agentCustom: '커스텀',
  };

  // Task Status
  static const String taskStatusPending = 'pending';
  static const String taskStatusInProgress = 'in_progress';
  static const String taskStatusCompleted = 'completed';
  static const String taskStatusFailed = 'failed';

  // Task Status Labels (Korean)
  static const Map<String, String> taskStatusLabels = {
    taskStatusPending: '대기중',
    taskStatusInProgress: '진행중',
    taskStatusCompleted: '완료',
    taskStatusFailed: '실패',
  };

  // Pagination
  static const int defaultPageSize = 20;
  static const int maxPageSize = 100;

  // Cache
  static const Duration cacheExpiration = Duration(hours: 24);
  static const int maxCacheSize = 100;

  // Firebase
  static const String fcmTopicAll = 'all';
  static const String fcmTopicTasks = 'tasks';

  // Google OAuth
  static const List<String> googleScopes = [
    'email',
    'profile',
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/presentations',
    'https://www.googleapis.com/auth/drive.file',
  ];

  // WebSocket
  static const String wsPath = '/ws';
  static const Duration wsReconnectDelay = Duration(seconds: 5);
  static const int wsMaxReconnectAttempts = 5;

  // Error Messages
  static const String errorGeneric = '알 수 없는 오류가 발생했습니다';
  static const String errorNetwork = '네트워크 연결을 확인해주세요';
  static const String errorAuth = '인증에 실패했습니다';
  static const String errorTimeout = '요청 시간이 초과되었습니다';
  static const String errorServer = '서버 오류가 발생했습니다';

  // UI
  static const double borderRadius = 12.0;
  static const double borderRadiusLarge = 16.0;
  static const double borderRadiusSmall = 8.0;
  static const double paddingDefault = 16.0;
  static const double paddingLarge = 24.0;
  static const double paddingSmall = 8.0;

  // Animation
  static const Duration animationDuration = Duration(milliseconds: 300);
  static const Duration animationDurationFast = Duration(milliseconds: 150);
  static const Duration animationDurationSlow = Duration(milliseconds: 500);
}
