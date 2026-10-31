import '../core/network/api_client.dart';
import '../models/auth_models.dart';

abstract class AuthRepo {
  Future<AuthSession> login(String username, String password, {String? membershipId});
  Future<AuthSession> getSession();
  Future<List<StoreMembership>> getMemberships();
  Future<AuthSession> switchMembership(String membershipId);
  Future<void> logout();
  Future<AuthSession> register({
    required String businessName,
    required String storeName,
    required String username,
    required String password,
    String? phone,
    String? city,
  });
}

class HttpAuthRepo implements AuthRepo {
  final ApiClient _client;

  HttpAuthRepo(this._client);

  @override
  Future<AuthSession> login(String username, String password, {String? membershipId}) async {
    final payload = {
      'username': username,
      'password': password,
      'membership_id': ?membershipId,
    };
    final res = await _client.post('/api/auth/login', body: payload);
    final session = AuthSession.fromJson(res as Map<String, dynamic>);
    if (session.csrfToken != null) {
      await _client.saveSession(
        sessionToken: _client.sessionCookie ?? '',
        csrfToken: session.csrfToken!,
      );
    }
    return session;
  }

  @override
  Future<AuthSession> getSession() async {
    final res = await _client.get('/api/auth/session');
    if (res is Map<String, dynamic>) {
      final session = AuthSession.fromJson(res);
      if (session.authenticated && session.csrfToken != null) {
        await _client.saveSession(
          sessionToken: _client.sessionCookie ?? '',
          csrfToken: session.csrfToken!,
        );
      }
      return session;
    }
    return AuthSession.unauthenticated();
  }

  @override
  Future<List<StoreMembership>> getMemberships() async {
    final res = await _client.get('/api/auth/memberships');
    if (res is Map<String, dynamic> && res['memberships'] is List) {
      return (res['memberships'] as List)
          .map((m) => StoreMembership.fromJson(m as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  @override
  Future<AuthSession> switchMembership(String membershipId) async {
    final payload = {'membership_id': membershipId};
    final res = await _client.post('/api/auth/switch-membership', body: payload);
    final session = AuthSession.fromJson(res as Map<String, dynamic>);
    if (session.csrfToken != null) {
      await _client.saveSession(
        sessionToken: _client.sessionCookie ?? '',
        csrfToken: session.csrfToken!,
      );
    }
    return session;
  }

  @override
  Future<void> logout() async {
    try {
      await _client.post('/api/auth/logout');
    } catch (_) {}
    await _client.clearSession();
  }

  @override
  Future<AuthSession> register({
    required String businessName,
    required String storeName,
    required String username,
    required String password,
    String? phone,
    String? city,
  }) async {
    final payload = {
      'business_name': businessName,
      'store_name': storeName,
      'username': username,
      'password': password,
      'phone': ?phone,
      'city': ?city,
      'timezone': 'Asia/Kolkata',
    };
    final res = await _client.post('/api/auth/register', body: payload);
    final session = AuthSession.fromJson(res as Map<String, dynamic>);
    if (session.csrfToken != null) {
      await _client.saveSession(
        sessionToken: _client.sessionCookie ?? '',
        csrfToken: session.csrfToken!,
      );
    }
    return session;
  }
}
