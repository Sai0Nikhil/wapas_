import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:wapas_app/main.dart';

void main() {
  testWidgets('Wapas App smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const ProviderScope(child: WapasMerchantApp()));
    expect(find.byType(WapasMerchantApp), findsOneWidget);
  });
}
