import 'package:flutter/foundation.dart';

/// Legacy StoreState placeholder.
///
/// NOTE: Hardcoded mock data lists have been completely migrated to real
/// Riverpod Notifiers and API Repositories per Step 9 requirements.
/// Real runtime state is managed by:
/// - authNotifierProvider (lib/providers/app_providers.dart)
/// - posBillingProvider (lib/providers/billing_providers.dart)
/// - recoveryTowerProvider (lib/providers/recovery_providers.dart)
/// - khataLedgerProvider (lib/providers/khata_providers.dart)
/// - soundboxProvider (lib/providers/soundbox_providers.dart)
class StoreState extends ChangeNotifier {
  String storeName = "Wapas Kirana Store";
  String merchantName = "Wapas Merchant";
  bool isSoundboxLive = true;
}

final storeState = StoreState();
