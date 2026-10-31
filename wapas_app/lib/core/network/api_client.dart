import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

import 'api_exceptions.dart';

class ApiClient {
  static const String _defaultUrl = String.fromEnvironment(
    'WAPAS_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );
  static const String _prefsKeyUrl = 'wapas_base_url';
  static const String _keySession = 'wapas_session';
  static const String _keyCsrf = 'wapas_csrf';

  final http.Client _httpClient;
  final FlutterSecureStorage _storage;
  final Uuid _uuid = const Uuid();

  String _baseUrl = _defaultUrl;
  String? _sessionCookie;
  String? _csrfToken;
  VoidCallback? onSessionExpired;

  ApiClient({
    http.Client? httpClient,
    FlutterSecureStorage? storage,
  })  : _httpClient = httpClient ?? http.Client(),
        _storage = storage ?? const FlutterSecureStorage();

  String get baseUrl => _baseUrl;
  String? get sessionCookie => _sessionCookie;
  String? get csrfToken => _csrfToken;
  bool get isAuthenticated => _sessionCookie != null && _sessionCookie!.isNotEmpty;

  static String _normalizeUrl(String url) {
    var u = url.trim().replaceAll(RegExp(r'/+$'), '');
    if (u.startsWith('http://') && !u.contains('127.0.0.1') && !u.contains('localhost') && !u.contains('10.0.2.2')) {
      u = 'https://${u.substring(7)}';
    }
    return u;
  }

  Future<void> init() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final savedUrl = prefs.getString(_prefsKeyUrl);
      if (savedUrl != null && savedUrl.isNotEmpty && !savedUrl.contains('10.0.2.2')) {
        _baseUrl = _normalizeUrl(savedUrl);
      } else {
        _baseUrl = _defaultUrl;
      }
    } catch (e) {
      debugPrint('ApiClient: could not read saved base URL: $e');
    }

    try {
      _sessionCookie = await _storage.read(key: _keySession);
      _csrfToken = await _storage.read(key: _keyCsrf);
    } catch (e) {
      debugPrint('ApiClient: could not read secure storage: $e');
    }
  }

  Future<void> setBaseUrl(String newUrl) async {
    _baseUrl = _normalizeUrl(newUrl);
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_prefsKeyUrl, _baseUrl);
    } catch (e) {
      debugPrint('ApiClient: failed to persist base URL: $e');
    }
  }

  Future<void> saveSession({required String sessionToken, required String csrfToken}) async {
    _sessionCookie = sessionToken;
    _csrfToken = csrfToken;
    try {
      await _storage.write(key: _keySession, value: sessionToken);
      await _storage.write(key: _keyCsrf, value: csrfToken);
    } catch (e) {
      debugPrint('ApiClient: failed to save session to secure storage: $e');
    }
  }

  Future<void> clearSession() async {
    _sessionCookie = null;
    _csrfToken = null;
    try {
      await _storage.delete(key: _keySession);
      await _storage.delete(key: _keyCsrf);
    } catch (e) {
      debugPrint('ApiClient: failed to clear secure storage: $e');
    }
  }

  String generateIdempotencyKey(String prefix) {
    return '${prefix}_${_uuid.v4().replaceAll('-', '')}';
  }

  String _getOriginHeader() {
    try {
      final uri = Uri.parse(_baseUrl);
      final portSuffix = (uri.port == 80 && uri.scheme == 'http') || (uri.port == 443 && uri.scheme == 'https')
          ? ''
          : ':${uri.port}';
      return '${uri.scheme}://${uri.host}$portSuffix';
    } catch (_) {
      return _baseUrl;
    }
  }

  Map<String, String> _buildHeaders({bool isMutating = false, Map<String, String>? extraHeaders}) {
    final headers = <String, String>{
      'Accept': 'application/json',
      'Content-Type': 'application/json',
    };

    // Cookie header
    final cookieParts = <String>[];
    if (_sessionCookie != null && _sessionCookie!.isNotEmpty) {
      cookieParts.add('wapas_session=$_sessionCookie');
    }
    if (_csrfToken != null && _csrfToken!.isNotEmpty) {
      cookieParts.add('wapas_csrf=$_csrfToken');
    }
    if (cookieParts.isNotEmpty) {
      headers['Cookie'] = cookieParts.join('; ');
    }

    if (isMutating) {
      if (_csrfToken != null && _csrfToken!.isNotEmpty) {
        headers['x-wapas-csrf'] = _csrfToken!;
      }
      headers['Origin'] = _getOriginHeader();
      headers['sec-fetch-site'] = 'same-origin';
    }

    if (extraHeaders != null) {
      headers.addAll(extraHeaders);
    }
    return headers;
  }

  void _extractCookiesFromResponse(http.Response response) {
    final setCookieHeader = response.headers['set-cookie'];
    if (setCookieHeader == null || setCookieHeader.isEmpty) return;

    final sessionMatch = RegExp(r'wapas_session=([^;]+)').firstMatch(setCookieHeader);
    if (sessionMatch != null) {
      _sessionCookie = sessionMatch.group(1);
      _storage.write(key: _keySession, value: _sessionCookie);
    }

    final csrfMatch = RegExp(r'wapas_csrf=([^;]+)').firstMatch(setCookieHeader);
    if (csrfMatch != null) {
      _csrfToken = csrfMatch.group(1);
      _storage.write(key: _keyCsrf, value: _csrfToken);
    }
  }

  Future<dynamic> get(String path, {Map<String, dynamic>? queryParams, int maxRetries = 2}) async {
    Uri uri = Uri.parse('$_baseUrl$path');
    if (queryParams != null && queryParams.isNotEmpty) {
      uri = uri.replace(queryParameters: queryParams.map((k, v) => MapEntry(k, v.toString())));
    }

    int attempts = 0;
    while (true) {
      attempts++;
      try {
        final response = await _httpClient
            .get(uri, headers: _buildHeaders(isMutating: false))
            .timeout(const Duration(seconds: 12));

        _extractCookiesFromResponse(response);

        if (response.statusCode >= 200 && response.statusCode < 300) {
          if (response.body.isEmpty) return null;
          return jsonDecode(response.body);
        }

        if (response.statusCode == 401) {
          onSessionExpired?.call();
        }

        dynamic errorBody;
        try {
          errorBody = jsonDecode(response.body);
        } catch (_) {
          errorBody = response.body;
        }
        throw ApiException.fromResponse(response.statusCode, errorBody);
      } catch (e) {
        if (e is ApiException) {
          rethrow;
        }
        if (attempts > maxRetries) {
          throw ApiException.networkError(e);
        }
        await Future.delayed(Duration(milliseconds: 300 * attempts));
      }
    }
  }

  Future<dynamic> post(String path, {dynamic body, Map<String, String>? extraHeaders}) async {
    return _sendMutating('POST', path, body: body, extraHeaders: extraHeaders);
  }

  Future<dynamic> put(String path, {dynamic body, Map<String, String>? extraHeaders}) async {
    return _sendMutating('PUT', path, body: body, extraHeaders: extraHeaders);
  }

  Future<dynamic> patch(String path, {dynamic body, Map<String, String>? extraHeaders}) async {
    return _sendMutating('PATCH', path, body: body, extraHeaders: extraHeaders);
  }

  Future<dynamic> delete(String path, {dynamic body, Map<String, String>? extraHeaders}) async {
    return _sendMutating('DELETE', path, body: body, extraHeaders: extraHeaders);
  }

  Future<dynamic> _sendMutating(
    String method,
    String path, {
    dynamic body,
    Map<String, String>? extraHeaders,
    bool retryCsrf = true,
  }) async {
    final uri = Uri.parse('$_baseUrl$path');
    final headers = _buildHeaders(isMutating: true, extraHeaders: extraHeaders);
    final String? encodedBody = body != null ? jsonEncode(body) : null;

    try {
      http.Response response;
      switch (method) {
        case 'POST':
          response = await _httpClient.post(uri, headers: headers, body: encodedBody).timeout(const Duration(seconds: 10));
          break;
        case 'PUT':
          response = await _httpClient.put(uri, headers: headers, body: encodedBody).timeout(const Duration(seconds: 10));
          break;
        case 'PATCH':
          response = await _httpClient.patch(uri, headers: headers, body: encodedBody).timeout(const Duration(seconds: 10));
          break;
        case 'DELETE':
          response = await _httpClient.delete(uri, headers: headers, body: encodedBody).timeout(const Duration(seconds: 10));
          break;
        default:
          throw UnsupportedError('HTTP method $method not supported');
      }

      _extractCookiesFromResponse(response);

      if (response.statusCode >= 200 && response.statusCode < 300) {
        if (response.body.isEmpty) return null;
        return jsonDecode(response.body);
      }

      // If 307/308/301/302 redirect occurred (e.g. ngrok http -> https), upgrade and retry
      if ((response.statusCode == 301 || response.statusCode == 302 || response.statusCode == 307 || response.statusCode == 308) &&
          response.headers['location'] != null) {
        final loc = response.headers['location']!;
        if (loc.startsWith('https://')) {
          final uri = Uri.parse(loc);
          await setBaseUrl('${uri.scheme}://${uri.host}${uri.hasPort && uri.port != 443 ? ':${uri.port}' : ''}');
          return await _sendMutating(method, path, body: body, extraHeaders: extraHeaders, retryCsrf: retryCsrf);
        }
      }

      // If 403 CSRF failure occurred, try refreshing CSRF via /api/auth/session once
      if (response.statusCode == 403 && retryCsrf) {
        final detail = response.body.toLowerCase();
        if (detail.contains('csrf')) {
          final refreshed = await _refreshCsrfToken();
          if (refreshed) {
            return await _sendMutating(method, path, body: body, extraHeaders: extraHeaders, retryCsrf: false);
          }
        }
      }

      if (response.statusCode == 401) {
        onSessionExpired?.call();
      }

      dynamic errorBody;
      try {
        errorBody = jsonDecode(response.body);
      } catch (_) {
        errorBody = response.body;
      }
      throw ApiException.fromResponse(response.statusCode, errorBody);
    } catch (e) {
      if (e is ApiException) rethrow;
      throw ApiException.networkError(e);
    }
  }

  Future<bool> _refreshCsrfToken() async {
    try {
      final res = await get('/api/auth/session');
      if (res is Map<String, dynamic> && res['csrf_token'] != null) {
        _csrfToken = res['csrf_token'].toString();
        await _storage.write(key: _keyCsrf, value: _csrfToken);
        return true;
      }
    } catch (_) {}
    return false;
  }

  Future<bool> testHealth() async {
    try {
      final uri = Uri.parse('$_baseUrl/healthz');
      final res = await _httpClient.get(uri).timeout(const Duration(seconds: 3));
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }
}
