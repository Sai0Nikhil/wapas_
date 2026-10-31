import 'package:flutter_test/flutter_test.dart';
import 'package:wapas_app/core/network/api_client.dart';
import 'package:wapas_app/core/network/api_exceptions.dart';
import 'package:wapas_app/models/auth_models.dart';
import 'package:wapas_app/models/recovery_models.dart';

void main() {
  group('AuthModels and ApiException Tests', () {
    test('UserRole parse and serialization', () {
      expect(UserRole.fromString('OWNER'), UserRole.owner);
      expect(UserRole.fromString('owner'), UserRole.owner);
      expect(UserRole.fromString('STAFF'), UserRole.staff);
      expect(UserRole.fromString(null), UserRole.staff);

      expect(UserRole.owner.toApiString(), 'OWNER');
      expect(UserRole.staff.toApiString(), 'STAFF');
      expect(UserRole.owner.isOwner, isTrue);
      expect(UserRole.staff.isOwner, isFalse);
    });

    test('AuthSession fromJson and toJson', () {
      final json = {
        'authenticated': true,
        'user_id': 'usr_1',
        'username': 'demo_owner',
        'membership_id': 'mem_1',
        'role': 'OWNER',
        'merchant_id': 'mer_1',
        'store_id': 'sto_1',
        'store_slug': 'koramangala',
        'merchant_name': 'Wapas Retail',
        'store_name': 'Koramangala Branch',
        'csrf_token': 'csrf_token_abc123',
        'expires_at': '2026-12-31T23:59:59Z',
      };

      final session = AuthSession.fromJson(json);
      expect(session.authenticated, isTrue);
      expect(session.username, 'demo_owner');
      expect(session.role, UserRole.owner);
      expect(session.csrfToken, 'csrf_token_abc123');

      final serialized = session.toJson();
      expect(serialized['authenticated'], isTrue);
      expect(serialized['role'], 'OWNER');
      expect(serialized['csrf_token'], 'csrf_token_abc123');
    });

    test('ApiException bilingual mappings', () {
      final authError = ApiException.fromResponse(401, {'detail': 'Session expired'});
      expect(authError.isAuthError, isTrue);
      expect(authError.messageHindi, contains('साइन-इन सत्र समाप्त'));

      final forbiddenError = ApiException.fromResponse(403, {'detail': 'Owner required'});
      expect(forbiddenError.isForbidden, isTrue);
      expect(forbiddenError.messageHindi, contains('मालिक'));

      final netError = ApiException.networkError('Connection refused');
      expect(netError.isNetworkError, isTrue);
      expect(netError.statusCode, 0);
    });

    test('RecoveryCaseSummary parses live backend case row', () {
      final json = {
        'id': 'case_101',
        'name': 'Rao Garu',
        'customer_id': 'cust_101',
        'language': 'te',
        'language_name': 'Telugu',
        'amount': 300.0,
        'amount_fmt': '₹300',
        'state': 'WAITING_OWNER',
        'diagnosis': 'UPI technical decline at sender bank',
        'confidence': 0.94,
        'messages_sent': 1,
      };

      final summary = RecoveryCaseSummary.fromJson(json);
      expect(summary.id, 'case_101');
      expect(summary.name, 'Rao Garu');
      expect(summary.language, 'te');
      expect(summary.isWaitingOwner, isTrue);
      expect(summary.isRecovered, isFalse);
    });

    test('ApiClient idempotency key generator produces prefixed unique strings', () {
      final client = ApiClient();
      final key1 = client.generateIdempotencyKey('bill');
      final key2 = client.generateIdempotencyKey('bill');

      expect(key1, startsWith('bill_'));
      expect(key2, startsWith('bill_'));
      expect(key1, isNot(equals(key2)));
    });
  });
}
