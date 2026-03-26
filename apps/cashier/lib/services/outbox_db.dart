import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import 'outbox_crypto.dart';

class OutboxEntry {
  OutboxEntry({
    required this.id,
    required this.clientMutationId,
    required this.idempotencyKey,
    required this.eventJson,
  });

  final int id;
  final String clientMutationId;
  final String idempotencyKey;
  final String eventJson;
}

class OutboxDb {
  static Database? _db;

  static Future<Database> _database() async {
    if (_db != null) return _db!;
    final dir = await getDatabasesPath();
    final path = p.join(dir, 'cashier_outbox.db');
    _db = await openDatabase(
      path,
      version: 1,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_mutation_id TEXT NOT NULL UNIQUE,
            idempotency_key TEXT NOT NULL,
            event_json TEXT NOT NULL,
            created_at INTEGER NOT NULL
          )
        ''');
      },
    );
    return _db!;
  }

  static Future<void> insert({
    required String clientMutationId,
    required String idempotencyKey,
    required String eventJson,
  }) async {
    final db = await _database();
    final stored = await OutboxCrypto.seal(eventJson);
    await db.insert(
      'outbox',
      {
        'client_mutation_id': clientMutationId,
        'idempotency_key': idempotencyKey,
        'event_json': stored,
        'created_at': DateTime.now().millisecondsSinceEpoch,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  static Future<List<OutboxEntry>> pendingOrdered() async {
    final db = await _database();
    final rows = await db.query('outbox', orderBy: 'id ASC');
    final out = <OutboxEntry>[];
    for (final r in rows) {
      final raw = r['event_json']! as String;
      final plain = await OutboxCrypto.open(raw);
      out.add(
        OutboxEntry(
          id: r['id']! as int,
          clientMutationId: r['client_mutation_id']! as String,
          idempotencyKey: r['idempotency_key']! as String,
          eventJson: plain,
        ),
      );
    }
    return out;
  }

  static Future<int> countPending() async {
    final db = await _database();
    final raw = await db.rawQuery('SELECT COUNT(*) AS c FROM outbox');
    final n = Sqflite.firstIntValue(raw);
    return n ?? 0;
  }

  static Future<void> deleteById(int id) async {
    final db = await _database();
    await db.delete('outbox', where: 'id = ?', whereArgs: [id]);
  }

  static Future<void> clearAll() async {
    final db = await _database();
    await db.delete('outbox');
  }
}
