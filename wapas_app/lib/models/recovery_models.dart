class RecoveryCounts {
  final int flagged;
  final int contacted;
  final int paid;
  final int waitingOwner;
  final int stoppedByPolicy;
  final int unknown;
  final double recoveredInr;
  final String recoveredFmt;

  RecoveryCounts({
    required this.flagged,
    required this.contacted,
    required this.paid,
    required this.waitingOwner,
    required this.stoppedByPolicy,
    required this.unknown,
    required this.recoveredInr,
    required this.recoveredFmt,
  });

  factory RecoveryCounts.empty() => RecoveryCounts(
        flagged: 0,
        contacted: 0,
        paid: 0,
        waitingOwner: 0,
        stoppedByPolicy: 0,
        unknown: 0,
        recoveredInr: 0.0,
        recoveredFmt: '₹0',
      );

  factory RecoveryCounts.fromJson(Map<String, dynamic> json) {
    return RecoveryCounts(
      flagged: (json['flagged'] as num?)?.toInt() ?? 0,
      contacted: (json['contacted'] as num?)?.toInt() ?? 0,
      paid: (json['paid'] as num?)?.toInt() ?? 0,
      waitingOwner: (json['waiting_owner'] as num?)?.toInt() ?? 0,
      stoppedByPolicy: (json['stopped_by_policy'] as num?)?.toInt() ?? 0,
      unknown: (json['unknown'] as num?)?.toInt() ?? 0,
      recoveredInr: (json['recovered_inr'] as num?)?.toDouble() ?? 0.0,
      recoveredFmt: (json['recovered_fmt'] ?? '₹0').toString(),
    );
  }
}

class RecoveryCaseSummary {
  final String id;
  final String name;
  final String customerId;
  final String language;
  final String languageName;
  final double amount;
  final String amountFmt;
  final String? orderId;
  final String? bank;
  final String? failureCode;
  final String state; // NEW, WAITING_OWNER, APPROVED, SENT, RECOVERED, STOPPED, BLOCKED
  final String? reason;
  final String? diagnosis;
  final double confidence;
  final int messagesSent;
  final String? openedAt;
  final String? source;

  RecoveryCaseSummary({
    required this.id,
    required this.name,
    required this.customerId,
    required this.language,
    required this.languageName,
    required this.amount,
    required this.amountFmt,
    this.orderId,
    this.bank,
    this.failureCode,
    required this.state,
    this.reason,
    this.diagnosis,
    required this.confidence,
    required this.messagesSent,
    this.openedAt,
    this.source,
  });

  factory RecoveryCaseSummary.fromJson(Map<String, dynamic> json) {
    return RecoveryCaseSummary(
      id: (json['id'] ?? '').toString(),
      name: (json['name'] ?? 'Customer').toString(),
      customerId: (json['customer_id'] ?? '').toString(),
      language: (json['language'] ?? 'en').toString(),
      languageName: (json['language_name'] ?? 'English').toString(),
      amount: (json['amount'] as num?)?.toDouble() ?? 0.0,
      amountFmt: (json['amount_fmt'] ?? '₹0').toString(),
      orderId: json['order_id']?.toString(),
      bank: json['bank']?.toString(),
      failureCode: json['failure_code']?.toString(),
      state: (json['state'] ?? 'NEW').toString(),
      reason: json['reason']?.toString(),
      diagnosis: json['diagnosis']?.toString(),
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
      messagesSent: (json['messages_sent'] as num?)?.toInt() ?? 0,
      openedAt: json['opened_at']?.toString(),
      source: json['source']?.toString(),
    );
  }

  bool get isWaitingOwner => state == 'WAITING_OWNER';
  bool get isRecovered => state == 'RECOVERED';
  bool get isBlocked => state == 'BLOCKED' || state == 'STOPPED';
}

class CaseDecisionData {
  final String? diagnosis;
  final String? chosenAction;
  final double confidence;
  final String? reasoner;
  final String? template;
  final String? language;
  final List<dynamic> options;

  CaseDecisionData({
    this.diagnosis,
    this.chosenAction,
    required this.confidence,
    this.reasoner,
    this.template,
    this.language,
    this.options = const [],
  });

  factory CaseDecisionData.fromJson(Map<String, dynamic> json) {
    return CaseDecisionData(
      diagnosis: json['diagnosis']?.toString(),
      chosenAction: json['chosen_action']?.toString(),
      confidence: (json['confidence'] as num?)?.toDouble() ?? 0.0,
      reasoner: json['reasoner']?.toString(),
      template: json['template']?.toString(),
      language: json['language']?.toString(),
      options: json['options'] is List ? (json['options'] as List) : const [],
    );
  }
}

class CasePolicyItem {
  final String outcome;
  final String rule;
  final String version;
  final String? at;

  CasePolicyItem({
    required this.outcome,
    required this.rule,
    required this.version,
    this.at,
  });

  factory CasePolicyItem.fromJson(Map<String, dynamic> json) {
    return CasePolicyItem(
      outcome: (json['outcome'] ?? '').toString(),
      rule: (json['rule'] ?? '').toString(),
      version: (json['version'] ?? '').toString(),
      at: json['at']?.toString(),
    );
  }
}

class CaseActionItem {
  final String kind;
  final String? key;
  final String? url;
  final String state;
  final String? error;
  final String? sentAt;

  CaseActionItem({
    required this.kind,
    this.key,
    this.url,
    required this.state,
    this.error,
    this.sentAt,
  });

  factory CaseActionItem.fromJson(Map<String, dynamic> json) {
    return CaseActionItem(
      kind: (json['kind'] ?? '').toString(),
      key: json['key']?.toString(),
      url: json['url']?.toString(),
      state: (json['state'] ?? '').toString(),
      error: json['error']?.toString(),
      sentAt: json['sent_at']?.toString(),
    );
  }
}

class CaseDetailData {
  final RecoveryCaseSummary summary;
  final CaseDecisionData? decision;
  final List<CasePolicyItem> policy;
  final List<CaseActionItem> actions;
  final List<Map<String, dynamic>> messages;
  final List<Map<String, dynamic>> timeline;
  final Map<String, dynamic>? evidence;

  CaseDetailData({
    required this.summary,
    this.decision,
    this.policy = const [],
    this.actions = const [],
    this.messages = const [],
    this.timeline = const [],
    this.evidence,
  });

  factory CaseDetailData.fromJson(Map<String, dynamic> json) {
    final summary = RecoveryCaseSummary.fromJson(json);
    final decision = json['decision'] is Map<String, dynamic>
        ? CaseDecisionData.fromJson(json['decision'] as Map<String, dynamic>)
        : null;

    final policyList = (json['policy'] as List?)
            ?.map((p) => CasePolicyItem.fromJson(p as Map<String, dynamic>))
            .toList() ??
        [];

    final actionsList = (json['actions'] as List?)
            ?.map((a) => CaseActionItem.fromJson(a as Map<String, dynamic>))
            .toList() ??
        [];

    final messagesList = (json['messages'] as List?)
            ?.map((m) => m as Map<String, dynamic>)
            .toList() ??
        [];

    final timelineList = (json['timeline'] as List?)
            ?.map((t) => t as Map<String, dynamic>)
            .toList() ??
        [];

    return CaseDetailData(
      summary: summary,
      decision: decision,
      policy: policyList,
      actions: actionsList,
      messages: messagesList,
      timeline: timelineList,
      evidence: json['job'] is Map<String, dynamic> ? json['job'] as Map<String, dynamic> : null,
    );
  }
}

class RecoveryStateData {
  final String merchant;
  final String gateway;
  final bool llm;
  final bool sarvam;
  final RecoveryCounts counts;
  final List<RecoveryCaseSummary> cases;
  final List<Map<String, dynamic>> messages;
  final List<Map<String, dynamic>> events;

  RecoveryStateData({
    required this.merchant,
    required this.gateway,
    required this.llm,
    required this.sarvam,
    required this.counts,
    required this.cases,
    this.messages = const [],
    this.events = const [],
  });

  factory RecoveryStateData.fromJson(Map<String, dynamic> json) {
    return RecoveryStateData(
      merchant: (json['merchant'] ?? '').toString(),
      gateway: (json['gateway'] ?? 'fake').toString(),
      llm: json['llm'] == true,
      sarvam: json['sarvam'] == true,
      counts: json['counts'] is Map<String, dynamic>
          ? RecoveryCounts.fromJson(json['counts'] as Map<String, dynamic>)
          : RecoveryCounts.empty(),
      cases: (json['cases'] as List?)
              ?.map((c) => RecoveryCaseSummary.fromJson(c as Map<String, dynamic>))
              .toList() ??
          [],
      messages: (json['messages'] as List?)?.map((m) => m as Map<String, dynamic>).toList() ?? [],
      events: (json['events'] as List?)?.map((e) => e as Map<String, dynamic>).toList() ?? [],
    );
  }
}
