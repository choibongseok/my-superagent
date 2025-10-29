import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'api_client.dart';

/// Provider for ApiClient singleton
final apiClientProvider = Provider<ApiClient>((ref) {
  // TODO: Get base URL from environment or config
  const baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000/api/v1',
  );

  return ApiClient(baseUrl: baseUrl);
});
