/// Base exception class for app errors
abstract class AppException implements Exception {
  final String message;
  final String? code;
  final dynamic originalError;
  final StackTrace? stackTrace;

  const AppException({
    required this.message,
    this.code,
    this.originalError,
    this.stackTrace,
  });

  @override
  String toString() => message;
}

/// Authentication related errors
class AuthException extends AppException {
  const AuthException({
    required super.message,
    super.code,
    super.originalError,
    super.stackTrace,
  });
}

/// Network related errors
class NetworkException extends AppException {
  const NetworkException({
    required super.message,
    super.code,
    super.originalError,
    super.stackTrace,
  });
}

/// Server errors (4xx, 5xx)
class ServerException extends AppException {
  final int statusCode;

  const ServerException({
    required super.message,
    required this.statusCode,
    super.code,
    super.originalError,
    super.stackTrace,
  });
}

/// Validation errors
class ValidationException extends AppException {
  final Map<String, List<String>>? errors;

  const ValidationException({
    required super.message,
    this.errors,
    super.code,
    super.originalError,
    super.stackTrace,
  });
}

/// Timeout errors
class TimeoutException extends AppException {
  const TimeoutException({
    String message = 'Request timeout',
    super.code,
    super.originalError,
    super.stackTrace,
  }) : super(message: message);
}

/// Unauthorized errors (401)
class UnauthorizedException extends ServerException {
  const UnauthorizedException({
    String message = 'Unauthorized',
    super.code,
    super.originalError,
    super.stackTrace,
  }) : super(message: message, statusCode: 401);
}

/// Forbidden errors (403)
class ForbiddenException extends ServerException {
  const ForbiddenException({
    String message = 'Forbidden',
    super.code,
    super.originalError,
    super.stackTrace,
  }) : super(message: message, statusCode: 403);
}

/// Not found errors (404)
class NotFoundException extends ServerException {
  const NotFoundException({
    String message = 'Not found',
    super.code,
    super.originalError,
    super.stackTrace,
  }) : super(message: message, statusCode: 404);
}
