import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../errors/app_exception.dart';

/// API Client with Dio for HTTP requests
class ApiClient {
  late final Dio _dio;
  final FlutterSecureStorage _storage;
  final String baseUrl;

  ApiClient({
    required this.baseUrl,
    FlutterSecureStorage? storage,
  }) : _storage = storage ?? const FlutterSecureStorage() {
    _dio = Dio(
      BaseOptions(
        baseUrl: baseUrl,
        connectTimeout: const Duration(seconds: 30),
        receiveTimeout: const Duration(seconds: 30),
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
      ),
    );

    // Add interceptors
    _dio.interceptors.add(_authInterceptor());
    _dio.interceptors.add(_errorInterceptor());
    _dio.interceptors.add(_loggingInterceptor());
  }

  /// Authentication interceptor - injects Bearer token
  Interceptor _authInterceptor() {
    return InterceptorsWrapper(
      onRequest: (options, handler) async {
        // Skip auth for login/register endpoints
        if (options.path.contains('/auth/google') ||
            options.path.contains('/auth/guest')) {
          return handler.next(options);
        }

        // Get token from secure storage
        final token = await _storage.read(key: 'access_token');
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }

        handler.next(options);
      },
      onError: (error, handler) async {
        // Handle 401 Unauthorized - try to refresh token
        if (error.response?.statusCode == 401) {
          final refreshed = await _refreshToken();
          if (refreshed) {
            // Retry original request with new token
            final options = error.requestOptions;
            final token = await _storage.read(key: 'access_token');
            options.headers['Authorization'] = 'Bearer $token';

            try {
              final response = await _dio.fetch(options);
              return handler.resolve(response);
            } catch (e) {
              return handler.next(error);
            }
          }
        }
        handler.next(error);
      },
    );
  }

  /// Error handling interceptor
  Interceptor _errorInterceptor() {
    return InterceptorsWrapper(
      onError: (error, handler) {
        final exception = _handleError(error);
        handler.reject(
          DioException(
            requestOptions: error.requestOptions,
            error: exception,
            response: error.response,
            type: error.type,
          ),
        );
      },
    );
  }

  /// Logging interceptor for debugging
  Interceptor _loggingInterceptor() {
    return InterceptorsWrapper(
      onRequest: (options, handler) {
        print('🌐 REQUEST[${options.method}] => ${options.path}');
        print('Headers: ${options.headers}');
        print('Data: ${options.data}');
        handler.next(options);
      },
      onResponse: (response, handler) {
        print('✅ RESPONSE[${response.statusCode}] => ${response.requestOptions.path}');
        print('Data: ${response.data}');
        handler.next(response);
      },
      onError: (error, handler) {
        print('❌ ERROR[${error.response?.statusCode}] => ${error.requestOptions.path}');
        print('Message: ${error.message}');
        print('Data: ${error.response?.data}');
        handler.next(error);
      },
    );
  }

  /// Refresh access token using refresh token
  Future<bool> _refreshToken() async {
    try {
      final refreshToken = await _storage.read(key: 'refresh_token');
      if (refreshToken == null) return false;

      final response = await _dio.post(
        '/auth/refresh',
        data: {'refresh_token': refreshToken},
      );

      if (response.statusCode == 200) {
        final data = response.data;
        await _storage.write(key: 'access_token', value: data['access_token']);
        if (data['refresh_token'] != null) {
          await _storage.write(key: 'refresh_token', value: data['refresh_token']);
        }
        return true;
      }
      return false;
    } catch (e) {
      print('Token refresh failed: $e');
      return false;
    }
  }

  /// Handle Dio errors and convert to AppException
  AppException _handleError(DioException error) {
    switch (error.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return TimeoutException(
          message: 'Connection timeout',
          originalError: error,
          stackTrace: error.stackTrace,
        );

      case DioExceptionType.badResponse:
        final statusCode = error.response?.statusCode ?? 0;
        final message = error.response?.data?['message'] ?? 
                       error.response?.data?['detail'] ?? 
                       'Server error';

        if (statusCode == 401) {
          return UnauthorizedException(
            message: message,
            originalError: error,
            stackTrace: error.stackTrace,
          );
        } else if (statusCode == 403) {
          return ForbiddenException(
            message: message,
            originalError: error,
            stackTrace: error.stackTrace,
          );
        } else if (statusCode == 404) {
          return NotFoundException(
            message: message,
            originalError: error,
            stackTrace: error.stackTrace,
          );
        } else if (statusCode == 422) {
          return ValidationException(
            message: message,
            errors: _parseValidationErrors(error.response?.data),
            originalError: error,
            stackTrace: error.stackTrace,
          );
        } else {
          return ServerException(
            message: message,
            statusCode: statusCode,
            originalError: error,
            stackTrace: error.stackTrace,
          );
        }

      case DioExceptionType.cancel:
        return NetworkException(
          message: 'Request cancelled',
          originalError: error,
          stackTrace: error.stackTrace,
        );

      case DioExceptionType.connectionError:
      case DioExceptionType.unknown:
      default:
        return NetworkException(
          message: 'Network error: ${error.message}',
          originalError: error,
          stackTrace: error.stackTrace,
        );
    }
  }

  /// Parse validation errors from response
  Map<String, List<String>>? _parseValidationErrors(dynamic data) {
    if (data == null) return null;
    if (data is! Map) return null;

    final errors = <String, List<String>>{};
    if (data['errors'] != null && data['errors'] is Map) {
      (data['errors'] as Map).forEach((key, value) {
        if (value is List) {
          errors[key.toString()] = value.map((e) => e.toString()).toList();
        } else {
          errors[key.toString()] = [value.toString()];
        }
      });
    }
    return errors.isEmpty ? null : errors;
  }

  /// GET request
  Future<Response> get(
    String path, {
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    try {
      final response = await _dio.get(
        path,
        queryParameters: queryParameters,
        options: options,
      );
      return response;
    } on DioException catch (e) {
      throw e.error ?? e;
    }
  }

  /// POST request
  Future<Response> post(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    try {
      final response = await _dio.post(
        path,
        data: data,
        queryParameters: queryParameters,
        options: options,
      );
      return response;
    } on DioException catch (e) {
      throw e.error ?? e;
    }
  }

  /// PUT request
  Future<Response> put(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    try {
      final response = await _dio.put(
        path,
        data: data,
        queryParameters: queryParameters,
        options: options,
      );
      return response;
    } on DioException catch (e) {
      throw e.error ?? e;
    }
  }

  /// DELETE request
  Future<Response> delete(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    try {
      final response = await _dio.delete(
        path,
        data: data,
        queryParameters: queryParameters,
        options: options,
      );
      return response;
    } on DioException catch (e) {
      throw e.error ?? e;
    }
  }

  /// PATCH request
  Future<Response> patch(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    try {
      final response = await _dio.patch(
        path,
        data: data,
        queryParameters: queryParameters,
        options: options,
      );
      return response;
    } on DioException catch (e) {
      throw e.error ?? e;
    }
  }

  /// Upload file
  Future<Response> upload(
    String path,
    String filePath, {
    String fieldName = 'file',
    Map<String, dynamic>? data,
    ProgressCallback? onSendProgress,
  }) async {
    final formData = FormData.fromMap({
      fieldName: await MultipartFile.fromFile(filePath),
      ...?data,
    });

    try {
      final response = await _dio.post(
        path,
        data: formData,
        onSendProgress: onSendProgress,
      );
      return response;
    } on DioException catch (e) {
      throw e.error ?? e;
    }
  }

  /// Clear stored tokens
  Future<void> clearTokens() async {
    await _storage.delete(key: 'access_token');
    await _storage.delete(key: 'refresh_token');
  }

  /// Store tokens
  Future<void> storeTokens(String accessToken, String refreshToken) async {
    await _storage.write(key: 'access_token', value: accessToken);
    await _storage.write(key: 'refresh_token', value: refreshToken);
  }

  /// Get access token
  Future<String?> getAccessToken() async {
    return await _storage.read(key: 'access_token');
  }

  /// Get refresh token
  Future<String?> getRefreshToken() async {
    return await _storage.read(key: 'refresh_token');
  }
}
