import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../constants/app_constants.dart';

/// HTTP client for API communication
class ApiClient {
  late final Dio _dio;
  final FlutterSecureStorage _secureStorage = const FlutterSecureStorage();

  ApiClient({String? baseUrl}) {
    _dio = Dio(
      BaseOptions(
        baseUrl: baseUrl ?? AppConstants.baseUrl,
        connectTimeout: AppConstants.connectTimeout,
        receiveTimeout: AppConstants.receiveTimeout,
        sendTimeout: AppConstants.sendTimeout,
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
      ),
    );

    _setupInterceptors();
  }

  void _setupInterceptors() {
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          // Add auth token to headers
          final token = await _secureStorage.read(
            key: AppConstants.keyAccessToken,
          );
          if (token != null) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          return handler.next(options);
        },
        onResponse: (response, handler) {
          // Log response
          print('Response [${response.statusCode}]: ${response.requestOptions.path}');
          return handler.next(response);
        },
        onError: (error, handler) async {
          // Handle 401 Unauthorized - refresh token
          if (error.response?.statusCode == 401) {
            try {
              final refreshed = await _refreshToken();
              if (refreshed) {
                // Retry original request
                final options = error.requestOptions;
                final token = await _secureStorage.read(
                  key: AppConstants.keyAccessToken,
                );
                options.headers['Authorization'] = 'Bearer $token';

                final response = await _dio.fetch(options);
                return handler.resolve(response);
              }
            } catch (e) {
              // Refresh failed, clear tokens and redirect to login
              await _clearAuth();
            }
          }

          return handler.next(error);
        },
      ),
    );

    // Add logging interceptor in debug mode
    if (const bool.fromEnvironment('dart.vm.product') == false) {
      _dio.interceptors.add(LogInterceptor(
        requestBody: true,
        responseBody: true,
        error: true,
        requestHeader: true,
        responseHeader: false,
      ));
    }
  }

  Future<bool> _refreshToken() async {
    try {
      final refreshToken = await _secureStorage.read(
        key: AppConstants.keyRefreshToken,
      );

      if (refreshToken == null) return false;

      final response = await _dio.post(
        '/auth/refresh',
        data: {'refresh_token': refreshToken},
      );

      if (response.statusCode == 200) {
        final accessToken = response.data['access_token'];
        final newRefreshToken = response.data['refresh_token'];

        await _secureStorage.write(
          key: AppConstants.keyAccessToken,
          value: accessToken,
        );
        await _secureStorage.write(
          key: AppConstants.keyRefreshToken,
          value: newRefreshToken,
        );

        return true;
      }
      return false;
    } catch (e) {
      print('Token refresh failed: $e');
      return false;
    }
  }

  Future<void> _clearAuth() async {
    await _secureStorage.delete(key: AppConstants.keyAccessToken);
    await _secureStorage.delete(key: AppConstants.keyRefreshToken);
    await _secureStorage.delete(key: AppConstants.keyUserId);
  }

  // GET request
  Future<Response<T>> get<T>(
    String path, {
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    return await _dio.get<T>(
      path,
      queryParameters: queryParameters,
      options: options,
      cancelToken: cancelToken,
    );
  }

  // POST request
  Future<Response<T>> post<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    return await _dio.post<T>(
      path,
      data: data,
      queryParameters: queryParameters,
      options: options,
      cancelToken: cancelToken,
    );
  }

  // PUT request
  Future<Response<T>> put<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    return await _dio.put<T>(
      path,
      data: data,
      queryParameters: queryParameters,
      options: options,
      cancelToken: cancelToken,
    );
  }

  // DELETE request
  Future<Response<T>> delete<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    return await _dio.delete<T>(
      path,
      data: data,
      queryParameters: queryParameters,
      options: options,
      cancelToken: cancelToken,
    );
  }

  // PATCH request
  Future<Response<T>> patch<T>(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    return await _dio.patch<T>(
      path,
      data: data,
      queryParameters: queryParameters,
      options: options,
      cancelToken: cancelToken,
    );
  }

  // Upload file
  Future<Response<T>> upload<T>(
    String path,
    FormData formData, {
    ProgressCallback? onSendProgress,
    Options? options,
    CancelToken? cancelToken,
  }) async {
    return await _dio.post<T>(
      path,
      data: formData,
      onSendProgress: onSendProgress,
      options: options,
      cancelToken: cancelToken,
    );
  }

  // Download file
  Future<Response> download(
    String urlPath,
    String savePath, {
    ProgressCallback? onReceiveProgress,
    CancelToken? cancelToken,
  }) async {
    return await _dio.download(
      urlPath,
      savePath,
      onReceiveProgress: onReceiveProgress,
      cancelToken: cancelToken,
    );
  }
}
