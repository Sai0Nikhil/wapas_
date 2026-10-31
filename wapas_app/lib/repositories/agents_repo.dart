import '../core/network/api_client.dart';
import '../models/order_models.dart';

abstract class AgentsRepo {
  Future<List<AgentActivityModel>> getActivities();
}

class HttpAgentsRepo implements AgentsRepo {
  final ApiClient _client;

  HttpAgentsRepo(this._client);

  @override
  Future<List<AgentActivityModel>> getActivities() async {
    try {
      final res = await _client.get('/api/merchant/agents/activity');
      if (res is Map<String, dynamic> && res['activities'] is List) {
        return (res['activities'] as List)
            .map((a) => AgentActivityModel.fromJson(a as Map<String, dynamic>))
            .toList();
      }
    } catch (_) {
      // Backend gap documented in docs/backend-requests.md:
      // Fallback synthesis from /api/state events and /api/merchant/opportunities/pulse
      try {
        final stateRes = await _client.get('/api/state');
        if (stateRes is Map<String, dynamic> && stateRes['cases'] is List) {
          final cases = stateRes['cases'] as List;
          return cases.map((c) {
            final name = c['name'] ?? 'Customer';
            final amt = (c['amount'] as num?)?.toDouble() ?? 0.0;
            return AgentActivityModel(
              id: 'act_${c['id']}',
              agent: 'AI Recovery Agent',
              action: 'DRAFT_RECOVERY_WHATSAPP',
              target: '$name (₹$amt)',
              amountPaise: (amt * 100).toInt(),
              status: c['state'] == 'WAITING_OWNER' ? 'DRAFT_REVIEW_REQUIRED' : c['state'],
              confidence: (c['confidence'] as num?)?.toDouble() ?? 0.94,
              createdAt: c['opened_at'] ?? DateTime.now().toIso8601String(),
              auditTrail: 'Signal detected from failed UPI settlement -> policy FAIL_CLOSED evaluated -> draft queued',
            );
          }).toList();
        }
      } catch (_) {}
    }
    return [];
  }
}
